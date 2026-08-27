from __future__ import annotations

import logging
import sys
import threading
import time
from datetime import datetime

logger = logging.getLogger(__name__)

# Exact executable names for communication apps (lowercased)
COMM_PROCESS_NAMES = {
    "teams.exe", "ms-teams.exe", "msteams.exe",
    "zoom.exe", "zoomit.exe",
    "webexmta.exe", "webex.exe", "ciscowebexmeetings.exe",
    "skype.exe", "skypeforbus.exe",
    "slack.exe",
    "discord.exe",
    "chime.exe",
    "lync.exe",
}

# Window title substrings that positively identify an ACTIVE call/meeting window.
# These are intentionally precise to avoid matching browser tabs, Outlook invites, etc.
MEETING_TITLE_KEYWORDS = (
    "| microsoft teams",    # Teams meeting windows always end with this
    "teams meeting",
    "zoom meeting",
    "webex meeting",
    "cisco webex meetings",
    "discord call",
    "huddle | ",
    "slack huddle",
    "- google meet",
    "meet - ",
    "in a call",            # Slack/Discord "In a Call" window
)

# Titles to ignore outright even if they contain a keyword above
IGNORE_TITLE_PREFIXES = (
    "chat |",
    "calendar |",
    "activity |",
    "teams |",
    "files |",
    "assignments |",
    "calls |",
    "settings |",
    "notifications |",
    "general |",
    "feed |",
    "search |",
    "help |",
    "apps |",
)

IGNORE_TITLE_EXACT = {
    "microsoft teams",
    "teams",
    "slack",
    "zoom",
    "zoom workplace",
    "zoom cloud meetings",
    "skype",
    "discord",
    "cisco webex",
    "webex",
    "settings",
    "call history",
    "microsoft teams - preview",
}


