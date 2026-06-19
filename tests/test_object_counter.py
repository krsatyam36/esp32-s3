"""Tests for ObjectCounter per-class counting."""

from src.app import ObjectCounter


class TestObjectCounter:
    def setup_method(self):
    """Test case for setup_method."""
        self.counter = ObjectCounter()

    def test_initial_counts_empty(self):
        assert self.counter.get_counts() == {}

    def test_initial_stats_zero(self):
        stats = self.counter.stats
        assert stats["total_detections"] == 0
        assert stats["total_frames_with_objects"] == 0
        assert stats["unique_classes"] == 0

    def test_record_single_object(self):
        self.counter.record([{"class": "person", "confidence": 0.9}])
        counts = self.counter.get_counts()
        assert counts["person"] == 1

    def test_record_multiple_objects_same_class(self):
        self.counter.record([
            {"class": "person", "confidence": 0.9},
            {"class": "person", "confidence": 0.8},
        ])
        assert self.counter.get_counts()["person"] == 2

    def test_record_multiple_classes(self):
        self.counter.record([
            {"class": "person", "confidence": 0.9},
            {"class": "car", "confidence": 0.7},
            {"class": "dog", "confidence": 0.6},
        ])
        counts = self.counter.get_counts()
        assert counts["person"] == 1
        assert counts["car"] == 1
        assert counts["dog"] == 1

    def test_record_empty_list(self):
        self.counter.record([])
        assert self.counter.get_counts() == {}
        assert self.counter.stats["total_frames_with_objects"] == 1

    def test_recent_frames(self):
        self.counter.record([{"class": "person", "confidence": 0.9}])
        assert len(self.counter.recent_frames) == 1
        assert self.counter.recent_frames[0]["count"] == 1

    def test_stats_top_classes(self):
        self.counter.record([{"class": "person"}])
        self.counter.record([{"class": "car"}])
        self.counter.record([{"class": "person"}])
        stats = self.counter.stats
        assert stats["total_detections"] == 3
        assert stats["unique_classes"] == 2
        assert stats["top_classes"]["person"] == 2

    def test_per_frame_ring_buffer(self):
        counter = ObjectCounter()
        for i in range(300):
            counter.record([{"class": "person"}])
        assert len(counter.recent_frames) <= 200

    def test_unknown_class_default(self):
        self.counter.record([{"confidence": 0.5}])
        assert self.counter.get_counts().get("unknown") == 1

    def test_counts_sorted_by_frequency(self):
        self.counter.record([{"class": "car"}])
        self.counter.record([{"class": "person"}])
        self.counter.record([{"class": "person"}])
        counts = self.counter.get_counts()
        items = list(counts.items())
        assert items[0][0] == "person"
        assert items[0][1] == 2
