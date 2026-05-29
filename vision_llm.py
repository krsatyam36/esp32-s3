"""
ESP32-S3 Live Feed → Ollama Vision LLM

Captures frames from the ESP32 camera stream and sends them to locally
running Ollama vision models (llama3.2-vision, gemma3, qwen2.5vl, etc.)
for real-time description without blocking the video display.
"""

import cv2
import urllib.request
import numpy as np
import time
import json
import base64
import threading
import requests
from io import BytesIO
from config import ESP32_IP

BASE_URL = ESP32_IP.rstrip("/")
OLLAMA_URL = "http://localhost:11434"

# Vision-capable models available locally
VISION_MODELS = [
    "llama3.2-vision:latest",
    "qwen2.5vl:7b",
    "minicpm-v:latest",
    "llava:7b",
    "gemma3:latest",
]

SYSTEM_PROMPT = "You are a real-time camera assistant. Describe what you see in the image in 1-3 concise sentences. Focus on objects, people, text, colors, and motion."
USER_PROMPT = "What do you see in this camera frame? Be brief and descriptive."


# ============================================================
#  OLLAMA CLIENT
# ============================================================

class OllamaVisionClient:
    def __init__(self, model: str):
        self.model = model
        self.session = requests.Session()
        self.last_response = ""
        self.last_error = ""
        self.processing = False
        self.lock = threading.Lock()

    def _encode_frame(self, frame: np.ndarray) -> str:
        _, buffer = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
        return base64.b64encode(buffer).decode("utf-8")

    def ask(self, frame: np.ndarray):
        if self.processing:
            return
        self.processing = True
        thread = threading.Thread(target=self._ask_async, args=(frame.copy(),), daemon=True)
        thread.start()

    def _ask_async(self, frame: np.ndarray):
        try:
            b64 = self._encode_frame(frame)
            payload = {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": USER_PROMPT, "images": [b64]},
                ],
                "stream": False,
            }
            resp = self.session.post(
                f"{OLLAMA_URL}/api/chat", json=payload, timeout=60
            )
            if resp.status_code == 200:
                data = resp.json()
                with self.lock:
                    self.last_response = data.get("message", {}).get("content", "").strip()
                    self.last_error = ""
            else:
                with self.lock:
                    self.last_error = f"HTTP {resp.status_code}"
        except Exception as e:
            with self.lock:
                self.last_error = str(e)
        finally:
            self.processing = False

    def get_status(self) -> tuple[str, str]:
        with self.lock:
            return self.last_response, self.last_error


# ============================================================
#  STREAM BUFFER
# ============================================================

class StreamBuffer:
    def __init__(self):
        self.buffer = b""

    def feed(self, data: bytes):
        self.buffer += data

    def get_frame(self) -> np.ndarray | None:
        a = self.buffer.find(b"\xff\xd8")
        b = self.buffer.find(b"\xff\xd9")
        if a != -1 and b != -1 and b > a:
            jpg = self.buffer[a : b + 2]
            self.buffer = self.buffer[b + 2 :]
            return cv2.imdecode(np.frombuffer(jpg, dtype=np.uint8), cv2.IMREAD_COLOR)
        return None


# ============================================================
#  MODEL CHECK
# ============================================================

def get_available_vision_models() -> list[str]:
    try:
        resp = requests.get(f"{OLLAMA_URL}/api/tags", timeout=5)
        if resp.status_code != 200:
            return VISION_MODELS
        installed = {m["name"] for m in resp.json().get("models", [])}
        available = [m for m in VISION_MODELS if m in installed]
        if not available:
            available = [m for m in VISION_MODELS]
        return available
    except Exception:
        return VISION_MODELS


# ============================================================
#  MAIN
# ============================================================

def main():
    available_models = get_available_vision_models()

    print("\n=== ESP32-S3 Vision LLM ===\n")
    print("Available vision models:")
    for i, m in enumerate(available_models, 1):
        print(f"  {i}. {m}")

    choice = input(f"\nSelect model [1-{len(available_models)}] (default 1): ").strip()
    try:
        idx = int(choice) - 1
        model = available_models[max(0, min(idx, len(available_models) - 1))]
    except (ValueError, IndexError):
        model = available_models[0]

    interval = input("Analysis interval in seconds [default 5]: ").strip()
    try:
        analysis_interval = max(1, float(interval))
    except ValueError:
        analysis_interval = 5

    print(f"\nModel: {model}")
    print(f"Interval: {analysis_interval}s")
    print("Connecting to stream...\n")

    try:
        stream = urllib.request.urlopen(f"{BASE_URL}/", timeout=10)
    except Exception as e:
        print(f"Failed to connect: {e}")
        return

    print("Connected! Controls:")
    print("  q  - Quit")
    print("  a  - Toggle auto-analysis")
    print("  n  - Analyze current frame now")
    print(f"  Capturing every {analysis_interval}s\n")

    ollama = OllamaVisionClient(model)
    buffer = StreamBuffer()
    auto_analyze = True
    last_analysis = 0
    analysis_result = ""
    analysis_error = ""
    fps_history = []
    frame_count = 0
    fps_start = time.time()

    while True:
        try:
            data = stream.read(4096)
            if not data:
                print("Reconnecting...")
                stream = urllib.request.urlopen(f"{BASE_URL}/", timeout=10)
                continue

            buffer.feed(data)
            frame = buffer.get_frame()
            if frame is None:
                continue

            frame_count += 1
            elapsed = time.time() - fps_start
            fps = frame_count / elapsed if elapsed > 0 else 0

            now = time.time()

            if auto_analyze and (now - last_analysis >= analysis_interval) and not ollama.processing:
                ollama.ask(frame)
                last_analysis = now

            response_text, error_text = ollama.get_status()
            if response_text:
                analysis_result = response_text
                analysis_error = ""
            if error_text:
                analysis_error = error_text

            overlay = frame.copy()
            cv2.rectangle(overlay, (0, 0), (frame.shape[1], 140), (0, 0, 0), -1)
            frame = cv2.addWeighted(frame, 1.0, overlay, 0.5, 0)

            cv2.putText(frame, f"Model: {model}", (10, 25),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 255, 0), 2)
            cv2.putText(frame, f"FPS: {fps:.1f} | Auto: {'ON' if auto_analyze else 'OFF'} | "
                        f"Interval: {analysis_interval}s | Next: {max(0, analysis_interval - (now - last_analysis)):.0f}s",
                        (10, 50), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 0), 1)

            status = "Processing..." if ollama.processing else "Ready"
            cv2.putText(frame, f"LLM: {status}", (10, 72),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 0), 1)

            if analysis_result:
                y = 95
                for line in analysis_result.split("\n"):
                    cv2.putText(frame, line, (10, y),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
                    y += 20
                    if y > 135:
                        break
            elif analysis_error:
                cv2.putText(frame, f"Error: {analysis_error}", (10, 95),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 1)

            cv2.imshow("ESP32-S3 Vision LLM", frame)
            key = cv2.waitKey(1) & 0xFF

            if key == ord("q"):
                break
            elif key == ord("a"):
                auto_analyze = not auto_analyze
                print(f"Auto-analysis: {'ON' if auto_analyze else 'OFF'}")
                if auto_analyze:
                    last_analysis = 0
            elif key == ord("n"):
                if not ollama.processing:
                    ollama.ask(frame)
                    last_analysis = now

        except Exception as e:
            print(f"Error: {e}")
            break

    cv2.destroyAllWindows()
    print("Vision LLM viewer closed.")


if __name__ == "__main__":
    main()
