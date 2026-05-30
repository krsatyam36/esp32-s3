"""
Production-grade FastAPI server for ESP32-S3 Camera Stream + Ollama Vision LLM.
Runs a background capture thread to continuously read the ESP32 MJPEG stream,
serves it via multipart/x-mixed-replace, and streams Vision LLM analysis
over Server-Sent Events.

Usage:
    pip install fastapi uvicorn requests
    python app.py
    # Open http://localhost:8000
"""

import asyncio
import base64
import json
import os
import threading
import time
import urllib.request
import urllib.error

import cv2
import numpy as np
import requests
from fastapi import FastAPI, Request, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, HTMLResponse
from pydantic import BaseModel

from config import ESP32_IP

# ──────────────────────────────────────────────
#  Configuration
# ──────────────────────────────────────────────

BASE_URL = ESP32_IP.rstrip("/")
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "gemma3:latest")
ANALYSIS_INTERVAL = float(os.environ.get("ANALYSIS_INTERVAL", "5"))

# ──────────────────────────────────────────────
#  ESP32 HTTP Client (proxies commands to ESP32)
# ──────────────────────────────────────────────

class ESP32Client:
    def __init__(self, base_url: str):
        self.base_url = base_url

    def send_command(self, endpoint: str) -> dict:
        try:
            resp = urllib.request.urlopen(f"{self.base_url}{endpoint}", timeout=5)
            return json.loads(resp.read().decode())
        except Exception as e:
            return {"success": False, "error": str(e)}

    def get_telemetry(self) -> dict:
        return self.send_command("/telemetry")

esp32 = ESP32Client(BASE_URL)

# ──────────────────────────────────────────────
#  MJPEG Stream Buffer (self-healing)
# ──────────────────────────────────────────────

class StreamBuffer:
    """Extracts complete JPEG frames from a raw MJPEG byte stream."""

    def __init__(self):
        self._buf = b""

    def feed(self, data: bytes):
        self._buf += data

    def get_frame(self) -> bytes | None:
        a = self._buf.find(b"\xff\xd8")
        b = self._buf.find(b"\xff\xd9")
        if a != -1 and b != -1 and b > a:
            jpg = self._buf[a : b + 2]
            self._buf = self._buf[b + 2 :]
            return jpg
        if a != -1 and b != -1 and a > b:
            self._buf = self._buf[a:]
        return None

# ──────────────────────────────────────────────
#  Camera Capture (background thread)
# ──────────────────────────────────────────────

class CameraCapture:
    """Continuously pulls 64 KB chunks from the ESP32 MJPEG endpoint,
    extracts JPEG frames, and keeps the latest one available."""

    def __init__(self, stream_url: str):
        self._url = stream_url
        self._buffer = StreamBuffer()
        self._latest_frame: bytes | None = None
        self._lock = threading.Lock()
        self._running = False
        self._frame_id = 0

    def start(self):
        self._running = True
        t = threading.Thread(target=self._capture_loop, daemon=True)
        t.start()

    def stop(self):
        self._running = False

    @property
    def latest_frame(self) -> bytes | None:
        with self._lock:
            return self._latest_frame

    @property
    def frame_id(self) -> int:
        with self._lock:
            return self._frame_id

    def _capture_loop(self):
        while self._running:
            try:
                stream = urllib.request.urlopen(self._url, timeout=3)
                while self._running:
                    try:
                        data = stream.read(65536)
                        if not data:
                            break
                        self._buffer.feed(data)
                        while True:
                            jpg = self._buffer.get_frame()
                            if jpg is None:
                                break
                            with self._lock:
                                self._latest_frame = jpg
                                self._frame_id += 1
                    except (urllib.error.URLError, ConnectionError):
                        break
                    except Exception:
                        break
            except Exception:
                time.sleep(1)

# ──────────────────────────────────────────────
#  Ollama Vision Analyzer (background thread)
# ──────────────────────────────────────────────

OLLAMA_SYSTEM_PROMPT = (
    "You are a real-time camera assistant. "
    "Describe what you see in 1-3 concise sentences. "
    "Focus on objects, people, text, colors, and motion. "
    "Start directly with the description — no introductory phrases."
)
OLLAMA_USER_PROMPT = "What do you see in this camera frame?"


class OllamaAnalyzer:
    """Periodically grabs the latest camera frame and sends it to Ollama
    for visual analysis.  Results are polled via get_result().
    Supports on-demand analysis via trigger_now() and dynamic model switching."""

    def __init__(self, camera: CameraCapture, model: str, interval: float = 5.0):
        self.camera = camera
        self.model = model
        self.interval = interval
        self._last_text = ""
        self._lock = threading.Lock()
        self._running = False
        self._session = requests.Session()
        self._trigger = threading.Event()

    def start(self):
        self._running = True
        t = threading.Thread(target=self._loop, daemon=True)
        t.start()

    def stop(self):
        self._running = False

    def trigger_now(self):
        """Force an immediate analysis on the next loop iteration."""
        self._trigger.set()

    def set_model(self, model: str):
        """Change the model at runtime."""
        with self._lock:
            self.model = model

    def set_interval(self, interval: float):
        """Change the analysis interval at runtime."""
        with self._lock:
            self.interval = max(1.0, interval)

    def _loop(self):
        last_frame_id = -1
        while self._running:
            # If not forced, wait for the interval
            forced = self._trigger.wait(timeout=self.interval)
            self._trigger.clear()

            raw = self.camera.latest_frame
            if raw is None:
                continue

            # Skip if same frame (unless forced)
            fid = self.camera.frame_id
            if fid == last_frame_id and not forced:
                continue
            last_frame_id = fid

            try:
                b64 = base64.b64encode(raw).decode("utf-8")
                with self._lock:
                    current_model = self.model
                payload = {
                    "model": current_model,
                    "system": OLLAMA_SYSTEM_PROMPT,
                    "prompt": OLLAMA_USER_PROMPT,
                    "images": [b64],
                    "stream": False,
                }
                resp = self._session.post(
                    f"{OLLAMA_URL}/api/generate", json=payload, timeout=30
                )
                if resp.status_code == 200:
                    text = resp.json().get("response", "").strip()
                    with self._lock:
                        self._last_text = text
            except Exception:
                pass

    def get_result(self) -> str:
        with self._lock:
            return self._last_text

    def get_model(self) -> str:
        with self._lock:
            return self.model


