"""
ESP32-S3 Live Feed → Ollama Vision LLM

Captures frames from the ESP32 camera stream and sends them to locally
running Ollama vision models (llama3.2-vision, gemma3, qwen2.5vl, etc.)
for real-time description without blocking the video display.
"""

import argparse
import base64
import http.client
import logging
import os
import sys
import threading
import time
import urllib.error
import urllib.request

import cv2
import numpy as np
import requests

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("vision_llm")

parser = argparse.ArgumentParser(description="ESP32-S3 Vision LLM")
parser.add_argument("--ip", type=str, default=None, help="ESP32 IP address (overrides config.py)")
parser.add_argument("--stream", action="store_true", help="Enable streaming responses from Ollama")
parser.add_argument("--output-json", type=str, default=None, help="Save analysis results as JSON to file")
args, _ = parser.parse_known_args()
STREAM_LLM = args.stream
OUTPUT_JSON = args.output_json

def _auto_discover() -> str:
    from discover_esp32 import discover
    ip = discover(timeout=10)
    if ip:
        return f"http://{ip}"
    print("ERROR: Could not auto-discover ESP32.")
    print("Make sure the board is powered on and connected to WiFi.")
    print("Or provide the IP manually: python vision_llm.py --ip http://192.168.1.X/")
    sys.exit(1)


if args.ip:
    BASE_URL = args.ip.rstrip("/")
else:
    _env_ip = os.environ.get("ESP32_IP", "").strip()
    if _env_ip:
        BASE_URL = _env_ip.rstrip("/")
    else:
        try:
            from config import ESP32_IP
            BASE_URL = ESP32_IP.rstrip("/")
            if "192.168.1.X" in BASE_URL:
                print("Default IP in config.py — auto-discovering...")
                BASE_URL = _auto_discover()
        except ImportError:
            print("No config.py found — auto-discovering...")
            BASE_URL = _auto_discover()
OLLAMA_URL = "http://localhost:11434"

# Vision-capable models available locally
# gemma3:latest is the default (first position)
VISION_MODELS = [
    "gemma3:latest",
    "llama3.2-vision:latest",
    "qwen2.5vl:7b",
    "minicpm-v:latest",
    "llava:7b",
]

