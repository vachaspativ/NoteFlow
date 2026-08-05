from __future__ import annotations

import os
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from dotenv import load_dotenv, set_key


class TranscriptionMode(str, Enum):
    LIVE = 'live'
    BATCH = 'batch'


class Theme(str, Enum):
    DARK = 'dark'
    LIGHT = 'light'


@dataclass
class Settings:
    theme: Theme
    transcription_mode: TranscriptionMode
    whisper_model: str
    whisper_device: str
    chunk_duration_secs: int
    vad_threshold: float
    ollama_host: str
    ollama_port: int
    ollama_model: str
    ollama_timeout: int
    smtp_host: str
    smtp_port: int
    smtp_use_tls: bool
    smtp_username: str
    smtp_password: str
    email_from: str
    email_to: str
    email_subject_prefix: str

    _env_path: str | Path | None = None

    @classmethod
    def from_env(cls, env_path: str | Path | None = None) -> Settings:
        if env_path is not None:
            load_dotenv(env_path, override=True)
        else:
            load_dotenv(override=True)
            env_path = os.environ.get("DOTENV_PATH", ".env")

        required_smtp_vars = [
            "SMTP_HOST", "SMTP_PORT", "SMTP_USE_TLS",
            "SMTP_USERNAME", "SMTP_PASSWORD",
            "EMAIL_FROM", "EMAIL_TO", "EMAIL_SUBJECT_PREFIX"
        ]

        missing_vars = [var for var in required_smtp_vars if os.getenv(var) is None]
        if missing_vars:
            raise ValueError(f"Missing required SMTP environment variables: {', '.join(missing_vars)}")

        mode_str = os.getenv("TRANSCRIPTION_MODE", "live")
        theme_str = os.getenv("THEME", "dark")

        transcription_mode = TranscriptionMode(mode_str)
        theme = Theme(theme_str)

        smtp_use_tls_str = os.getenv("SMTP_USE_TLS", "false").lower()
        smtp_use_tls = smtp_use_tls_str in ("true", "1", "yes")

        return cls(
            theme=theme,
            transcription_mode=transcription_mode,
            whisper_model=os.getenv("WHISPER_MODEL", "base"),
            whisper_device=os.getenv("WHISPER_DEVICE", "cpu"),
            chunk_duration_secs=int(os.getenv("CHUNK_DURATION_SECS", "30")),
            vad_threshold=float(os.getenv("VAD_THRESHOLD", "0.5")),
            ollama_host=os.getenv("OLLAMA_HOST", "localhost"),
            ollama_port=int(os.getenv("OLLAMA_PORT", "11434")),
            ollama_model=os.getenv("OLLAMA_MODEL", "llama3"),
            ollama_timeout=int(os.getenv("OLLAMA_TIMEOUT", "60")),
            smtp_host=os.getenv("SMTP_HOST"),
            smtp_port=int(os.getenv("SMTP_PORT")),
            smtp_use_tls=smtp_use_tls,
            smtp_username=os.getenv("SMTP_USERNAME"),
            smtp_password=os.getenv("SMTP_PASSWORD"),
            email_from=os.getenv("EMAIL_FROM"),
            email_to=os.getenv("EMAIL_TO"),
            email_subject_prefix=os.getenv("EMAIL_SUBJECT_PREFIX"),
            _env_path=env_path
        )

    def save_theme(self, theme: Theme) -> None:
        self.theme = theme
        if self._env_path:
            set_key(str(self._env_path), "THEME", theme.value)

    def save_mode(self, mode: TranscriptionMode) -> None:
        self.transcription_mode = mode
        if self._env_path:
            set_key(str(self._env_path), "TRANSCRIPTION_MODE", mode.value)
