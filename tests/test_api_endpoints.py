"""Tests for /led, /flash, /res, /flip, /ping, /diag endpoints."""

from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient


class TestControlEndpoints:
    def test_led_post(self):
        with patch("src.app.esp32.send_command") as mock_send:
            mock_send.return_value = {"success": True}
            from src.app import app
            client = TestClient(app)
            resp = client.post("/led", json={"state": "on"})
            assert resp.status_code == 200
            assert resp.json()["success"] is True
            mock_send.assert_called_with("/led?state=on")

    def test_led_off(self):
        with patch("src.app.esp32.send_command") as mock_send:
            mock_send.return_value = {"success": True}
            from src.app import app
            client = TestClient(app)
            resp = client.post("/led", json={"state": "off"})
            mock_send.assert_called_with("/led?state=off")

    def test_flash_default(self):
        with patch("src.app.esp32.send_command") as mock_send:
            mock_send.return_value = {"success": True}
            from src.app import app
            client = TestClient(app)
            resp = client.post("/flash?count=5")
            assert resp.status_code == 200
            mock_send.assert_called_with("/flash?count=5")

    def test_flash_custom_count(self):
        with patch("src.app.esp32.send_command") as mock_send:
            mock_send.return_value = {"success": True}
            from src.app import app
            client = TestClient(app)
            resp = client.post("/flash?count=10")
            mock_send.assert_called_with("/flash?count=10")

    def test_flash_out_of_range_low(self):
        from src.app import app
        client = TestClient(app)
        resp = client.post("/flash?count=0")
        assert resp.status_code == 422

    def test_flash_out_of_range_high(self):
        from src.app import app
        client = TestClient(app)
        resp = client.post("/flash?count=21")
        assert resp.status_code == 422

    def test_res_post(self):
        with patch("src.app.esp32.send_command") as mock_send:
            mock_send.return_value = {"success": True}
            from src.app import app
            client = TestClient(app)
            resp = client.post("/res", json={"value": "SVGA"})
            assert resp.status_code == 200
            mock_send.assert_called_with("/res?val=SVGA")

    def test_res_uxga(self):
        with patch("src.app.esp32.send_command") as mock_send:
            mock_send.return_value = {"success": True}
            from src.app import app
            client = TestClient(app)
            resp = client.post("/res", json={"value": "UXGA"})
            mock_send.assert_called_with("/res?val=UXGA")

    def test_flip_v(self):
        with patch("src.app.esp32.send_command") as mock_send:
            mock_send.return_value = {"success": True}
            from src.app import app
            client = TestClient(app)
            resp = client.post("/flip", json={"mode": "v"})
            assert resp.status_code == 200
            mock_send.assert_called_with("/flip?mode=v")

    def test_flip_h(self):
        with patch("src.app.esp32.send_command") as mock_send:
            mock_send.return_value = {"success": True}
            from src.app import app
            client = TestClient(app)
            resp = client.post("/flip", json={"mode": "h"})
            mock_send.assert_called_with("/flip?mode=h")

    def test_diag_proxy(self):
        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_resp = MagicMock()
            mock_resp.status = 200
            mock_resp.read.return_value = '{"free_heap": 123456}'.encode()
            mock_urlopen.return_value = mock_resp
            from src.app import app
            client = TestClient(app)
            resp = client.get("/diag")
            data = resp.json()
            assert data["esp32"]["free_heap"] == 123456
            assert data["cached"] is False

    def test_diag_proxy_error(self):
        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_urlopen.side_effect = ConnectionError("ESP32 unreachable")
            from src.app import app
            client = TestClient(app)
            resp = client.get("/diag")
            data = resp.json()
            assert data["esp32"] is None
            assert "error" in data

    def test_led_validation(self):
        from src.app import app
        client = TestClient(app)
        resp = client.post("/led", json={"state": ""})
        assert resp.status_code == 200
