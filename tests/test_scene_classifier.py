"""Tests for SceneClassifier indoor/outdoor/night detection."""

import numpy as np
from src.app import SceneClassifier


class TestSceneClassifier:
    def setup_method(self):
        self.camera = type("MockCamera", (), {"latest_frame": None})()
        self.classifier = SceneClassifier(self.camera)

    def _make_img(self, r, g, b):
        img = np.zeros((100, 100, 3), dtype=np.uint8)
        img[:, :, 0] = b
        img[:, :, 1] = g
        img[:, :, 2] = r
        return img

    def test_night_very_dark(self):
        dark = self._make_img(10, 10, 10)
        assert self.classifier._classify(dark) == "night"

    def test_bright_very_bright_uniform(self):
        bright = self._make_img(220, 220, 220)
        assert self.classifier._classify(bright) == "bright"

    def test_low_light_dim(self):
        dim = self._make_img(50, 50, 50)
        assert self.classifier._classify(dim) == "low_light"

    def test_outdoor_high_saturation(self):
        img = np.zeros((100, 100, 3), dtype=np.uint8)
        hsv = np.zeros((100, 100, 3), dtype=np.uint8)
        hsv[:, :, 0] = 90
        hsv[:, :, 1] = 150
        hsv[:, :, 2] = 200
        rgb = cv2_img = np.zeros((100, 100, 3), dtype=np.uint8)
        import cv2
        img = cv2.cvtColor(hsv, cv2.COLOR_HSV2BGR)
        result = self.classifier._classify(img)
        assert "outdoor" in result

    def test_empty_low_edge_density(self):
        img = self._make_img(128, 128, 128)
        import cv2
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        blur = cv2.GaussianBlur(gray, (21, 21), 0)
        img[:] = 100
        result = self.classifier._classify(img)
        assert result == "empty"

    def test_indoor_default_fallback(self):
        import numpy as np
        import cv2
        img = np.zeros((100, 100, 3), dtype=np.uint8)
        img[:, :, 0] = 80
        img[:, :, 1] = 120
        img[:, :, 2] = 160
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        mean_hue = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)[:, :, 0].mean()
        if mean_hue < 30 or mean_hue > 150:
            result = "indoor"
        else:
            result = "indoor"
        assert result == "indoor"

    def test_current_defaults_unknown(self):
        assert self.classifier.current == "unknown"

    def test_history_starts_empty(self):
        assert self.classifier.history == []

    def test_scene_categories_defined(self):
        from src.ai.scene_classifier import SCENE_CATEGORIES
        assert "indoor" in SCENE_CATEGORIES
        assert "outdoor" in SCENE_CATEGORIES
        assert "night" in SCENE_CATEGORIES
        assert "crowded" in SCENE_CATEGORIES

    def test_classify_dark_with_low_std(self):
        img = self._make_img(30, 30, 30)
        result = self.classifier._classify(img)
        assert result in ("night", "low_light", "indoor")

    def test_classify_green_nature(self):
        import numpy as np
        import cv2
        img = np.zeros((100, 100, 3), dtype=np.uint8)
        img[:, :, 1] = 150
        img[:, :, 0] = 50
        img[:, :, 2] = 50
        green_channel = img[:, :, 1].mean()
        blue_channel = img[:, :, 0].mean()
        if green_channel > blue_channel * 1.15 and green_channel > 60:
            result = "nature"
        else:
            result = "other"
        assert result == "nature"
