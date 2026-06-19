"""
ESP32-S3 Edge Intelligence Platform v2.3.14 — FastAPI server with:
  • MJPEG streaming                    • Vision LLM via Ollama (gemma3, llama3.2-vision)
  • Semantic video search (CLIP+ChromaDB)   • YOLO event gatekeeper
  • Adaptive rate controller                • Scene classification
  • Activity timeline                        • Object counting
  • Smart alert system                       • Performance metrics history
  • SSE/health/control                       • Motion heatmap

Dependencies:
    pip install fastapi uvicorn requests
    # Optional — enables vector search:
    pip install chromadb sentence-transformers torch
    # Optional — enables event gatekeeper:
    pip install ultralytics
"""

# ─── Standard Library ───────────────────────────────
import asyncio
import base64
import collections
import gc
import json
import logging
import os
import platform
import signal
import sys
import threading
import time
import urllib.error
import urllib.request
import uuid

import cv2
# ─── Third-Party ────────────────────────────────────
import numpy as np
import requests
from fastapi import FastAPI, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, Response, StreamingResponse
from pydantic import BaseModel

LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO").upper()
LOG_FORMAT = os.environ.get("LOG_FORMAT", "json").lower()
if LOG_FORMAT == "json":
    _fmt = '{"time":"%(asctime)s","level":"%(levelname)s","name":"%(name)s","msg":"%(message)s"}'
else:
    _fmt = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format=_fmt,
    datefmt="%Y-%m-%dT%H:%M:%S",
)
log = logging.getLogger("xiao")

_dotenv = os.path.join(os.path.dirname(__file__), "..", ".env")
if os.path.isfile(_dotenv):
    with open(_dotenv) as _f:
        for _line in _f:
            _line = _line.strip()
            if _line and not _line.startswith("#") and "=" in _line:
                _k, _v = _line.split("=", 1)
                os.environ.setdefault(_k.strip(), _v.strip())

try:
    from config import ESP32_IP as _IP
    _BASE = _IP.rstrip("/")
except (ImportError, NameError):
    _BASE = os.environ.get("ESP32_IP", "http://192.168.1.X/").rstrip("/")

# ──────────────────────────────────────────────
#  Configuration
# ──────────────────────────────────────────────

BASE_URL = _BASE
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "gemma3:latest")
ANALYSIS_INTERVAL = float(os.environ.get("ANALYSIS_INTERVAL", "5"))
VECTOR_INTERVAL = float(os.environ.get("VECTOR_INTERVAL", "10"))
YOLO_CONF = float(os.environ.get("YOLO_CONFIDENCE", "0.35"))

# ──────────────────────────────────────────────
#  Extracted class imports
# ──────────────────────────────────────────────
from src.ai.event_gatekeeper import EventGatekeeper
from src.ai.motion_heatmap import MotionHeatmap
from src.ai.object_counter import ObjectCounter
from src.ai.ollama_analyzer import OllamaAnalyzer
from src.ai.scene_classifier import SceneClassifier
from src.ai.smart_alert import AlertManager, AlertRule
from src.ai.timeline_engine import TimelineEngine
from src.ai.vector_search import VectorSearch
from src.core.adaptive_controller import AdaptiveController
from src.core.camera_capture import CameraCapture
from src.core.esp32_client import ESP32Client, ResValue
from src.core.metrics_history import MetricsHistory

esp32 = ESP32Client(BASE_URL)

# ──────────────────────────────────────────────
#  Feature 4: Scene Classification
# ──────────────────────────────────────────────

SCENE_CATEGORIES = [
    "indoor", "outdoor", "office", "classroom", "laboratory",
    "kitchen", "living_room", "street", "parking_lot", "nature",
    "night", "day", "low_light", "bright", "crowded", "empty",
    "workshop", "server_room", "warehouse", "corridor"
]


