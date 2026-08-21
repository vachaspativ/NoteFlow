from __future__ import annotations

import logging
import sys
import threading
import time
from datetime import datetime

logger = logging.getLogger(__name__)

TARGET_COMMUNICATION_KEYWORDS = [
    "teams", "ms-teams", "msteams", "zoom", "webex", "skype", "slack", "chime", "discord"
]

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

    def _check_active_call(self) -> bool:
        if not sys.platform.startswith("win"):
            return False

        # Layer 1: WASAPI Audio Peak Meter check via pycaw
        try:
            from pycaw.pycaw import AudioUtilities, IAudioMeterInformation
            sessions = AudioUtilities.GetAllSessions()
            for session in sessions:
                if session.Process:
                    proc_name = session.Process.name().lower()
                    if any(kw in proc_name for kw in TARGET_COMMUNICATION_KEYWORDS):
                        # AudioSessionStateActive == 1
                        if hasattr(session, "State") and session.State == 1:
                            try:
                                meter = session._ctl.QueryInterface(IAudioMeterInformation)
                                peak = meter.GetPeakValue()
                                if peak > 0.01: # Active audio volume present
                                    return True
                            except Exception:
                                pass
        except Exception as e:
            logger.debug(f"Error querying WASAPI audio sessions: {e}")

        # Layer 2: Explicit meeting/call window title check (ignoring idle app windows)
        try:
            import win32gui
            found_call_window = False

            ignore_exact = ["microsoft teams", "teams", "slack", "zoom", "skype", "discord"]
            ignore_prefixes = ["chat |", "calendar |", "activity |", "teams |", "files |", "assignments |", "calls |"]

            def _enum_window_callback(hwnd, extra):
                nonlocal found_call_window
                if win32gui.IsWindowVisible(hwnd):
                    title = win32gui.GetWindowText(hwnd).lower().strip()
                    if not title:
                        return
                    if title in ignore_exact:
                        return
                    if any(title.startswith(prefix) for prefix in ignore_prefixes):
                        return
                    
                    meeting_keywords = [
                        "meeting |", "teams meeting", "meeting in", "meeting with",
                        "call with", "in a call", "zoom meeting", "webex meeting",
                        "discord call", "huddle |", "slack huddle"
                    ]
                    if any(kw in title for kw in meeting_keywords):
                        found_call_window = True

            win32gui.EnumWindows(_enum_window_callback, None)
            if found_call_window:
                return True
        except Exception as e:
            logger.debug(f"Error checking window titles: {e}")

        return False

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
                    logger.info("Auto-detected call end (silence timeout). Stopping session...")
                    self.is_in_call = False
                    try:
                        notes = self.controller.stop_session()
                        # If transcript was empty, set a 15-second cooldown to prevent infinite re-triggering
                        if not notes.get("transcript") or not notes.get("transcript", "").strip():
                            logger.info("Auto call session had empty transcript. Entering 15s cooldown...")
                            self._last_cooldown_until = time.time() + 15.0
                    except Exception as e:
                        logger.error(f"Failed to auto-stop session: {e}")

            except Exception as e:
                logger.error(f"Error in CallDetectorDaemon loop: {e}")

            time.sleep(self.poll_interval)