# ──────────────────────────────────────────────
#  Instantiate capture & analyzer
# ──────────────────────────────────────────────

camera = CameraCapture(BASE_URL + "/")
analyzer = OllamaAnalyzer(camera=camera, model=OLLAMA_MODEL, interval=ANALYSIS_INTERVAL)

# ──────────────────────────────────────────────
#  FastAPI Application
# ──────────────────────────────────────────────

app = FastAPI(
    title="ESP32-S3 Camera Dashboard",
    description="Low-latency MJPEG stream + Vision LLM analysis",
    version="2.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def startup():
    print(f"Connecting to ESP32 at {BASE_URL} ...")
    camera.start()
    analyzer.start()
    print(f"Streaming at http://localhost:8000")


@app.on_event("shutdown")
async def shutdown():
    camera.stop()
    analyzer.stop()


# ─── MJPEG Video Stream ───────────────────────

@app.get("/stream")
async def video_stream():
    """Returns an infinite multipart/x-mixed-replace MJPEG stream."""

    async def generate():
        while True:
            frame = camera.latest_frame
            if frame is not None:
                yield (
                    b"--frame\r\n"
                    b"Content-Type: image/jpeg\r\n\r\n" + frame + b"\r\n"
                )
            await asyncio.sleep(0.03)

    return StreamingResponse(
        generate(),
        media_type="multipart/x-mixed-replace; boundary=frame",
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
            "Expires": "0",
        },
    )


# ─── SSE Analysis Stream ──────────────────────

@app.get("/analysis")
async def analysis_sse(request: Request):
    """Server-Sent Events endpoint that pushes new analysis text
    whenever the background OllamaAnalyzer produces a result."""

    async def event_stream():
        previous = ""
        while True:
            if await request.is_disconnected():
                break
            text = analyzer.get_result()
            if text and text != previous:
                yield f"data: {json.dumps({'text': text, 'model': analyzer.get_model()})}\n\n"
                previous = text
            await asyncio.sleep(0.5)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ─── Available Ollama Models ──────────────────

@app.get("/models")
async def list_models():
    """Returns the list of vision models available on this Ollama instance."""
    try:
        resp = requests.get(f"{OLLAMA_URL}/api/tags", timeout=5)
        if resp.status_code == 200:
            names = [m["name"] for m in resp.json().get("models", [])]
            return {"models": names}
    except Exception:
        pass
    return {"models": [OLLAMA_MODEL]}


# ─── ESP32 Control Proxy ──────────────────────

class LedState(BaseModel):
    state: str  # "on" | "off"


class ResValue(BaseModel):
    value: str  # "SVGA" | "UXGA"


@app.post("/led")
async def set_led(body: LedState):
    return esp32.send_command(f"/led?state={body.state}")


@app.post("/flash")
async def flash_led(count: int = Query(5, ge=1, le=20)):
    return esp32.send_command(f"/flash?count={count}")


@app.post("/res")
async def set_resolution(body: ResValue):
    return esp32.send_command(f"/res?val={body.value}")


@app.get("/telemetry")
async def get_telemetry():
    return esp32.get_telemetry()


# ─── Model & Analysis Control ────────────────

class ModelSelect(BaseModel):
    model: str


class IntervalSelect(BaseModel):
    interval: float


@app.post("/model")
async def set_model(body: ModelSelect):
    """Switch the vision model at runtime."""
    analyzer.set_model(body.model)
    return {"success": True, "model": body.model}


@app.post("/interval")
async def set_interval(body: IntervalSelect):
    """Change the analysis interval (seconds)."""
    analyzer.set_interval(body.interval)
    return {"success": True, "interval": max(1.0, body.interval)}


@app.post("/analyze-now")
async def analyze_now():
    """Force an immediate analysis of the latest frame."""
    analyzer.trigger_now()
    return {"success": True}


# ─── Health & Status ─────────────────────────

@app.get("/health")
async def health():
    """Returns connection status for ESP32 and Ollama."""
    status = {
        "esp32": {"connected": False, "error": None},
        "ollama": {"connected": False, "error": None},
        "model": analyzer.get_model(),
        "interval": analyzer.interval,
    }
    # Check ESP32
    try:
        resp = urllib.request.urlopen(f"{BASE_URL}/telemetry", timeout=3)
        if resp.status == 200:
            status["esp32"]["connected"] = True
    except Exception as e:
        status["esp32"]["error"] = str(e)
    # Check Ollama
    try:
        resp = requests.get(f"{OLLAMA_URL}/api/tags", timeout=3)
        if resp.status_code == 200:
            status["ollama"]["connected"] = True
    except Exception as e:
        status["ollama"]["error"] = str(e)
    return status


# ─── Serve Frontend ──────────────────────────

@app.get("/")
async def index():
    with open("index.html", "r") as f:
        return HTMLResponse(f.read(), headers={"Cache-Control": "no-cache"})


# ──────────────────────────────────────────────
#  Entrypoint
# ──────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("PORT", "8000"))
    uvicorn.run(
        "app:app",
        host="0.0.0.0",
        port=port,
        reload=False,
        log_level="info",
    )