class CallDetectorDaemon:
    """Background service monitoring active communication calls."""

    def __init__(self, controller, poll_interval: float = 3.0):
        self.controller = controller
        self.poll_interval = poll_interval
        self._thread: threading.Thread | None = None
        self._stop_event: threading.Event = threading.Event()
        self.is_in_call: bool = False
        self._active_streak: int = 0
        self._silence_streak: int = 0
        self._last_cooldown_until: float = 0.0

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self._thread.start()
        print("\n[NoteFlow Daemon] 🎧 Background call listener active. Monitoring Teams, Zoom, Webex, Slack, and Discord calls...", flush=True)
        logger.info("CallDetectorDaemon background thread started.")

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)
        logger.info("CallDetectorDaemon background thread stopped.")

    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive() and not self._stop_event.is_set()

    def notify_session_started(self) -> None:
        """Called when a recording session starts."""
        self.is_in_call = True

    def notify_session_stopped(self, manual: bool = False) -> None:
        """Called when a recording session stops."""
        self.is_in_call = False
        if manual:
            self._last_cooldown_until = time.time() + 30.0

    def _get_comm_process_pids(self) -> set[int]:
        """Return the set of PIDs currently running known communication apps."""
        try:
            import psutil
            pids = set()
            for proc in psutil.process_iter(["pid", "name"]):
                try:
                    if proc.info["name"] and proc.info["name"].lower() in COMM_PROCESS_NAMES:
                        pids.add(proc.info["pid"])
                except Exception:
                    pass
            return pids
        except Exception as e:
            logger.debug(f"psutil process scan failed: {e}")
            return set()

    def _has_meeting_window(self) -> bool:
        """Check for an active meeting window owned by a known communication process.

        Key design constraint: we ONLY accept windows whose owning process is a known
        communication executable (Teams, Zoom, Webex, etc.).  This prevents false
        positives from browser tabs, Outlook calendar invites, or any other application
        that incidentally has "meeting" in its title.
        """
        try:
            import win32gui
            import win32process

            # First collect comm-app PIDs so we only match their windows
            comm_pids = self._get_comm_process_pids()
            if not comm_pids:
                # No known communication app is running at all
                return False

            found_match: list[str] = []   # non-local mutable via list

            def _enum_cb(hwnd, _):
                try:
                    if found_match:          # already found one, skip
                        return
                    if not win32gui.IsWindowVisible(hwnd):
                        return
                    title = win32gui.GetWindowText(hwnd).strip()
                    if not title:
                        return

                    # Only consider windows owned by comm apps
                    _, pid = win32process.GetWindowThreadProcessId(hwnd)
                    if pid not in comm_pids:
                        return

                    title_lower = title.lower()

                    if title_lower in IGNORE_TITLE_EXACT:
                        return
                    if any(title_lower.startswith(p) for p in IGNORE_TITLE_PREFIXES):
                        return

                    if any(kw in title_lower for kw in MEETING_TITLE_KEYWORDS):
                        found_match.append(title)
                        logger.debug(f"Meeting window detected: '{title}' (pid={pid})")
                except Exception:
                    pass   # never raise inside EnumWindows callback

            win32gui.EnumWindows(_enum_cb, None)
            return bool(found_match)

        except Exception as e:
            logger.debug(f"Error in _has_meeting_window: {e}")
            return False

    def _has_active_comm_audio(self) -> bool:
        """Check WASAPI peak meters for communication processes with substantial audio."""
        try:
            from pycaw.pycaw import AudioUtilities, IAudioMeterInformation
            sessions = AudioUtilities.GetAllSessions()
            for session in sessions:
                if session.Process:
                    proc_name = session.Process.name().lower()
                    if proc_name in COMM_PROCESS_NAMES:
                        if hasattr(session, "State") and session.State == 1:
                            try:
                                meter = session._ctl.QueryInterface(IAudioMeterInformation)
                                peak = meter.GetPeakValue()
                                # Require >5% to ignore idle dither, Bluetooth keepalives, and notification pings
                                if peak > 0.05:
                                    return True
                            except Exception:
                                pass
        except Exception as e:
            logger.debug(f"Error querying WASAPI audio sessions: {e}")
        return False

    def _check_active_call(self) -> bool:
        """Determines if a real meeting/call is actively in progress.

        Strategy:
        - Primary gate: a meeting/call window must be open AND owned by a known
          communication process (not just any window with "meeting" in the title).
        - This eliminates false positives from browser tabs, Outlook calendar
          reminders, Bluetooth audio device connections, and notification pings.
        """
        if not sys.platform.startswith("win"):
            return False

        return self._has_meeting_window()

    def _monitor_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                now = time.time()
                recording = self.controller.is_recording()

                # Sync state if recording was stopped externally
                if self.is_in_call and not recording:
                    self.is_in_call = False

                active = self._check_active_call()

                if active:
                    self._silence_streak = 0
                    self._active_streak += 1
                else:
                    self._active_streak = 0
                    self._silence_streak += 1

                # Require 2 consecutive active polls (6 seconds) & past cooldown before starting
                if active and not self.is_in_call and self._active_streak >= 2 and now > self._last_cooldown_until:
                    # Double check if controller is already recording manually
                    if not recording:
                        prefix = getattr(self.controller.settings, "default_meeting_title_prefix", "[NoteFlow] Meeting")
                        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        auto_title = f"{prefix} {now_str}"

                        print(f"\n[NoteFlow Daemon] 📞 Active call detected! Auto-starting recording for '{auto_title}'...", flush=True)
                        logger.info("=== Auto-Detected Active Call ===")
                        logger.info(f"Auto-detected active call! Starting session '{auto_title}'...")
                        self.is_in_call = True
                        try:
                            self.controller.start_session(
                                title=auto_title,
                                mode=self.controller.settings.transcription_mode,
                                theme=self.controller.settings.theme
                            )
                        except Exception as e:
                            logger.error(f"Failed to auto-start session: {e}")

                # Require 4 consecutive silent polls (12 seconds) before stopping active call
                elif not active and self.is_in_call and self._silence_streak >= 4:
                    print(f"\n[NoteFlow Daemon] 🛑 Call ended — meeting window closed. Stopping recording and generating notes...", flush=True)
                    logger.info("Auto-detected call end (meeting window closed). Stopping session...")
                    self.is_in_call = False
                    try:
                        notes = self.controller.stop_session()
                        print(f"[NoteFlow Daemon] ✅ Recording stopped. Notes generation complete.", flush=True)
                        # If transcript was empty, set a 15-second cooldown to prevent infinite re-triggering
                        if not notes.get("transcript") or not notes.get("transcript", "").strip():
                            logger.info("Auto call session had empty transcript. Entering 15s cooldown...")
                            self._last_cooldown_until = time.time() + 15.0
                    except Exception as e:
                        logger.error(f"Failed to auto-stop session: {e}")

            except Exception as e:
                logger.error(f"Error in CallDetectorDaemon loop: {e}")

            time.sleep(self.poll_interval)
