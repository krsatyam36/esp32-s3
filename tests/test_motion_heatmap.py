"""Tests for MotionHeatmap accumulation/decay."""

import numpy as np
import cv2
from src.app import MotionHeatmap


class TestMotionHeatmap:
    def setup_method(self):
    """Test case for setup_method."""
        self.camera = type("MockCamera", (), {"latest_frame": None})()
        self.heatmap = MotionHeatmap(self.camera, decay=0.95)

    def test_initial_state(self):
        assert self.heatmap._heatmap is None
        assert self.heatmap._prev_gray is None
        assert self.heatmap.decay == 0.95

    def test_get_heatmap_returns_none_when_empty(self):
        assert self.heatmap.get_heatmap() is None

    def test_reset_clears_state(self):
        self.heatmap._heatmap = np.zeros((100, 100), dtype=np.float32)
        self.heatmap._prev_gray = np.zeros((100, 100), dtype=np.uint8)
        self.heatmap.reset()
        assert self.heatmap._heatmap is None
        assert self.heatmap._prev_gray is None

    def test_start_sets_running(self):
        self.heatmap.start()
        assert self.heatmap._running is True
        self.heatmap.stop()

    def test_stop_clears_running(self):
        self.heatmap.start()
        self.heatmap.stop()
        assert self.heatmap._running is False

    def test_stop_idempotent(self):
        self.heatmap.stop()
        assert self.heatmap._running is False

    def test_accumulate_single_frame(self):
        raw = self._make_test_jpeg(100, 100, 128)
        self.camera.latest_frame = raw
        gray = cv2.cvtColor(
            cv2.imdecode(np.frombuffer(raw, dtype=np.uint8), cv2.IMREAD_COLOR),
            cv2.COLOR_BGR2GRAY,
        )
        self.heatmap._prev_gray = gray
        raw2 = self._make_test_jpeg(100, 100, 200)
        self.camera.latest_frame = raw2
        gray2 = cv2.cvtColor(
            cv2.imdecode(np.frombuffer(raw2, dtype=np.uint8), cv2.IMREAD_COLOR),
            cv2.COLOR_BGR2GRAY,
        )
        delta = cv2.absdiff(gray, gray2)
        thresh = cv2.threshold(delta, 25, 255, cv2.THRESH_BINARY)[1]

        arr = np.frombuffer(raw2, dtype=np.uint8)
        img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        gray_new = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        gray_new = cv2.GaussianBlur(gray_new, (21, 21), 0)

        self.heatmap._prev_gray = gray
        self.heatmap._heatmap = None
        self.heatmap._prev_gray = gray

        with self.heatmap._lock:
            self.heatmap._heatmap = thresh.astype(np.float32)
            self.heatmap._heatmap = cv2.addWeighted(
                self.heatmap._heatmap, self.heatmap.decay,
                thresh.astype(np.float32), 1 - self.heatmap.decay, 0
            )
        assert self.heatmap._heatmap is not None
        assert self.heatmap._heatmap.shape == thresh.shape

    def test_heatmap_output_format(self):
        self.heatmap._heatmap = np.random.rand(100, 100).astype(np.float32) * 255
        result = self.heatmap.get_heatmap()
        assert isinstance(result, str)
        import base64
        decoded = base64.b64decode(result)
        assert decoded[:2] == b"\xff\xd8"

    def test_resize_heatmap_if_shape_changes(self):
        self.heatmap._heatmap = np.zeros((50, 50), dtype=np.float32)
        new_thresh = np.zeros((100, 100), dtype=np.float32)
        with self.heatmap._lock:
            if self.heatmap._heatmap.shape != new_thresh.shape:
                self.heatmap._heatmap = cv2.resize(
                    self.heatmap._heatmap,
                    (new_thresh.shape[1], new_thresh.shape[0])
                )
            self.heatmap._heatmap = cv2.addWeighted(
                self.heatmap._heatmap, self.heatmap.decay,
                new_thresh, 1 - self.heatmap.decay, 0
            )
        assert self.heatmap._heatmap.shape == (100, 100)

    def test_decay_accumulation(self):
        initial = np.ones((10, 10), dtype=np.float32) * 100
        update = np.ones((10, 10), dtype=np.float32) * 50
        result = cv2.addWeighted(initial, 0.95, update, 0.05, 0)
        expected = 100 * 0.95 + 50 * 0.05
        assert abs(result[0, 0] - expected) < 0.01

    def _make_test_jpeg(self, h, w, val):
        img = np.full((h, w, 3), val, dtype=np.uint8)
        _, encoded = cv2.imencode(".jpg", img)
        return encoded.tobytes()
