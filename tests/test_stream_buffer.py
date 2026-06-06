"""Tests for StreamBuffer JPEG boundary detection."""

from src.core.stream_buffer import StreamBuffer


class TestStreamBuffer:
    def setup_method(self):
        self.buf = StreamBuffer()

    def test_feed_and_get_single_frame(self):
        data = b"\xff\xd8" + b"x" * 100 + b"\xff\xd9"
        self.buf.feed(data)
        frame = self.buf.get_frame()
        assert frame == b"\xff\xd8" + b"x" * 100 + b"\xff\xd9"

    def test_get_frame_returns_none_when_no_markers(self):
        self.buf.feed(b"no jpeg markers here")
        assert self.buf.get_frame() is None

    def test_get_frame_returns_none_when_only_start(self):
        self.buf.feed(b"\xff\xd8" + b"no end marker")
        assert self.buf.get_frame() is None

    def test_get_frame_returns_none_when_only_end(self):
        self.buf.feed(b"no start marker" + b"\xff\xd9")
        assert self.buf.get_frame() is None

    def test_multiple_frames_in_single_feed(self):
        data = (
            b"\xff\xd8" + b"frame1" + b"\xff\xd9"
            + b"\xff\xd8" + b"frame2" + b"\xff\xd9"
        )
        self.buf.feed(data)
        f1 = self.buf.get_frame()
        assert f1 == b"\xff\xd8" + b"frame1" + b"\xff\xd9"
        f2 = self.buf.get_frame()
        assert f2 == b"\xff\xd8" + b"frame2" + b"\xff\xd9"

    def test_partial_frame_then_complete(self):
        self.buf.feed(b"\xff\xd8" + b"partial")
        assert self.buf.get_frame() is None
        self.buf.feed(b"rest" + b"\xff\xd9")
        frame = self.buf.get_frame()
        assert frame == b"\xff\xd8" + b"partialrest" + b"\xff\xd9"

    def test_corrupt_data_trims_then_returns_valid(self):
        self.buf.feed(b"\xff\xd9" + b"garbage" + b"\xff\xd8" + b"data" + b"\xff\xd9")
        f1 = self.buf.get_frame()
        assert f1 is None
        f2 = self.buf.get_frame()
        assert f2 == b"\xff\xd8" + b"data" + b"\xff\xd9"

    def test_empty_feed(self):
        self.buf.feed(b"")
        assert self.buf.get_frame() is None

    def test_exact_boundaries_preserved(self):
        payload = b"\x01\x02\x03" * 33
        data = b"\xff\xd8" + payload + b"\xff\xd9"
        self.buf.feed(data)
        frame = self.buf.get_frame()
        assert frame[:2] == b"\xff\xd8"
        assert frame[-2:] == b"\xff\xd9"
        assert frame[2:-2] == payload
