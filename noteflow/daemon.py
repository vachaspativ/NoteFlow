from __future__ import annotations

import logging
import sys
import threading
import time
from datetime import datetime

logger = logging.getLogger(__name__)

TARGET_COMMUNICATION_APPS = [
    "teams.exe", "ms-teams.exe", "zoom.exe",
    "webex.exe", "skype.exe", "slack.exe"
]

class CallDetectorDaemon:
    """Background service monitoring active communication calls."""

    def __init__(self, controller, poll_interval: float = 3.0):
        self.controller = controller
        self.poll_interval = poll_interval
        self._thread: threading.Thread | None = None
        self._stop_event: threading.Event = threading.Event()
        self.is_in_call: bool = False

    def start() -> None:
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self._thread.start()
        logger.info("CallDetectorDaemon background thread started.")

    def stop() -> None:
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)
        logger.info("CallDetectorDaemon background thread stopped.")

    def _check_active_call() -> bool:
        if not sys.platform.startswith("win"):
            return False

        try:
            from pycaw.pycaw import AudioUtilities
            sessions = AudioUtilities.GetAllSessions()
            for session in sessions:
                if session.Process:
                    proc_name = session.Process.name().lower()
                    if proc_name in TARGET_COMMUNICATION_APPS:
                        # AudioSessionStateActive == 1
                        if hasattr(session, "State") and session.State == 1:
                            return True
        except Exception as e:
            logger.debug(f"Error querying WASAPI audio sessions: {e}")

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
