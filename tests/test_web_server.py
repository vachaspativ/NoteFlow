import pytest
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient

from noteflow.config import Settings, TranscriptionMode, Theme, UIMode
from noteflow.controller import SessionController
from noteflow.session_metadata import SessionMetadata
from noteflow.web_server import create_app


@pytest.fixture
def mock_settings():
    return Settings(
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
        smtp_host="smtp.example.com",
        smtp_port=587,
        smtp_use_tls=True,
        smtp_username="user@example.com",
        smtp_password="password",
        email_from="user@example.com",
        email_to="recipient@example.com",
        email_subject_prefix="[NoteFlow]",
        ui_mode=UIMode.NODE,
        web_host="127.0.0.1",
        web_port=5000,
    )


@pytest.fixture
def mock_controller(mock_settings):
    controller = SessionController(mock_settings)
    controller.initialize = MagicMock(return_value={"whisper": True, "ollama": True, "microphone": True, "smtp": True})
    controller.is_recording = MagicMock(return_value=False)
    controller.get_current_session_info = MagicMock(return_value={
        "active": False,
        "title": "Test Sync",
        "mode": "live",
        "duration_seconds": 12,
        "duration_display": "12s",
        "segment_count": 2,
    })
    controller.get_history_sessions = MagicMock(return_value=[
        {"session_id": "12345678", "title": "Q3 Planning", "mode": "live", "duration_display": "25m 10s"}
    ])
    controller.get_session_details = MagicMock(return_value={
        "session_id": "12345678",
        "title": "Q3 Planning",
        "notes": {"summary": "Great meeting", "action_items": []},
        "transcript": "Hello world",
    })
    controller.start_session = MagicMock(return_value=SessionMetadata(title="Test Meeting", mode=TranscriptionMode.LIVE, theme=Theme.DARK))
    controller.stop_session = MagicMock(return_value={"title": "Test Meeting", "summary": "Done", "action_items": []})
    return controller


@pytest.fixture
def client(mock_controller):
    app = create_app(mock_controller)
    return TestClient(app)


def test_api_status(client, mock_controller):
    response = client.get("/api/status")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "online"
    assert data["components"]["whisper"] is True


def test_api_settings(client, mock_controller):
    response = client.get("/api/settings")
    assert response.status_code == 200
    data = response.json()
    assert data["theme"] == "dark"
    assert data["transcription_mode"] == "live"
    assert data["ui_mode"] == "node"


def test_api_update_settings(client, mock_controller):
    response = client.post("/api/settings", json={"theme": "light", "whisper_model": "small.en"})
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True


def test_api_devices(client):
    with patch("noteflow.web_server.list_audio_devices", return_value=[{"name": "Mic 1", "max_input_channels": 2}]):
        response = client.get("/api/devices")
        assert response.status_code == 200
        assert len(response.json()) == 1
        assert response.json()[0]["name"] == "Mic 1"


def test_api_start_and_stop_session(client, mock_controller):
    # Start
    response = client.post("/api/session/start", json={"title": "Strategy Sync", "mode": "live", "theme": "dark"})
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["title"] == "Test Meeting"

    # Stop
    response = client.post("/api/session/stop")
    assert response.status_code == 200
    assert response.json()["success"] is True


def test_api_history_sessions(client, mock_controller):
    response = client.get("/api/sessions")
    assert response.status_code == 200
    sessions = response.json()
    assert len(sessions) == 1
    assert sessions[0]["title"] == "Q3 Planning"


def test_api_session_detail(client, mock_controller):
    response = client.get("/api/sessions/12345678")
    assert response.status_code == 200
    data = response.json()
    assert data["session_id"] == "12345678"
    assert data["title"] == "Q3 Planning"


def test_serve_static_index(client):
    response = client.get("/")
    assert response.status_code == 200
    assert "NoteFlow" in response.text


def test_api_regenerate_session_notes(client, mock_controller):
    mock_controller.regenerate_notes = MagicMock(return_value={"summary": "Re-generated summary"})
    response = client.post("/api/session/regenerate")
    assert response.status_code == 200
    assert response.json()["success"] is True
    assert response.json()["notes"]["summary"] == "Re-generated summary"


def test_api_download_session_transcript(client, mock_controller):
    response = client.get("/api/sessions/12345678/transcript/download")
    assert response.status_code == 200
    assert "Hello world" in response.text
