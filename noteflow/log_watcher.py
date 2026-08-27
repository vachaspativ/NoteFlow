"""Teams call-state detection via local log file tailing (Windows-only).

Supports:
  - New Teams (SlimCore / Store app):
      %LOCALAPPDATA%\\Packages\\MSTeams_8wekyb3d8bbwe\\LocalCache\\Microsoft\\MSTeams\\Logs\\
      File pattern: MSTeamsNM_SlimCore_*.log
  - Classic Teams:
      %APPDATA%\\Microsoft\\Teams\\logs.txt
      Markers: OnThePhone / StatusChanged:InACall

The watcher tails whichever log file it finds, scanning only NEW lines since
the last read position. It maintains a stateful _in_call boolean that flips
based on call-start and call-end log markers.

Limitations / fragility notes:
  - Log format is undocumented and may change with any Teams update.
  - SlimCore logs may be partially structured (JSON-like fragments); regex
    patterns target stable surface-level keywords that appear across versions.
  - Falls back gracefully (returns False) if no log file is found.
"""
from __future__ import annotations

import logging
import os
import re
from pathlib import Path

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Regex patterns for call state transitions (case-insensitive)
# ---------------------------------------------------------------------------

# Patterns that indicate a call has STARTED (or is still active)
_CALL_START_PATTERNS: list[re.Pattern] = [
    re.compile(r"callConnected", re.I),
    re.compile(r"InACall", re.I),
    re.compile(r"callStarted", re.I),
    re.compile(r'"state":\s*"inCall"', re.I),
    re.compile(r"mediaSession.*started", re.I),
    re.compile(r"OnThePhone"),            # Classic Teams
    re.compile(r"StatusChanged.*InACall", re.I),   # Classic Teams
]

# Patterns that indicate a call has ENDED
_CALL_END_PATTERNS: list[re.Pattern] = [
    re.compile(r"callEnded", re.I),
    re.compile(r"callDisconnected", re.I),
    re.compile(r"leaveCall", re.I),
    re.compile(r"sessionDestroyed", re.I),
    re.compile(r'"state":\s*"(?:available|busy|away|offline)"', re.I),
    re.compile(r"StatusChanged.*Available", re.I),  # Classic Teams
    re.compile(r"OnlineStatusChanged.*Available", re.I),
]


def _find_teams_log() -> Path | None:
    """Return the most-recently-modified Teams log file, or None."""
    # New Teams (SlimCore, Windows Store)
    local_app_data = os.environ.get("LOCALAPPDATA", "")
    slimcore_dir = (
        Path(local_app_data)
        / "Packages"
        / "MSTeams_8wekyb3d8bbwe"
        / "LocalCache"
        / "Microsoft"
        / "MSTeams"
        / "Logs"
    )
    if slimcore_dir.exists():
        candidates = sorted(
            slimcore_dir.glob("MSTeamsNM_SlimCore_*.log"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        if candidates:
            logger.debug(f"[LogWatcher] Using SlimCore log: {candidates[0]}")
            return candidates[0]

    # Classic Teams
    app_data = os.environ.get("APPDATA", "")
    classic_log = Path(app_data) / "Microsoft" / "Teams" / "logs.txt"
    if classic_log.exists():
        logger.debug(f"[LogWatcher] Using classic Teams log: {classic_log}")
        return classic_log

    return None


class TeamsLogWatcher:
    """Tail Teams log files to detect active call state transitions.

    Call ``check()`` on every daemon poll cycle. Returns True if the
    most recent log evidence indicates an active call.
    """

    def __init__(self) -> None:
        self._in_call: bool = False
        self._log_path: Path | None = None
        self._file_pos: int = 0

    def _refresh_log_path(self) -> None:
        """Periodically re-discover the log file (it rotates)."""
        new_path = _find_teams_log()
        if new_path != self._log_path:
            logger.debug(f"[LogWatcher] Log file changed: {new_path}")
            self._log_path = new_path
            self._file_pos = 0  # Reset position for new file

    def check(self) -> bool:
        """Read any new log lines and update call state. Returns current _in_call."""
        self._refresh_log_path()
        if self._log_path is None:
            return self._in_call

        try:
            with open(self._log_path, encoding="utf-8", errors="ignore") as fh:
                fh.seek(self._file_pos)
                new_content = fh.read()
                self._file_pos = fh.tell()

            for line in new_content.splitlines():
                if any(p.search(line) for p in _CALL_START_PATTERNS):
                    if not self._in_call:
                        logger.info("[LogWatcher] Call started (log marker detected)")
                    self._in_call = True
                elif any(p.search(line) for p in _CALL_END_PATTERNS):
                    if self._in_call:
                        logger.info("[LogWatcher] Call ended (log marker detected)")
                    self._in_call = False

        except FileNotFoundError:
            # Log file was rotated; reset on next check
            self._log_path = None
            self._file_pos = 0
        except Exception as exc:
            logger.debug(f"[LogWatcher] Error reading log: {exc}")

        return self._in_call

    def reset(self) -> None:
        """Force state reset (e.g. after manual session stop)."""
        self._in_call = False
        self._file_pos = 0
