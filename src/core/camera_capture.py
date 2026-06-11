from __future__ import annotations

import http.client
import threading
import time
import urllib.error
import urllib.request
from collections import deque

from src.core.stream_buffer import StreamBuffer


class CameraCapture:
    def __init__(self, stream_url: str) -> None:
        self._url = stream_url
        self._buffer = StreamBuffer()
        self._latest_frame: bytes | None = None
        self._lock = threading.Lock()
        self._running = False
        self._frame_id = 0
        self._frame_timestamps: deque[float] = deque(maxlen=120)
        self._capture_start = 0.0
        self._reconnects = 0
        self._total_errors = 0
        self._last_error_time = 0.0
        self._last_error_msg = ""

    def start(self) -> None:
        self._running = True
        self._capture_start = time.time()
        t = threading.Thread(target=self._capture_loop, daemon=True)
        t.start()

    def stop(self) -> None:
        self._running = False

    @property
    def latest_frame(self) -> bytes | None:
        with self._lock:
            return self._latest_frame

    @property
    def frame_id(self) -> int:
        with self._lock:
            return self._frame_id

    @property
    def buffer_depth(self) -> int:
        with self._lock:
            return len(self._frame_timestamps)

    @property
    def capture_fps(self) -> float:
        with self._lock:
            n = len(self._frame_timestamps)
            if n < 2:
                return 0.0
            return n / (self._frame_timestamps[-1] - self._frame_timestamps[0])

    @property
    def uptime(self) -> float:
        return time.time() - self._capture_start if self._capture_start else 0.0

    @property
    def stats(self) -> dict:
        return {
            "reconnects": self._reconnects,
            "total_errors": self._total_errors,
            "last_error": self._last_error_msg,
            "last_error_time": round(self._last_error_time, 1) if self._last_error_time else 0,
            "buffer_size": self._buffer.buffer_size,
            "discarded_bytes": self._buffer.bytes_discarded,
        }

    def _capture_loop(self) -> None:
        while self._running:
            stream = None
            try:
                stream = urllib.request.urlopen(self._url, timeout=3)
                while self._running:
                    try:
                        data = stream.read(65536)
                        if not data:
                            break
                        self._buffer.feed(data)
                        while True:
                            jpg = self._buffer.get_frame()
                            if jpg is None:
                                break
                            with self._lock:
                                self._latest_frame = jpg
                                self._frame_id += 1
                                self._frame_timestamps.append(time.time())
                    except (
                        TimeoutError,
                        urllib.error.URLError,
                        ConnectionError,
                        http.client.IncompleteRead,
                        http.client.RemoteDisconnected,
                    ):
                        break
                    except Exception:
                        break
            except Exception as e:
                self._total_errors += 1
                self._last_error_time = time.time()
                self._last_error_msg = str(e)
            finally:
                if stream is not None:
                    try:
                        stream.close()
                    except Exception:
                        pass
            self._reconnects += 1
            time.sleep(2)
