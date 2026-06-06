import logging
import os
import threading
import time
from collections import deque
from datetime import datetime, timezone

import cv2
import numpy as np


YOLO_CONF = float(os.environ.get("YOLO_CONFIDENCE", "0.35"))

TARGET_CLASSES = {
    0: "person", 1: "bicycle", 2: "car", 3: "motorcycle", 5: "bus",
    6: "train", 7: "truck", 16: "dog", 17: "cat", 32: "sports ball",
    39: "bottle", 41: "cup", 43: "knife", 44: "spoon", 47: "mouse",
    56: "chair", 57: "couch", 62: "tv", 63: "laptop", 64: "mouse",
    67: "cell phone", 73: "book", 74: "clock", 76: "scissors",
    77: "teddy bear",
}

object_counter = None
timeline = None
alert_manager = None


class EventGatekeeper:
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

    def get_events(self, since: float = 0, limit: int = 50) -> list[dict]:
        with self._lock:
            events = [e for e in self._events if e["time"] >= since]
            return events[-limit:]

    @property
    def stats(self) -> dict:
        with self._lock:
            return {**self._stats, "queue": len(self._events)}