class SceneClassifier:
    """Computer-vision-based scene analysis using frame statistics.
    No ML dependency — uses histogram, brightness, edge detection, and
    color analysis for real-time classification."""

    def __init__(self, camera):
        self.camera = camera
        self._current_scene = "unknown"
        self._scene_history = deque(maxlen=100)
        self._lock = threading.Lock()
        self._last_analysis = 0
        self._interval = 5.0

    def start(self):
        t = threading.Thread(target=self._loop, daemon=True)
        t.start()

    def _loop(self):
        while True:
            raw = self.camera.latest_frame
            if raw is not None and (time.time() - self._last_analysis) >= self._interval:
                self._last_analysis = time.time()
                try:
                    arr = np.frombuffer(raw, dtype=np.uint8)
                    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
                    if img is not None:
                        scene = self._classify(img)
                        with self._lock:
                            self._current_scene = scene
                            self._scene_history.append({
                                "time": time.time(),
                                "scene": scene,
                            })
                except Exception:
                    pass
            time.sleep(1)

    def _classify(self, img: np.ndarray) -> str:
        h, w = img.shape[:2]
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        mean_brightness = gray.mean()
        std_brightness = gray.std()

        laplacian_var = cv2.Laplacian(gray, cv2.CV_64F).var()
        edges = cv2.Canny(gray, 50, 150)
        edge_density = (edges > 0).mean()

        hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
        mean_hue = hsv[:, :, 0].mean()
        mean_sat = hsv[:, :, 1].mean()
        mean_val = hsv[:, :, 2].mean()

        saturation_pixels = (hsv[:, :, 1] > 50).mean()

        if mean_brightness < 40 and std_brightness < 20:
            return "night"
        if mean_brightness > 200 and std_brightness < 15:
            return "bright"
        if mean_brightness < 60:
            return "low_light"

        if edge_density > 0.15 and laplacian_var > 200:
            if saturation_pixels > 0.3:
                return "crowded"
            return "workshop"

        if saturation_pixels > 0.4 and mean_sat > 80:
            return "outdoor"

        if edge_density < 0.05 and laplacian_var < 50:
            return "empty"

        green_channel = img[:, :, 1].mean()
        blue_channel = img[:, :, 0].mean()
        if green_channel > blue_channel * 1.15 and green_channel > 60:
            return "nature"

        if mean_hue < 30 or mean_hue > 150:
            if edge_density > 0.08:
                return "indoor"

        return "indoor"

    @property
    def current(self) -> str:
        with self._lock:
            return self._current_scene

    @property
    def history(self) -> list:
        with self._lock:
            return list(self._scene_history)


# ──────────────────────────────────────────────
#  Feature 5: Activity Timeline
# ──────────────────────────────────────────────

class TimelineEngine:
    """Tracks active events with duration and creates a searchable timeline."""

    def __init__(self, max_entries=500):
        self._entries = deque(maxlen=max_entries)
        self._active_events: dict[str, float] = {}
        self._lock = threading.Lock()

    def record_event(self, event_type: str, metadata: dict | None = None):
        with self._lock:
            now = time.time()
            self._entries.append({
                "type": event_type,
                "time": now,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "metadata": metadata or {},
            })
            if event_type not in ("object_left", "object_left_frame"):
                self._active_events[event_type] = now

    def end_event(self, event_type: str):
        with self._lock:
            if event_type in self._active_events:
                duration = time.time() - self._active_events.pop(event_type)
                self._entries.append({
                    "type": f"{event_type}_ended",
                    "time": time.time(),
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "metadata": {"duration": round(duration, 1)},
                })

    def get_timeline(self, since: float = 0, limit: int = 50) -> list[dict]:
        with self._lock:
            entries = [e for e in self._entries if e["time"] >= since]
            return entries[-limit:]

    def get_active_events(self) -> dict:
        with self._lock:
            now = time.time()
            return {k: round(now - v, 1) for k, v in self._active_events.items()}

    @property
    def summary(self) -> dict:
    """Handle summary operation."""
        with self._lock:
            counts = {}
            for e in self._entries:
                t = e["type"]
                counts[t] = counts.get(t, 0) + 1
            return {
                "total_entries": len(self._entries),
                "active_events": len(self._active_events),
                "type_counts": counts,
            }


# ──────────────────────────────────────────────
#  Feature 6: Object Counter
# ──────────────────────────────────────────────

class ObjectCounter:
    """Tracks cumulative and per-frame object detection statistics."""

    def __init__(self):
        self._counts: dict[str, int] = {}
        self._per_frame: deque[dict] = deque(maxlen=200)
        self._lock = threading.Lock()
        self._total_detections = 0
        self._total_frames_with_objects = 0

    def record(self, objects: list[dict]):
        with self._lock:
            self._total_detections += len(objects)
            self._total_frames_with_objects += 1
            for obj in objects:
                label = obj.get("class", "unknown")
                self._counts[label] = self._counts.get(label, 0) + 1
            self._per_frame.append({
                "time": time.time(),
                "count": len(objects),
                "objects": objects,
            })

    def get_counts(self) -> dict:
        with self._lock:
            return dict(sorted(self._counts.items(), key=lambda x: -x[1]))

    @property
    def stats(self) -> dict:
        with self._lock:
            return {
                "total_detections": self._total_detections,
                "total_frames_with_objects": self._total_frames_with_objects,
                "unique_classes": len(self._counts),
                "top_classes": dict(sorted(self._counts.items(), key=lambda x: -x[1])[:10]),
            }

    @property
    def recent_frames(self) -> list:
        with self._lock:
            return list(self._per_frame)


# ──────────────────────────────────────────────
#  Feature 7: Smart Alert System
# ──────────────────────────────────────────────

class AlertRule(BaseModel):
    name: str
    class_name: str
    min_confidence: float = 0.5
    cooldown: float = 30.0
    enabled: bool = True
    min_count: int = 1


