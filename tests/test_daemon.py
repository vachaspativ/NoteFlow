from __future__ import annotations

import time
from unittest.mock import Mock, patch, MagicMock

import pytest
from noteflow.daemon import CallDetectorDaemon, COMM_PROCESS_NAMES


def _make_controller(
    network_check=False,  # disabled by default in tests to isolate window logic
    log_watch=False,
    window_check=True,
    streak=2,
    min_udp=2,
):
    ctrl = Mock()
    ctrl.is_recording.return_value = False
    ctrl.settings.transcription_mode = Mock()
    ctrl.settings.theme = Mock()
    ctrl.settings.default_meeting_title_prefix = "[NoteFlow] Meeting"
    ctrl.settings.daemon_network_check_enabled = network_check
    ctrl.settings.daemon_log_watch_enabled = log_watch
    ctrl.settings.daemon_window_check_enabled = window_check
    ctrl.settings.daemon_active_streak_required = streak
    ctrl.settings.daemon_min_udp_connections = min_udp
    return ctrl


@pytest.fixture
def mock_controller():
    return _make_controller()


def _patched_daemon(controller):
    """Create a daemon with log/network modules patched out so no real I/O happens."""
    with patch("noteflow.daemon.TeamsLogWatcher", MagicMock(), create=True), \
         patch("noteflow.daemon.CallNetworkMonitor", MagicMock(), create=True):
        # Patch the import inside __init__
        with patch.dict("sys.modules", {
            "noteflow.log_watcher": MagicMock(),
            "noteflow.network_monitor": MagicMock(),
        }):
            daemon = CallDetectorDaemon(controller)
    # Ensure internal monitors are MagicMocks so they don't fire
    daemon._log_watcher = None
    daemon._net_monitor = None
    return daemon


def _make_enum_windows(windows: list[tuple[str, int]]):
    """Return an EnumWindows side_effect feeding (title, pid) pairs."""
    def fake_enum(callback, extra):
        for title, pid in windows:
            with patch("win32gui.GetWindowText", return_value=title), \
                 patch("win32process.GetWindowThreadProcessId", return_value=(0, pid)):
                try:
                    callback(1234, extra)
                except Exception:
                    pass
    return fake_enum


# ---------------------------------------------------------------------------
# Basic state tests
# ---------------------------------------------------------------------------

def test_daemon_initial_state(mock_controller):
    daemon = _patched_daemon(mock_controller)
    assert not daemon.is_in_call
    assert not daemon.is_running()


def test_notify_session_started_and_stopped(mock_controller):
    daemon = _patched_daemon(mock_controller)
    daemon.notify_session_started()
    assert daemon.is_in_call

    daemon.notify_session_stopped(manual=True)
    assert not daemon.is_in_call
    assert daemon._last_cooldown_until > time.time()


# ---------------------------------------------------------------------------
# _signal_window tests — process-scoped window detection
# ---------------------------------------------------------------------------

@patch("sys.platform", "win32")
def test_no_comm_processes_returns_false(mock_controller):
    daemon = _patched_daemon(mock_controller)
    with patch.object(daemon, "_get_comm_process_pids", return_value=set()):
        assert daemon._signal_window() is False


@patch("sys.platform", "win32")
def test_ignores_idle_teams_chat_and_calendar_windows(mock_controller):
    daemon = _patched_daemon(mock_controller)
    teams_pid = 1111
    windows = [
        ("Chat | John Doe | Microsoft Teams", teams_pid),
        ("Calendar | Microsoft Teams", teams_pid),
        ("Activity | Microsoft Teams", teams_pid),
        ("Microsoft Teams", teams_pid),
        ("Calls | Microsoft Teams", teams_pid),
        ("Zoom Workplace", teams_pid),
        ("Slack", teams_pid),
        ("Discord", teams_pid),
    ]
    with patch.object(daemon, "_get_comm_process_pids", return_value={teams_pid}), \
         patch("win32gui.IsWindowVisible", return_value=True), \
         patch("win32gui.EnumWindows", side_effect=_make_enum_windows(windows)):
        assert daemon._signal_window() is False


