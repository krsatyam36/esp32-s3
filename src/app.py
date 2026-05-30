"""
ESP32-S3 Edge Intelligence Platform — FastAPI server with:
  • MJPEG streaming                    • Vision LLM via Ollama
  • Semantic video search (CLIP+ChromaDB)   • YOLO event gatekeeper
  • Adaptive rate controller                • SSE/health/control

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
import threading
import time
import urllib.request
import urllib.error
import http.client
import socket
from datetime import datetime, timezone
from collections import deque

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
VECTOR_INTERVAL = float(os.environ.get("VECTOR_INTERVAL", "10"))
YOLO_CONF = float(os.environ.get("YOLO_CONFIDENCE", "0.35"))

# ──────────────────────────────────────────────
#  ESP32 HTTP Client
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
#  MJPEG Stream Buffer
# ──────────────────────────────────────────────

class StreamBuffer:
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
    def __init__(self, stream_url: str):
        self._url = stream_url
        self._buffer = StreamBuffer()
        self._latest_frame: bytes | None = None
        self._lock = threading.Lock()
        self._running = False
        self._frame_id = 0
        self._frame_timestamps: deque = deque(maxlen=120)
        self._capture_start = 0.0

    def start(self):
        self._running = True
        self._capture_start = time.time()
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

    @property
    def buffer_depth(self) -> int:
        with self._lock:
            return len(self._frame_timestamps)

    @property
    def capture_fps(self) -> float:
        with self._lock:
            n = len(self._frame_timestamps)
            if n < 2:
                return 0.0
            return n / (self._frame_timestamps[-1] - self._frame_timestamps[0])

    @property
    def uptime(self) -> float:
        return time.time() - self._capture_start if self._capture_start else 0.0

    def _capture_loop(self):
        while self._running:
            stream = None
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
                                self._frame_timestamps.append(time.time())
                    except (urllib.error.URLError, ConnectionError,
                            http.client.IncompleteRead, http.client.RemoteDisconnected,
                            socket.timeout):
                        break
                    except Exception:
                        break
            except Exception:
                pass
            finally:
                if stream is not None:
                    try:
                        stream.close()
                    except Exception:
                        pass
            time.sleep(2)

# ──────────────────────────────────────────────
#  Adaptive Rate Controller
# ──────────────────────────────────────────────

class AdaptiveController:
    """Monitors system metrics and autonomously adjusts resolution,
    analysis interval, and model selection to prevent pipeline stalls."""

    MODE_NORMAL = "normal"
    MODE_THROTTLED = "throttled"
    MODE_EMERGENCY = "emergency"

    def __init__(self, analyzer, camera, esp32):
        self.analyzer = analyzer
        self.camera = camera
        self.esp32 = esp32
        self.mode = self.MODE_NORMAL
        self._lock = threading.Lock()
        self._running = False
        self._history = deque(maxlen=60)

        # thresholds
        self.rssi_throttle = -70
        self.rssi_emergency = -85
        self.latency_throttle = 15.0
        self.latency_emergency = 30.0
        self.buffer_depth_throttle = 15
        self.buffer_depth_emergency = 30

        # current metrics (updated each cycle)
        self.rssi = 0
        self.latency = 0.0
        self.buffer_depth_val = 0
        self.last_action = ""

    def start(self):
        self._running = True
        t = threading.Thread(target=self._loop, daemon=True)
        t.start()

    def stop(self):
        self._running = False

    def _loop(self):
        last_res_check = 0.0
        while self._running:
            try:
                # Read telemetry
                tele = esp32.get_telemetry()
                rssi_str = tele.get("rssi", "0")
                self.rssi = int(rssi_str) if isinstance(rssi_str, (int, str)) and str(rssi_str).lstrip("-").isdigit() else 0
                self.buffer_depth_val = self.camera.buffer_depth
                self.latency = self.analyzer.last_latency

                if self.rssi > self.rssi_throttle and self.latency < self.latency_throttle and self.buffer_depth_val < self.buffer_depth_throttle:
                    target = self.MODE_NORMAL
                elif self.rssi < self.rssi_emergency or self.latency > self.latency_emergency or self.buffer_depth_val > self.buffer_depth_emergency:
                    target = self.MODE_EMERGENCY
                else:
                    target = self.MODE_THROTTLED

                if target != self.mode:
                    self.mode = target
                    if target == self.MODE_NORMAL:
                        self.analyzer.set_interval(ANALYSIS_INTERVAL)
                        if time.time() - last_res_check > 15:
                            self.esp32.send_command("/res?val=UXGA")
                            last_res_check = time.time()
                        self.last_action = "UXGA + normal interval"
                    elif target == self.MODE_THROTTLED:
                        self.analyzer.set_interval(min(self.analyzer.interval + 2, 20))
                        self.last_action = f"interval={self.analyzer.interval:.0f}s"
                    else:
                        self.analyzer.set_interval(30)
                        self.esp32.send_command("/res?val=SVGA")
                        last_res_check = time.time()
                        self.last_action = "SVGA + 30s interval"

                self._history.append({
                    "time": time.time(),
                    "mode": self.mode,
                    "rssi": self.rssi,
                    "latency": self.latency,
                    "buffer_depth": self.buffer_depth_val,
                })
            except Exception:
                pass
            time.sleep(3)

    @property
    def summary(self) -> dict:
        return {
            "mode": self.mode,
            "rssi": self.rssi,
            "latency": round(self.latency, 1),
            "buffer_depth": self.buffer_depth_val,
            "last_action": self.last_action,
            "history": list(self._history),
        }

# ──────────────────────────────────────────────
#  Feature 1: Semantic Video Search (CLIP + ChromaDB)
# ──────────────────────────────────────────────

class VectorSearch:
    """CLIP-based embedding + ChromaDB for natural-language video search.
    Gracefully degrades if dependencies are missing."""

    def __init__(self, camera, interval=10.0):
        self.camera = camera
        self.interval = interval
        self.collection = None
        self._encoder = None
        self._model_name = None
        self.ready = False
        self.error = ""
        self._running = False
        self._lock = threading.Lock()
        self._index_count = 0

        try:
            import chromadb
            self._chroma = chromadb.Client(
                chromadb.Settings(anonymized_telemetry=False, is_persistent=True, persist_directory="./chroma_db")
            )
            self.collection = self._chroma.get_or_create_collection("frames")
            self._ready_chroma = True
        except Exception as e:
            self._ready_chroma = False
            self.error = f"ChromaDB init failed: {e}"

    def _load_encoder(self):
        if self._encoder is not None:
            return True
        try:
            from sentence_transformers import SentenceTransformer
            import torch
            self._model_name = "clip-ViT-B-32"
            self._encoder = SentenceTransformer(self._model_name)
            self.ready = True
            return True
        except Exception as e:
            self.error = f"CLIP load failed: {e}"
            return False

    def _encode_image(self, frame_bytes) -> list[float] | None:
        if not self._load_encoder():
            return None
        try:
            arr = np.frombuffer(frame_bytes, dtype=np.uint8)
            img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
            if img is None:
                return None
            rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
            emb = self._encoder.encode(rgb)
            return emb.tolist()
        except Exception:
            return None

    def _encode_text(self, text: str) -> list[float] | None:
        if not self._load_encoder():
            return None
        try:
            emb = self._encoder.encode(text)
            return emb.tolist()
        except Exception:
            return None

    def start(self):
        if not self._ready_chroma:
            return
        self._running = True
        t = threading.Thread(target=self._loop, daemon=True)
        t.start()

    def stop(self):
        self._running = False

    def _loop(self):
        last_id = -1
        while self._running:
            fid = self.camera.frame_id
            raw = self.camera.latest_frame
            if raw is not None and fid != last_id:
                last_id = fid
                emb = self._encode_image(raw)
                if emb is not None:
                    ts = datetime.now(timezone.utc).isoformat()
                    try:
                        self.collection.add(
                            embeddings=[emb],
                            ids=[f"fid_{fid}"],
                            metadatas=[{"frame_id": fid, "timestamp": ts}],
                        )
                        with self._lock:
                            self._index_count += 1
                    except Exception:
                        pass
            time.sleep(self.interval)

    def search(self, query: str, top_k: int = 5) -> list[dict]:
        if not self.ready or not self._ready_chroma:
            return []
        text_emb = self._encode_text(query)
        if text_emb is None:
            return []
        try:
            results = self.collection.query(
                query_embeddings=[text_emb],
                n_results=min(top_k, self._index_count or 1),
            )
            hits = []
            if results.get("ids") and results["ids"][0]:
                for i, fid in enumerate(results["ids"][0]):
                    meta = (results.get("metadatas") or [{}])[0].get(i, {}) if isinstance(results.get("metadatas"), list) else {}
                    dist = (results.get("distances") or [[]])[0][i] if results.get("distances") else 0
                    hits.append({
                        "frame_id": meta.get("frame_id", fid),
                        "timestamp": meta.get("timestamp", ""),
                        "score": round(1.0 - float(dist), 4),
                    })
            return hits
        except Exception:
            return []

    @property
    def info(self) -> dict:
        return {
            "ready": self.ready,
            "chroma_ok": self._ready_chroma,
            "index_count": self._index_count,
            "error": self.error,
        }

# ──────────────────────────────────────────────
#  Feature 2: Event Gatekeeper (YOLOv8-nano)
# ──────────────────────────────────────────────

TARGET_CLASSES = {
    0: "person", 1: "bicycle", 2: "car", 3: "motorcycle", 5: "bus",
    6: "train", 7: "truck", 16: "dog", 17: "cat", 32: "sports ball",
    39: "bottle", 41: "cup", 43: "knife", 44: "spoon", 47: "mouse",
    56: "chair", 57: "couch", 62: "tv", 63: "laptop", 64: "mouse",
    67: "cell phone", 73: "book", 74: "clock", 76: "scissors",
    77: "teddy bear",
}


class EventGatekeeper:
    """YOLOv8-nano gatekeeper running at high speed.
    Detects objects and fires events + optionally triggers the heavy LLM."""

    def __init__(self, camera, analyzer):
        self.camera = camera
        self.analyzer = analyzer
        self.model = None
        self.ready = False
        self.error = ""
        self._running = False
        self._events = deque(maxlen=200)
        self._stats = {"detections": 0, "triggers": 0}
        self._lock = threading.Lock()

        try:
            from ultralytics import YOLO
            self.model = YOLO("yolov8n.pt")
            self.ready = True
        except Exception as e:
            self.error = f"YOLO load failed: {e}"

    def start(self):
        if not self.ready:
            return
        self._running = True
        t = threading.Thread(target=self._loop, daemon=True)
        t.start()

    def stop(self):
        self._running = False

    def _loop(self):
        last_id = -1
        last_llm_trigger = 0.0
        while self._running:
            fid = self.camera.frame_id
            raw = self.camera.latest_frame
            if raw is None or fid == last_id:
                time.sleep(0.05)
                continue
            last_id = fid

            try:
                arr = np.frombuffer(raw, dtype=np.uint8)
                img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
                if img is None:
                    continue
                results = self.model(img, verbose=False, conf=YOLO_CONF)
                dets = results[0].boxes
                if dets is None or len(dets) == 0:
                    continue

                objs = []
                for box in dets:
                    cls_id = int(box.cls[0])
                    label = TARGET_CLASSES.get(cls_id, f"class_{cls_id}")
                    conf = float(box.conf[0])
                    objs.append({"class": label, "confidence": round(conf, 3)})

                event = {
                    "frame_id": fid,
                    "time": time.time(),
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "objects": objs,
                }
                with self._lock:
                    self._events.append(event)
                    self._stats["detections"] += 1

                # Trigger heavy LLM if a high-value object appears (person, car, etc.)
                high_value = {"person", "dog", "cat", "car", "laptop", "cell phone"}
                detected_labels = {o["class"] for o in objs}
                if detected_labels & high_value and (time.time() - last_llm_trigger) > 10:
                    self.analyzer.trigger_now()
                    last_llm_trigger = time.time()
                    with self._lock:
                        self._stats["triggers"] += 1
            except Exception:
                pass

    def get_events(self, since: float = 0, limit: int = 50) -> list[dict]:
        with self._lock:
            events = [e for e in self._events if e["time"] >= since]
            return events[-limit:]

    @property
    def stats(self) -> dict:
        with self._lock:
            return {**self._stats, "queue": len(self._events)}

# ──────────────────────────────────────────────
#  Ollama Vision Analyzer
# ──────────────────────────────────────────────

OLLAMA_SYSTEM_PROMPT = (
    "You are a real-time camera assistant. "
    "Describe what you see in 1-3 concise sentences. "
    "Focus on objects, people, text, colors, and motion. "
    "Start directly with the description — no introductory phrases."
)
OLLAMA_USER_PROMPT = "What do you see in this camera frame?"


class OllamaAnalyzer:
    def __init__(self, camera: CameraCapture, model: str, interval: float = 5.0):
        self.camera = camera
        self.model = model
        self.interval = interval
        self._last_text = ""
        self._lock = threading.Lock()
        self._running = False
        self._session = requests.Session()
        self._trigger = threading.Event()
        self.last_latency = 0.0

    def start(self):
        self._running = True
        t = threading.Thread(target=self._loop, daemon=True)
        t.start()

    def stop(self):
        self._running = False

    def trigger_now(self):
        self._trigger.set()

    def set_model(self, model: str):
        with self._lock:
            self.model = model

    def set_interval(self, interval: float):
        with self._lock:
            self.interval = max(1.0, interval)

    def _loop(self):
        last_frame_id = -1
        while self._running:
            forced = self._trigger.wait(timeout=self.interval)
            self._trigger.clear()
            raw = self.camera.latest_frame
            if raw is None:
                continue
            fid = self.camera.frame_id
            if fid == last_frame_id and not forced:
                continue
            last_frame_id = fid
            try:
                b64 = base64.b64encode(raw).decode("utf-8")
                with self._lock:
                    current_model = self.model
                t0 = time.time()
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
                self.last_latency = time.time() - t0
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
#  Global Instances
# ──────────────────────────────────────────────

camera = CameraCapture(BASE_URL + "/")
analyzer = OllamaAnalyzer(camera=camera, model=OLLAMA_MODEL, interval=ANALYSIS_INTERVAL)
vector_search = VectorSearch(camera=camera, interval=VECTOR_INTERVAL)
gatekeeper = EventGatekeeper(camera=camera, analyzer=analyzer)
controller = AdaptiveController(analyzer=analyzer, camera=camera, esp32=esp32)

# ──────────────────────────────────────────────
#  FastAPI Application
# ──────────────────────────────────────────────

app = FastAPI(
    title="ESP32-S3 Edge Intelligence Platform",
    description="Streaming, Vision LLM, semantic search, event gatekeeper, adaptive controller",
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
    print(f"[startup] ESP32: {BASE_URL}")
    camera.start()
    analyzer.start()
    vector_search.start()
    gatekeeper.start()
    controller.start()
    if vector_search.ready:
        print(f"[startup] Vector search ready — {vector_search.info['encoder']}")
    if gatekeeper.ready:
        print(f"[startup] YOLO gatekeeper ready")
    print(f"[startup] Dashboard at http://localhost:8000")


@app.on_event("shutdown")
async def shutdown():
    camera.stop()
    analyzer.stop()
    vector_search.stop()
    gatekeeper.stop()
    controller.stop()


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
                yield f"data: {json.dumps({'text': text, 'model': analyzer.get_model()})}\n\n"
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
class ResValue(BaseModel): value: str

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
    port = int(os.environ.get("PORT", "8000"))
    uvicorn.run(app, host="0.0.0.0", port=port, reload=False, log_level="info")