class SmartAlert:
    def __init__(self, rule: AlertRule):
        self.rule = rule
        self.last_triggered = 0.0

    def check(self, objects: list[dict]) -> bool:
        if not self.rule.enabled:
            return False
        now = time.time()
        if (now - self.last_triggered) < self.rule.cooldown:
            return False
        matches = [
            o for o in objects
            if o.get("class") == self.rule.class_name
            and o.get("confidence", 0) >= self.rule.min_confidence
        ]
        if len(matches) >= self.rule.min_count:
            self.last_triggered = now
            return True
        return False


class AlertManager:
    """Manages configurable alert rules and triggers."""

    def __init__(self):
        self._alerts: list[SmartAlert] = []
        self._history: deque = deque(maxlen=200)
        self._lock = threading.Lock()
        self._default_rules = [
            AlertRule(name="person_detected", class_name="person", min_confidence=0.6, cooldown=10.0),
            AlertRule(name="vehicle_nearby", class_name="car", min_confidence=0.5, cooldown=30.0),
            AlertRule(name="animal_spotted", class_name="dog", min_confidence=0.5, cooldown=60.0),
            AlertRule(name="phone_in_use", class_name="cell phone", min_confidence=0.4, cooldown=15.0),
        ]
        for r in self._default_rules:
            self._alerts.append(SmartAlert(r))

    def evaluate(self, objects: list[dict]) -> list[str]:
        triggered = []
        with self._lock:
            for alert in self._alerts:
                if alert.check(objects):
                    triggered.append(alert.rule.name)
                    self._history.append({
                        "time": time.time(),
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "rule": alert.rule.name,
                        "class": alert.rule.class_name,
                        "objects": [o for o in objects if o.get("class") == alert.rule.class_name],
                    })
        return triggered

    def get_rules(self) -> list[AlertRule]:
        with self._lock:
            return [a.rule for a in self._alerts]

    def update_rule(self, idx: int, rule: AlertRule) -> bool:
        if idx < 0 or idx >= len(self._alerts):
            return False
        with self._lock:
            self._alerts[idx] = SmartAlert(rule)
        return True

    def add_rule(self, rule: AlertRule):
        with self._lock:
            self._alerts.append(SmartAlert(rule))

    def remove_rule(self, idx: int) -> bool:
        if idx < 0 or idx >= len(self._alerts):
            return False
        with self._lock:
            self._alerts.pop(idx)
        return True

    def get_history(self, since: float = 0, limit: int = 50) -> list[dict]:
        with self._lock:
            entries = [e for e in self._history if e["time"] >= since]
            return entries[-limit:]

    @property
    def stats(self) -> dict:
        with self._lock:
            return {
                "total_alerts": len(self._alerts),
                "enabled_alerts": sum(1 for a in self._alerts if a.rule.enabled),
                "total_triggered": len(self._history),
            }


# ──────────────────────────────────────────────
#  Feature 8: Performance Metrics History
# ──────────────────────────────────────────────

class MetricsHistory:
    """Ring buffer of system metrics for real-time performance charts."""

    def __init__(self, max_points=300):
        self._points = deque(maxlen=max_points)
        self._lock = threading.Lock()
        self._start_time = time.time()

    def record(self, fps: float, latency: float, queue_depth: int, mode: str):
        with self._lock:
            self._points.append({
                "time": time.time(),
                "t": round(time.time() - self._start_time, 1),
                "fps": round(fps, 1),
                "latency": round(latency, 2),
                "queue_depth": queue_depth,
                "mode": mode,
            })

    def get_series(self, metric: str = "fps", limit: int = 100) -> list[dict]:
        with self._lock:
            pts = list(self._points)[-limit:]
            if metric == "all":
                return pts
            return [{"t": p["t"], "v": p.get(metric, 0)} for p in pts]

    @property
    def summary(self) -> dict:
        with self._lock:
            pts = list(self._points)
            if not pts:
                return {}
            fps_vals = [p["fps"] for p in pts]
            lat_vals = [p["latency"] for p in pts]
            return {
                "points": len(pts),
                "fps_avg": round(sum(fps_vals) / len(fps_vals), 1) if fps_vals else 0,
                "fps_min": min(fps_vals) if fps_vals else 0,
                "fps_max": max(fps_vals) if fps_vals else 0,
                "latency_avg": round(sum(lat_vals) / len(lat_vals), 2) if lat_vals else 0,
                "latency_max": max(lat_vals) if lat_vals else 0,
            }


# ──────────────────────────────────────────────
#  Feature 9: Motion Heatmap
# ──────────────────────────────────────────────