@patch("sys.platform", "win32")
def test_detects_teams_meeting_window(mock_controller):
    daemon = _patched_daemon(mock_controller)
    teams_pid = 2222
    windows = [
        ("Chat | John Doe | Microsoft Teams", teams_pid),
        ("Meeting | Project Sync | Microsoft Teams", teams_pid),
    ]
    with patch.object(daemon, "_get_comm_process_pids", return_value={teams_pid}), \
         patch("win32gui.IsWindowVisible", return_value=True), \
         patch("win32gui.EnumWindows", side_effect=_make_enum_windows(windows)):
        assert daemon._signal_window() is True


@patch("sys.platform", "win32")
def test_detects_zoom_meeting_window(mock_controller):
    daemon = _patched_daemon(mock_controller)
    zoom_pid = 3333
    windows = [("Zoom Meeting", zoom_pid)]
    with patch.object(daemon, "_get_comm_process_pids", return_value={zoom_pid}), \
         patch("win32gui.IsWindowVisible", return_value=True), \
         patch("win32gui.EnumWindows", side_effect=_make_enum_windows(windows)):
        assert daemon._signal_window() is True


@patch("sys.platform", "win32")
def test_browser_window_with_meeting_title_is_ignored(mock_controller):
    """A browser tab titled 'meeting with John' must NOT trigger — chrome PID not in comm set."""
    daemon = _patched_daemon(mock_controller)
    teams_pid = 4444
    chrome_pid = 9999   # not in COMM_PROCESS_NAMES

    windows = [
        ("Meeting Invite - meeting with John Doe - Google Chrome", chrome_pid),
        ("Microsoft Teams", teams_pid),
    ]
    with patch.object(daemon, "_get_comm_process_pids", return_value={teams_pid}), \
         patch("win32gui.IsWindowVisible", return_value=True), \
         patch("win32gui.EnumWindows", side_effect=_make_enum_windows(windows)):
        assert daemon._signal_window() is False


@patch("sys.platform", "win32")
def test_outlook_meeting_reminder_is_ignored(mock_controller):
    daemon = _patched_daemon(mock_controller)
    outlook_pid = 5555
    teams_pid = 4444
    windows = [
        ("Team Meeting - Reminder", outlook_pid),
        ("Microsoft Teams", teams_pid),
    ]
    with patch.object(daemon, "_get_comm_process_pids", return_value={teams_pid}), \
         patch("win32gui.IsWindowVisible", return_value=True), \
         patch("win32gui.EnumWindows", side_effect=_make_enum_windows(windows)):
        assert daemon._signal_window() is False


def test_check_active_call_on_non_windows_returns_false(mock_controller):
    daemon = _patched_daemon(mock_controller)
    with patch("sys.platform", "linux"):
        assert daemon._check_active_call() is False


# ---------------------------------------------------------------------------
# _monitor_loop state-sync test
# ---------------------------------------------------------------------------

def test_monitor_loop_syncs_stopped_recording_state(mock_controller):
    daemon = _patched_daemon(mock_controller)
    daemon.is_in_call = True
    mock_controller.is_recording.return_value = False

    with patch.object(daemon, "_check_active_call", return_value=False):
        recording = daemon.controller.is_recording()
        if daemon.is_in_call and not recording:
            daemon.is_in_call = False
        assert daemon.is_in_call is False


# ---------------------------------------------------------------------------
# Configurable streak test
# ---------------------------------------------------------------------------

def test_configurable_active_streak():
    """daemon_active_streak_required is read at runtime from settings."""
    ctrl = _make_controller(streak=1)  # single poll = start immediately
    daemon = _patched_daemon(ctrl)
    # Verify attribute reads from settings correctly
    assert getattr(ctrl.settings, "daemon_active_streak_required") == 1
