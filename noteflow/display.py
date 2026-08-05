from __future__ import annotations

import asyncio
from datetime import datetime
from pathlib import Path
from typing import Any

from textual import work
from textual.app import App, ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Button, Header, Footer, Input, Label, Switch, RichLog, Static, ProgressBar
from textual.binding import Binding

from noteflow.config import Settings, TranscriptionMode, Theme
from noteflow.controller import SessionController
from noteflow.session_metadata import SessionMetadata
from noteflow.transcript_store import TranscriptStore

class SetupScreen(Screen):
    def compose(self) -> ComposeResult:
        with Vertical(id="setup-container"):
            with Horizontal(id="setup-header"):
                yield Label("🎙️ NoteFlow", id="app-title")
                yield Switch(value=self.app.dark, id="theme-switch")
                yield Label("Dark Mode")
            
            yield Input(placeholder="Enter meeting title...", id="meeting-title")
            
            with Horizontal(id="mode-container"):
                yield Label("BATCH")
                yield Switch(value=True, id="mode-switch") # True for LIVE, false for BATCH
                yield Label("LIVE")
            
            yield Static("Mic: default", id="mic-label")
            yield Button("▶ Start Recording", id="start-btn", variant="success")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "start-btn":
            title_input = self.query_one("#meeting-title", Input)
            title = title_input.value.strip() or "Untitled Meeting"
            
            mode_switch = self.query_one("#mode-switch", Switch)
            mode = TranscriptionMode.LIVE if mode_switch.value else TranscriptionMode.BATCH
            
            theme = Theme.DARK if self.app.dark else Theme.LIGHT
            
            # Start session via controller
            self.app._controller.start_session(title, mode, theme)
            self.app.push_screen(RecordingScreen(title=title, mode=mode))

    def on_switch_changed(self, event: Switch.Changed) -> None:
        if event.switch.id == "theme-switch":
            self.app.dark = event.value
            self.app._settings.theme = Theme.DARK if event.value else Theme.LIGHT
            self.app._settings.save_theme()

class RecordingScreen(Screen):
    def __init__(self, title: str, mode: TranscriptionMode, **kwargs) -> None:
        super().__init__(**kwargs)
        self.meeting_title = title
        self.mode = mode
        self._start_time = datetime.now()
        self._timer = None

    def compose(self) -> ComposeResult:
        with Vertical(id="recording-container"):
            with Horizontal(id="recording-header"):
                yield Label(f"Mode: {self.mode.value}", id="badge-mode")
                yield Label(f"Title: {self.meeting_title}", id="recording-title")
            
            if self.mode == TranscriptionMode.LIVE:
                yield RichLog(id="transcript-log", markup=True)
            else:
                yield Static("Recording in BATCH mode...\nChunks accumulating...", id="batch-status")
            
            with Horizontal(id="recording-footer"):
                yield Label(f"Started: {self._start_time.strftime('%H:%M:%S')}", id="start-time-label")
                yield Label("Duration: 00:00:00", id="duration-label")
            
            yield Button("⏹ Stop & Generate Notes", id="stop-btn", variant="error")

    def on_mount(self) -> None:
        self._timer = self.set_interval(1.0, self._update_timer)
        if self.mode == TranscriptionMode.LIVE:
            self._transcript_timer = self.set_interval(0.5, self._update_transcript)

    def _update_timer(self) -> None:
        duration = datetime.now() - self._start_time
        # format duration to HH:MM:SS
        hours, remainder = divmod(int(duration.total_seconds()), 3600)
        minutes, seconds = divmod(remainder, 60)
        self.query_one("#duration-label", Label).update(f"Duration: {hours:02}:{minutes:02}:{seconds:02}")

    def _update_transcript(self) -> None:
        # Assuming we can fetch the transcript from the controller or store
        if hasattr(self.app._controller, "transcript_store") and self.app._controller.transcript_store:
            store = self.app._controller.transcript_store
            log = self.query_one("#transcript-log", RichLog)
            log.clear()
            for seg in store.get_all_segments():
                log.write(seg.text)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "stop-btn":
            self.app.push_screen(ProcessingScreen())
            self.stop_and_process()

    @work(thread=True)
    def stop_and_process(self) -> None:
        def status_callback(step_num: int, total_steps: int, msg: str):
            self.app.call_from_thread(self._update_processing_screen, step_num, total_steps, msg)
            
        try:
            # We mock the interface to stop_session with status_callback
            self.app._controller.stop_session(status_callback=status_callback) if hasattr(self.app._controller.stop_session, '__code__') and 'status_callback' in self.app._controller.stop_session.__code__.co_varnames else self.app._controller.stop_session()
            self.app.call_from_thread(self._processing_done, True)
        except Exception as e:
            self.app.call_from_thread(self._update_processing_screen, 0, 3, f"Error: {e}")
            self.app.call_from_thread(self._processing_done, False)

    def _update_processing_screen(self, step_num: int, total_steps: int, msg: str) -> None:
        if isinstance(self.app.screen, ProcessingScreen):
            self.app.screen.update_status(step_num, total_steps, msg)

    def _processing_done(self, success: bool) -> None:
        if isinstance(self.app.screen, ProcessingScreen):
            self.app.screen.finish(success)

class ProcessingScreen(Screen):
    def compose(self) -> ComposeResult:
        with Vertical(id="processing-container"):
            yield Label("Processing...", id="processing-header")
            yield Label("Meeting details here", id="processing-details")
            yield ProgressBar(total=3, show_eta=False, id="progress-bar")
            yield Label("Initializing...", id="progress-status")

    def update_status(self, step_num: int, total_steps: int, msg: str) -> None:
        pb = self.query_one("#progress-bar", ProgressBar)
        pb.update(total=total_steps, progress=step_num)
        
        status = self.query_one("#progress-status", Label)
        status.update(f"Step {step_num}/{total_steps}: {msg}")

    def finish(self, success: bool) -> None:
        status = self.query_one("#progress-status", Label)
        if success:
            status.update("✅ Done! Returning to Setup...")
            self.app.notify("Processing complete!", severity="information")
        else:
            status.update("❌ Failed. Returning to Setup...")
            self.app.notify("Processing failed.", severity="error")
        
        # Pop back to setup after 2 seconds
        self.set_timer(2.0, self._pop_to_setup)

    def _pop_to_setup(self) -> None:
        while not isinstance(self.app.screen, SetupScreen):
            self.app.pop_screen()

class NoteFlowApp(App):
    TITLE = "NoteFlow"
    
    CSS_PATH = [
        "css/setup_screen.tcss",
        "css/recording_screen.tcss",
        "css/processing_screen.tcss"
    ]

    def __init__(self, settings: Settings, controller: SessionController, **kwargs) -> None:
        super().__init__(**kwargs)
        self._settings = settings
        self._controller = controller

    def on_mount(self) -> None:
        self.dark = self._settings.theme == Theme.DARK
        self.push_screen(SetupScreen())