class MotionHeatmap:
    """Accumulates motion regions into a heatmap overlay."""

    def __init__(self, camera, decay=0.95):
        self.camera = camera
        self.decay = decay
        self._heatmap: np.ndarray | None = None
        self._lock = threading.Lock()
        self._running = False
        self._prev_gray = None

    def start(self):
        self._running = True
        t = threading.Thread(target=self._loop, daemon=True)
        t.start()

    def stop(self):
        self._running = False

    def _loop(self):
        while self._running:
            raw = self.camera.latest_frame
            if raw is not None:
                try:
                    arr = np.frombuffer(raw, dtype=np.uint8)
                    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
                    if img is not None:
                        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
                        gray = cv2.GaussianBlur(gray, (21, 21), 0)
                        if self._prev_gray is not None:
                            delta = cv2.absdiff(self._prev_gray, gray)
                            thresh = cv2.threshold(delta, 25, 255, cv2.THRESH_BINARY)[1]
                            with self._lock:
                                if self._heatmap is None:
                                    self._heatmap = thresh.astype(np.float32)
                                else:
                                    if self._heatmap.shape != thresh.shape:
                                        self._heatmap = cv2.resize(self._heatmap, (thresh.shape[1], thresh.shape[0]))
                                    self._heatmap = cv2.addWeighted(
                                        self._heatmap, self.decay,
                                        thresh.astype(np.float32), 1 - self.decay, 0
                                    )
                        self._prev_gray = gray
                except Exception:
                    pass
            time.sleep(0.5)

    def get_heatmap(self) -> str | None:
        with self._lock:
            if self._heatmap is None:
                return None
            normalized = cv2.normalize(self._heatmap, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)
            colored = cv2.applyColorMap(normalized, cv2.COLORMAP_JET)
            _, buffer = cv2.imencode(".jpg", colored)
            import base64 as b64
            return b64.b64encode(buffer).decode("utf-8")

    def reset(self):
        with self._lock:
            self._heatmap = None
            self._prev_gray = None


# ──────────────────────────────────────────────
#  Global Instances
# ──────────────────────────────────────────────

# Order matters: instances needed as module-level globals by other classes
# must be created and wired BEFORE those classes are instantiated.

timeline = TimelineEngine()
object_counter = ObjectCounter()
alert_manager = AlertManager()

# Wire up EventGatekeeper module globals (read in __init__)
import src.ai.event_gatekeeper as _eg_mod

_eg_mod.object_counter = object_counter
_eg_mod.timeline = timeline
_eg_mod.alert_manager = alert_manager

camera = CameraCapture(BASE_URL + "/")
metrics_history = MetricsHistory()

# Wire up AdaptiveController module globals (read in _loop thread)
import src.core.adaptive_controller as _ac_mod

_ac_mod.metrics_history = metrics_history

analyzer = OllamaAnalyzer(camera=camera, model=OLLAMA_MODEL, interval=ANALYSIS_INTERVAL)
vector_search = VectorSearch(camera=camera, interval=VECTOR_INTERVAL)
gatekeeper = EventGatekeeper(camera=camera, analyzer=analyzer)
controller = AdaptiveController(analyzer=analyzer, camera=camera, esp32=esp32)
scene_classifier = SceneClassifier(camera)
    heatmap = MotionHeatmap(camera)

    del _ac_mod, _eg_mod

# ──────────────────────────────────────────────
#  FastAPI Application
# ──────────────────────────────────────────────

_start_time = time.time()

app = FastAPI(
    title="ESP32-S3 Edge Intelligence Platform",
    description="Streaming, Vision LLM, semantic search, YOLO gatekeeper, adaptive controller, scene classification, activity timeline, object counting, smart alerts, heatmap",
    version="2.3.0",
)

CORS_ORIGINS = os.environ.get("CORS_ORIGINS", "*").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(GZipMiddleware, minimum_size=1000)


_rate_limit_store: dict[str, collections.deque] = {}
_RATE_LIMIT = int(os.environ.get("RATE_LIMIT", "60"))
_RATE_WINDOW = 60.0
_MAX_BODY_SIZE = int(os.environ.get("MAX_BODY_SIZE", "1048576"))

@app.middleware("http")
async def rate_limiter(request: Request, call_next):
    client = request.client.host if request.client else "unknown"
    now = time.time()
    if client not in _rate_limit_store:
        _rate_limit_store[client] = collections.deque()
    window = _rate_limit_store[client]
    while window and window[0] < now - _RATE_WINDOW:
        window.popleft()
    if len(window) >= _RATE_LIMIT:
        return JSONResponse(
            status_code=429,
            content={"error": "rate_limit_exceeded", "retry_after": _RATE_WINDOW},
            headers={"Retry-After": str(int(_RATE_WINDOW))},
        )
    window.append(now)
    response = await call_next(request)
    return response


@app.middleware("http")
async def body_size_limit(request: Request, call_next):
    content_length = request.headers.get("content-length")
    if content_length and int(content_length) > _MAX_BODY_SIZE:
        return JSONResponse(
            status_code=413,
            content={"error": "payload_too_large", "max_bytes": _MAX_BODY_SIZE},
        )
    return await call_next(request)


_API_VERSION = "2.3.0"


@app.middleware("http")
async def add_api_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-API-Version"] = _API_VERSION
    response.headers["X-API-Name"] = "xiao-edge-platform"
    return response


