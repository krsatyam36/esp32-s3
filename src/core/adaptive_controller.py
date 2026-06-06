import logging
import os
import threading
import time
from collections import deque
from enum import Enum


ANALYSIS_INTERVAL = float(os.environ.get("ANALYSIS_INTERVAL", "5"))
metrics_history = None


class ControllerMode(Enum):
    NORMAL = "normal"
    THROTTLED = "throttled"
    EMERGENCY = "emergency"


class AdaptiveController:
    MODE_NORMAL = ControllerMode.NORMAL.value
    MODE_THROTTLED = ControllerMode.THROTTLED.value
    MODE_EMERGENCY = ControllerMode.EMERGENCY.value

    def __init__(self, analyzer, camera, esp32):
        self.analyzer = analyzer
        self.camera = camera
        self.esp32 = esp32
        self.mode = self.MODE_NORMAL
        self._lock = threading.Lock()
        self._running = False
        self._history = deque(maxlen=60)
        self.rssi_throttle = -70
        self.rssi_emergency = -85
        self.latency_throttle = 15.0
        self.latency_emergency = 30.0
        self.buffer_depth_throttle = 15
        self.buffer_depth_emergency = 30
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
                tele = self.esp32.get_telemetry()
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
