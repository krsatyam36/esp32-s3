"""
ESP32-S3 Edge Intelligence Platform v2.0.0 — FastAPI server with:
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

import asyncio
import base64
import json
import math
import os
import platform
import subprocess
import threading
import time
import urllib.request
import urllib.error
import http.client
import socket
import sys
from datetime import datetime, timezone
from collections import deque

import cv2
import numpy as np
import requests
import uuid

from fastapi import FastAPI, Request, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import StreamingResponse, HTMLResponse, JSONResponse
from pydantic import BaseModel

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
from src.core.esp32_client import ESP32Client, ResValue
from src.core.camera_capture import CameraCapture
from src.core.adaptive_controller import AdaptiveController
from src.core.metrics_history import MetricsHistory
from src.ai.scene_classifier import SceneClassifier
from src.ai.timeline_engine import TimelineEngine
from src.ai.object_counter import ObjectCounter
from src.ai.smart_alert import AlertRule, AlertManager
from src.ai.motion_heatmap import MotionHeatmap
from src.ai.vector_search import VectorSearch
from src.ai.event_gatekeeper import EventGatekeeper
from src.ai.ollama_analyzer import OllamaAnalyzer

esp32 = ESP32Client(BASE_URL)


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
    version="2.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(GZipMiddleware, minimum_size=1000)


@app.middleware("http")
async def add_request_id(request: Request, call_next):
    request_id = str(uuid.uuid4())[:8]
    start = time.time()
    response = await call_next(request)
    elapsed = time.time() - start
    response.headers["X-Request-ID"] = request_id
    response.headers["X-Response-Time"] = f"{elapsed*1000:.0f}ms"
    return response


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    return JSONResponse(
        status_code=500,
        content={"error": str(exc), "path": str(request.url.path)},
        headers={"X-Request-ID": str(uuid.uuid4())[:8]},
    )


@app.on_event("startup")
async def startup():
    print(f"[startup] ESP32: {BASE_URL}")
    print(f"[startup] Ollama: {OLLAMA_URL} ({OLLAMA_MODEL})")
    camera.start()
    analyzer.start()
    vector_search.start()
    gatekeeper.start()
    controller.start()
    scene_classifier.start()
    heatmap.start()
    if vector_search.ready:
        print(f"[startup] Vector search ready")
    if gatekeeper.ready:
        print(f"[startup] YOLO gatekeeper ready")
    print(f"[startup] Scene classifier active")
    print(f"[startup] Motion heatmap active")
    print(f"[startup] Dashboard at http://localhost:8000")


@app.on_event("shutdown")
async def shutdown():
    camera.stop()
    analyzer.stop()
    vector_search.stop()
    gatekeeper.stop()
    controller.stop()
    heatmap.stop()


# ─── MJPEG Video Stream ───────────────────────

@app.get("/stream")
async def video_stream():
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
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
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

class LedState(BaseModel): state: str

@app.post("/led")
async def set_led(body: LedState):
    return esp32.send_command(f"/led?state={body.state}")

@app.post("/flash")
async def flash_led(count: int = Query(5, ge=1, le=20)):
    return esp32.send_command(f"/flash?count={count}")

@app.post("/res")
async def set_resolution(body: ResValue):
    return esp32.send_command(f"/res?val={body.value}")

class FlipMode(BaseModel): mode: str

@app.post("/flip")
async def set_flip(body: FlipMode):
    """Flip camera: mode 'v' for vertical, 'h' for horizontal."""
    return esp32.send_command(f"/flip?mode={body.mode}")

@app.get("/telemetry")
async def get_telemetry():
    return esp32.get_telemetry()


# ─── Model & Analysis Control ────────────────

class ModelSelect(BaseModel): model: str
class IntervalSelect(BaseModel): interval: float

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

class SearchQuery(BaseModel): q: str

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


# ─── Feature 6: Object Counting ──────────────

@app.get("/stats")
async def get_stats():
    return {
        "counts": object_counter.get_counts(),
        "stats": object_counter.stats,
        "recent": object_counter.recent_frames[-10:],
    }


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


@app.delete("/alerts/{idx}")
async def delete_alert(idx: int):
    ok = alert_manager.remove_rule(idx)
    return {"success": ok}


@app.get("/alerts/history")
async def get_alert_history(limit: int = Query(50), since: float = Query(0)):
    return {"history": alert_manager.get_history(since=since, limit=limit)}


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


# ─── Version & Info ──────────────────────────

@app.get("/api/version")
async def api_version():
    return {
        "version": "2.0.0",
        "name": "ESP32-S3 Edge Intelligence Platform",
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "endpoints": [
            "/health", "/api/version", "/api/stats",
            "/stream", "/snapshot", "/telemetry",
            "/scene", "/timeline", "/stats",
            "/alerts", "/heatmap", "/dashboard-data",
        ],
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
        "analysis_latency": round(analyzer.last_latency, 2) if hasattr(analyzer, "last_latency") else None,
    }


@app.get("/api/gatekeeper/stats")
async def gatekeeper_stats():
    return {"stats": gatekeeper.stats if hasattr(gatekeeper, "stats") else {}, "ready": gatekeeper.ready}


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
    with open("src/index.html", "r") as f:
        return HTMLResponse(f.read(), headers={"Cache-Control": "no-cache"})


# ──────────────────────────────────────────────
#  Entrypoint
# ──────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn

    _parser = argparse.ArgumentParser(description="ESP32-S3 Edge Intelligence Platform")
    _parser.add_argument("--port", type=int, default=int(os.environ.get("PORT", "8000")), help="Server port")
    _parser.add_argument("--host", type=str, default="0.0.0.0", help="Server host")
    _args, _ = _parser.parse_known_args()

    port = _args.port
    print(f"[startup] Server: http://{_args.host}:{port}")
    print(f"[startup] ESP32_IP env: {os.environ.get('ESP32_IP', '(use config.py)')}")
    uvicorn.run(app, host=_args.host, port=port, reload=False, log_level="info")