# Use a single combined prompt for /api/generate — no chat structure.
# The explicit "Start directly with" prefix suppresses verbose preamble.
SYSTEM_PROMPT = (
    "You are a real-time camera assistant. "
    "Describe what you see in 1-3 concise sentences. "
    "Focus on objects, people, text, colors, and motion. "
    "Start directly with the description — no introductory phrases."
)
USER_PROMPT = "What do you see in this camera frame?"


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
                "system": SYSTEM_PROMPT,
                "prompt": USER_PROMPT,
                "images": [b64],
                "stream": STREAM_LLM,
            }
            if STREAM_LLM:
                resp = self.session.post(f"{OLLAMA_URL}/api/generate", json=payload, timeout=120, stream=True)
                collected = ""
                if resp.status_code == 200:
                    for line in resp.iter_lines(decode_unicode=True):
                        if line:
                            try:
                                chunk = json.loads(line)
                                collected += chunk.get("response", "")
                                with self.lock:
                                    self.last_response = collected.strip()
                                    self.last_error = ""
                            except json.JSONDecodeError:
                                pass
                else:
                    with self.lock:
                        self.last_error = f"HTTP {resp.status_code}"
            else:
                resp = self.session.post(f"{OLLAMA_URL}/api/generate", json=payload, timeout=60)
                if resp.status_code == 200:
                    data = resp.json()
                    with self.lock:
                        self.last_response = data.get("response", "").strip()
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

    _parser = argparse.ArgumentParser(description="ESP32-S3 Vision LLM")
    _parser.add_argument("--model", type=str, default=None, help="Ollama vision model")
    _parser.add_argument(
        "--interval", type=float, default=None, help="Analysis interval in seconds"
    )
    _parser.add_argument(
        "--non-interactive", action="store_true", help="Skip prompts, use defaults"
    )
    _args, _ = _parser.parse_known_args()

    if _args.model and _args.model in available_models:
        model = _args.model
    elif _args.non_interactive:
        model = available_models[0]
    else:
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

    if _args.interval:
        analysis_interval = max(1, _args.interval)
    elif _args.non_interactive:
        analysis_interval = 5
    else:
        interval_in = input("Analysis interval in seconds [default 5]: ").strip()
        try:
            analysis_interval = max(1, float(interval_in))
        except ValueError:
            analysis_interval = 5

    print(f"\nModel: {model}")
    print(f"Interval: {analysis_interval}s")
    print(f"Stream URL: {BASE_URL}/")
    print("Connecting to stream...\n")

    ollama = OllamaVisionClient(model)
    buffer = StreamBuffer()
    auto_analyze = True
    last_analysis = 0
    analysis_result = ""
    analysis_error = ""
    frame_count = 0
    fps_start = time.time()
    rotation_angle = 0
    show_grid = False
    running = True

    help_text = "Controls: q=Quit  a=Auto-toggle  n=Analyze now  o=Rotate  g=Grid  h=Help"

    def wrap_text(text, max_width, scale=0.5, thick=1):
        """Word-wrap text to fit within max_width pixels."""
        words = text.split()
        lines = []
        current_line = ""
        for word in words:
            test_line = current_line + " " + word if current_line else word
            (w, _), _ = cv2.getTextSize(test_line, cv2.FONT_HERSHEY_SIMPLEX, scale, thick)
            if w <= max_width:
                current_line = test_line
            else:
                if current_line:
                    lines.append(current_line)
                current_line = word
        if current_line:
            lines.append(current_line)
        return lines if lines else [text]

    def draw_text(img, text, x, y, color=(255, 255, 255), scale=0.5, thick=1):
        cv2.putText(
            img,
            text,
            (x + 1, y + 1),
            cv2.FONT_HERSHEY_SIMPLEX,
            scale,
            (0, 0, 0),
            thick + 1,
            cv2.LINE_AA,
        )
        cv2.putText(img, text, (x, y), cv2.FONT_HERSHEY_SIMPLEX, scale, color, thick, cv2.LINE_AA)

    print("Controls:")
    print("  q  - Quit")
    print("  a  - Toggle auto-analysis")
    print("  n  - Analyze current frame now")
    print("  o  - Rotate 90° CW")
    print("  g  - Toggle grid overlay")
    print("  h  - Show controls")
    print(f"  Capturing every {analysis_interval}s\n")

    while running:
        stream = None
        try:
            stream = urllib.request.urlopen(f"{BASE_URL}/", timeout=10)
            print("Connected to ESP32-S3 stream.")
            while running:
                try:
                    data = stream.read(4096)
                    if not data:
                        print("Reconnecting...")
                        break

                    buffer.feed(data)
                    frame = buffer.get_frame()
                    if frame is None:
                        continue

                    frame_count += 1
                    elapsed = time.time() - fps_start
                    fps = frame_count / elapsed if elapsed > 0 else 0

                    now = time.time()

                    if (
                        auto_analyze
                        and (now - last_analysis >= analysis_interval)
                        and not ollama.processing
                    ):
                        ollama.ask(frame)
                        last_analysis = now

                    response_text, error_text = ollama.get_status()
                    if response_text:
                        analysis_result = response_text
                        analysis_error = ""
                    if error_text:
                        analysis_error = error_text

                    # Apply rotation
                    if rotation_angle == 90:
                        frame = cv2.rotate(frame, cv2.ROTATE_90_CLOCKWISE)
                    elif rotation_angle == 180:
                        frame = cv2.rotate(frame, cv2.ROTATE_180)
                    elif rotation_angle == 270:
                        frame = cv2.rotate(frame, cv2.ROTATE_90_COUNTERCLOCKWISE)

                    # Draw grid overlay
                    if show_grid:
                        h, w = frame.shape[:2]
                        color = (180, 180, 180)
                        cv2.line(frame, (w // 3, 0), (w // 3, h), color, 1)
                        cv2.line(frame, (2 * w // 3, 0), (2 * w // 3, h), color, 1)
                        cv2.line(frame, (0, h // 3), (w, h // 3), color, 1)
                        cv2.line(frame, (0, 2 * h // 3), (w, 2 * h // 3), color, 1)

                    # ── Compact top status bar ──
                    top_bar_h = 95
                    overlay = frame.copy()
                    cv2.rectangle(overlay, (0, 0), (frame.shape[1], top_bar_h), (0, 0, 0), -1)
                    frame = cv2.addWeighted(frame, 0.7, overlay, 0.3, 0)

                    draw_text(frame, f"Model: {model}", 10, 22, (0, 255, 0), 0.55, 2)
                    draw_text(
                        frame,
                        f"FPS: {fps:.1f} | Auto: {'ON' if auto_analyze else 'OFF'} | "
                        f"Interval: {analysis_interval}s | Next: {max(0, analysis_interval - (now - last_analysis)):.0f}s",
                        10,
                        46,
                        (255, 255, 0),
                        0.5,
                        1,
                    )

                    status = "Processing..." if ollama.processing else "Ready"
                    draw_text(frame, f"LLM: {status}", 10, 68, (255, 255, 0), 0.5, 1)

                    if rotation_angle:
                        draw_text(frame, f"Rot: {rotation_angle}°", 10, 88, (0, 255, 255), 0.5, 1)

                    # ── Bottom analysis panel (dynamic height) ──
                    if analysis_result:
                        margin = 10
                        max_text_width = frame.shape[1] - 2 * margin
                        lines = wrap_text(analysis_result, max_text_width, scale=0.5, thick=1)
                        line_h = 22
                        pad = 12
                        max_lines = min(len(lines), 8)
                        panel_h = max_lines * line_h + pad
                        fh = frame.shape[0]
                        overlay = frame.copy()
                        cv2.rectangle(
                            overlay, (0, fh - panel_h), (frame.shape[1], fh), (0, 0, 0), -1
                        )
                        frame = cv2.addWeighted(frame, 0.7, overlay, 0.3, 0)
                        for i, line in enumerate(lines[:max_lines]):
                            draw_text(
                                frame,
                                line,
                                margin,
                                fh - panel_h + pad + i * line_h + 12,
                                (255, 255, 255),
                                0.5,
                                1,
                            )
                        if len(lines) > max_lines:
                            draw_text(
                                frame,
                                f"... +{len(lines) - max_lines} more lines",
                                margin,
                                fh - 8,
                                (180, 180, 180),
                                0.4,
                                1,
                            )
                    elif analysis_error:
                        overlay = frame.copy()
                        cv2.rectangle(
                            overlay,
                            (0, frame.shape[0] - 40),
                            (frame.shape[1], frame.shape[0]),
                            (0, 0, 0),
                            -1,
                        )
                        frame = cv2.addWeighted(frame, 0.7, overlay, 0.3, 0)
                        draw_text(
                            frame,
                            f"Error: {analysis_error}",
                            10,
                            frame.shape[0] - 14,
                            (0, 0, 255),
                            0.5,
                            1,
                        )

                    cv2.imshow("ESP32-S3 Vision LLM", frame)
                    key = cv2.waitKey(1) & 0xFF

                    if key == ord("q"):
                        running = False
                        break
                    if key == ord("o"):
                        rotation_angle = (rotation_angle + 90) % 360
                        print(f"Rotation: {rotation_angle}°")
                    elif key == ord("g"):
                        show_grid = not show_grid
                        print(f"Grid: {'ON' if show_grid else 'OFF'}")
                    elif key == ord("h"):
                        print(help_text)
                    elif key == ord("a"):
                        auto_analyze = not auto_analyze
                        print(f"Auto-analysis: {'ON' if auto_analyze else 'OFF'}")
                        if auto_analyze:
                            last_analysis = 0
                    if analysis_result and OUTPUT_JSON:
                    try:
                        with open(OUTPUT_JSON, "w") as jf:
                            json.dump({
                                "timestamp": time.time(),
                                "model": model,
                                "result": analysis_result,
                            }, jf)
                    except Exception:
                        pass

                elif key == ord("n"):
                        if not ollama.processing:
                            ollama.ask(frame)
                            last_analysis = now

                except (
                    TimeoutError,
                    urllib.error.URLError,
                    ConnectionError,
                    http.client.IncompleteRead,
                    http.client.RemoteDisconnected,
                ):
                    print("Connection lost, reconnecting...")
                    break
                except Exception as e:
                    print(f"Stream error: {e}")
                    break
        except Exception as e:
            print(f"Connection failed: {e}. Retrying in 2 seconds...")
        finally:
            if stream is not None:
                try:
                    stream.close()
                except Exception:
                    pass
        if running:
            time.sleep(2)

    cv2.destroyAllWindows()
    print("Vision LLM viewer closed.")


if __name__ == "__main__":
    main()
