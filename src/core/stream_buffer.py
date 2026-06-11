from __future__ import annotations

import logging

log = logging.getLogger("stream_buffer")

MAX_BUF_SIZE = 5 * 1024 * 1024  # 5MB


class StreamBuffer:
    def __init__(self, max_size: int = MAX_BUF_SIZE) -> None:
        self._buf: bytes = b""
        self._max_size = max_size
        self._discarded = 0

    def feed(self, data: bytes) -> None:
        self._buf += data
        if len(self._buf) > self._max_size:
            self._discarded += len(self._buf) - self._max_size
            self._buf = self._buf[-self._max_size:]
            log.warning("Buffer overflow: discarded %d bytes", len(self._buf) - self._max_size)

    def get_frame(self) -> bytes | None:
        a = self._buf.find(b"\xff\xd8")
        b = self._buf.find(b"\xff\xd9")
        if a != -1 and b != -1 and b > a:
            jpg = self._buf[a : b + 2]
            self._buf = self._buf[b + 2 :]
            return jpg
        if a != -1 and b != -1 and a > b:
            self._buf = self._buf[a:]
        return None

    @property
    def buffer_size(self) -> int:
        return len(self._buf)

    @property
    def bytes_discarded(self) -> int:
        return self._discarded
