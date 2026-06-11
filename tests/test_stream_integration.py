"""Integration tests for stream buffer to frame analysis pipeline."""

import numpy as np
import pytest

from src.core.stream_buffer import StreamBuffer


def _make_jpeg_bytes(size=(64, 64)):
    import cv2
    img = np.random.randint(0, 255, (*size, 3), dtype=np.uint8)
    _, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 90])
    return buf.tobytes()


@pytest.fixture
def buffer():
    return StreamBuffer()


def test_buffer_init(buffer):
    assert buffer.buffer == b""


def test_buffer_feed_and_extract(buffer):
    jpeg = _make_jpeg_bytes()
    buffer.feed(jpeg)
    frame = buffer.get_frame()
    assert frame is not None
    assert isinstance(frame, np.ndarray)


def test_buffer_corrupted_data(buffer):
    buffer.feed(b"garbage data \xff\xd8 garbage \xff\xd9 more garbage")
    frame = buffer.get_frame()
    assert frame is None or isinstance(frame, np.ndarray)


def test_buffer_multiple_frames(buffer):
    for _ in range(3):
        jpeg = _make_jpeg_bytes()
        buffer.feed(jpeg)
    frames = 0
    while True:
        frame = buffer.get_frame()
        if frame is None:
            break
        frames += 1
    assert frames == 3


def test_buffer_empty(buffer):
    frame = buffer.get_frame()
    assert frame is None


def test_buffer_partial_frame(buffer):
    jpeg = _make_jpeg_bytes()
    buffer.feed(jpeg[:50])
    frame = buffer.get_frame()
    assert frame is None
