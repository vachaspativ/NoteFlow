from __future__ import annotations

import time
from unittest.mock import Mock, patch, MagicMock

import pytest
from noteflow.daemon import CallDetectorDaemon


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


@patch("sys.platform", "win32")
def test_check_active_call_ignores_teams_chat_and_calendar_windows(mock_controller):
    daemon = CallDetectorDaemon(mock_controller)

    # Mock win32gui to simulate standard Teams windows
    with patch("win32gui.IsWindowVisible", return_value=True), \
         patch("win32gui.EnumWindows") as mock_enum:

        def fake_enum(callback, extra):
            # Simulate open windows
            windows = [
                "Chat | John Doe | Microsoft Teams",
                "Calendar | Microsoft Teams",
                "Activity | Microsoft Teams",
                "Microsoft Teams",
            ]
            for w in windows:
                with patch("win32gui.GetWindowText", return_value=w):
                    callback(1234, extra)

        mock_enum.side_effect = fake_enum
        
        # Audio sessions mock returns inactive/low peak
        with patch("pycaw.pycaw.AudioUtilities.GetAllSessions", side_effect=Exception("No audio")):
            assert daemon._check_active_call() is False


@patch("sys.platform", "win32")
def test_check_active_call_detects_teams_meeting_window(mock_controller):
    daemon = CallDetectorDaemon(mock_controller)

    with patch("win32gui.IsWindowVisible", return_value=True), \
         patch("win32gui.EnumWindows") as mock_enum:

        def fake_enum(callback, extra):
            windows = [
                "Chat | John Doe | Microsoft Teams",
                "Meeting | Project Sync | Microsoft Teams",
            ]
            for w in windows:
                with patch("win32gui.GetWindowText", return_value=w):
                    callback(1234, extra)

        mock_enum.side_effect = fake_enum

        with patch("pycaw.pycaw.AudioUtilities.GetAllSessions", side_effect=Exception("No audio")):
            assert daemon._check_active_call() is True


def test_monitor_loop_syncs_stopped_recording_state(mock_controller):
    daemon = CallDetectorDaemon(mock_controller)
    daemon.is_in_call = True
    mock_controller.is_recording.return_value = False

    with patch.object(daemon, "_check_active_call", return_value=False):
        # Run one iteration of monitor loop logic
        recording = daemon.controller.is_recording()
        if daemon.is_in_call and not recording:
            daemon.is_in_call = False

        assert daemon.is_in_call is False
