"""Tests for timeline export and extended functionality."""

from datetime import datetime, timezone

import pytest

from src.ai.timeline_engine import TimelineEngine


@pytest.fixture
def timeline():
    return TimelineEngine()


def test_timeline_init(timeline):
    assert timeline.get_timeline() == []
    assert timeline.summary["total_events"] == 0


def test_timeline_add_event(timeline):
    timeline.add_event("person", confidence=0.9)
    entries = timeline.get_timeline()
    assert len(entries) == 1
    assert entries[0]["class_name"] == "person"
    assert entries[0]["confidence"] == 0.9


def test_timeline_multiple_events(timeline):
    for cls in ["person", "car", "dog"]:
        timeline.add_event(cls, confidence=0.8)
    entries = timeline.get_timeline()
    assert len(entries) == 3
    assert timeline.summary["total_events"] == 3


def test_timeline_active_events(timeline):
    timeline.add_event("person", confidence=0.9)
    timeline.add_event("car", confidence=0.7)
    active = timeline.get_active_events()
    assert isinstance(active, list)


def test_timeline_summary(timeline):
    timeline.add_event("person", confidence=0.9)
    timeline.add_event("person", confidence=0.8)
    timeline.add_event("car", confidence=0.7)
    summary = timeline.summary
    assert summary["total_events"] == 3
    assert summary.get("class_breakdown", {}).get("person", 0) == 2


def test_timeline_export(timeline):
    timeline.add_event("person", confidence=0.95)
    timeline.add_event("car", confidence=0.85)
    entries = timeline.get_timeline(limit=500)
    assert len(entries) == 2


def test_timeline_filter_by_time(timeline):
    timeline.add_event("person", confidence=0.9)
    import time
    future = time.time() + 1000
    entries = timeline.get_timeline(since=future)
    assert len(entries) == 0
