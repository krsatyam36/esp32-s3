"""Extended tests for motion heatmap including persistence."""

import tempfile
from pathlib import Path

import cv2
import numpy as np
import pytest

from src.ai.motion_heatmap import MotionHeatmap


class DummyCamera:
    latest_frame = None
    capture_fps = 15.0


@pytest.fixture
def heatmap():
    cam = DummyCamera()
    hm = MotionHeatmap(cam)
    hm.width = 320
    hm.height = 240
    return hm


def test_heatmap_init(heatmap):
    assert heatmap.map is not None
    assert heatmap.map.shape == (240, 320)


def test_heatmap_update(heatmap):
    frame = np.zeros((240, 320, 3), dtype=np.uint8)
    frame[50:100, 50:100] = 255
    heatmap.update(frame)
    assert heatmap.map.sum() > 0


def test_heatmap_reset(heatmap):
    heatmap.map[:, :] = 255
    heatmap.reset()
    assert heatmap.map.sum() == 0


def test_heatmap_get_heatmap(heatmap):
    result = heatmap.get_heatmap()
    assert result is None or isinstance(result, str)


def test_heatmap_persistence():
    with tempfile.TemporaryDirectory() as tmp:
        cam = DummyCamera()
        hm = MotionHeatmap(cam, heatmap_file=str(Path(tmp) / "heatmap.npy"))
        hm.width = 160
        hm.height = 120
        frame = np.random.randint(0, 256, (120, 160, 3), dtype=np.uint8)
        hm.update(frame)
        hm.save()
        assert (Path(tmp) / "heatmap.npy").exists()
        hm2 = MotionHeatmap(cam, heatmap_file=str(Path(tmp) / "heatmap.npy"))
        hm2.load()
        assert hm2.map is not None
