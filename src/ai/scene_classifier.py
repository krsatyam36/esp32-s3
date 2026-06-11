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
        self._current_confidence: float = 0.0
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
                        scene, confidence = self._classify(img)
                        with self._lock:
                            self._current_scene = scene
                            self._current_confidence = confidence
                            self._scene_history.append(
                                {
                                    "time": time.time(),
                                    "scene": scene,
                                    "confidence": confidence,
                                }
                            )
                except Exception:
                    pass
            time.sleep(1)

    def _classify(self, img: np.ndarray) -> tuple[str, float]:
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
        scores: list[tuple[str, float]] = []
        if mean_brightness < 40 and std_brightness < 20:
            scores.append(("night", 0.9))
        else:
            scores.append(("night", max(0, 0.9 - (mean_brightness - 40) / 200)))
        if mean_brightness > 200 and std_brightness < 15:
            scores.append(("bright", 0.9))
        else:
            scores.append(("bright", max(0, 0.9 - (255 - mean_brightness) / 200)))
        if mean_brightness < 60:
            scores.append(("low_light", 0.85))
        else:
            scores.append(("low_light", max(0, 0.85 - (mean_brightness - 60) / 200)))
        if edge_density > 0.15 and laplacian_var > 200:
            if saturation_pixels > 0.3:
                scores.append(("crowded", 0.8))
            else:
                scores.append(("workshop", 0.7))
        else:
            scores.append(("crowded", min(0.8, edge_density * 2)))
            scores.append(("workshop", min(0.7, laplacian_var / 500)))
        if saturation_pixels > 0.4 and mean_sat > 80:
            scores.append(("outdoor", 0.75))
        else:
            scores.append(("outdoor", max(0, saturation_pixels * 0.8)))
        if edge_density < 0.05 and laplacian_var < 50:
            scores.append(("empty", 0.8))
        green_channel = img[:, :, 1].mean()
        blue_channel = img[:, :, 0].mean()
        if green_channel > blue_channel * 1.15 and green_channel > 60:
            scores.append(("nature", 0.8))
        else:
            scores.append(("nature", max(0, (green_channel - blue_channel) / 255)))
        if mean_hue < 30 or mean_hue > 150:
            scores.append(("indoor", 0.7 if edge_density > 0.08 else 0.4))
        else:
            scores.append(("indoor", 0.3))
        scores.append(("day", min(0.9, mean_brightness / 255)))
        best = max(scores, key=lambda x: x[1])
        return best[0], round(best[1], 2)

    @property
    def current(self) -> str:
        with self._lock:
            return self._current_scene

    @property
    def confidence(self) -> float:
        with self._lock:
            return self._current_confidence

    @property
    def history(self) -> list[dict[str, object]]:
        with self._lock:
            return list(self._scene_history)
