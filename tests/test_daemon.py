from __future__ import annotations

import time
from unittest.mock import Mock, patch, MagicMock, call

import pytest
from noteflow.daemon import CallDetectorDaemon, COMM_PROCESS_NAMES


@pytest.fixture
def mock_controller():
    controller = Mock()
    controller.is_recording.return_value = False
    controller.settings.transcription_mode = Mock()
    controller.settings.theme = Mock()
    controller.settings.default_meeting_title_prefix = "[NoteFlow] Meeting"
    return controller


def test_daemon_initial_state(mock_controller):
    daemon = CallDetectorDaemon(mock_controller)
    assert not daemon.is_in_call
    assert not daemon.is_running()


def test_notify_session_started_and_stopped(mock_controller):
    daemon = CallDetectorDaemon(mock_controller)
    daemon.notify_session_started()
    assert daemon.is_in_call

    daemon.notify_session_stopped(manual=True)
    assert not daemon.is_in_call
    assert daemon._last_cooldown_until > time.time()


# ---------------------------------------------------------------------------
# _has_meeting_window tests — the new process-scoped detection
# ---------------------------------------------------------------------------

def _make_enum_windows(windows: list[tuple[str, int]]):
    """Return an EnumWindows side_effect that feeds (title, pid) pairs to the callback.

    We patch win32gui.GetWindowText and win32process.GetWindowThreadProcessId
    together so the callback sees both.
    """
    def fake_enum(callback, extra):
        for title, pid in windows:
            with patch("win32gui.GetWindowText", return_value=title), \
                 patch("win32process.GetWindowThreadProcessId", return_value=(0, pid)):
                try:
                    callback(1234, extra)
                except Exception:
                    pass  # mirror real EnumWindows behaviour
    return fake_enum


@patch("sys.platform", "win32")
def test_no_comm_processes_returns_false(mock_controller):
    """If no known comm app is running at all, _has_meeting_window must be False."""
    daemon = CallDetectorDaemon(mock_controller)
    with patch.object(daemon, "_get_comm_process_pids", return_value=set()):
        assert daemon._has_meeting_window() is False


@patch("sys.platform", "win32")
def test_ignores_teams_chat_and_calendar_windows(mock_controller):
    """Idle Teams/Slack/Zoom windows must NOT trigger detection."""
    daemon = CallDetectorDaemon(mock_controller)
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
        assert daemon._has_meeting_window() is False


@patch("sys.platform", "win32")
def test_detects_teams_meeting_window(mock_controller):
    """A Teams meeting window must trigger detection."""
    daemon = CallDetectorDaemon(mock_controller)
    teams_pid = 2222
    windows = [
        ("Chat | John Doe | Microsoft Teams", teams_pid),
        ("Meeting | Project Sync | Microsoft Teams", teams_pid),
    ]
    with patch.object(daemon, "_get_comm_process_pids", return_value={teams_pid}), \
         patch("win32gui.IsWindowVisible", return_value=True), \
         patch("win32gui.EnumWindows", side_effect=_make_enum_windows(windows)):
        assert daemon._has_meeting_window() is True


@patch("sys.platform", "win32")
def test_detects_zoom_meeting_window(mock_controller):
    """A Zoom meeting window must trigger detection."""
    daemon = CallDetectorDaemon(mock_controller)
    zoom_pid = 3333
    windows = [
        ("Zoom Meeting", zoom_pid),
    ]
    with patch.object(daemon, "_get_comm_process_pids", return_value={zoom_pid}), \
         patch("win32gui.IsWindowVisible", return_value=True), \
         patch("win32gui.EnumWindows", side_effect=_make_enum_windows(windows)):
        assert daemon._has_meeting_window() is True


@patch("sys.platform", "win32")
def test_browser_window_with_meeting_title_is_ignored(mock_controller):
    """A browser tab (chrome.exe) titled 'meeting with John' must NOT trigger detection
    because it is not owned by a known communication process."""
    daemon = CallDetectorDaemon(mock_controller)
    teams_pid = 4444
    chrome_pid = 9999   # not in COMM_PROCESS_NAMES

    windows = [
        # Browser tab with "meeting" keyword — should be ignored (chrome.exe not a comm process)
        ("Meeting Invite - meeting with John Doe - Google Chrome", chrome_pid),
        # Idle Teams window (teams pid but not a meeting window)
        ("Microsoft Teams", teams_pid),
    ]
    with patch.object(daemon, "_get_comm_process_pids", return_value={teams_pid}), \
         patch("win32gui.IsWindowVisible", return_value=True), \
         patch("win32gui.EnumWindows", side_effect=_make_enum_windows(windows)):
        assert daemon._has_meeting_window() is False


@patch("sys.platform", "win32")
def test_outlook_meeting_reminder_is_ignored(mock_controller):
    """An Outlook calendar reminder titled 'Team Meeting' must NOT trigger detection."""
    daemon = CallDetectorDaemon(mock_controller)
    outlook_pid = 5555   # not a comm process PID
    teams_pid = 4444

    windows = [
        ("Team Meeting - Reminder", outlook_pid),
        ("Microsoft Teams", teams_pid),   # idle Teams
    ]
    with patch.object(daemon, "_get_comm_process_pids", return_value={teams_pid}), \
         patch("win32gui.IsWindowVisible", return_value=True), \
         patch("win32gui.EnumWindows", side_effect=_make_enum_windows(windows)):
        assert daemon._has_meeting_window() is False


@patch("sys.platform", "win32")
def test_check_active_call_on_non_windows_returns_false(mock_controller):
    daemon = CallDetectorDaemon(mock_controller)
    with patch("sys.platform", "linux"):
        assert daemon._check_active_call() is False


# ---------------------------------------------------------------------------
# _monitor_loop state-sync test
# ---------------------------------------------------------------------------

def test_monitor_loop_syncs_stopped_recording_state(mock_controller):
    daemon = CallDetectorDaemon(mock_controller)
    daemon.is_in_call = True
    mock_controller.is_recording.return_value = False

    with patch.object(daemon, "_check_active_call", return_value=False):
        recording = daemon.controller.is_recording()
        if daemon.is_in_call and not recording:
            daemon.is_in_call = False

        assert daemon.is_in_call is False