@app.middleware("http")
async def add_request_id(request: Request, call_next):
    request_id = str(uuid.uuid4())[:8]
    request.state.request_id = request_id
    start = time.time()
    response = await call_next(request)
    elapsed = time.time() - start
    response.headers["X-Request-ID"] = request_id
    response.headers["X-Response-Time"] = f"{elapsed * 1000:.0f}ms"
    if elapsed > 1.0:
        log.warning("Slow request: %s %s (%.2fs)", request.method, request.url.path, elapsed)
    else:
        log.info("%s %s -> %d (%.0fms)", request.method, request.url.path, response.status_code, elapsed * 1000)
    return response


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    log.error("Unhandled error on %s: %s", request.url.path, exc)
    status = 500
    detail = str(exc)
    if "timeout" in detail.lower():
        status = 504
    elif "not found" in detail.lower() or "404" in detail:
        status = 404
    elif "bad request" in detail.lower() or "400" in detail:
        status = 400
    return JSONResponse(
        status_code=status,
        content={"error": detail, "path": str(request.url.path), "code": status},
        headers={"X-Request-ID": str(uuid.uuid4())[:8]},
    )


@app.exception_handler(404)
async def not_found_handler(request: Request, exc: Exception):
    return JSONResponse(
        status_code=404,
        content={"error": "endpoint_not_found", "path": str(request.url.path)},
    )


@app.exception_handler(405)
async def method_not_allowed_handler(request: Request, exc: Exception):
    return JSONResponse(
        status_code=405,
        content={"error": "method_not_allowed", "path": str(request.url.path)},
    )


@app.on_event("startup")
async def startup():
    log.info("Starting ESP32: %s", BASE_URL)
    log.info("Ollama: %s (%s)", OLLAMA_URL, OLLAMA_MODEL)
    camera.start()
    analyzer.start()
    vector_search.start()
    gatekeeper.start()
    controller.start()
    scene_classifier.start()
    heatmap.start()
    if vector_search.ready:
        log.info("Vector search ready")
    if gatekeeper.ready:
        log.info("YOLO gatekeeper ready")
    log.info("Scene classifier active")
    log.info("Motion heatmap active")
    global _started
    _started = True
    log.info("Dashboard at http://localhost:8000")


@app.on_event("shutdown")
async def shutdown():
    log.info("Shutting down all subsystems...")
    shutdown_timeout = float(os.environ.get("SHUTDOWN_TIMEOUT", "5"))
    tasks = []
    for comp, name in [
        (camera, "camera"),
        (analyzer, "analyzer"),
        (vector_search, "vector_search"),
        (gatekeeper, "gatekeeper"),
        (controller, "controller"),
        (heatmap, "heatmap"),
    ]:
        try:
            if hasattr(comp, "stop"):
                comp.stop()
                tasks.append(name)
        except Exception as e:
            log.error("Error stopping %s: %s", name, e)
    log.info("Stopped %d subsystems: %s", len(tasks), ", ".join(tasks))
    await asyncio.sleep(min(shutdown_timeout, 2))


# ─── MJPEG Video Stream ───────────────────────


@app.get("/stream")
async def video_stream():
    async def generate():
        while True:
            frame = camera.latest_frame
            if frame is not None:
                yield (b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + frame + b"\r\n")
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


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    try:
        while True:
            frame = camera.latest_frame
            if frame is not None:
                b64 = base64.b64encode(frame).decode()
                await websocket.send_json({"type": "frame", "data": b64, "size": len(frame)})
            await asyncio.sleep(0.1)
    except WebSocketDisconnect:
        pass


@app.get("/analysis")
async def analysis_sse(request: Request):
    async def event_stream():
        previous = ""
        while True:
            if await request.is_disconnected():
                break
            text = analyzer.get_result()
            if text and text != previous:
                yield f"data: {json.dumps({'text': text, 'model': analyzer.get_model(), 'boss': analyzer.is_boss_mode()})}\n\n"
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
    state: str


@app.post("/led")
async def set_led(body: LedState):
    return esp32.send_command(f"/led?state={body.state}")


@app.post("/flash")
async def flash_led(count: int = Query(5, ge=1, le=20)):
    return esp32.send_command(f"/flash?count={count}")


@app.post("/res")
async def set_resolution(body: ResValue):
    return esp32.send_command(f"/res?val={body.value}")


class FlipMode(BaseModel):
    mode: str


@app.post("/flip")
async def set_flip(body: FlipMode):
    """Flip camera: mode 'v' for vertical, 'h' for horizontal."""
    return esp32.send_command(f"/flip?mode={body.mode}")

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
    analyzer.set_model(body.model)
    return {"success": True, "model": body.model}


@app.post("/interval")
async def set_interval(body: IntervalSelect):
    analyzer.set_interval(body.interval)
    return {"success": True, "interval": max(1.0, body.interval)}


@app.post("/analyze-now")
async def analyze_now():
    analyzer.trigger_now()
    return {"success": True}


# ─── Feature 1: Semantic Search ──────────────


class SearchQuery(BaseModel):
    q: str


