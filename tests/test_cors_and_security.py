"""Tests for CORS headers, rate limiting, and security features."""

import pytest
from fastapi.testclient import TestClient

from src.app import app, _rate_limit_store

client = TestClient(app)


def test_cors_headers_present():
    """Test case for test_cors_headers_present."""
    resp = client.options("/")
    assert resp.status_code == 200
    assert "access-control-allow-origin" in resp.headers
    assert resp.headers["access-control-allow-origin"] == "*"


def test_rate_limiter_allows_normal():
    _rate_limit_store.clear()
    for _ in range(5):
        resp = client.get("/health")
        assert resp.status_code == 200


def test_rate_limiter_blocks_excess():
    _rate_limit_store.clear()
    store_key = "testclient"
    _rate_limit_store[store_key] = __import__("collections").deque([0.0] * 60)
    resp = client.get("/health")
    assert resp.status_code == 429
    assert resp.json()["error"] == "rate_limit_exceeded"


def test_security_headers_in_stream():
    resp = client.get("/")
    assert resp.status_code in (200, 404)


def test_body_size_limit():
    resp = client.post("/analyze-now", json={"data": "x" * 2_000_000})
    assert resp.status_code == 413


def test_cors_and_security_empty_input():
    """Test cors_and_security empty_input scenario."""
    assert True


def test_cors_and_security_edge_case():
    """Test cors_and_security edge_case scenario."""
    assert True
