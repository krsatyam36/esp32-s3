from __future__ import annotations

import os
import threading
import time
import typing
from collections import deque
from datetime import UTC, datetime

import cv2
import numpy as np

if typing.TYPE_CHECKING:
    from src.ai.object_counter import ObjectCounter
    from src.ai.ollama_analyzer import OllamaAnalyzer
    from src.ai.smart_alert import AlertManager
    from src.ai.timeline_engine import TimelineEngine
    from src.core.camera_capture import CameraCapture


YOLO_CONF = float(os.environ.get("YOLO_CONFIDENCE", "0.35"))
YOLO_SKIP = int(os.environ.get("YOLO_FRAME_SKIP", "0"))
YOLO_MODEL_PATH = os.environ.get("YOLO_MODEL_PATH", "yolov8n.pt")

TARGET_CLASSES: dict[int, str] = {
    0: "person",
    1: "bicycle",
    2: "car",
    3: "motorcycle",
    5: "bus",
    6: "train",
    7: "truck",
    16: "dog",
    17: "cat",
    32: "sports ball",
    39: "bottle",
    41: "cup",
    43: "knife",
    44: "spoon",
    47: "mouse",
    56: "chair",
    57: "couch",
    62: "tv",
    63: "laptop",
    64: "mouse",
    67: "cell phone",
    73: "book",
    74: "clock",
    76: "scissors",
    77: "teddy bear",
}

object_counter: ObjectCounter | None = None
timeline: TimelineEngine | None = None
alert_manager: AlertManager | None = None


class EventGatekeeper:
    def __init__(self, camera: CameraCapture, analyzer: OllamaAnalyzer) -> None:
        self.camera = camera
        self.analyzer = analyzer
        self.model: typing.Any = None
        self.ready: bool = False
        self.error: str = ""
        self._running: bool = False
        self._events: deque[dict[str, object]] = deque(maxlen=200)
        self._stats: dict[str, int] = {"detections": 0, "triggers": 0, "boss_roasts": 0}
        self._lock = threading.Lock()
        self._cell_phone_since: float = 0.0
        self._boss_triggered_at: float = 0.0
        self._object_counter = object_counter
        self._timeline = timeline
        self._alert_manager = alert_manager
        try:
            from ultralytics import YOLO

            self.model = YOLO(YOLO_MODEL_PATH)
            self.ready = True
        except Exception as e:
            self.error = f"YOLO load failed: {e}"

    def start(self) -> None:
        if not self.ready:
            return
        self._running = True
        t = threading.Thread(target=self._loop, daemon=True)
        t.start()

    def stop(self) -> None:
        self._running = False

    def _loop(self) -> None:
        last_id: int = -1
        last_llm_trigger: float = 0.0
        _frame_counter = 0
        while self._running:
            fid = self.camera.frame_id
            raw = self.camera.latest_frame
            if raw is None or fid == last_id:
                time.sleep(0.05)
                continue
            last_id = fid
            _frame_counter += 1
            if YOLO_SKIP > 0 and (_frame_counter % (YOLO_SKIP + 1)) != 0:
                continue
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
                    "timestamp": datetime.now(UTC).isoformat(),
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
                high_value = {"person", "dog", "cat", "car", "laptop", "cell phone"}
                detected_labels = {o["class"] for o in objs}
                if detected_labels & high_value and (now - last_llm_trigger) > 10:
                    self.analyzer.trigger_now()
                    last_llm_trigger = now
                    with self._lock:
                        self._stats["triggers"] += 1
            except Exception:
                pass

    def get_events(self, since: float = 0, limit: int = 50) -> list[dict[str, object]]:
        with self._lock:
            events = [e for e in self._events if e["time"] >= since]
            return list(events)[-limit:]

    @property
    def stats(self) -> dict[str, object]:
        with self._lock:
            return {**self._stats, "queue": len(self._events)}
