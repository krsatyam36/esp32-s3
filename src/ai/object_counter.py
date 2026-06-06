from __future__ import annotations

import collections
import threading
import time


class ObjectCounter:
    def __init__(self) -> None:
        self._counts: dict[str, int] = {}
        self._per_frame: collections.deque[dict[str, object]] = collections.deque(maxlen=200)
        self._lock = threading.Lock()
        self._total_detections: int = 0
        self._total_frames_with_objects: int = 0

    def record(self, objects: list[dict[str, object]]) -> None:
        with self._lock:
            self._total_detections += len(objects)
            self._total_frames_with_objects += 1
            for obj in objects:
                label: str = str(obj.get("class", "unknown"))
                self._counts[label] = self._counts.get(label, 0) + 1
            self._per_frame.append(
                {
                    "time": time.time(),
                    "count": len(objects),
                    "objects": objects,
                }
            )

    def get_counts(self) -> dict[str, int]:
        with self._lock:
            return dict(sorted(self._counts.items(), key=lambda x: -x[1]))

    @property
    def stats(self) -> dict[str, object]:
        with self._lock:
            return {
                "total_detections": self._total_detections,
                "total_frames_with_objects": self._total_frames_with_objects,
                "unique_classes": len(self._counts),
                "top_classes": dict(sorted(self._counts.items(), key=lambda x: -x[1])[:10]),
            }

    @property
    def recent_frames(self) -> list[dict[str, object]]:
        with self._lock:
            return list(self._per_frame)