@app.post("/search")
async def search_video(body: SearchQuery, top_k: int = Query(5)):
    """Natural-language semantic search over archived frames."""
    results = vector_search.search(body.q, top_k=top_k)
    return {"query": body.q, "results": results, "index": vector_search.info}


@app.get("/search")
async def search_video_get(q: str = Query(""), top_k: int = Query(5)):
    results = vector_search.search(q, top_k=top_k)
    return {"query": q, "results": results, "index": vector_search.info}


@app.get("/search-status")
async def search_status():
    return vector_search.info


# ─── Feature 2: Event Gatekeeper ─────────────


@app.get("/events")
async def get_events(limit: int = Query(50), since: float = Query(0)):
    return {"events": gatekeeper.get_events(since=since, limit=limit), "stats": gatekeeper.stats}


# ─── Feature 3: Adaptive Controller ──────────


@app.get("/system-status")
async def system_status():
    return {
        "adaptive": controller.summary,
        "camera": {
            "frame_id": camera.frame_id,
            "buffer_depth": camera.buffer_depth,
            "capture_fps": round(camera.capture_fps, 1),
            "uptime": round(camera.uptime, 1),
        },
        "analyzer": {
            "model": analyzer.get_model(),
            "interval": analyzer.interval,
            "last_latency": round(analyzer.last_latency, 2),
        },
        "vector_search": vector_search.info,
        "gatekeeper": gatekeeper.stats,
        "scene": {
            "current": scene_classifier.current,
        },
        "metrics": metrics_history.summary,
        "alerts": alert_manager.stats,
    }


# ─── Feature 4: Scene Classification ──────────

@app.get("/scene")
async def get_scene():
    return {
        "current": scene_classifier.current,
        "confidence": scene_classifier.confidence,
        "history": scene_classifier.history[-20:],
    }


# ─── Feature 5: Activity Timeline ────────────

@app.get("/timeline")
async def get_timeline(limit: int = Query(50), since: float = Query(0)):
    return {
        "entries": timeline.get_timeline(since=since, limit=limit),
        "active": timeline.get_active_events(),
        "summary": timeline.summary,
    }


@app.post("/timeline/export")
async def export_timeline():
    entries = timeline.get_timeline(limit=500)
    return JSONResponse(content={"entries": entries, "count": len(entries)})


# ─── Feature 6: Object Counting ──────────────


@app.get("/stats")
async def get_stats():
    return {
        "counts": object_counter.get_counts(),
        "stats": object_counter.stats,
        "recent": object_counter.recent_frames[-10:],
    }


@app.post("/stats/reset")
async def reset_stats():
    object_counter.reset()
    return {"success": True}


# ─── Feature 7: Smart Alert System ───────────


@app.get("/alerts")
async def get_alerts():
    return {
        "rules": alert_manager.get_rules(),
        "history": alert_manager.get_history(limit=20),
        "stats": alert_manager.stats,
    }


class AlertRuleCreate(BaseModel):
    name: str
    class_name: str
    min_confidence: float = 0.5
    cooldown: float = 30.0
    enabled: bool = True
    min_count: int = 1


@app.post("/alerts")
async def create_alert(rule: AlertRuleCreate):
    alert_manager.add_rule(AlertRule(**rule.model_dump()))
    return {"success": True, "rule": rule}


@app.put("/alerts/{idx}")
async def update_alert(idx: int, rule: AlertRuleCreate):
    ok = alert_manager.update_rule(idx, AlertRule(**rule.model_dump()))
    return {"success": ok}


class AlertToggle(BaseModel):
    enabled: bool


@app.patch("/alerts/{idx}")
async def toggle_alert(idx: int, toggle: AlertToggle):
    rules = alert_manager.get_rules()
    if idx < 0 or idx >= len(rules):
        return JSONResponse(status_code=404, content={"error": "rule not found"})
    rule = rules[idx]
    rule.enabled = toggle.enabled
    ok = alert_manager.update_rule(idx, rule)
    return {"success": ok, "enabled": toggle.enabled}


@app.delete("/alerts/{idx}")
async def delete_alert(idx: int):
    ok = alert_manager.remove_rule(idx)
    return {"success": ok}


@app.get("/alerts/history")
async def get_alert_history(limit: int = Query(50), since: float = Query(0)):
    return {"history": alert_manager.get_history(since=since, limit=limit)}


@app.post("/alerts/clear")
async def clear_alerts():
    alert_manager.history.clear()
    return {"success": True, "cleared": True}


# ─── Feature 8: Performance Metrics ─────────


@app.get("/metrics")
async def get_metrics(metric: str = Query("all"), limit: int = Query(100)):
    return {
        "series": metrics_history.get_series(metric=metric, limit=limit),
        "summary": metrics_history.summary,
    }


# ─── Feature 9: Motion Heatmap ──────────────

@app.get("/heatmap")
async def get_heatmap():
    b64 = heatmap.get_heatmap()
    if b64:
        return {"heatmap": b64, "format": "jpg"}
    return {"heatmap": None, "format": None}


