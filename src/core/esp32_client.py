from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request

from pydantic import BaseModel

try:
    from src.config import ESP32_IP as _IP

    _BASE = _IP.rstrip("/")
except (ImportError, NameError):
    import os

    _BASE = os.environ.get("ESP32_IP", "http://192.168.1.X/").rstrip("/")

BASE_URL = _BASE


class ResValue(BaseModel):
    value: str


class ESP32Client:
    def __init__(self, base_url: str) -> None:
        self.base_url = base_url

    def send_command(self, endpoint: str) -> dict:
        try:
            resp = urllib.request.urlopen(f"{self.base_url}{endpoint}", timeout=5)
            return json.loads(resp.read().decode())
        except Exception as e:
            return {"success": False, "error": str(e)}

    def get_telemetry(self) -> dict:
        return self.send_command("/telemetry")
