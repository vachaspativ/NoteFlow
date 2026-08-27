"""Tests for noteflow.log_watcher — TeamsLogWatcher."""
from __future__ import annotations

import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest
from noteflow.log_watcher import TeamsLogWatcher, _find_teams_log


# ---------------------------------------------------------------------------
# Helper: write a temp log file with given content
# ---------------------------------------------------------------------------

def _write_log(content: str) -> Path:
    tmp = tempfile.NamedTemporaryFile(
        mode="w", suffix=".log", delete=False, encoding="utf-8"
    )
    tmp.write(content)
    tmp.flush()
    tmp.close()
    return Path(tmp.name)


# ---------------------------------------------------------------------------
# _find_teams_log resolution tests
# ---------------------------------------------------------------------------

def test_find_log_returns_none_when_no_teams(tmp_path):
    with patch.dict(os.environ, {"LOCALAPPDATA": str(tmp_path), "APPDATA": str(tmp_path)}):
        assert _find_teams_log() is None


def test_find_log_returns_classic_teams_when_present(tmp_path):
    classic_dir = tmp_path / "Microsoft" / "Teams"
    classic_dir.mkdir(parents=True)
    log_file = classic_dir / "logs.txt"
    log_file.write_text("dummy")
    with patch.dict(os.environ, {"APPDATA": str(tmp_path), "LOCALAPPDATA": str(tmp_path / "nonexistent")}):
        result = _find_teams_log()
    assert result == log_file


# ---------------------------------------------------------------------------
# TeamsLogWatcher state-machine tests
# ---------------------------------------------------------------------------

def test_call_started_on_callConnected_marker():
    log = _write_log("2025-01-01 callConnected: session abc123\n")
    watcher = TeamsLogWatcher()
    with patch("noteflow.log_watcher._find_teams_log", return_value=log):
        assert watcher.check() is True
    log.unlink()


def test_call_ended_on_callEnded_marker():
    # Simulate: call started, then ended
    log = _write_log(
        "2025-01-01 callConnected: session abc123\n"
        "2025-01-01 callEnded: session abc123\n"
    )
    watcher = TeamsLogWatcher()
    with patch("noteflow.log_watcher._find_teams_log", return_value=log):
        assert watcher.check() is False
    log.unlink()


def test_in_call_state_persists_between_polls():
    """Watcher remains in-call across polls until an end marker appears."""
    log = _write_log("callConnected started\n")
    watcher = TeamsLogWatcher()
    with patch("noteflow.log_watcher._find_teams_log", return_value=log):
        watcher.check()   # reads callConnected → in_call = True
        assert watcher._in_call is True
        # Second poll — no new lines, state must persist
        assert watcher.check() is True
    log.unlink()


def test_new_lines_appended_are_detected():
    """Watcher picks up new content appended after initial read."""
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".log", delete=False, encoding="utf-8"
    ) as tmp:
        tmp.write("idle line\n")
        log_path = Path(tmp.name)

    watcher = TeamsLogWatcher()
    with patch("noteflow.log_watcher._find_teams_log", return_value=log_path):
        assert watcher.check() is False  # no call markers yet
        # Append call marker
        with open(log_path, "a", encoding="utf-8") as f:
            f.write("callConnected: session xyz\n")
        assert watcher.check() is True  # new line detected

    log_path.unlink()


def test_classic_teams_OnThePhone_marker():
    log = _write_log("StatusChanged: OnThePhone\n")
    watcher = TeamsLogWatcher()
    with patch("noteflow.log_watcher._find_teams_log", return_value=log):
        assert watcher.check() is True
    log.unlink()


def test_reset_clears_in_call_state():
    log = _write_log("callConnected\n")
    watcher = TeamsLogWatcher()
    with patch("noteflow.log_watcher._find_teams_log", return_value=log):
        watcher.check()
        assert watcher._in_call is True
        watcher.reset()
        assert watcher._in_call is False
    log.unlink()


def test_missing_log_file_returns_current_state():
    """If log file is not found, watcher returns whatever _in_call currently is."""
    watcher = TeamsLogWatcher()
    with patch("noteflow.log_watcher._find_teams_log", return_value=None):
        assert watcher.check() is False
        watcher._in_call = True
        assert watcher.check() is True