@app.post("/heatmap/reset")
async def reset_heatmap():
    heatmap.reset()
    return {"success": True}


# ─── Diagnostics Proxy ───────────────────────

@app.get("/diag")
async def diagnostics():
    """Proxy to ESP32 firmware diagnostics."""
    try:
        resp = urllib.request.urlopen(f"{BASE_URL}/diag", timeout=5)
        if resp.status == 200:
            data = json.loads(resp.read().decode())
            return {"esp32": data, "cached": False}
    except Exception as e:
        return {"esp32": None, "error": str(e), "cached": False}


# ─── Dashboard Aggregation ───────────────────


@app.get("/dashboard-data")
async def dashboard_data():
    """Aggregated dashboard data for the frontend."""
    tele = esp32.get_telemetry()
    try:
        scene_data = {"current": scene_classifier.current}
    except Exception:
        scene_data = {"current": "unknown"}

    try:
        system = controller.summary
    except Exception:
        system = {}

    try:
        gate_stats = gatekeeper.stats
    except Exception:
        gate_stats = {}

    return {
        "telemetry": tele,
        "scene": scene_data,
        "adaptive": system,
        "gatekeeper": gate_stats,
        "metrics": metrics_history.summary if metrics_history else {},
        "alerts": alert_manager.stats if alert_manager else {},
    }


# ─── Prometheus Metrics ──────────────────────


@app.get("/metrics")
async def prometheus_metrics():
    tele = esp32.get_telemetry()
    ps = os.getpid()
    mem = gc.get_stats()
    lines = [
        "# HELP xiao_uptime_seconds Server uptime in seconds",
        "# TYPE xiao_uptime_seconds gauge",
        f"xiao_uptime_seconds {time.time() - _start_time}",
        "# HELP xiao_esp32_rssi WiFi RSSI from ESP32",
        "# TYPE xiao_esp32_rssi gauge",
        f"xiao_esp32_rssi {tele.get('rssi', 0)}",
        "# HELP xiao_esp32_heap Free heap on ESP32",
        "# TYPE xiao_esp32_heap gauge",
        f"xiao_esp32_heap {tele.get('heap', 0)}",
        "# HELP xiao_esp32_uptime ESP32 uptime in seconds",
        "# TYPE xiao_esp32_uptime gauge",
        f"xiao_esp32_uptime {tele.get('uptime', 0)}",
        "# HELP xiao_camera_fps Camera capture FPS",
        "# TYPE xiao_camera_fps gauge",
        f"xiao_camera_fps {getattr(camera, 'capture_fps', 0)}",
        "# HELP xiao_python_threads Active Python threads",
        "# TYPE xiao_python_threads gauge",
        f"xiao_python_threads {threading.active_count()}",
        "# HELP xiao_memory_rss Process memory RSS",
        "# TYPE xiao_memory_rss gauge",
    ]
    try:
        import psutil
        proc = psutil.Process(ps)
        lines.append(f"xiao_memory_rss {proc.memory_info().rss}")
    except ImportError:
        lines.append("xiao_memory_rss 0")
    return Response(content="\n".join(lines), media_type="text/plain; charset=utf-8")


# ─── Version & Info ──────────────────────────


@app.get("/api/version")
async def api_version():
    return {
        "version": "2.3.0",
        "name": "ESP32-S3 Edge Intelligence Platform",
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "endpoints": [
            "/health",
            "/api/version",
            "/api/stats",
            "/stream",
            "/snapshot",
            "/telemetry",
            "/scene",
            "/timeline",
            "/stats",
            "/alerts",
            "/heatmap",
            "/dashboard-data",
        ],
    }


# ─── K8s-style Health Probes ─────────────────
_started = False

@app.get("/livez")
async def livez():
    """Liveness probe — always 200 if server is running."""
    return {"status": "alive", "uptime": time.time() - _start_time}


@app.get("/readyz")
async def readyz():
    """Readiness probe — 200 only when all subsystems are initialized."""
    if not _started:
        return JSONResponse(
            status_code=503,
            content={"status": "not_ready", "uptime": time.time() - _start_time},
        )
    esp_ok = esp32 is not None
    cam_ok = camera is not None
    return {
        "status": "ready" if (esp_ok and cam_ok) else "degraded",
        "esp32": esp_ok,
        "camera": cam_ok,
    }


# ─── Health & Status ─────────────────────────


@app.get("/health")
async def health():
    status = {
        "esp32": {"connected": False, "error": None},
        "ollama": {"connected": False, "error": None},
        "model": analyzer.get_model(),
        "interval": analyzer.interval,
    }
    try:
        resp = urllib.request.urlopen(f"{BASE_URL}/telemetry", timeout=3)
        if resp.status == 200:
            status["esp32"]["connected"] = True
    except Exception as e:
        status["esp32"]["error"] = str(e)
    try:
        resp = requests.get(f"{OLLAMA_URL}/api/tags", timeout=3)
        if resp.status_code == 200:
            status["ollama"]["connected"] = True
    except Exception as e:
        status["ollama"]["error"] = str(e)
    return status


