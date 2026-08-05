from __future__ import annotations

import json
import logging
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Callable, Any

from noteflow.config import Settings, TranscriptionMode, Theme
from noteflow.session_metadata import SessionMetadata
from noteflow.transcript_store import TranscriptStore
from noteflow.llm_client import LLMClient, OllamaNotAvailableError
from noteflow.email_sender import EmailSender
from noteflow.audio_capture import AudioCapture
from noteflow.transcription import WhisperTranscriber

logger = logging.getLogger(__name__)

class SessionController:
    def __init__(self, settings: Settings):
        self.settings = settings
        self._stop_event = threading.Event()
        self._processing_thread: threading.Thread | None = None
        
        self._transcript_store = TranscriptStore()
        
        # Lazy init components
        self._audio_capture: AudioCapture | None = None
        self._transcriber: WhisperTranscriber | None = None
        self._llm_client = LLMClient(settings)
        self._email_sender = EmailSender(settings)
        
        self._session: SessionMetadata | None = None
        self._status_callback: Callable[[str, float], None] | None = None

    def initialize(self) -> dict[str, bool]:
        """Initializes components and returns status dict."""
        status = {'whisper': False, 'ollama': False, 'microphone': False}
        
        try:
            self._audio_capture = AudioCapture()
            status['microphone'] = True
        except Exception as e:
            logger.error(f"Microphone init failed: {e}")

        try:
            self._transcriber = WhisperTranscriber(self.settings)
            status['whisper'] = True
        except Exception as e:
            logger.error(f"Whisper init failed: {e}")

        try:
            # Simple check if ollama is alive
            status['ollama'] = self._llm_client.check_availability()
        except Exception as e:
            logger.error(f"Ollama init failed: {e}")

        return status

    def start_session(self, title: str, mode: TranscriptionMode, theme: Theme) -> SessionMetadata:
        """Starts a recording session."""
        self._session = SessionMetadata(title=title, mode=mode, theme=theme)
        self._transcript_store.reset()
        self._stop_event.clear()
        
        if not self._audio_capture:
            self._audio_capture = AudioCapture()
            
        batch_mode = (mode == TranscriptionMode.BATCH)
        self._audio_capture.start(batch_mode=batch_mode)
        
        if mode == TranscriptionMode.LIVE:
            self._processing_thread = threading.Thread(target=self._processing_loop, daemon=True)
            self._processing_thread.start()
            
        return self._session

    def stop_session(self) -> dict:
        """Stops the recording session and processes the result."""
        if not self._session:
            return {}

        self._stop_event.set()
        
        if self._audio_capture:
            self._audio_capture.stop()
            
        if self._session.mode == TranscriptionMode.LIVE:
            if self._processing_thread:
                self._processing_thread.join()
        elif self._session.mode == TranscriptionMode.BATCH:
            if self._audio_capture and self._transcriber:
                full_audio = self._audio_capture.get_full_audio()
                if full_audio is not None:
                    result = self._transcriber.transcribe_full(full_audio)
                    for seg in result:
                        self._transcript_store.append(seg)
        
        self._session.mark_stopped()
        notes = self._generate_and_send()
        
        return notes

    def _processing_loop(self) -> None:
        """Processing loop for LIVE mode."""
        if not self._audio_capture or not self._transcriber:
            return
            
        while not self._stop_event.is_set() or not self._audio_capture.is_queue_empty():
            chunk = self._audio_capture.get_chunk()
            if chunk is not None:
                segments = self._transcriber.transcribe_chunk(chunk)
                for seg in segments:
                    self._transcript_store.append(seg)
            else:
                time.sleep(0.1)

    def _generate_and_send(self) -> dict:
        """Generates notes via LLM, sends email, and saves backups."""
        transcript = self._transcript_store.get_full_text()
        title = self._session.title if self._session else "Untitled"
        duration = self._session.duration if self._session else 0
        start_time = self._session.start_time if self._session else datetime.now()
        end_time = self._session.end_time if self._session else datetime.now()
        
        notes = {"title": title, "transcript": transcript, "summary": "", "action_items": []}
        
        self._update_status('Generating notes...', 0.33)
        try:
            if transcript.strip():
                notes = self._llm_client.generate_notes(transcript, title, duration)
            else:
                logger.warning("Empty transcript, skipping LLM generation.")
        except Exception as e:
            logger.error(f"LLM generation failed: {e}")
            
        self._update_status('Sending email...', 0.66)
        if not getattr(self.settings, 'dry_run', False):
            try:
                self._email_sender.send(
                    notes=notes,
                    title=title,
                    duration=duration,
                    start_time=start_time,
                    end_time=end_time,
                    transcript=transcript
                )
            except Exception as e:
                logger.error(f"Email sending failed: {e}")
        else:
            logger.info("Dry run enabled, skipping email.")
            
        self._update_status('Saving session...', 0.90)
        self._write_session_archive(notes, transcript)
        self._write_markdown_backup(notes, transcript)
        
        self._update_status('Done', 1.0)
        return notes

    def _write_session_archive(self, notes: dict, transcript: str) -> Path:
        """Writes JSON archive of the session."""
        sessions_dir = Path("sessions")
        sessions_dir.mkdir(parents=True, exist_ok=True)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filepath = sessions_dir / f"session_{timestamp}.json"
        
        data = {
            "title": self._session.title if self._session else "",
            "mode": self._session.mode.name if self._session else "",
            "start_time": self._session.start_time.isoformat() if self._session else "",
            "end_time": self._session.end_time.isoformat() if self._session and self._session.end_time else "",
            "duration": self._session.duration if self._session else 0,
            "notes": notes,
            "transcript": transcript
        }
        
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
            
        return filepath

    def _write_markdown_backup(self, notes: dict, transcript: str) -> Path:
        """Writes markdown backup of the notes."""
        notes_dir = Path("notes")
        notes_dir.mkdir(parents=True, exist_ok=True)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filepath = notes_dir / f"notes_{timestamp}.md"
        
        content = f"# {notes.get('title', 'Untitled')}\n\n"
        content += f"## Summary\n{notes.get('summary', '')}\n\n"
        content += "## Action Items\n"
        for item in notes.get('action_items', []):
            content += f"- {item}\n"
        content += f"\n## Transcript\n{transcript}\n"
        
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)
            
        return filepath

    def _update_status(self, message: str, progress: float) -> None:
        """Calls the status callback if configured."""
        if self._status_callback:
            self._status_callback(message, progress)

    def set_status_callback(self, callback: Callable[[str, float], None]) -> None:
        """Sets the callback for status updates."""
        self._status_callback = callback

    def get_transcript_store(self) -> TranscriptStore:
        """Returns the transcript store."""
        return self._transcript_store

    def get_audio_stats(self) -> dict:
        """Returns stats from audio capture."""
        if self._audio_capture:
            return self._audio_capture.get_stats()
        return {}
