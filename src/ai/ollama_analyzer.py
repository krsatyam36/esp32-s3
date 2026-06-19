"""ollama_analyzer module."""
__all__ = ['OllamaAnalyzer']

from __future__ import annotations

import base64
import os
import subprocess
import threading
import time

import requests

from src.core.camera_capture import CameraCapture

OLLAMA_URL: str = os.environ.get("OLLAMA_URL", "http://localhost:11434")

OLLAMA_SYSTEM_PROMPT: str = os.environ.get(
    "OLLAMA_SYSTEM_PROMPT",
    (
        "You are a real-time camera assistant. "
        "Describe what you see in 1-3 concise sentences. "
        "Focus on objects, people, text, colors, and motion. "
        "Start directly with the description \u2014 no introductory phrases."
    ),
)
BOSS_SYSTEM_PROMPT: str = os.environ.get(
    "BOSS_SYSTEM_PROMPT",
    (
        "You are a toxic, passive-aggressive boss. "
        "The user in this image is looking at their phone instead of coding. "
        "Roast them mercilessly in one short sentence based on what you see."
    ),
)
OLLAMA_USER_PROMPT: str = os.environ.get("OLLAMA_USER_PROMPT", "What do you see in this camera frame?")


class OllamaAnalyzer:
    def __init__(self, camera: CameraCapture, model: str, interval: float = 5.0) -> None:
        self.camera = camera
        self.model = model
        self.interval = interval
        self._last_text: str = ""
        self._boss_mode: bool = False
        self._lock = threading.Lock()
        self._running: bool = False
        self._session = requests.Session()
        self._trigger = threading.Event()
        self.last_latency: float = 0.0

    def start(self) -> None:
        self._running = True
        t = threading.Thread(target=self._loop, daemon=True)
        t.start()

    def stop(self) -> None:
        self._running = False

    def trigger_now(self) -> None:
        self._trigger.set()

    def set_model(self, model: str) -> None:
        with self._lock:
            self.model = model

    def set_interval(self, interval: float) -> None:
        with self._lock:
            self.interval = max(1.0, interval)

    def activate_boss_mode(self) -> None:
        with self._lock:
            self._boss_mode = True

    def deactivate_boss_mode(self) -> None:
        with self._lock:
            self._boss_mode = False

    def is_boss_mode(self) -> bool:
        with self._lock:
            return self._boss_mode

    def _say(self, text: str) -> None:
        try:
            subprocess.Popen(
                ["espeak", "-v", "en-us", "-s", "150", "-p", "60", text],
                stderr=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
            )
        except Exception:
            pass

    def _loop(self) -> None:
        last_frame_id: int = -1
        while self._running:
            forced = self._trigger.wait(timeout=self.interval)
            self._trigger.clear()
            raw = self.camera.latest_frame
            if raw is None:
                continue
            fid = self.camera.frame_id
            if fid == last_frame_id and not forced:
                continue
            last_frame_id = fid
            try:
                b64 = base64.b64encode(raw).decode("utf-8")
                with self._lock:
                    current_model = self.model
                    boss = self._boss_mode
                t0 = time.time()
                payload: dict[str, object] = {
                    "model": current_model,
                    "system": BOSS_SYSTEM_PROMPT if boss else OLLAMA_SYSTEM_PROMPT,
                    "prompt": OLLAMA_USER_PROMPT if not boss else "Roast them.",
                    "images": [b64],
                    "stream": False,
                }
                resp = self._session.post(f"{OLLAMA_URL}/api/generate", json=payload, timeout=30)
                self.last_latency = time.time() - t0
                if resp.status_code == 200:
                    text: str = resp.json().get("response", "").strip()
                    with self._lock:
                        self._last_text = text
                    if boss and text:
                        self._say(text)
            except Exception:
                pass

    def get_result(self) -> str:
        with self._lock:
            return self._last_text

    def get_model(self) -> str:
        with self._lock:
            return self.model
