"""
ESP32-S3 Edge Intelligence Platform v2.1.0 — FastAPI server with:
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
import subprocess
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
                metrics_history.record(
                    fps=self.camera.capture_fps,
                    latency=self.latency,
                    queue_depth=self.buffer_depth_val,
                    mode=self.mode,
                )
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
        self._stats = {"detections": 0, "triggers": 0, "boss_roasts": 0}
        self._lock = threading.Lock()
        self._cell_phone_since = 0.0
        self._boss_triggered_at = 0.0
        self._object_counter = object_counter
        self._timeline = timeline
        self._alert_manager = alert_manager

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
                    self._cell_phone_since = 0.0
                    self.analyzer.deactivate_boss_mode()
                    continue

                objs = []
                has_cell_phone = False
                for box in dets:
                    cls_id = int(box.cls[0])
                    label = TARGET_CLASSES.get(cls_id, f"class_{cls_id}")
                    conf = float(box.conf[0])
                    objs.append({"class": label, "confidence": round(conf, 3)})
                    if label == "cell phone":
                        has_cell_phone = True

                event = {
                    "frame_id": fid,
                    "time": time.time(),
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "objects": objs,
                }
                with self._lock:
                    self._events.append(event)
                    self._stats["detections"] += 1

                self._object_counter.record(objs)
                self._timeline.record_event("detection", {"objects": objs})
                triggered = self._alert_manager.evaluate(objs)
                for alert_name in triggered:
                    self._timeline.record_event(f"alert_{alert_name}", {"objects": objs})
                    self._stats["triggers"] += 1

                # Boss mode: cell phone detected for > 5 seconds
                now = time.time()
                if has_cell_phone:
                    if self._cell_phone_since == 0.0:
                        self._cell_phone_since = now
                    elapsed = now - self._cell_phone_since
                    if elapsed >= 5.0 and (now - self._boss_triggered_at) > 10:
                        self.analyzer.activate_boss_mode()
                        self.analyzer.trigger_now()
                        self._boss_triggered_at = now
                        last_llm_trigger = now
                        with self._lock:
                            self._stats["boss_roasts"] += 1
                else:
                    self._cell_phone_since = 0.0
                    self.analyzer.deactivate_boss_mode()

                # Trigger heavy LLM if a high-value object appears (person, car, etc.)
                high_value = {"person", "dog", "cat", "car", "laptop", "cell phone"}
                detected_labels = {o["class"] for o in objs}
                if detected_labels & high_value and (now - last_llm_trigger) > 10:
                    self.analyzer.trigger_now()
                    last_llm_trigger = now
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
BOSS_SYSTEM_PROMPT = (
    "You are a toxic, passive-aggressive boss. "
    "The user in this image is looking at their phone instead of coding. "
    "Roast them mercilessly in one short sentence based on what you see."
)
OLLAMA_USER_PROMPT = "What do you see in this camera frame?"


class OllamaAnalyzer:
    def __init__(self, camera: CameraCapture, model: str, interval: float = 5.0):
        self.camera = camera
        self.model = model
        self.interval = interval
        self._last_text = ""
        self._boss_mode = False
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

    def activate_boss_mode(self):
        with self._lock:
            self._boss_mode = True

    def deactivate_boss_mode(self):
        with self._lock:
            self._boss_mode = False

    def is_boss_mode(self) -> bool:
        with self._lock:
            return self._boss_mode

    def _say(self, text: str):
        try:
            subprocess.Popen(
                ["espeak", "-v", "en-us", "-s", "150", "-p", "60", text],
                stderr=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
            )
        except Exception:
            pass

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
                    boss = self._boss_mode
                t0 = time.time()
                payload = {
                    "model": current_model,
                    "system": BOSS_SYSTEM_PROMPT if boss else OLLAMA_SYSTEM_PROMPT,
                    "prompt": OLLAMA_USER_PROMPT if not boss else "Roast them.",
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
                    if boss and text:
                        self._say(text)
            except Exception:
                pass

    def get_result(self) -> str:
        with self._lock:
            return self._last_text

    def get_model(self) -> str:
        with self._lock:
            return self.model

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

camera = CameraCapture(BASE_URL + "/")
analyzer = OllamaAnalyzer(camera=camera, model=OLLAMA_MODEL, interval=ANALYSIS_INTERVAL)
vector_search = VectorSearch(camera=camera, interval=VECTOR_INTERVAL)
gatekeeper = EventGatekeeper(camera=camera, analyzer=analyzer)
controller = AdaptiveController(analyzer=analyzer, camera=camera, esp32=esp32)
scene_classifier = SceneClassifier(camera)
timeline = TimelineEngine()
object_counter = ObjectCounter()
alert_manager = AlertManager()
metrics_history = MetricsHistory()
heatmap = MotionHeatmap(camera)

# ──────────────────────────────────────────────
#  FastAPI Application
# ──────────────────────────────────────────────

app = FastAPI(
    title="ESP32-S3 Edge Intelligence Platform",
    description="Streaming, Vision LLM, semantic search, YOLO gatekeeper, adaptive controller, scene classification, activity timeline, object counting, smart alerts, heatmap",
    version="2.1.0",
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

    _parser = argparse.ArgumentParser(description="ESP32-S3 Edge Intelligence Platform")
    _parser.add_argument("--port", type=int, default=int(os.environ.get("PORT", "8000")), help="Server port")
    _parser.add_argument("--host", type=str, default="0.0.0.0", help="Server host")
    _args, _ = _parser.parse_known_args()

    port = _args.port
    print(f"[startup] Server: http://{_args.host}:{port}")
    print(f"[startup] ESP32_IP env: {os.environ.get('ESP32_IP', '(use config.py)')}")
    uvicorn.run(app, host=_args.host, port=port, reload=False, log_level="info")
