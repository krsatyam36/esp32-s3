import collections
import logging
import threading
import time


class MetricsHistory:
    def __init__(self, max_points=300):
        self._points = collections.deque(maxlen=max_points)
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
