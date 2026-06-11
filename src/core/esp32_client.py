from __future__ import annotations

import json
import time
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

MAX_RETRIES = int(os.environ.get("ESP32_MAX_RETRIES", "3"))
RETRY_DELAY = float(os.environ.get("ESP32_RETRY_DELAY", "1.0"))


class ResValue(BaseModel):
    value: str


class ESP32Client:
    def __init__(self, base_url: str) -> None:
        self.base_url = base_url
        self._last_request_time: float = 0.0

    def send_command(self, endpoint: str, retries: int = MAX_RETRIES) -> dict:
        last_error = ""
        for attempt in range(retries):
            try:
                resp = urllib.request.urlopen(
                    f"{self.base_url}{endpoint}", timeout=5
                )
                self._last_request_time = time.time()
                return json.loads(resp.read().decode())
            except Exception as e:
                last_error = str(e)
                if attempt < retries - 1:
                    time.sleep(RETRY_DELAY * (2 ** attempt))
        return {"success": False, "error": last_error}

    def get_telemetry(self) -> dict:
        return self.send_command("/telemetry")
