from __future__ import annotations


class StreamBuffer:
    def __init__(self) -> None:
        self._buf: bytes = b""

    def feed(self, data: bytes) -> None:
        self._buf += data

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
