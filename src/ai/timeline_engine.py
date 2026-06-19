"""timeline_engine module."""
__all__ = ['TimelineEngine']

from __future__ import annotations

import collections
import os
import threading
import time
from datetime import UTC, datetime, timezone, timedelta


class TimelineEngine:
    def __init__(self, max_entries: int = 500) -> None:
        self._entries: collections.deque[dict[str, object]] = collections.deque(maxlen=max_entries)
        self._active_events: dict[str, float] = {}
        self._lock = threading.Lock()
        tz_offset = int(os.environ.get("TZ_OFFSET", "0"))
        self._tz = timezone(timedelta(hours=tz_offset)) if tz_offset else UTC

    def record_event(self, event_type: str, metadata: dict[str, object] | None = None) -> None:
        with self._lock:
            now = time.time()
            self._entries.append(
                {
                    "type": event_type,
                    "time": now,
                    "timestamp": datetime.now(self._tz).isoformat(),
                    "metadata": metadata or {},
                }
            )
            if event_type not in ("object_left", "object_left_frame"):
                self._active_events[event_type] = now

    def end_event(self, event_type: str) -> None:
        with self._lock:
            if event_type in self._active_events:
                duration = time.time() - self._active_events.pop(event_type)
                self._entries.append(
                    {
                        "type": f"{event_type}_ended",
                        "time": time.time(),
                        "timestamp": datetime.now(UTC).isoformat(),
                        "metadata": {"duration": round(duration, 1)},
                    }
                )

    def get_timeline(self, since: float = 0, limit: int = 50) -> list[dict[str, object]]:
        with self._lock:
            entries = [e for e in self._entries if e["time"] >= since]
            return list(entries)[-limit:]

    def get_active_events(self) -> dict[str, float]:
        with self._lock:
            now = time.time()
            return {k: round(now - v, 1) for k, v in self._active_events.items()}

    @property
    def summary(self) -> dict[str, object]:
        with self._lock:
            counts: dict[str, int] = {}
            for e in self._entries:
                t: str = e["type"]  # type: ignore[assignment]
                counts[t] = counts.get(t, 0) + 1
            return {
                "total_entries": len(self._entries),
                "active_events": len(self._active_events),
                "type_counts": counts,
            }
