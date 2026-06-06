"""Tests for /scene, /timeline, /stats, /heatmap, /alerts, /dashboard-data."""

from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient


class TestSceneEndpoint:
    def test_scene_returns_current_and_history(self):
        from src.app import app, scene_classifier
        client = TestClient(app)
        resp = client.get("/scene")
        data = resp.json()
        assert "current" in data
        assert "history" in data

    def test_scene_status_code(self):
        from src.app import app
        client = TestClient(app)
        resp = client.get("/scene")
        assert resp.status_code == 200


class TestTimelineEndpoint:
    def test_timeline_returns_entries(self):
        from src.app import app, timeline
        client = TestClient(app)
        timeline.record_event("test_event")
        resp = client.get("/timeline")
        data = resp.json()
        assert "entries" in data
        assert "active" in data
        assert "summary" in data

    def test_timeline_status_code(self):
        from src.app import app
        client = TestClient(app)
        resp = client.get("/timeline")
        assert resp.status_code == 200


class TestStatsEndpoint:
    def test_stats_returns_counts(self):
        from src.app import app, object_counter
        object_counter.record([{"class": "person", "confidence": 0.9}])
        client = TestClient(app)
        resp = client.get("/stats")
        data = resp.json()
        assert "counts" in data
        assert "stats" in data
        assert "recent" in data
        assert data["counts"].get("person") == 1

    def test_stats_status_code(self):
        from src.app import app
        client = TestClient(app)
        resp = client.get("/stats")
        assert resp.status_code == 200


class TestHeatmapEndpoint:
    def test_heatmap_returns_none_when_empty(self):
        from src.app import app
        client = TestClient(app)
        resp = client.get("/heatmap")
        data = resp.json()
        assert data["heatmap"] is None

    def test_heatmap_reset(self):
        from src.app import app
        client = TestClient(app)
        resp = client.post("/heatmap/reset")
        assert resp.status_code == 200
        assert resp.json()["success"] is True


class TestAlertsEndpoint:
    def test_alerts_returns_rules_and_history(self):
        from src.app import app
        client = TestClient(app)
        resp = client.get("/alerts")
        data = resp.json()
        assert "rules" in data
        assert "history" in data
        assert "stats" in data

    def test_alerts_create_rule(self):
        from src.app import app
        client = TestClient(app)
        resp = client.post("/alerts", json={
            "name": "laptop_detected",
            "class_name": "laptop",
            "min_confidence": 0.5,
        })
        assert resp.status_code == 200
        assert resp.json()["success"] is True

    def test_alerts_update_rule(self):
        from src.app import app
        client = TestClient(app)
        resp = client.put("/alerts/0", json={
            "name": "updated_rule",
            "class_name": "cat",
            "min_confidence": 0.8,
        })
        assert resp.status_code == 200

    def test_alerts_delete_rule(self):
        from src.app import app
        client = TestClient(app)
        resp = client.delete("/alerts/0")
        assert resp.status_code == 200

    def test_alerts_history(self):
        from src.app import app
        client = TestClient(app)
        resp = client.get("/alerts/history")
        assert resp.status_code == 200
        assert "history" in resp.json()

    def test_alerts_delete_invalid_index(self):
        from src.app import app
        client = TestClient(app)
        resp = client.delete("/alerts/999")
        assert resp.json()["success"] is False


class TestDashboardDataEndpoint:
    def test_dashboard_data_has_all_keys(self):
        with patch("src.app.esp32.get_telemetry") as mock_tele:
            mock_tele.return_value = {"rssi": "-65", "heap": "123456"}
            from src.app import app
            client = TestClient(app)
            resp = client.get("/dashboard-data")
            data = resp.json()
            assert "telemetry" in data
            assert "scene" in data
            assert "adaptive" in data
            assert "gatekeeper" in data
            assert "metrics" in data
            assert "alerts" in data

    def test_dashboard_data_status_code(self):
        with patch("src.app.esp32.get_telemetry") as mock_tele:
            mock_tele.return_value = {"rssi": "-65"}
            from src.app import app
            client = TestClient(app)
            resp = client.get("/dashboard-data")
            assert resp.status_code == 200


class TestSystemStatusEndpoint:
    def test_system_status_has_all_sections(self):
        from src.app import app
        client = TestClient(app)
        resp = client.get("/system-status")
        data = resp.json()
        assert "adaptive" in data
        assert "camera" in data
        assert "analyzer" in data
        assert "vector_search" in data
        assert "gatekeeper" in data
        assert "scene" in data
        assert "metrics" in data
        assert "alerts" in data

    def test_system_status_status_code(self):
        from src.app import app
        client = TestClient(app)
        resp = client.get("/system-status")
        assert resp.status_code == 200
