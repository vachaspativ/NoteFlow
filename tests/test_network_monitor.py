"""Tests for noteflow.network_monitor — CallNetworkMonitor."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from noteflow.network_monitor import CallNetworkMonitor, STUN_TURN_PORTS


def _make_conn(pid: int, remote_ip: str, remote_port: int):
    conn = MagicMock()
    conn.pid = pid
    conn.raddr = MagicMock()
    conn.raddr.ip = remote_ip
    conn.raddr.port = remote_port
    return conn


def _proc_iter(pid: int, name: str):
    """Return a side_effect list for psutil.process_iter."""
    proc = MagicMock()
    proc.info = {"pid": pid, "name": name}
    return [proc]


# ---------------------------------------------------------------------------
# Teams — IP range matching
# ---------------------------------------------------------------------------

def test_teams_media_relay_ip_triggers_detection():
    monitor = CallNetworkMonitor(min_connections=2)
    teams_pid = 1111
    # Two UDP connections to a Teams media relay IP
    conns = [
        _make_conn(teams_pid, "13.107.64.1", 50000),
        _make_conn(teams_pid, "13.107.64.2", 50001),
    ]
    with patch("psutil.process_iter", return_value=_proc_iter(teams_pid, "ms-teams.exe")), \
         patch("psutil.net_connections", return_value=conns):
        result = monitor.check_call_active()
    assert result.is_active is True
    assert "teams" in result.app_name
    assert result.qualifying_count >= 2


def test_single_teams_connection_below_threshold_not_active():
    """One UDP connection is not enough (min_connections=2)."""
    monitor = CallNetworkMonitor(min_connections=2)
    teams_pid = 2222
    conns = [_make_conn(teams_pid, "13.107.64.1", 50000)]
    with patch("psutil.process_iter", return_value=_proc_iter(teams_pid, "ms-teams.exe")), \
         patch("psutil.net_connections", return_value=conns):
        result = monitor.check_call_active()
    assert result.is_active is False


# ---------------------------------------------------------------------------
# STUN/TURN port fallback (VPN scenarios)
# ---------------------------------------------------------------------------

def test_stun_port_fallback_triggers_detection():
    """When relay IP is a VPN gateway (not in range), STUN/TURN port should match."""
    monitor = CallNetworkMonitor(min_connections=2)
    teams_pid = 3333
    # Remote IP is a corporate VPN relay — not in known Microsoft ranges
    conns = [
        _make_conn(teams_pid, "10.10.10.1", 3478),
        _make_conn(teams_pid, "10.10.10.2", 3479),
    ]
    with patch("psutil.process_iter", return_value=_proc_iter(teams_pid, "teams.exe")), \
         patch("psutil.net_connections", return_value=conns):
        result = monitor.check_call_active()
    assert result.is_active is True
    assert result.signal_type == "stun_port"


# ---------------------------------------------------------------------------
# Google Meet / Chrome — IP range matching
# ---------------------------------------------------------------------------

def test_chrome_google_ip_triggers_detection():
    monitor = CallNetworkMonitor(min_connections=2)
    chrome_pid = 4444
    # Two UDP connections to Google's media relay range
    conns = [
        _make_conn(chrome_pid, "74.125.0.1", 19302),
        _make_conn(chrome_pid, "74.125.0.2", 19303),
    ]
    with patch("psutil.process_iter", return_value=_proc_iter(chrome_pid, "chrome.exe")), \
         patch("psutil.net_connections", return_value=conns):
        result = monitor.check_call_active()
    assert result.is_active is True
    assert result.app_name == "chrome.exe"


# ---------------------------------------------------------------------------
# Negative cases — idle app / loopback / no comm process
# ---------------------------------------------------------------------------

def test_loopback_udp_not_detected():
    monitor = CallNetworkMonitor(min_connections=2)
    teams_pid = 5555
    conns = [
        _make_conn(teams_pid, "127.0.0.1", 3478),
        _make_conn(teams_pid, "127.0.0.1", 3479),
    ]
    with patch("psutil.process_iter", return_value=_proc_iter(teams_pid, "ms-teams.exe")), \
         patch("psutil.net_connections", return_value=conns):
        result = monitor.check_call_active()
    assert result.is_active is False



def test_no_comm_process_running_returns_false():
    monitor = CallNetworkMonitor(min_connections=2)
    with patch("psutil.process_iter", return_value=[]), \
         patch("psutil.net_connections", return_value=[]):
        result = monitor.check_call_active()
    assert result.is_active is False


def test_random_udp_traffic_not_from_comm_app_ignored():
    """UDP connections from a non-comm process (e.g. browser background) are ignored."""
    monitor = CallNetworkMonitor(min_connections=2)
    teams_pid = 6666
    other_pid = 9999   # not a comm process
    conns = [
        _make_conn(other_pid, "13.107.64.1", 3478),
        _make_conn(other_pid, "13.107.64.2", 3479),
    ]
    with patch("psutil.process_iter", return_value=_proc_iter(teams_pid, "ms-teams.exe")), \
         patch("psutil.net_connections", return_value=conns):
        result = monitor.check_call_active()
    assert result.is_active is False


def test_process_scan_exception_returns_false():
    """If psutil.process_iter raises, monitor returns not-active gracefully."""
    monitor = CallNetworkMonitor()
    with patch("psutil.process_iter", side_effect=Exception("access denied")), \
         patch("psutil.net_connections", return_value=[]):
        result = monitor.check_call_active()
    assert result.is_active is False
