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
        self._is_recording: bool = False
        
        self._transcript_store = TranscriptStore()
        
        # Lazy init components
        self._audio_capture: AudioCapture | None = None
        self._transcriber: WhisperTranscriber | None = None
        self._llm_client = LLMClient(
            host=settings.ollama_host,
            port=settings.ollama_port,
            model=settings.ollama_model,
            timeout=settings.ollama_timeout
        )
        self._email_sender = EmailSender(
            host=settings.smtp_host,
            port=settings.smtp_port,
            use_tls=settings.smtp_use_tls,
            username=settings.smtp_username,
            password=settings.smtp_password,
            email_from=settings.email_from,
            email_to=settings.email_to,
            subject_prefix=settings.email_subject_prefix
        )
        
        self._session: SessionMetadata | None = None
        self._status_callback: Callable[[str, float], None] | None = None
        self._segment_callbacks: list[Callable[[dict[str, Any]], None]] = []
        self._last_processed_notes: dict[str, Any] = {}

        try:
            from noteflow.daemon import CallDetectorDaemon
            self._call_daemon = CallDetectorDaemon(self)
        except Exception as e:
            logger.warning(f"Could not initialize CallDetectorDaemon: {e}")
            self._call_daemon = None

    def sync_daemon_state(self) -> None:
        """Starts or stops the call detection daemon based on configuration."""
        if not self._call_daemon:
            return
        if getattr(self.settings, 'auto_call_detection', False):
            if not self._call_daemon.is_running():
                self._call_daemon.start()
        else:
            if self._call_daemon.is_running():
                self._call_daemon.stop()

    def initialize(self) -> dict[str, bool]:
        """Initializes components and returns status dict."""
        status = {'whisper': False, 'ollama': False, 'microphone': False, 'smtp': False}
        
        self.sync_daemon_state()

        try:
            device_id = getattr(self.settings, 'device_id', None)
            self._audio_capture = AudioCapture(device_id=device_id)
            status['microphone'] = True
        except Exception as e:
            logger.error(f"Microphone init failed: {e}")

        try:
            self._transcriber = WhisperTranscriber(
                model_name=self.settings.whisper_model,
                device=self.settings.whisper_device,
                vad_threshold=self.settings.vad_threshold
            )
            status['whisper'] = True
        except Exception as e:
            logger.error(f"Whisper init failed: {e}")

        try:
            status['ollama'] = self._llm_client.check_available()
        except Exception as e:
            logger.error(f"Ollama init failed: {e}")

        # Check SMTP configuration presence
        status['smtp'] = bool(self.settings.smtp_host and self.settings.smtp_username)

        return status

    def is_recording(self) -> bool:
        """Returns whether a recording session is actively running."""
        return self._is_recording

    def get_current_session_info(self) -> dict[str, Any]:
        """Returns real-time session information."""
        if not self._session:
            return {
                "active": False,
                "title": "",
                "mode": self.settings.transcription_mode.value,
                "theme": self.settings.theme.value,
                "duration_seconds": 0,
                "segment_count": 0,
                "audio_stats": self.get_audio_stats(),
            }

        duration = (datetime.now() - self._session.start_time).total_seconds() if self._is_recording else self._session.duration_seconds

        return {
            "active": self._is_recording,
            "session_id": self._session.session_id,
            "title": self._session.title,
            "mode": self._session.transcription_mode,
            "theme": self._session.theme,
            "start_time": self._session.start_time.isoformat(),
            "end_time": self._session.end_time.isoformat() if self._session.end_time else None,
            "duration_seconds": duration,
            "duration_display": self._format_duration(duration),
            "segment_count": self._transcript_store.segment_count(),
            "audio_stats": self.get_audio_stats(),
            "latest_notes": self._last_processed_notes,
        }

    def add_segment_callback(self, callback: Callable[[dict[str, Any]], None]) -> None:
        """Register a callback invoked when a new transcript segment arrives."""
        if callback not in self._segment_callbacks:
            self._segment_callbacks.append(callback)

    def remove_segment_callback(self, callback: Callable[[dict[str, Any]], None]) -> None:
        """Remove a previously registered segment callback."""
        if callback in self._segment_callbacks:
            self._segment_callbacks.remove(callback)

    def _broadcast_segment(self, timestamp: float, text: str) -> None:
        """Broadcast new segment to all listeners."""
        data = {
            "timestamp": timestamp,
            "timestamp_display": f"[{int(timestamp // 60):02d}:{int(timestamp % 60):02d}]",
            "text": text,
        }
        for cb in list(self._segment_callbacks):
            try:
                cb(data)
            except Exception as e:
                logger.error(f"Error invoking segment callback: {e}")

    def start_session(self, title: str, mode: TranscriptionMode, theme: Theme, device_id: int | None = None) -> SessionMetadata:
        """Starts a recording session."""
        self._session = SessionMetadata(title=title, mode=mode, theme=theme)
        self._transcript_store.reset()
        self._stop_event.clear()
        self._last_processed_notes = {}
        
        target_device = device_id if device_id is not None else getattr(self.settings, 'device_id', None)
        
        if self._audio_capture is None or getattr(self._audio_capture, 'device_id', None) != target_device or getattr(self._audio_capture, 'enable_loopback', True) != getattr(self.settings, 'enable_loopback', True):
            self._audio_capture = AudioCapture(device_id=target_device, enable_loopback=getattr(self.settings, 'enable_loopback', True))
            
        batch_mode = (mode == TranscriptionMode.BATCH)
        self._audio_capture.start(batch_mode=batch_mode)
        self._is_recording = True
        
        if mode == TranscriptionMode.LIVE:
            if self._transcriber is None:
                self._transcriber = WhisperTranscriber(
                    model_name=self.settings.whisper_model,
                    device=self.settings.whisper_device,
                    vad_threshold=self.settings.vad_threshold,
                    allow_online=getattr(self.settings, 'allow_online_model_download', False)
                )
            self._processing_thread = threading.Thread(target=self._processing_loop, daemon=True)
            self._processing_thread.start()
            
        return self._session

    def stop_session(self, status_callback: Callable[[str, float], None] | None = None) -> dict[str, Any]:
        """Stops the recording session and processes the result."""
        if not self._session:
            return {}

        if status_callback:
            self._status_callback = status_callback

        self._stop_event.set()
        self._is_recording = False
        
        self._update_status('Stopping audio capture...', 0.10)
        if self._audio_capture:
            self._audio_capture.stop()
            
        if self._session.mode == TranscriptionMode.LIVE:
            if self._processing_thread and self._processing_thread.is_alive():
                self._update_status('Finalizing live transcription queue...', 0.20)
                self._processing_thread.join(timeout=10.0)
        elif self._session.mode == TranscriptionMode.BATCH:
            self._update_status('Transcribing full recording (Batch mode)...', 0.25)
            if self._audio_capture:
                if self._transcriber is None:
                    self._transcriber = WhisperTranscriber(
                        model_name=self.settings.whisper_model,
                        device=self.settings.whisper_device,
                        vad_threshold=self.settings.vad_threshold,
                        allow_online=getattr(self.settings, 'allow_online_model_download', False)
                    )
                full_audio = self._audio_capture.get_full_audio()
                if full_audio is not None and len(full_audio) > 0:
                    text = self._transcriber.transcribe_full(full_audio)
                    if text.strip():
                        self._transcript_store.append(text)
                        self._broadcast_segment(0.0, text)
        
        self._session.mark_stopped()
        notes = self._generate_and_send()
        self._last_processed_notes = notes
        
        return notes

    def regenerate_notes(self, session_id: str | None = None) -> dict[str, Any]:
        """Re-triggers Ollama note generation for the current session or a saved session by ID."""
        target_transcript = ""
        target_timestamped = ""
        title = "Untitled Meeting"
        duration = "0s"

        if session_id:
            if self._session and self._session.session_id == session_id:
                target_transcript = self._transcript_store.get_full_transcript() or self._last_processed_notes.get("transcript", "")
                target_timestamped = self._transcript_store.get_timestamped_transcript() or self._last_processed_notes.get("timestamped_transcript", "")
                title = self._session.title
                duration = self._session.duration_display()
            else:
                detail = self.get_session_details(session_id)
                if not detail and self._session:
                    target_transcript = self._transcript_store.get_full_transcript() or self._last_processed_notes.get("transcript", "")
                    target_timestamped = self._transcript_store.get_timestamped_transcript() or self._last_processed_notes.get("timestamped_transcript", "")
                    title = self._session.title
                    duration = self._session.duration_display()
                elif not detail:
                    raise ValueError(f"Session '{session_id}' not found")
                else:
                    target_transcript = detail.get("transcript") or detail.get("notes", {}).get("transcript", "")
                    target_timestamped = detail.get("timestamped_transcript") or detail.get("notes", {}).get("timestamped_transcript", "")
                    title = detail.get("title", "Untitled Meeting")
                    duration = detail.get("duration_display", "0s")
        else:
            target_transcript = self._transcript_store.get_full_transcript() or self._last_processed_notes.get("transcript", "")
            target_timestamped = self._transcript_store.get_timestamped_transcript() or self._last_processed_notes.get("timestamped_transcript", "")
            title = self._session.title if self._session else "Untitled Meeting"
            duration = self._session.duration_display() if self._session else "0s"

        if not target_transcript.strip():
            raise ValueError("Cannot regenerate notes: Transcript is empty")

        # Sync LLM client settings with latest controller settings
        self._llm_client.host = self.settings.ollama_host
        self._llm_client.port = self.settings.ollama_port
        self._llm_client.model = self.settings.ollama_model
        self._llm_client.timeout = self.settings.ollama_timeout
        self._llm_client.max_retries = self.settings.ollama_max_retries
        self._llm_client.base_url = f"{self.settings.ollama_host.rstrip('/')}:{self.settings.ollama_port}"

        start_time = datetime.now().isoformat()
        end_time = datetime.now().isoformat()
        if self._session:
            start_time = self._session.start_time.isoformat()
            if self._session.end_time:
                end_time = self._session.end_time.isoformat()

        notes: dict[str, Any] = {
            "title": title,
            "transcript": target_transcript,
            "timestamped_transcript": target_timestamped,
            "duration": duration,
            "start_time": start_time,
            "end_time": end_time,
            "summary": "Note generation failed.",
            "action_items": [],
            "highlights": [],
            "decisions": [],
        }

        self._update_status('Re-generating structured notes with Ollama...', 0.50)
        try:
            generated = self._llm_client.generate_notes(target_transcript, title, duration)
            notes.update(generated)
        except Exception as e:
            logger.error(f"LLM generation failed during regeneration: {e}")
            notes["summary"] = f"(Note generation failed after retries: {e})"
            notes["action_items"] = []
            notes["highlights"] = []
            notes["decisions"] = []
            notes["error"] = str(e)

        self._update_status('Saving updated session archive and markdown...', 0.90)
        json_path = self._write_session_archive(notes, target_transcript)
        md_path = self._write_markdown_backup(notes, target_transcript)

        notes["json_archive"] = str(json_path)
        notes["markdown_file"] = str(md_path)

        self._last_processed_notes = notes
        self._update_status('Regeneration complete!', 1.0)
        return notes

    def _processing_loop(self) -> None:
        """Processing loop for LIVE mode."""
        if not self._audio_capture or not self._transcriber:
            return
            
        while not self._stop_event.is_set():
            chunk = self._audio_capture.get_chunk(timeout=0.5)
            if chunk is not None:
                text = self._transcriber.transcribe_chunk(chunk)
                if text.strip():
                    self._transcript_store.append(text)
                    elapsed = time.time() - self._transcript_store._start_time
                    self._broadcast_segment(elapsed, text)

        # Drain any remaining audio chunks
        while True:
            chunk = self._audio_capture.get_chunk(timeout=0.2)
            if chunk is None:
                break
            text = self._transcriber.transcribe_chunk(chunk)
            if text.strip():
                self._transcript_store.append(text)
                elapsed = time.time() - self._transcript_store._start_time
                self._broadcast_segment(elapsed, text)

    def _generate_and_send(self) -> dict[str, Any]:
        """Generates notes via LLM, sends email, and saves backups."""
        transcript = self._transcript_store.get_full_transcript()
        timestamped_transcript = self._transcript_store.get_timestamped_transcript()
        title = self._session.title if self._session else "Untitled Meeting"
        duration = self._session.duration_display() if self._session else "0s"
        start_time = self._session.start_time.strftime('%Y-%m-%d %H:%M:%S') if self._session else datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        end_time = self._session.end_time.strftime('%Y-%m-%d %H:%M:%S') if self._session and self._session.end_time else datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        notes: dict[str, Any] = {
            "title": title,
            "transcript": transcript,
            "timestamped_transcript": timestamped_transcript,
            "summary": "No speech detected during this session.",
            "action_items": [],
            "highlights": [],
            "decisions": [],
            "duration": duration,
            "start_time": start_time,
            "end_time": end_time,
        }
        
        self._update_status('Generating structured notes with Ollama...', 0.50)
        try:
            if transcript.strip():
                self._llm_client.host = self.settings.ollama_host
                self._llm_client.port = self.settings.ollama_port
                self._llm_client.model = self.settings.ollama_model
                self._llm_client.timeout = self.settings.ollama_timeout
                self._llm_client.max_retries = self.settings.ollama_max_retries
                self._llm_client.base_url = f"{self.settings.ollama_host.rstrip('/')}:{self.settings.ollama_port}"
                generated = self._llm_client.generate_notes(transcript, title, duration)
                notes.update(generated)
            else:
                logger.warning("Empty transcript, skipping LLM generation.")
        except Exception as e:
            logger.error(f"LLM generation failed: {e}")
            notes["summary"] = f"(Note generation failed after retries: {e})"
            notes["action_items"] = []
            notes["highlights"] = []
            notes["decisions"] = []
            notes["error"] = str(e)
            
        should_send = (
            not getattr(self.settings, 'dry_run', False) and 
            getattr(self.settings, 'enable_email', True) and 
            bool(self.settings.email_to)
        )
        
        if should_send:
            self._update_status('Sending meeting notes via SMTP...', 0.75)
            try:
                self._email_sender.send(
                    notes=notes,
                    title=title,
                    duration=duration,
                    start_time=start_time,
                    end_time=end_time,
                    transcript=timestamped_transcript or transcript
                )
                notes["email_sent"] = True
            except Exception as e:
                logger.error(f"Email sending failed: {e}")
                notes["email_sent"] = False
                notes["email_error"] = str(e)
        else:
            is_dry = getattr(self.settings, 'dry_run', False)
            email_disabled = not getattr(self.settings, 'enable_email', True)
            if is_dry:
                msg = 'Dry Run mode active (SMTP email skipped)...'
            elif email_disabled:
                msg = 'Automatic email dispatch disabled in settings...'
            else:
                msg = 'No recipient email configured, skipping SMTP email...'
            self._update_status(msg, 0.75)
            logger.info(msg)
            notes["email_sent"] = False
            
        self._update_status('Saving session archive and markdown...', 0.90)
        json_path = self._write_session_archive(notes, transcript)
        md_path = self._write_markdown_backup(notes, transcript)
        
        notes["json_archive"] = str(json_path)
        notes["markdown_file"] = str(md_path)
        
        self._update_status('Processing complete!', 1.0)
        return notes

    def _write_session_archive(self, notes: dict[str, Any], transcript: str) -> Path:
        """Writes JSON archive of the session."""
        sessions_dir = self.settings.get_sessions_dir()
        
        if self._session:
            filename = self._session.archive_filename()
        else:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"session_{timestamp}.json"
            
        filepath = sessions_dir / filename
        
        data = {
            "session_id": self._session.session_id if self._session else "manual",
            "title": self._session.title if self._session else "Untitled Meeting",
            "mode": self._session.transcription_mode if self._session else "live",
            "theme": self._session.theme if self._session else "dark",
            "start_time": self._session.start_time.isoformat() if self._session else datetime.now().isoformat(),
            "end_time": self._session.end_time.isoformat() if self._session and self._session.end_time else datetime.now().isoformat(),
            "duration_seconds": self._session.duration_seconds if self._session else 0,
            "duration_display": self._session.duration_display() if self._session else "0s",
            "notes": notes,
            "transcript": transcript,
            "timestamped_transcript": self._transcript_store.get_timestamped_transcript(),
        }
        
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
            
        return filepath

    def _write_markdown_backup(self, notes: dict[str, Any], transcript: str) -> Path:
        """Writes markdown backup of the notes."""
        notes_dir = self.settings.get_notes_dir()
        
        if self._session:
            safe_title = self._session.sanitized_filename()
            date_str = self._session.start_time.strftime("%Y-%m-%d")
            filename = f"{date_str}_{safe_title}_{self._session.session_id}.md"
        else:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"notes_{timestamp}.md"
            
        filepath = notes_dir / filename
        
        title = notes.get('title', 'Untitled Meeting')
        duration = notes.get('duration', '')
        summary = notes.get('summary', '')
        action_items = notes.get('action_items', [])
        highlights = notes.get('highlights', [])
        decisions = notes.get('decisions', [])
        
        content = f"# 📝 {title}\n\n"
        content += f"**Duration:** {duration} | **Recorded:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
        content += "---\n\n"
        content += f"## 📋 Executive Summary\n{summary}\n\n"
        
        if action_items:
            content += "## ✅ Action Items\n"
            for item in action_items:
                if isinstance(item, dict):
                    owner = item.get('owner', 'Unassigned')
                    action = item.get('action', '')
                    deadline = item.get('deadline', 'Not specified')
                    content += f"- [ ] **{owner}**: {action} *(Due: {deadline})*\n"
                else:
                    content += f"- [ ] {item}\n"
            content += "\n"
            
        if highlights:
            content += "## 💡 Key Highlights\n"
            for hl in highlights:
                content += f"- {hl}\n"
            content += "\n"
            
        if decisions:
            content += "## 🎯 Decisions Made\n"
            for dec in decisions:
                content += f"- {dec}\n"
            content += "\n"
            
        content += "## 🎙️ Transcript\n\n"
        timestamped = notes.get('timestamped_transcript') or self._transcript_store.get_timestamped_transcript()
        content += timestamped if timestamped else transcript
        content += "\n\n---\n*Generated by NoteFlow (100% Offline AI)*\n"
        
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)
            
        return filepath

    def get_history_sessions(self) -> list[dict[str, Any]]:
        """Scans the sessions directory and returns metadata for past meetings."""
        sessions_dir = self.settings.get_sessions_dir()
        if not sessions_dir.exists():
            return []
            
        results = []
        for file in sorted(sessions_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
            try:
                with open(file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    results.append({
                        "file_name": file.name,
                        "session_id": data.get("session_id", file.stem),
                        "title": data.get("title", "Untitled Meeting"),
                        "mode": data.get("mode", "live"),
                        "start_time": data.get("start_time", ""),
                        "duration_display": data.get("duration_display", "0s"),
                        "summary_preview": (data.get("notes", {}).get("summary", "")[:150] + "...") if data.get("notes", {}).get("summary") else "No summary available",
                        "action_items_count": len(data.get("notes", {}).get("action_items", [])),
                    })
            except Exception as e:
                logger.error(f"Error reading session file {file}: {e}")
                
        return results

    def get_session_details(self, session_id: str) -> dict[str, Any] | None:
        """Retrieves full notes and transcript for a given session."""
        sessions_dir = self.settings.get_sessions_dir()
        if not sessions_dir.exists():
            return None
            
        for file in sessions_dir.glob("*.json"):
            if session_id in file.name:
                try:
                    with open(file, "r", encoding="utf-8") as f:
                        return json.load(f)
                except Exception as e:
                    logger.error(f"Error reading session detail {file}: {e}")
        return None

    def resend_session_email(self, session_id: str, email_to: str | None = None) -> bool:
        """Re-dispatches email for a past session."""
        data = self.get_session_details(session_id)
        if not data:
            return False
            
        notes = data.get("notes", {})
        title = data.get("title", "Untitled Meeting")
        duration = data.get("duration_display", "0s")
        start_time = data.get("start_time", "")
        end_time = data.get("end_time", "")
        transcript = data.get("timestamped_transcript") or data.get("transcript", "")
        
        target_email = email_to or self.settings.email_to
        if not target_email:
            return False
            
        try:
            self._email_sender.email_to = target_email
            self._email_sender.send(
                notes=notes,
                title=title,
                duration=duration,
                start_time=start_time,
                end_time=end_time,
                transcript=transcript
            )
            return True
        except Exception as e:
            logger.error(f"Resend email failed: {e}")
            return False

    def _update_status(self, message: str, progress: float) -> None:
        """Calls the status callback if configured."""
        if self._status_callback:
            try:
                self._status_callback(message, progress)
            except Exception as e:
                logger.error(f"Error updating status: {e}")

    def set_status_callback(self, callback: Callable[[str, float], None]) -> None:
        """Sets the callback for status updates."""
        self._status_callback = callback

    def get_transcript_store(self) -> TranscriptStore:
        """Returns the transcript store."""
        return self._transcript_store

    def get_audio_stats(self) -> dict[str, Any]:
        """Returns stats from audio capture."""
        if self._audio_capture:
            return self._audio_capture.get_stats()
        return {"chunk_count": 0, "dropped_chunks": 0, "approx_size_mb": 0.0}

    @staticmethod
    def _format_duration(seconds: float) -> str:
        """Format seconds into HH:MM:SS string."""
        total_secs = int(seconds)
        h = total_secs // 3600
        m = (total_secs % 3600) // 60
        s = total_secs % 60
        if h > 0:
            return f"{h:02d}:{m:02d}:{s:02d}"
        return f"{m:02d}:{s:02d}"
