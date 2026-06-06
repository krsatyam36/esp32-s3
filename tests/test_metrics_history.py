"""Tests for MetricsHistory ring buffer."""

import time
from src.app import MetricsHistory


class TestMetricsHistory:
    def setup_method(self):
        self.metrics = MetricsHistory(max_points=50)

    def test_record_adds_point(self):
        self.metrics.record(fps=30.0, latency=0.5, queue_depth=5, mode="normal")
        series = self.metrics.get_series(metric="all")
        assert len(series) == 1
        assert series[0]["fps"] == 30.0
        assert series[0]["latency"] == 0.5
        assert series[0]["mode"] == "normal"

    def test_get_series_fps(self):
        self.metrics.record(fps=25.0, latency=0.3, queue_depth=3, mode="normal")
        self.metrics.record(fps=30.0, latency=0.4, queue_depth=4, mode="normal")
        series = self.metrics.get_series(metric="fps", limit=10)
        assert len(series) == 2
        assert series[0]["v"] == 25.0
        assert series[1]["v"] == 30.0

    def test_get_series_latency(self):
        self.metrics.record(fps=25.0, latency=0.3, queue_depth=3, mode="normal")
        series = self.metrics.get_series(metric="latency", limit=10)
        assert series[0]["v"] == 0.3

    def test_get_series_queue_depth(self):
        self.metrics.record(fps=25.0, latency=0.3, queue_depth=7, mode="normal")
        series = self.metrics.get_series(metric="queue_depth", limit=10)
        assert series[0]["v"] == 7

    def test_summary_empty(self):
        assert self.metrics.summary == {}

    def test_summary_with_data(self):
        self.metrics.record(fps=30.0, latency=0.5, queue_depth=5, mode="normal")
        self.metrics.record(fps=20.0, latency=0.8, queue_depth=8, mode="throttled")
        summary = self.metrics.summary
        assert summary["points"] == 2
        assert summary["fps_avg"] == 25.0
        assert summary["fps_min"] == 20.0
        assert summary["fps_max"] == 30.0
        assert summary["latency_avg"] == 0.65
        assert summary["latency_max"] == 0.8

    def test_ring_buffer_max_points(self):
        metrics = MetricsHistory(max_points=10)
        for i in range(20):
            metrics.record(fps=float(i), latency=0.1, queue_depth=1, mode="normal")
        series = metrics.get_series(metric="all")
        assert len(series) == 10

    def test_limit_parameter(self):
        for i in range(20):
            self.metrics.record(fps=float(i), latency=0.1, queue_depth=1, mode="normal")
        series = self.metrics.get_series(metric="all", limit=5)
        assert len(series) == 5

    def test_timestamps_present(self):
        self.metrics.record(fps=30.0, latency=0.5, queue_depth=5, mode="normal")
        self.metrics.record(fps=31.0, latency=0.4, queue_depth=4, mode="normal")
        series = self.metrics.get_series(metric="all")
        assert len(series) == 2
        assert "t" in series[0]
        assert "t" in series[1]
        assert series[0]["t"] >= 0
        assert series[1]["t"] >= 0

    def test_get_series_all_returns_full_dicts(self):
        self.metrics.record(fps=30.0, latency=0.5, queue_depth=5, mode="normal")
        series = self.metrics.get_series(metric="all")
        assert "fps" in series[0]
        assert "latency" in series[0]
        assert "queue_depth" in series[0]
        assert "mode" in series[0]
        assert "t" in series[0]

    def test_unknown_metric_returns_zero(self):
        self.metrics.record(fps=30.0, latency=0.5, queue_depth=5, mode="normal")
        series = self.metrics.get_series(metric="nonexistent")
        assert series[0]["v"] == 0
