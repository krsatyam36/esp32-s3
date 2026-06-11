from __future__ import annotations

import os
import threading
import time
import typing
from collections import deque
from enum import Enum

if typing.TYPE_CHECKING:
    from src.ai.ollama_analyzer import OllamaAnalyzer
    from src.core.camera_capture import CameraCapture
    from src.core.esp32_client import ESP32Client
    from src.core.metrics_history import MetricsHistory


ANALYSIS_INTERVAL = float(os.environ.get("ANALYSIS_INTERVAL", "5"))
RSSI_THROTTLE = int(os.environ.get("RSSI_THROTTLE", "-70"))
RSSI_EMERGENCY = int(os.environ.get("RSSI_EMERGENCY", "-85"))
LATENCY_THROTTLE = float(os.environ.get("LATENCY_THROTTLE", "15.0"))
LATENCY_EMERGENCY = float(os.environ.get("LATENCY_EMERGENCY", "30.0"))
BUFFER_DEPTH_THROTTLE = int(os.environ.get("BUFFER_DEPTH_THROTTLE", "15"))
BUFFER_DEPTH_EMERGENCY = int(os.environ.get("BUFFER_DEPTH_EMERGENCY", "30"))
metrics_history: MetricsHistory | None = None


class ControllerMode(Enum):
    NORMAL = "normal"
    THROTTLED = "throttled"
    EMERGENCY = "emergency"


class AdaptiveController:
    MODE_NORMAL: str = ControllerMode.NORMAL.value
    MODE_THROTTLED: str = ControllerMode.THROTTLED.value
    MODE_EMERGENCY: str = ControllerMode.EMERGENCY.value

    def __init__(
        self,
        analyzer: OllamaAnalyzer,
        camera: CameraCapture,
        esp32: ESP32Client,
    ) -> None:
        self.analyzer = analyzer
        self.camera = camera
        self.esp32 = esp32
        self.mode: str = self.MODE_NORMAL
        self._lock = threading.Lock()
        self._running = False
        self._history: deque[dict[str, object]] = deque(maxlen=60)
        self.rssi_throttle: int = RSSI_THROTTLE
        self.rssi_emergency: int = RSSI_EMERGENCY
        self.latency_throttle: float = LATENCY_THROTTLE
        self.latency_emergency: float = LATENCY_EMERGENCY
        self.buffer_depth_throttle: int = BUFFER_DEPTH_THROTTLE
        self.buffer_depth_emergency: int = BUFFER_DEPTH_EMERGENCY
        self.rssi: int = 0
        self.latency: float = 0.0
        self.buffer_depth_val: int = 0
        self.last_action: str = ""

    def start(self) -> None:
        self._running = True
        t = threading.Thread(target=self._loop, daemon=True)
        t.start()

    def stop(self) -> None:
        self._running = False

    def _loop(self) -> None:
        last_res_check = 0.0
        while self._running:
            try:
                tele = self.esp32.get_telemetry()
                rssi_str = tele.get("rssi", "0")
                self.rssi = (
                    int(rssi_str)
                    if isinstance(rssi_str, (int, str)) and str(rssi_str).lstrip("-").isdigit()
                    else 0
                )
                self.buffer_depth_val = self.camera.buffer_depth
                self.latency = self.analyzer.last_latency
                if (
                    self.rssi > self.rssi_throttle
                    and self.latency < self.latency_throttle
                    and self.buffer_depth_val < self.buffer_depth_throttle
                ):
                    target = self.MODE_NORMAL
                elif (
                    self.rssi < self.rssi_emergency
                    or self.latency > self.latency_emergency
                    or self.buffer_depth_val > self.buffer_depth_emergency
                ):
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
                self._history.append(
                    {
                        "time": time.time(),
                        "mode": self.mode,
                        "rssi": self.rssi,
                        "latency": self.latency,
                        "buffer_depth": self.buffer_depth_val,
                    }
                )
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
