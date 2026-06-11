from __future__ import annotations

import collections
import threading
import time


class MetricsHistory:
    def __init__(self, max_points: int = 300) -> None:
        self._points: collections.deque[dict[str, object]] = collections.deque(maxlen=max_points)
        self._lock = threading.Lock()
        self._start_time: float = time.time()

    def record(self, fps: float, latency: float, queue_depth: int, mode: str):
        with self._lock:
            self._points.append(
                {
                    "time": time.time(),
                    "t": round(time.time() - self._start_time, 1),
                    "fps": round(fps, 1),
                    "latency": round(latency, 2),
                    "queue_depth": queue_depth,
                    "mode": mode,
                }
            )

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
            fps_vals = sorted([p["fps"] for p in pts])
            lat_vals = sorted([p["latency"] for p in pts])
            n_fps = len(fps_vals)
            n_lat = len(lat_vals)
            def percentile(vals, p):
                if not vals:
                    return 0
                k = max(0, min(len(vals) - 1, int(len(vals) * p / 100)))
                return vals[k]
            return {
                "points": len(pts),
                "fps_avg": round(sum(fps_vals) / n_fps, 1) if fps_vals else 0,
                "fps_min": min(fps_vals) if fps_vals else 0,
                "fps_max": max(fps_vals) if fps_vals else 0,
                "fps_p50": round(percentile(fps_vals, 50), 1),
                "fps_p95": round(percentile(fps_vals, 95), 1),
                "fps_p99": round(percentile(fps_vals, 99), 1),
                "latency_avg": round(sum(lat_vals) / n_lat, 2) if lat_vals else 0,
                "latency_max": max(lat_vals) if lat_vals else 0,
                "latency_p50": round(percentile(lat_vals, 50), 2),
                "latency_p95": round(percentile(lat_vals, 95), 2),
                "latency_p99": round(percentile(lat_vals, 99), 2),
                "uptime": round(time.time() - self._start_time, 1),
            }
