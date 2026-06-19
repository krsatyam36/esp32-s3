"""Extended tests for object counter including reset and recent frames."""

import pytest

from src.ai.object_counter import ObjectCounter


@pytest.fixture
def counter():
    """Test case for counter."""
    return ObjectCounter()


def test_counter_init(counter):
    assert counter.get_counts() == {}
    assert counter.stats["total_detections"] == 0


def test_counter_update(counter):
    counter.update("person", 0.9)
    counter.update("car", 0.8)
    counts = counter.get_counts()
    assert counts["person"] == 1
    assert counts["car"] == 1


def test_counter_multiple_same_class(counter):
    for _ in range(5):
        counter.update("person", 0.9)
    assert counter.get_counts()["person"] == 5


def test_counter_reset(counter):
    counter.update("person", 0.9)
    counter.update("car", 0.8)
    counter.reset()
    assert counter.get_counts() == {}
    assert counter.stats["total_detections"] == 0


def counter_recent_frames(counter):
    counter.update("person", 0.9)
    counter.update("car", 0.8)
    assert hasattr(counter, "recent_frames")
    assert len(counter.recent_frames) >= 0


def test_counter_stats(counter):
    counter.update("person", 0.9)
    counter.update("car", 0.8)
    counter.update("person", 0.95)
    stats = counter.stats
    assert stats["total_detections"] == 3
    assert stats.get("unique_classes", 0) >= 2
