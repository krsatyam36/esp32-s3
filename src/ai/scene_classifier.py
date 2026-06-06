from __future__ import annotations

import threading
import time
import typing
from collections import deque

import cv2
import numpy as np

if typing.TYPE_CHECKING:
    from src.core.camera_capture import CameraCapture


SCENE_CATEGORIES = [
    "indoor",
    "outdoor",
    "office",
    "classroom",
    "laboratory",
    "kitchen",
    "living_room",
    "street",
    "parking_lot",
    "nature",
    "night",
    "day",
    "low_light",
    "bright",
    "crowded",
    "empty",
    "workshop",
    "server_room",
    "warehouse",
    "corridor",
]


class SceneClassifier:
    def __init__(self, camera: CameraCapture) -> None:
        self.camera = camera
        self._current_scene: str = "unknown"
        self._scene_history: deque[dict[str, object]] = deque(maxlen=100)
        self._lock = threading.Lock()
        self._last_analysis: float = 0.0
        self._interval: float = 5.0

    def start(self) -> None:
        t = threading.Thread(target=self._loop, daemon=True)
        t.start()

    def _loop(self) -> None:
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
                            self._scene_history.append(
                                {
                                    "time": time.time(),
                                    "scene": scene,
                                }
                            )
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
    def history(self) -> list[dict[str, object]]:
        with self._lock:
            return list(self._scene_history)
