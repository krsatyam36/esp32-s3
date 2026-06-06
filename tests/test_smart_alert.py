"""Tests for SmartAlert and AlertManager."""

from src.app import AlertManager, AlertRule
from src.ai.smart_alert import SmartAlert


class TestSmartAlert:
    def test_check_matches_class_and_confidence(self):
        rule = AlertRule(name="test_alert", class_name="person", min_confidence=0.5)
        alert = SmartAlert(rule)
        assert alert.check([{"class": "person", "confidence": 0.7}]) is True

    def test_check_below_confidence(self):
        rule = AlertRule(name="test_alert", class_name="person", min_confidence=0.5)
        alert = SmartAlert(rule)
        assert alert.check([{"class": "person", "confidence": 0.3}]) is False

    def test_check_wrong_class(self):
        rule = AlertRule(name="test_alert", class_name="person", min_confidence=0.5)
        alert = SmartAlert(rule)
        assert alert.check([{"class": "car", "confidence": 0.9}]) is False

    def test_check_disabled_rule(self):
        rule = AlertRule(name="test_alert", class_name="person", enabled=False)
        alert = SmartAlert(rule)
        assert alert.check([{"class": "person", "confidence": 0.9}]) is False

    def test_check_cooldown(self):
        rule = AlertRule(name="test_alert", class_name="person", cooldown=60.0)
        alert = SmartAlert(rule)
        alert.last_triggered = 0
        assert alert.check([{"class": "person", "confidence": 0.9}]) is True
        assert alert.check([{"class": "person", "confidence": 0.9}]) is False

    def test_check_min_count(self):
        rule = AlertRule(name="multi", class_name="person", min_confidence=0.5, min_count=2)
        alert = SmartAlert(rule)
        assert alert.check([{"class": "person", "confidence": 0.7}]) is False
        assert alert.check([
            {"class": "person", "confidence": 0.7},
            {"class": "person", "confidence": 0.6},
        ]) is True


class TestAlertManager:
    def setup_method(self):
        self.mgr = AlertManager()

    def test_default_rules_loaded(self):
        rules = self.mgr.get_rules()
        names = [r.name for r in rules]
        assert "person_detected" in names
        assert "vehicle_nearby" in names
        assert "animal_spotted" in names
        assert "phone_in_use" in names

    def test_evaluate_triggers_person(self):
        triggered = self.mgr.evaluate([{"class": "person", "confidence": 0.8}])
        assert "person_detected" in triggered

    def test_evaluate_triggers_car(self):
        triggered = self.mgr.evaluate([{"class": "car", "confidence": 0.7}])
        assert "vehicle_nearby" in triggered

    def test_evaluate_triggers_dog(self):
        triggered = self.mgr.evaluate([{"class": "dog", "confidence": 0.6}])
        assert "animal_spotted" in triggered

    def test_evaluate_triggers_cell_phone(self):
        triggered = self.mgr.evaluate([{"class": "cell phone", "confidence": 0.5}])
        assert "phone_in_use" in triggered

    def test_evaluate_returns_multiple(self):
        triggered = self.mgr.evaluate([
            {"class": "person", "confidence": 0.8},
            {"class": "car", "confidence": 0.7},
        ])
        assert "person_detected" in triggered
        assert "vehicle_nearby" in triggered

    def test_history_recorded_on_trigger(self):
        self.mgr.evaluate([{"class": "person", "confidence": 0.8}])
        history = self.mgr.get_history()
        assert len(history) == 1
        assert history[0]["rule"] == "person_detected"

    def test_add_and_remove_rule(self):
        rule = AlertRule(name="custom", class_name="laptop", min_confidence=0.5)
        self.mgr.add_rule(rule)
        assert len(self.mgr.get_rules()) == 5
        assert self.mgr.remove_rule(4) is True
        assert len(self.mgr.get_rules()) == 4

    def test_update_rule(self):
        rule = AlertRule(name="updated", class_name="cat", min_confidence=0.9)
        assert self.mgr.update_rule(0, rule) is True
        assert self.mgr.get_rules()[0].name == "updated"

    def test_update_rule_invalid_index(self):
        rule = AlertRule(name="x", class_name="x")
        assert self.mgr.update_rule(999, rule) is False

    def test_remove_rule_invalid_index(self):
        assert self.mgr.remove_rule(999) is False

    def test_stats(self):
        stats = self.mgr.stats
        assert stats["total_alerts"] == 4
        assert stats["enabled_alerts"] == 4
        assert stats["total_triggered"] == 0

    def test_evaluate_no_match(self):
        triggered = self.mgr.evaluate([{"class": "toaster", "confidence": 0.9}])
        assert triggered == []
