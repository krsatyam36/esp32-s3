from __future__ import annotations

import base64 as b64
import io
import logging
import threading
import time

import cv2
import numpy as np

import typing

if typing.TYPE_CHECKING:
    from src.core.camera_capture import CameraCapture


class MotionHeatmap:
    def __init__(self, camera: CameraCapture, decay: float = 0.95) -> None:
        self.camera = camera
        self.decay = decay
        self._heatmap: np.ndarray | None = None
        self._lock = threading.Lock()
        self._running = False
        self._prev_gray: np.ndarray | None = None

    def start(self) -> None:
        self._running = True
        t = threading.Thread(target=self._loop, daemon=True)
        t.start()

    def stop(self) -> None:
        self._running = False

    def _loop(self) -> None:
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
            import base64 as _b64
            return _b64.b64encode(buffer).decode("utf-8")

    def reset(self) -> None:
        with self._lock:
            self._heatmap = None
            self._prev_gray = None
