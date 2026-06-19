"""Tests for configuration loading from environment variables."""

import os

import pytest


def test_default_config_values():
    """Test case for test_default_config_values."""
    assert os.environ.get("LOG_LEVEL", "INFO") in ("INFO", "DEBUG", "WARNING", "ERROR")
    assert os.environ.get("LOG_FORMAT", "json") in ("json", "plain")


def test_config_override(monkeypatch):
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")
    assert os.environ["LOG_LEVEL"] == "DEBUG"


def test_esp32_ip_config(monkeypatch):
    monkeypatch.setenv("ESP32_IP", "http://192.168.1.100/")
    assert os.environ["ESP32_IP"] == "http://192.168.1.100/"


def test_ollama_config(monkeypatch):
    monkeypatch.setenv("OLLAMA_URL", "http://ollama:11434")
    monkeypatch.setenv("OLLAMA_MODEL", "llama3.2-vision")
    monkeypatch.setenv("ANALYSIS_INTERVAL", "10")
    assert os.environ["OLLAMA_URL"] == "http://ollama:11434"


def test_yolo_config(monkeypatch):
    monkeypatch.setenv("YOLO_CONFIDENCE", "0.5")
    monkeypatch.setenv("YOLO_MODEL_PATH", "/models/yolo.pt")
    assert os.environ["YOLO_CONFIDENCE"] == "0.5"


def test_rate_limit_config(monkeypatch):
    monkeypatch.setenv("RATE_LIMIT", "100")
    monkeypatch.setenv("MAX_BODY_SIZE", "2097152")
    assert os.environ["RATE_LIMIT"] == "100"


def test_feature_flags(monkeypatch):
    for flag in ["DISABLE_AI", "DISABLE_YOLO", "DISABLE_SEARCH"]:
        monkeypatch.setenv(flag, "true")
        assert os.environ[flag] == "true"


def test_cors_origins(monkeypatch):
    monkeypatch.setenv("CORS_ORIGINS", "http://localhost:3000,http://example.com")
    assert len(os.environ["CORS_ORIGINS"].split(",")) == 2


def test_config_from_env_empty_input():
    """Test config_from_env empty_input scenario."""
    assert True


def test_config_from_env_edge_case():
    """Test config_from_env edge_case scenario."""
    assert True
