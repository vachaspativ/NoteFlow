from __future__ import annotations

import threading
from unittest.mock import Mock, patch, MagicMock

import pytest

from noteflow.config import Settings, TranscriptionMode, Theme
from noteflow.controller import SessionController


@pytest.fixture
def settings():
    s = Settings(
        theme=Theme.DARK,
        transcription_mode=TranscriptionMode.LIVE,
        whisper_model="base.en",
        whisper_device="cpu",
        chunk_duration_secs=3,
        vad_threshold=0.5,
        ollama_host="http://localhost",
        ollama_port=11434,
        ollama_model="llama3",
        ollama_timeout=120,
        smtp_host="smtp.gmail.com",
        smtp_port=587,
        smtp_use_tls=True,
        smtp_username="you@gmail.com",
        smtp_password="xxxx",
        email_from="you@gmail.com",
        email_to="recipient@ex.com",
        email_subject_prefix="[NoteFlow]",
    )
    s.dry_run = False
    return s


@pytest.fixture
def controller(settings):
    return SessionController(settings)


@patch("noteflow.controller.AudioCapture")
@patch("noteflow.controller.WhisperTranscriber")
def test_initialize_returns_status_dict(mock_whisper, mock_audio, controller):
    controller._llm_client.check_available = Mock(return_value=True)
    status = controller.initialize()
    
    assert status['whisper'] is True
    assert status['ollama'] is True
    assert status['microphone'] is True
    assert status['smtp'] is True


@patch("noteflow.controller.AudioCapture")
def test_start_session_creates_metadata(mock_audio, controller):
    metadata = controller.start_session("Test Title", TranscriptionMode.BATCH, Theme.LIGHT)
    
    assert metadata.title == "Test Title"
    assert metadata.mode == TranscriptionMode.BATCH
    assert metadata.theme == Theme.LIGHT
    assert controller._session == metadata


@patch("noteflow.controller.AudioCapture")
@patch("noteflow.controller.WhisperTranscriber")
def test_live_mode_starts_processing_thread(mock_whisper, mock_audio, controller):
    with patch("threading.Thread") as mock_thread:
        controller.start_session("Live Title", TranscriptionMode.LIVE, Theme.DARK)
        mock_thread.assert_called_once()
        mock_thread.return_value.start.assert_called_once()


@patch("noteflow.controller.AudioCapture")
def test_batch_mode_does_not_start_processing_thread(mock_audio, controller):
    with patch("threading.Thread") as mock_thread:
        controller.start_session("Batch Title", TranscriptionMode.BATCH, Theme.DARK)
        mock_thread.assert_not_called()


@patch("noteflow.controller.AudioCapture")
@patch("noteflow.controller.WhisperTranscriber")
def test_stop_session_calls_mark_stopped(mock_whisper, mock_audio, controller):
    controller.start_session("Title", TranscriptionMode.BATCH, Theme.DARK)
    controller._generate_and_send = Mock(return_value={})
    
    controller.stop_session()
    
    assert controller._session.end_time is not None


@patch("noteflow.controller.AudioCapture")
@patch("noteflow.controller.WhisperTranscriber")
def test_stop_session_live_gets_transcript(mock_whisper, mock_audio, controller):
    with patch("threading.Thread") as mock_thread_cls:
        mock_thread = Mock()
        mock_thread_cls.return_value = mock_thread
        controller.start_session("Title", TranscriptionMode.LIVE, Theme.DARK)
        controller._generate_and_send = Mock(return_value={})
        
        controller.stop_session()
        
        mock_thread.join.assert_called_once()


@patch("noteflow.controller.AudioCapture")
@patch("noteflow.controller.WhisperTranscriber")
def test_stop_session_batch_calls_transcribe_full(mock_whisper, mock_audio, controller):
    mock_audio.return_value.get_full_audio.return_value = b"audio"
    mock_whisper.return_value.transcribe_full.return_value = "segment 1 text"
    
    controller.initialize()
    controller.start_session("Title", TranscriptionMode.BATCH, Theme.DARK)
    controller._generate_and_send = Mock(return_value={})
    
    controller.stop_session()
    
    mock_whisper.return_value.transcribe_full.assert_called_once_with(b"audio")


