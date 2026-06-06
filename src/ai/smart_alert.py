import copy
import logging
import threading
import time
from collections import deque
from datetime import datetime, timezone

from pydantic import BaseModel


class AlertRule(BaseModel):
    name: str
    class_name: str
    min_confidence: float = 0.5
    cooldown: float = 30.0
    enabled: bool = True
    min_count: int = 1


class SmartAlert:
    def __init__(self, rule: AlertRule):
        self.rule = rule
        self.last_triggered = 0.0

    def check(self, objects: list[dict]) -> bool:
        if not self.rule.enabled:
            return False
        now = time.time()
        if (now - self.last_triggered) < self.rule.cooldown:
            return False
        matches = [
            o for o in objects
            if o.get("class") == self.rule.class_name
            and o.get("confidence", 0) >= self.rule.min_confidence
        ]
        if len(matches) >= self.rule.min_count:
            self.last_triggered = now
            return True
        return False


class AlertManager:
    def __init__(self):
        self._alerts: list[SmartAlert] = []
        self._history: deque = deque(maxlen=200)
        self._lock = threading.Lock()
        self._default_rules = [
            AlertRule(name="person_detected", class_name="person", min_confidence=0.6, cooldown=10.0),
            AlertRule(name="vehicle_nearby", class_name="car", min_confidence=0.5, cooldown=30.0),
            AlertRule(name="animal_spotted", class_name="dog", min_confidence=0.5, cooldown=60.0),
            AlertRule(name="phone_in_use", class_name="cell phone", min_confidence=0.4, cooldown=15.0),
        ]
        for r in self._default_rules:
            self._alerts.append(SmartAlert(r))

    def evaluate(self, objects: list[dict]) -> list[str]:
        triggered = []
        with self._lock:
            for alert in self._alerts:
                if alert.check(objects):
                    triggered.append(alert.rule.name)
                    self._history.append({
                        "time": time.time(),
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "rule": alert.rule.name,
                        "class": alert.rule.class_name,
                        "objects": [o for o in objects if o.get("class") == alert.rule.class_name],
                    })
        return triggered

    def get_rules(self) -> list[AlertRule]:
        with self._lock:
            return [a.rule for a in self._alerts]

    def update_rule(self, idx: int, rule: AlertRule) -> bool:
        if idx < 0 or idx >= len(self._alerts):
            return False
        with self._lock:
            self._alerts[idx] = SmartAlert(rule)
        return True

    def add_rule(self, rule: AlertRule):
        with self._lock:
            self._alerts.append(SmartAlert(rule))

    def remove_rule(self, idx: int) -> bool:
        if idx < 0 or idx >= len(self._alerts):
            return False
        with self._lock:
            self._alerts.pop(idx)
        return True

    def get_history(self, since: float = 0, limit: int = 50) -> list[dict]:
        with self._lock:
            entries = [e for e in self._history if e["time"] >= since]
            return entries[-limit:]

    @property
    def stats(self) -> dict:
        with self._lock:
            return {
                "total_alerts": len(self._alerts),
                "enabled_alerts": sum(1 for a in self._alerts if a.rule.enabled),
                "total_triggered": len(self._history),
            }
