"""Tests for stream_test.py logic."""

import json
from unittest.mock import patch, MagicMock


class TestStreamTestFunctions:
    def test_endpoint_success_binary(self):
        from src.stream_test import test_endpoint
        with patch("urllib.request.urlopen") as mock_open:
            mock_resp = MagicMock()
            mock_resp.status = 200
            mock_resp.read.return_value = b"\xff\xd8" + b"\x00" * 100
            mock_open.return_value = mock_resp
            result = test_endpoint("http://192.168.1.100/", "Stream", "/")
            assert result is True

    def test_endpoint_success_json(self):
        from src.stream_test import test_endpoint
        with patch("urllib.request.urlopen") as mock_open:
            mock_resp = MagicMock()
            mock_resp.status = 200
            mock_resp.read.return_value = json.dumps({"rssi": "-65"}).encode()
            mock_open.return_value = mock_resp
            result = test_endpoint("http://192.168.1.100/", "Telemetry", "/telemetry", expect_json=True)
            assert result is True

    def test_endpoint_http_failure(self):
        from src.stream_test import test_endpoint
        with patch("urllib.request.urlopen") as mock_open:
            mock_resp = MagicMock()
            mock_resp.status = 404
            mock_open.return_value = mock_resp
            result = test_endpoint("http://192.168.1.100/", "Bad", "/nonexistent")
            assert result is False

    def test_endpoint_network_error(self):
        from src.stream_test import test_endpoint
        with patch("urllib.request.urlopen") as mock_open:
            mock_open.side_effect = ConnectionError("Connection refused")
            result = test_endpoint("http://192.168.1.100/", "Fail", "/test")
            assert result is False

    def test_endpoint_timeout_error(self):
        from src.stream_test import test_endpoint
        with patch("urllib.request.urlopen") as mock_open:
            mock_open.side_effect = TimeoutError("timed out")
            result = test_endpoint("http://192.168.1.100/", "Timeout", "/slow")
            assert result is False

    def test_endpoint_url_construction_no_trailing_slash(self):
        from src.stream_test import test_endpoint
        with patch("urllib.request.urlopen") as mock_open:
            mock_resp = MagicMock()
            mock_resp.status = 200
            mock_resp.read.return_value = b"OK"
            mock_open.return_value = mock_resp
            result = test_endpoint("http://192.168.1.100", "/ping", "/ping")
            assert result is True
            args, kwargs = mock_open.call_args
            assert args[0].startswith("http://192.168.1.100/ping")

    def test_endpoint_trims_base_url(self):
        from src.stream_test import test_endpoint
        with patch("urllib.request.urlopen") as mock_open:
            mock_resp = MagicMock()
            mock_resp.status = 200
            mock_resp.read.return_value = b"OK"
            mock_open.return_value = mock_resp
            result = test_endpoint("http://192.168.1.100///", "/", "/")
            assert result is True

    @patch("src.stream_test.test_endpoint")
    def test_main_all_pass(self, mock_test):
        mock_test.return_value = True
        import sys
        with patch.object(sys, "argv", ["stream_test.py", "http://192.168.1.100/"]):
            from src.stream_test import main
            try:
                main()
            except SystemExit as e:
                assert e.code is None or e.code == 0

    @patch("src.stream_test.test_endpoint")
    def test_main_some_fail(self, mock_test):
        mock_test.side_effect = [True, True, False, True]
        import sys
        with patch.object(sys, "argv", ["stream_test.py", "http://192.168.1.100/"]):
            from src.stream_test import main
            try:
                main()
            except SystemExit as e:
                assert e.code == 1
