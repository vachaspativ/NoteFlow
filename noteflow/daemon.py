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

    def _check_active_call(self) -> bool:
        if not sys.platform.startswith("win"):
            return False

        # Layer 1: Check Windows Audio Sessions (pycaw)
        try:
            from pycaw.pycaw import AudioUtilities
            sessions = AudioUtilities.GetAllSessions()
            for session in sessions:
                if session.Process:
                    proc_name = session.Process.name().lower()
                    if any(kw in proc_name for kw in TARGET_COMMUNICATION_KEYWORDS):
                        # AudioSessionStateActive == 1
                        if hasattr(session, "State") and session.State == 1:
                            return True
        except Exception as e:
            logger.debug(f"Error querying WASAPI audio sessions: {e}")

        # Layer 2: Window title inspection for active call / meeting windows
        try:
            import win32gui
            found_call_window = False

            def _enum_window_callback(hwnd, extra):
                nonlocal found_call_window
                if win32gui.IsWindowVisible(hwnd):
                    title = win32gui.GetWindowText(hwnd).lower()
                    if title:
                        if any(kw in title for kw in ["meeting", "call with", "in a call", "teams meeting", "zoom meeting", "webex meeting"]):
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
                active = self._check_active_call()
                if active and not self.is_in_call:
                    prefix = getattr(self.controller.settings, "default_meeting_title_prefix", "[NoteFlow] Meeting")
                    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    auto_title = f"{prefix} {now_str}"
                    
                    logger.info(f"Auto-detected active call! Auto-starting session '{auto_title}'...")
                    self.is_in_call = True
                    try:
                        self.controller.start_session(
                            title=auto_title,
                            mode=self.controller.settings.transcription_mode,
                            theme=self.controller.settings.theme
                        )
                    except Exception as e:
                        logger.error(f"Failed to auto-start session: {e}")

                elif not active and self.is_in_call:
                    logger.info("Auto-detected call end! Auto-stopping session...")
                    self.is_in_call = False
                    try:
                        self.controller.stop_session()
                    except Exception as e:
                        logger.error(f"Failed to auto-stop session: {e}")

            except Exception as e:
                logger.error(f"Error in CallDetectorDaemon loop: {e}")

            time.sleep(self.poll_interval)
