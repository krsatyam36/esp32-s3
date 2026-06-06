"""Tests for TimelineEngine activity tracking."""

import time
from src.app import TimelineEngine


class TestTimelineEngine:
    def setup_method(self):
        self.timeline = TimelineEngine(max_entries=100)

    def test_record_event_adds_entry(self):
        self.timeline.record_event("detection", {"objects": [{"class": "person"}]})
        entries = self.timeline.get_timeline()
        assert len(entries) == 1
        assert entries[0]["type"] == "detection"
        assert entries[0]["metadata"]["objects"][0]["class"] == "person"

    def test_record_event_sets_active(self):
        self.timeline.record_event("person_detected")
        active = self.timeline.get_active_events()
        assert "person_detected" in active

    def test_end_event_removes_active(self):
        self.timeline.record_event("person_detected")
        self.timeline.end_event("person_detected")
        active = self.timeline.get_active_events()
        assert "person_detected" not in active

    def test_end_event_adds_ended_entry(self):
        self.timeline.record_event("motion")
        self.timeline.end_event("motion")
        entries = self.timeline.get_timeline()
        types = [e["type"] for e in entries]
        assert "motion_ended" in types

    def test_summary_counts(self):
        self.timeline.record_event("detection")
        self.timeline.record_event("detection")
        self.timeline.record_event("alert_person")
        summary = self.timeline.summary
        assert summary["total_entries"] == 3
        assert summary["type_counts"]["detection"] == 2
        assert summary["type_counts"]["alert_person"] == 1

    def test_since_filter(self):
        old = time.time() - 100
        self.timeline._entries.clear()
        self.timeline._entries.append({
            "type": "old", "time": old,
            "timestamp": "", "metadata": {},
        })
        self.timeline.record_event("new")
        entries = self.timeline.get_timeline(since=time.time() - 10)
        assert len(entries) == 1
        assert entries[0]["type"] == "new"

    def test_limit(self):
        for i in range(20):
            self.timeline.record_event(f"ev_{i}")
        entries = self.timeline.get_timeline(limit=5)
        assert len(entries) == 5

    def test_active_event_duration(self):
        self.timeline.record_event("active_one")
        import time as tmod
        active = self.timeline.get_active_events()
        assert "active_one" in active
        assert active["active_one"] >= 0.0

    def test_summary_active_count(self):
        self.timeline.record_event("ev1")
        self.timeline.record_event("ev2")
        summary = self.timeline.summary
        assert summary["active_events"] == 2

    def test_object_left_not_active(self):
        self.timeline.record_event("object_left")
        active = self.timeline.get_active_events()
        assert "object_left" not in active

    def test_object_left_frame_not_active(self):
        self.timeline.record_event("object_left_frame")
        active = self.timeline.get_active_events()
        assert "object_left_frame" not in active

    def test_end_event_unknown_does_not_raise(self):
        self.timeline.end_event("nonexistent")
        assert True

    def test_max_entries_ring_buffer(self):
        tl = TimelineEngine(max_entries=10)
        for i in range(20):
            tl.record_event(f"ev_{i}")
        assert len(tl._entries) == 10
        assert tl._entries[0]["type"] == "ev_10"