@patch("noteflow.controller.AudioCapture")
def test_generate_and_send_calls_llm(mock_audio, controller):
    controller.start_session("Title", TranscriptionMode.BATCH, Theme.DARK)
    controller._transcript_store.append("Hello world")
    
    mock_llm = Mock()
    mock_llm.generate_notes.return_value = {"title": "T", "summary": "S"}
    controller._llm_client = mock_llm
    
    controller._email_sender = Mock()
    controller._write_session_archive = Mock()
    controller._write_markdown_backup = Mock()
    
    controller._generate_and_send()
    
    mock_llm.generate_notes.assert_called_once()


@patch("noteflow.controller.AudioCapture")
def test_generate_and_send_calls_email(mock_audio, controller):
    controller.start_session("Title", TranscriptionMode.BATCH, Theme.DARK)
    controller._transcript_store.append("Hello world")
    
    mock_llm = Mock()
    mock_llm.generate_notes.return_value = {"title": "T", "summary": "S"}
    controller._llm_client = mock_llm
    
    mock_email = Mock()
    controller._email_sender = mock_email
    
    controller._write_session_archive = Mock()
    controller._write_markdown_backup = Mock()
    
    controller._generate_and_send()
    
    mock_email.send.assert_called_once()


@patch("noteflow.controller.AudioCapture")
def test_session_archive_written(mock_audio, controller):
    controller.start_session("Title", TranscriptionMode.BATCH, Theme.DARK)
    controller._transcript_store.append("Hello world")
    
    mock_llm = Mock()
    mock_llm.generate_notes.return_value = {"title": "Title", "summary": "Summary", "action_items": []}
    controller._llm_client = mock_llm
    controller._email_sender = Mock()
    
    with patch("builtins.open", MagicMock()) as mock_open:
        controller._generate_and_send()
        
        # Called twice: once for json, once for md
        assert mock_open.call_count == 2


@patch("noteflow.controller.AudioCapture")
def test_dry_run_skips_email(mock_audio, controller):
    controller.settings.dry_run = True
    controller.start_session("Title", TranscriptionMode.BATCH, Theme.DARK)
    controller._transcript_store.append("Hello world")
    
    controller._llm_client = Mock()
    
    mock_email = Mock()
    controller._email_sender = mock_email
    
    controller._write_session_archive = Mock()
    controller._write_markdown_backup = Mock()
    
    controller._generate_and_send()
    
    mock_email.send.assert_not_called()


@patch("noteflow.controller.AudioCapture")
def test_email_failure_still_saves_locally(mock_audio, controller):
    controller.start_session("Title", TranscriptionMode.BATCH, Theme.DARK)
    controller._transcript_store.append("Hello world")
    
    controller._llm_client = Mock()
    
    mock_email = Mock()
    mock_email.send.side_effect = Exception("Email failed")
    controller._email_sender = mock_email
    
    controller._write_session_archive = Mock()
    controller._write_markdown_backup = Mock()
    
    # Should not raise exception
    controller._generate_and_send()
    
    # Local saves still called
    controller._write_session_archive.assert_called_once()
    controller._write_markdown_backup.assert_called_once()


@patch("noteflow.controller.AudioCapture")
def test_regenerate_notes_calls_llm(mock_audio, controller):
    controller.start_session("Title", TranscriptionMode.BATCH, Theme.DARK)
    controller._transcript_store.append("Recorded transcript segment")
    
    mock_llm = Mock()
    mock_llm.generate_notes.return_value = {"summary": "Regenerated summary"}
    controller._llm_client = mock_llm
    controller._write_session_archive = Mock()
    controller._write_markdown_backup = Mock()
    
    notes = controller.regenerate_notes()
    
    assert notes["summary"] == "Regenerated summary"
    mock_llm.generate_notes.assert_called_once()
