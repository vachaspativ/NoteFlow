import os
import pytest
from pathlib import Path

from noteflow.config import Settings, TranscriptionMode, Theme, UIMode


@pytest.fixture(autouse=True)
def clear_env(monkeypatch):
    # clear all env vars to avoid bleeding between tests
    for key in list(os.environ.keys()):
        monkeypatch.delenv(key, raising=False)


def create_valid_env(path: Path, **overrides) -> Path:
    defaults = {
        "SMTP_HOST": "smtp.example.com",
        "SMTP_PORT": "587",
        "SMTP_USE_TLS": "true",
        "SMTP_USERNAME": "user",
        "SMTP_PASSWORD": "password",
        "EMAIL_FROM": "from@example.com",
        "EMAIL_TO": "to@example.com",
        "EMAIL_SUBJECT_PREFIX": "[NoteFlow]",
        "UI_MODE": "node"
    }
    defaults.update(overrides)
    
    content = ""
    for k, v in defaults.items():
        if v is not None:
            content += f"{k}={v}\n"
            
    env_file = path / ".env"
    env_file.write_text(content)
    return env_file


def test_valid_live_mode(tmp_path):
    env_file = create_valid_env(tmp_path, TRANSCRIPTION_MODE="live")
    settings = Settings.from_env(env_file)
    assert settings.transcription_mode == TranscriptionMode.LIVE


def test_valid_batch_mode(tmp_path):
    env_file = create_valid_env(tmp_path, TRANSCRIPTION_MODE="batch")
    settings = Settings.from_env(env_file)
    assert settings.transcription_mode == TranscriptionMode.BATCH


def test_valid_dark_theme(tmp_path):
    env_file = create_valid_env(tmp_path, THEME="dark")
    settings = Settings.from_env(env_file)
    assert settings.theme == Theme.DARK


def test_valid_light_theme(tmp_path):
    env_file = create_valid_env(tmp_path, THEME="light")
    settings = Settings.from_env(env_file)
    assert settings.theme == Theme.LIGHT


def test_invalid_mode_defaults_to_live(tmp_path):
    env_file = create_valid_env(tmp_path, TRANSCRIPTION_MODE="invalid")
    settings = Settings.from_env(env_file)
    assert settings.transcription_mode == TranscriptionMode.LIVE


def test_invalid_theme_defaults_to_dark(tmp_path):
    env_file = create_valid_env(tmp_path, THEME="invalid")
    settings = Settings.from_env(env_file)
    assert settings.theme == Theme.DARK


def test_mode_defaults_to_live(tmp_path):
    env_file = create_valid_env(tmp_path)
    settings = Settings.from_env(env_file)
    assert settings.transcription_mode == TranscriptionMode.LIVE


def test_theme_defaults_to_dark(tmp_path):
    env_file = create_valid_env(tmp_path)
    settings = Settings.from_env(env_file)
    assert settings.theme == Theme.DARK


def test_ui_mode_default_and_custom(tmp_path):
    env_file = create_valid_env(tmp_path, UI_MODE="tui")
    settings = Settings.from_env(env_file)
    assert settings.ui_mode == UIMode.TUI


def test_missing_smtp_fields_raises(tmp_path):
    env_file = create_valid_env(tmp_path, SMTP_HOST=None)
    with pytest.raises(ValueError, match="Missing required SMTP environment variables: SMTP_HOST"):
        Settings.from_env(env_file)


def test_save_theme_writes_env(tmp_path):
    env_file = create_valid_env(tmp_path)
    settings = Settings.from_env(env_file)
    settings.save_theme(Theme.LIGHT)
    assert settings.theme == Theme.LIGHT
    content = env_file.read_text()
    assert "THEME='light'" in content or "THEME=light" in content or 'THEME="light"' in content


def test_save_mode_writes_env(tmp_path):
    env_file = create_valid_env(tmp_path)
    settings = Settings.from_env(env_file)
    settings.save_mode(TranscriptionMode.BATCH)
    assert settings.transcription_mode == TranscriptionMode.BATCH
    content = env_file.read_text()
    assert "TRANSCRIPTION_MODE='batch'" in content or "TRANSCRIPTION_MODE=batch" in content or 'TRANSCRIPTION_MODE="batch"' in content


def test_save_ui_mode_writes_env(tmp_path):
    env_file = create_valid_env(tmp_path)
    settings = Settings.from_env(env_file)
    settings.save_ui_mode(UIMode.TUI)
    assert settings.ui_mode == UIMode.TUI
    content = env_file.read_text()
    assert "UI_MODE='tui'" in content or "UI_MODE=tui" in content or 'UI_MODE="tui"' in content

def test_yaml_config_load_and_save(tmp_path):
    yaml_file = tmp_path / "config.yaml"
    import yaml
    yaml_content = {
        "theme": "dark",
        "transcription_mode": "batch",
        "whisper_model": "small.en",
        "whisper_device": "cpu",
        "chunk_duration_secs": 5,
        "vad_threshold": 0.6,
        "ollama_host": "http://localhost",
        "ollama_port": 11434,
        "ollama_model": "llama3",
        "ollama_timeout": 150,
        "ollama_max_retries": 2,
        "smtp_host": "smtp.example.com",
        "smtp_port": 587,
        "smtp_use_tls": True,
        "smtp_username": "user",
        "smtp_password": "password",
        "email_from": "from@example.com",
        "email_to": "to@example.com",
        "email_subject_prefix": "[NoteFlow]",
        "ui_mode": "web",
        "web_host": "127.0.0.1",
        "web_port": 8080
    }
    with open(yaml_file, "w") as f:
        yaml.safe_dump(yaml_content, f)
        
    settings = Settings.from_env(yaml_file)
    assert settings.theme == Theme.DARK
    assert settings.transcription_mode == TranscriptionMode.BATCH
    assert settings.ollama_timeout == 150
    assert settings.ollama_max_retries == 2
    assert settings.web_port == 8080
    
    settings.save_theme(Theme.LIGHT)
    assert settings.theme == Theme.LIGHT
    
    with open(yaml_file, "r") as f:
        saved_data = yaml.safe_load(f)
    assert saved_data["theme"] == "light"
    assert saved_data["transcription_mode"] == "batch"
