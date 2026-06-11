"""Tests for api_utils endpoints."""

from fastapi.testclient import TestClient

from src.api_utils import router
from src.app import app

app.include_router(router)
client = TestClient(app)


def test_ping_endpoint():
    resp = client.get("/api/ping")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "pong"
    assert "timestamp" in data


def test_env_endpoint():
    resp = client.get("/api/env")
    assert resp.status_code == 200
    data = resp.json()
    assert "environment" in data


def test_system_endpoint():
    resp = client.get("/api/system")
    assert resp.status_code == 200
    data = resp.json()
    assert "platform" in data
    assert "hostname" in data


def test_disk_endpoint():
    resp = client.get("/api/disk")
    assert resp.status_code == 200
    data = resp.json()
    assert any(k in data for k in ("total_bytes", "info"))


def test_dependencies_endpoint():
    resp = client.get("/api/dependencies")
    assert resp.status_code == 200
    data = resp.json()
    assert "dependencies" in data
    deps = data["dependencies"]
    assert "cv2" in deps
    assert "fastapi" in deps
    assert "numpy" in deps
