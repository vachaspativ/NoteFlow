"""NoteFlow background call detector daemon.

Monitors for active meeting/call sessions using a three-layer signal waterfall:

  Layer 1 — Teams Log Watcher (Windows-only, highest confidence, near-zero latency)
      Tails MSTeamsNM_SlimCore_*.log / classic Teams logs.txt for call state markers.
      A single positive poll is enough (no streak required).

  Layer 2 — Network Activity Monitor (cross-platform, Teams + Google Meet/Chrome)
      Detects ≥ N simultaneous UDP connections from Teams/Chrome processes to
      Microsoft or Google media relay IP ranges, with STUN/TURN port fallback
      for corporate VPN environments.

  Layer 3 — Process-Scoped Window Title Check (Windows fallback)
      Enumerates visible windows owned by known communication-app PIDs and matches
      against confirmed meeting-window title patterns (e.g. "Meeting | ... | Microsoft Teams").

Start recording when: ANY layer fires for `daemon_active_streak_required` consecutive
polls (except Layer 1, which fires immediately on first positive).
Stop recording when: ALL layers silent for 4 consecutive polls (~12 seconds).
"""
from __future__ import annotations

import logging
import sys
import threading
import time
from datetime import datetime

logger = logging.getLogger(__name__)

# Exact executable names for known communication apps (lowercased)
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

MEETING_TITLE_KEYWORDS = (
    "| microsoft teams",
    "teams meeting",
    "zoom meeting",
    "webex meeting",
    "cisco webex meetings",
    "discord call",
    "huddle | ",
    "slack huddle",
    "- google meet",
    "meet - ",
    "in a call",
)

IGNORE_TITLE_PREFIXES = (
    "chat |", "calendar |", "activity |", "teams |", "files |",
    "assignments |", "calls |", "settings |", "notifications |",
    "general |", "feed |", "search |", "help |", "apps |",
)

IGNORE_TITLE_EXACT = {
    "microsoft teams", "teams", "slack", "zoom", "zoom workplace",
    "zoom cloud meetings", "skype", "discord", "cisco webex", "webex",
    "settings", "call history", "microsoft teams - preview",
}


