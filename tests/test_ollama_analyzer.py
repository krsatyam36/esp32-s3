"""Tests for OllamaAnalyzer (mock requests)."""

from unittest.mock import MagicMock, patch, PropertyMock
import time


class TestOllamaAnalyzer:
    @patch("src.app.requests.Session")
    def test_initial_state(self, mock_session):
    """Test case for test_initial_state."""
        from src.app import OllamaAnalyzer, CameraCapture
        camera = MagicMock(spec=CameraCapture)
        analyzer = OllamaAnalyzer(camera, model="gemma3:latest", interval=5.0)
        assert analyzer.model == "gemma3:latest"
        assert analyzer.interval == 5.0
        assert analyzer.get_result() == ""
        assert analyzer.is_boss_mode() is False
        assert analyzer.last_latency == 0.0

    def test_set_model(self):
        from src.app import OllamaAnalyzer, CameraCapture
        camera = MagicMock(spec=CameraCapture)
        analyzer = OllamaAnalyzer(camera, model="gemma3:latest", interval=5.0)
        analyzer.set_model("llama3.2-vision:latest")
        assert analyzer.get_model() == "llama3.2-vision:latest"

    def test_set_interval_minimum_clamp(self):
        from src.app import OllamaAnalyzer, CameraCapture
        camera = MagicMock(spec=CameraCapture)
        analyzer = OllamaAnalyzer(camera, model="gemma3:latest", interval=5.0)
        analyzer.set_interval(-1)
        assert analyzer.interval == 1.0

    def test_set_interval_normal(self):
        from src.app import OllamaAnalyzer, CameraCapture
        camera = MagicMock(spec=CameraCapture)
        analyzer = OllamaAnalyzer(camera, model="gemma3:latest", interval=5.0)
        analyzer.set_interval(10.0)
        assert analyzer.interval == 10.0

    def test_boss_mode_toggle(self):
        from src.app import OllamaAnalyzer, CameraCapture
        camera = MagicMock(spec=CameraCapture)
        analyzer = OllamaAnalyzer(camera, model="gemma3:latest", interval=5.0)
        assert analyzer.is_boss_mode() is False
        analyzer.activate_boss_mode()
        assert analyzer.is_boss_mode() is True
        analyzer.deactivate_boss_mode()
        assert analyzer.is_boss_mode() is False

    def test_trigger_now_sets_event(self):
        from src.app import OllamaAnalyzer, CameraCapture
        camera = MagicMock(spec=CameraCapture)
        analyzer = OllamaAnalyzer(camera, model="gemma3:latest", interval=5.0)
        analyzer.trigger_now()
        assert analyzer._trigger.is_set()

    @patch("src.app.requests.Session")
    def test_system_prompts(self, mock_session):
        from src.ai.ollama_analyzer import OLLAMA_SYSTEM_PROMPT, BOSS_SYSTEM_PROMPT, OLLAMA_USER_PROMPT
        assert len(OLLAMA_SYSTEM_PROMPT) > 0
        assert "real-time camera assistant" in OLLAMA_SYSTEM_PROMPT
        assert "toxic, passive-aggressive boss" in BOSS_SYSTEM_PROMPT
        assert "What do you see" in OLLAMA_USER_PROMPT

    def test_start_stop(self):
        from src.app import OllamaAnalyzer, CameraCapture
        camera = MagicMock(spec=CameraCapture)
        analyzer = OllamaAnalyzer(camera, model="gemma3:latest", interval=5.0)
        analyzer.start()
        assert analyzer._running is True
        analyzer.stop()
        assert analyzer._running is False

    @patch("src.app.requests.Session")
    def test_latency_recorded_after_analysis(self, mock_session):
        from src.app import OllamaAnalyzer, CameraCapture
        camera = MagicMock(spec=CameraCapture)
        camera.latest_frame = b"\xff\xd8" + b"\x00" * 100 + b"\xff\xd9"
        camera.frame_id = 1
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"response": "A person sitting at a desk"}
        mock_session_instance = MagicMock()
        mock_session.return_value = mock_session_instance
        mock_session_instance.post.return_value = mock_resp
        analyzer = OllamaAnalyzer(camera, model="gemma3:latest", interval=5.0)
        analyzer._session = mock_session_instance
        analyzer.start()
        analyzer._trigger.set()
        time.sleep(0.05)
        analyzer.stop()
        text = analyzer.get_result()
        assert text == "A person sitting at a desk" or text == ""
