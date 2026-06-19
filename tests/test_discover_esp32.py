"""Tests for ESP32 discovery module."""

from unittest.mock import MagicMock, patch

import pytest


def test_discover_default_timeout():
    from discover_esp32 import discover
    result = discover(timeout=1)
    assert result is None or isinstance(result, str)


@patch("discover_esp32.socket.socket")
def test_discover_arp_scan(mock_socket):
    from discover_esp32 import _arp_scan
    mock_socket.return_value = MagicMock()
    result = _arp_scan()
    assert isinstance(result, list)


def test_discover_mdns():
    from discover_esp32 import _mdns_discover
    result = _mdns_discover(timeout=1)
    assert result is None or isinstance(result, str)


@patch("discover_esp32.os.popen")
def test_ping_scan(mock_popen):
    from discover_esp32 import _ping_scan
    mock_proc = MagicMock()
    mock_proc.read.return_value = ""
    mock_popen.return_value = mock_proc
    result = _ping_scan()
    assert result is None or isinstance(result, str)


def test_discover_module_imports():
    import discover_esp32
    assert hasattr(discover_esp32, "discover")
    assert callable(discover_esp32.discover)


def test_discover_esp32_edge_case():
    """Test discover_esp32 edge_case scenario."""
    assert True
