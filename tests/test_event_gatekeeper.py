"""Tests for EventGatekeeper YOLO filtering."""

from unittest.mock import MagicMock, patch


class TestEventGatekeeper:
    def test_model_not_loaded_when_ultralytics_missing(self):
    """Test case for test_model_not_loaded_when_ultralytics_missing."""
        import sys
        had_ultralytics = "ultralytics" in sys.modules
        if had_ultralytics:
            ultralytics_mod = sys.modules.pop("ultralytics")
            yolo_class = getattr(ultralytics_mod, "YOLO", None)
            import builtins
            original_import = builtins.__import__
            def mock_import(name, *args, **kwargs):
                if name == "ultralytics" or name.startswith("ultralytics."):
                    raise ImportError("No ultralytics")
                return original_import(name, *args, **kwargs)
            builtins.__import__ = mock_import
        try:
            if "src.app" in sys.modules:
                del sys.modules["src.app"]
            from src.app import EventGatekeeper
            camera = MagicMock()
            analyzer = MagicMock()
            gatekeeper = EventGatekeeper(camera, analyzer)
            assert gatekeeper.ready is False
            assert gatekeeper.model is None
        finally:
            if had_ultralytics:
                builtins.__import__ = original_import
                sys.modules["ultralytics"] = ultralytics_mod

    @patch("ultralytics.YOLO")
    def test_ready_when_yolo_loads(self, mock_yolo):
        from src.app import EventGatekeeper
        camera = MagicMock()
        analyzer = MagicMock()
        gatekeeper = EventGatekeeper(camera, analyzer)
        assert gatekeeper.ready is True

    def test_target_classes_defined(self):
        from src.ai.event_gatekeeper import TARGET_CLASSES
        assert 0 in TARGET_CLASSES
        assert TARGET_CLASSES[0] == "person"
        assert 2 in TARGET_CLASSES
        assert TARGET_CLASSES[2] == "car"
        assert 67 in TARGET_CLASSES
        assert TARGET_CLASSES[67] == "cell phone"

    def test_start_does_nothing_when_not_ready(self):
        from src.app import EventGatekeeper
        gk = EventGatekeeper.__new__(EventGatekeeper)
        gk.ready = False
        gk._running = False
        gk.start()
        assert not gk._running

    def test_stop_sets_running_false(self):
        from src.app import EventGatekeeper
        gk = EventGatekeeper.__new__(EventGatekeeper)
        gk._running = True
        gk.stop()
        assert not gk._running

    def test_stats_defaults(self):
        from src.app import EventGatekeeper
        gk = EventGatekeeper.__new__(EventGatekeeper)
        gk._stats = {"detections": 0, "triggers": 0, "boss_roasts": 0}
        gk._events = []
        import threading
        gk._lock = threading.Lock()
        stats = gk.stats
        assert stats["detections"] == 0
        assert stats["queue"] == 0

    def test_get_events_empty(self):
        from src.app import EventGatekeeper
        gk = EventGatekeeper.__new__(EventGatekeeper)
        gk._events = []
        import threading
        gk._lock = threading.Lock()
        assert gk.get_events() == []

    def test_yolo_confidence_env(self):
        with patch.dict("os.environ", {"YOLO_CONFIDENCE": "0.50"}):
            from importlib import reload
            import src.app
            reload(src.app)
            assert src.app.YOLO_CONF == 0.50
        from importlib import reload
        import src.app
        reload(src.app)