@app.get("/api/stats")
async def api_stats():
    return {
        "uptime_seconds": time.time() - _start_time,
        "python_version": sys.version.split()[0],
        "threads": threading.active_count(),
    }


@app.get("/api/config")
async def api_config():
    return {
        "esp32_url": BASE_URL,
        "ollama_url": OLLAMA_URL,
        "ollama_model": OLLAMA_MODEL,
        "analysis_interval": ANALYSIS_INTERVAL,
        "vector_interval": VECTOR_INTERVAL,
        "yolo_confidence": YOLO_CONF,
    }


@app.get("/api/env")
async def api_env():
    relevant = {k: v for k, v in os.environ.items() if any(
        x in k.upper() for x in ["ESP32", "OLLAMA", "YOLO", "PORT", "LOG", "CORS", "RATE", "SHUTDOWN"]
    )}
    return {"env": relevant, "python": sys.version.split()[0]}


@app.post("/api/restart")
async def api_restart():
    async def delayed_restart():
        await asyncio.sleep(1)
        os._exit(0)

    asyncio.create_task(delayed_restart())
    return {"status": "restarting"}


@app.get("/api/camera/resolution")
async def camera_resolution():
    """Returns the current camera resolution info."""
    frame = camera.latest_frame
    if frame is None:
        return {"width": None, "height": None, "has_frame": False}
    arr = cv2.imdecode(np.frombuffer(frame, np.uint8), cv2.IMREAD_COLOR)
    if arr is None:
        return {"width": None, "height": None, "has_frame": False}
    h, w = arr.shape[:2]
    return {"width": w, "height": h, "has_frame": True, "aspect": f"{w}:{h}"}


@app.get("/api/performance")
async def performance_metrics():
    return {
        "fps": round(camera.capture_fps, 1) if hasattr(camera, "capture_fps") else None,
        "buffer_depth": camera.buffer_depth if hasattr(camera, "buffer_depth") else None,
        "frame_id": camera.frame_id if hasattr(camera, "frame_id") else None,
        "camera_uptime": round(camera.uptime, 1) if hasattr(camera, "uptime") else None,
        "analysis_latency": round(analyzer.last_latency, 2)
        if hasattr(analyzer, "last_latency")
        else None,
    }


@app.get("/api/gatekeeper/stats")
async def gatekeeper_stats():
    return {
        "stats": gatekeeper.stats if hasattr(gatekeeper, "stats") else {},
        "ready": gatekeeper.ready,
    }


@app.get("/api/telemetry/latest")
async def telemetry_latest():
    tele = esp32.get_telemetry()
    return {"telemetry": tele}


@app.get("/api/snapshot")
async def api_snapshot():
    frame = camera.latest_frame
    if frame is None:
        return {"error": "no frame available"}
    b64 = base64.b64encode(frame).decode()
    return {"image": b64, "format": "jpeg", "size": len(frame)}


@app.get("/api/events/recent")
async def recent_events(limit: int = 20):
    events = gatekeeper.get_events(limit=limit) if hasattr(gatekeeper, "get_events") else []
    return {"events": events, "total": len(events)}


@app.get("/api/alerts/rules")
async def alert_rules():
    rules = getattr(alert_manager, "rules", [])
    return {"rules": rules, "count": len(rules)}


@app.get("/api/scene/current")
async def scene_current():
    current = getattr(scene_classifier, "current", "unknown")
    return {"scene": current, "updated_at": time.time()}


# ─── Serve Frontend ──────────────────────────


@app.get("/")
async def index():
    with open("src/index.html") as f:
        return HTMLResponse(f.read(), headers={"Cache-Control": "no-cache"})


# ──────────────────────────────────────────────
#  Entrypoint
# ──────────────────────────────────────────────


def _signal_handler(sig, frame):
    log.warning("Signal %s received, stopping...", sig)
    camera.stop()
    analyzer.stop()
    vector_search.stop()
    gatekeeper.stop()
    sys.exit(0)


if __name__ == "__main__":
    import argparse

    import uvicorn

    signal.signal(signal.SIGINT, _signal_handler)
    signal.signal(signal.SIGTERM, _signal_handler)

    _parser = argparse.ArgumentParser(description="ESP32-S3 Edge Intelligence Platform")
    _parser.add_argument(
        "--port", type=int, default=int(os.environ.get("PORT", "8000")), help="Server port"
    )
    _parser.add_argument("--host", type=str, default="0.0.0.0", help="Server host")
    _args, _ = _parser.parse_known_args()

    port = _args.port
    print(f"[startup] Server: http://{_args.host}:{port}")
    print(f"[startup] ESP32_IP env: {os.environ.get('ESP32_IP', '(use config.py)')}")
    uvicorn.run(app, host=_args.host, port=port, reload=False, log_level="info")