class CallDetectorDaemon:
    """Background service monitoring active communication calls via three signal layers."""

    def __init__(self, controller, poll_interval: float = 3.0):
        self.controller = controller
        self.poll_interval = poll_interval
        self._thread: threading.Thread | None = None
        self._stop_event: threading.Event = threading.Event()
        self.is_in_call: bool = False
        self._is_auto_session: bool = False
        self._active_streak: int = 0
        self._silence_streak: int = 0
        self._last_cooldown_until: float = 0.0

        # Layer 1: Teams log watcher (Windows-only)
        self._log_watcher = None
        if sys.platform.startswith("win"):
            try:
                from noteflow.log_watcher import TeamsLogWatcher
                self._log_watcher = TeamsLogWatcher()
                logger.debug("TeamsLogWatcher initialised")
            except Exception as exc:
                logger.debug(f"TeamsLogWatcher not available: {exc}")

        # Layer 2: Network monitor (cross-platform)
        self._net_monitor = None
        try:
            from noteflow.network_monitor import CallNetworkMonitor
            min_udp = getattr(controller.settings, "daemon_min_udp_connections", 2)
            self._net_monitor = CallNetworkMonitor(min_connections=min_udp)
            logger.debug("CallNetworkMonitor initialised")
        except Exception as exc:
            logger.debug(f"CallNetworkMonitor not available: {exc}")

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self._thread.start()
        print(
            "\n[NoteFlow Daemon] 🎧 Background call listener active. "
            "Monitoring Teams, Zoom, Webex, Slack, Discord, and Google Meet calls...",
            flush=True,
        )
        logger.info("CallDetectorDaemon background thread started.")

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)
        logger.info("CallDetectorDaemon background thread stopped.")

    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive() and not self._stop_event.is_set()

    def notify_session_started(self, is_auto: bool = False) -> None:
        """Called when a recording session starts (manual or auto)."""
        self.is_in_call = is_auto  # Only daemon-initiated sessions participate in auto-termination
        self._is_auto_session = is_auto
        self._silence_streak = 0
        self._active_streak = 0

    def notify_session_stopped(self, manual: bool = False) -> None:
        """Called when a recording session stops (manual or auto)."""
        self.is_in_call = False
        self._is_auto_session = False
        self._silence_streak = 0
        self._active_streak = 0
        if manual:
            self._last_cooldown_until = time.time() + 30.0
        if self._log_watcher:
            self._log_watcher.reset()

    # ------------------------------------------------------------------
    # Signal Layer 1: Teams Log Watcher
    # ------------------------------------------------------------------

    def _signal_log_watcher(self) -> bool:
        """Returns True if Teams log markers indicate an active call."""
        if not getattr(self.controller.settings, "daemon_log_watch_enabled", True):
            return False
        if not self._log_watcher:
            return False
        return self._log_watcher.check()

    # ------------------------------------------------------------------
    # Signal Layer 2: Network Activity Monitor
    # ------------------------------------------------------------------

    def _signal_network(self) -> bool:
        """Returns True if sustained UDP connections to media relay IPs are detected."""
        if not getattr(self.controller.settings, "daemon_network_check_enabled", True):
            return False
        if not self._net_monitor:
            return False
        # Refresh min_connections from latest settings (user may have changed it)
        min_udp = getattr(self.controller.settings, "daemon_min_udp_connections", 2)
        self._net_monitor.min_connections = min_udp
        result = self._net_monitor.check_call_active()
        return result.is_active

    # ------------------------------------------------------------------
    # Signal Layer 3: Process-Scoped Window Title Check
    # ------------------------------------------------------------------

    def _get_comm_process_pids(self) -> set[int]:
        """Return the set of PIDs for currently running communication apps."""
        try:
            import psutil
            return {
                p.pid
                for p in psutil.process_iter(["pid", "name"])
                if p.info.get("name", "").lower() in COMM_PROCESS_NAMES
            }
        except Exception as exc:
            logger.debug(f"PID scan failed: {exc}")
            return set()

    def _signal_window(self) -> bool:
        """Returns True if an active meeting window owned by a comm process is found."""
        if not getattr(self.controller.settings, "daemon_window_check_enabled", True):
            return False
        if not sys.platform.startswith("win"):
            return False
        try:
            import win32gui
            import win32process

            comm_pids = self._get_comm_process_pids()
            if not comm_pids:
                return False

            found: list[str] = []

            def _enum_cb(hwnd, _):
                try:
                    if found:
                        return
                    if not win32gui.IsWindowVisible(hwnd):
                        return
                    title = win32gui.GetWindowText(hwnd).strip()
                    if not title:
                        return
                    _, pid = win32process.GetWindowThreadProcessId(hwnd)
                    if pid not in comm_pids:
                        return
                    title_lower = title.lower()
                    if title_lower in IGNORE_TITLE_EXACT:
                        return
                    if any(title_lower.startswith(p) for p in IGNORE_TITLE_PREFIXES):
                        return
                    if any(kw in title_lower for kw in MEETING_TITLE_KEYWORDS):
                        found.append(title)
                        logger.debug(f"Meeting window: '{title}' (pid={pid})")
                except Exception:
                    pass

            win32gui.EnumWindows(_enum_cb, None)
            return bool(found)
        except Exception as exc:
            logger.debug(f"Window check failed: {exc}")
            return False

    # ------------------------------------------------------------------
    # Combined signal check
    # ------------------------------------------------------------------

    def _check_active_call(self) -> bool:
        """Waterfall across all enabled signal layers.

        Layer 1 (log watcher) returns immediately — no streak required.
        Layers 2 & 3 contribute to the streak counter in _monitor_loop.
        """
        if not sys.platform.startswith("win"):
            return False

        # Layer 1: Teams log — highest confidence, immediate trigger
        if self._signal_log_watcher():
            logger.debug("[Daemon] Active call signal: Teams log watcher")
            return True

        # Layer 2: Network activity — cross-platform, Teams + Google Meet
        if self._signal_network():
            logger.debug("[Daemon] Active call signal: network monitor")
            return True

        # Layer 3: Window title — process-scoped, Windows fallback
        if self._signal_window():
            logger.debug("[Daemon] Active call signal: window title check")
            return True

        return False

    # ------------------------------------------------------------------
    # Monitor loop
    # ------------------------------------------------------------------

    def _monitor_loop(self) -> None:
        streak_required = getattr(
            self.controller.settings, "daemon_active_streak_required", 2
        )

        while not self._stop_event.is_set():
            try:
                now = time.time()
                recording = self.controller.is_recording()

                # Sync state if recording was stopped externally
                if self.is_in_call and not recording:
                    self.is_in_call = False

                active = self._check_active_call()

                # Re-read streak threshold in case settings changed at runtime
                streak_required = getattr(
                    self.controller.settings, "daemon_active_streak_required", 2
                )

                if active:
                    self._silence_streak = 0
                    self._active_streak += 1
                else:
                    self._active_streak = 0
                    self._silence_streak += 1

                # Start recording after N consecutive active polls & past cooldown
                if (
                    active
                    and not self.is_in_call
                    and self._active_streak >= streak_required
                    and now > self._last_cooldown_until
                    and not recording
                ):
                    prefix = getattr(
                        self.controller.settings,
                        "default_meeting_title_prefix",
                        "[NoteFlow] Meeting",
                    )
                    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    auto_title = f"{prefix} {now_str}"

                    print(
                        f"\n[NoteFlow Daemon] 📞 Active call detected! "
                        f"Auto-starting recording for '{auto_title}'...",
                        flush=True,
                    )
                    logger.info("=== Auto-Detected Active Call ===")
                    logger.info(f"Starting session '{auto_title}'...")
                    self.is_in_call = True
                    self._is_auto_session = True
                    try:
                        self.controller.start_session(
                            title=auto_title,
                            mode=self.controller.settings.transcription_mode,
                            theme=self.controller.settings.theme,
                            is_auto_started=True,
                        )
                    except Exception as exc:
                        logger.error(f"Failed to auto-start session: {exc}")
                        self.is_in_call = False
                        self._is_auto_session = False

                # Stop recording ONLY if this was an auto-detected daemon session and all signals went inactive
                elif not active and self.is_in_call and self._is_auto_session and self._silence_streak >= 4:
                    print(
                        "\n[NoteFlow Daemon] 🛑 Call ended — all signals inactive. "
                        "Stopping recording and generating notes...",
                        flush=True,
                    )
                    logger.info("Auto-detected call end. Stopping session...")
                    self.is_in_call = False
                    self._is_auto_session = False
                    try:
                        notes = self.controller.stop_session()
                        print(
                            "[NoteFlow Daemon] ✅ Recording stopped. Notes generation complete.",
                            flush=True,
                        )
                        # Cooldown if transcript was empty (avoids instant re-trigger)
                        if not (notes.get("transcript") or "").strip():
                            logger.info("Empty transcript — entering 15s cooldown.")
                            self._last_cooldown_until = time.time() + 15.0
                    except Exception as exc:
                        logger.error(f"Failed to auto-stop session: {exc}")

            except Exception as exc:
                logger.error(f"Error in CallDetectorDaemon loop: {exc}")

            time.sleep(self.poll_interval)
