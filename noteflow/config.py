from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from dotenv import load_dotenv
import yaml

logger = logging.getLogger(__name__)

class TranscriptionMode(str, Enum):
    LIVE = 'live'
    BATCH = 'batch'


class Theme(str, Enum):
    DARK = 'dark'
    LIGHT = 'light'


class UIMode(str, Enum):
    NODE = 'node'
    TUI = 'tui'
    WEB = 'web'


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
    smtp_host: str
    smtp_port: int
    smtp_use_tls: bool
    smtp_username: str
    smtp_password: str
    email_from: str
    email_to: str
    email_subject_prefix: str
    ollama_timeout: int = 300
    ollama_max_retries: int = 1
    enable_loopback: bool = True
    auto_call_detection: bool = False
    default_meeting_title_prefix: str = "[NoteFlow] Meeting"
    notes_dir: str = "../noteflow_notes"
    sessions_dir: str = "../noteflow_sessions"
    allow_online_model_download: bool = False
    enable_email: bool = True
    ui_mode: UIMode = UIMode.NODE
    web_host: str = "127.0.0.1"
    web_port: int = 5000
    dry_run: bool = False
    device_id: int | None = None
    enable_map_reduce: bool = False

    _env_path: str | Path | None = None

    @classmethod
    def from_env(cls, env_path: str | Path | None = None) -> Settings:
        # Default path resolution for yaml configuration file
        if env_path is None:
            possible_paths = [
                Path("config.yaml"),
                Path(__file__).parent.parent / "config.yaml"
            ]
            for p in possible_paths:
                if p.exists():
                    env_path = p
                    break
            if env_path is None:
                env_path = Path("config.yaml")
        else:
            env_path = Path(env_path)

        is_yaml = env_path.suffix in (".yaml", ".yml")
        if not is_yaml and env_path.exists():
            load_dotenv(env_path, override=True)
        else:
            load_dotenv(override=True)

        data = {}
        if is_yaml and env_path.exists():
            try:
                with open(env_path, "r", encoding="utf-8") as f:
                    data = yaml.safe_load(f) or {}
            except Exception as e:
                logger.error(f"Error loading config.yaml: {e}")

        required_smtp_keys = [
            "smtp_host", "smtp_port", "smtp_use_tls",
            "smtp_username", "smtp_password",
            "email_from", "email_to", "email_subject_prefix"
        ]

        # Check SMTP configuration keys in either YAML or env vars
        missing_vars = []
        for key in required_smtp_keys:
            env_var = key.upper()
            if data.get(key) is None and os.getenv(env_var) is None:
                missing_vars.append(env_var)

        if missing_vars:
            raise ValueError(f"Missing required SMTP environment variables: {', '.join(missing_vars)}")

        mode_str = data.get("transcription_mode") or os.getenv("TRANSCRIPTION_MODE", "live")
        theme_str = data.get("theme") or os.getenv("THEME", "dark")
        ui_mode_str = data.get("ui_mode") or os.getenv("UI_MODE", "node")

        transcription_mode = TranscriptionMode(mode_str.lower()) if mode_str.lower() in [m.value for m in TranscriptionMode] else TranscriptionMode.LIVE
        theme = Theme(theme_str.lower()) if theme_str.lower() in [t.value for t in Theme] else Theme.DARK
        ui_mode = UIMode(ui_mode_str.lower()) if ui_mode_str.lower() in [u.value for u in UIMode] else UIMode.NODE

        smtp_use_tls = data.get("smtp_use_tls")
        if smtp_use_tls is None:
            smtp_use_tls_str = os.getenv("SMTP_USE_TLS", "true").lower()
            smtp_use_tls = smtp_use_tls_str in ("true", "1", "yes")

        web_host = data.get("web_host") or os.getenv("WEB_HOST", "127.0.0.1")
        web_port = int(data.get("web_port") or os.getenv("WEB_PORT", "5000"))

        enable_loopback = data.get("enable_loopback") if data.get("enable_loopback") is not None else (os.getenv("ENABLE_LOOPBACK", "true").lower() in ("true", "1", "yes"))
        auto_call_detection = data.get("auto_call_detection") if data.get("auto_call_detection") is not None else (os.getenv("AUTO_CALL_DETECTION", "false").lower() in ("true", "1", "yes"))
        default_meeting_title_prefix = data.get("default_meeting_title_prefix") or os.getenv("DEFAULT_MEETING_TITLE_PREFIX", "[NoteFlow] Meeting")

        notes_dir = data.get("notes_dir") or os.getenv("NOTES_DIR", "../noteflow_notes")
        sessions_dir = data.get("sessions_dir") or os.getenv("SESSIONS_DIR", "../noteflow_sessions")
        allow_online_model_download = data.get("allow_online_model_download") if data.get("allow_online_model_download") is not None else (os.getenv("ALLOW_ONLINE_MODEL_DOWNLOAD", "false").lower() in ("true", "1", "yes"))
        enable_email = data.get("enable_email") if data.get("enable_email") is not None else (os.getenv("ENABLE_EMAIL", "true").lower() in ("true", "1", "yes"))
        enable_map_reduce = data.get("enable_map_reduce") if data.get("enable_map_reduce") is not None else (os.getenv("ENABLE_MAP_REDUCE", "false").lower() in ("true", "1", "yes"))

        return cls(
            theme=theme,
            transcription_mode=transcription_mode,
            whisper_model=data.get("whisper_model") or os.getenv("WHISPER_MODEL", "base.en"),
            whisper_device=data.get("whisper_device") or os.getenv("WHISPER_DEVICE", "cpu"),
            chunk_duration_secs=int(data.get("chunk_duration_secs") or os.getenv("CHUNK_DURATION_SECS", "3")),
            vad_threshold=float(data.get("vad_threshold") or os.getenv("VAD_THRESHOLD", "0.5")),
            ollama_host=data.get("ollama_host") or os.getenv("OLLAMA_HOST", "http://localhost"),
            ollama_port=int(data.get("ollama_port") or os.getenv("OLLAMA_PORT", "11434")),
            ollama_model=data.get("ollama_model") or os.getenv("OLLAMA_MODEL", "llama3.2"),
            ollama_timeout=int(data.get("ollama_timeout") or os.getenv("OLLAMA_TIMEOUT", "300")),
            ollama_max_retries=int(data.get("ollama_max_retries") if data.get("ollama_max_retries") is not None else os.getenv("OLLAMA_MAX_RETRIES", "1")),
            smtp_host=data.get("smtp_host") or os.getenv("SMTP_HOST", "smtp.gmail.com"),
            smtp_port=int(data.get("smtp_port") or os.getenv("SMTP_PORT", "587")),
            smtp_use_tls=smtp_use_tls,
            smtp_username=data.get("smtp_username") or os.getenv("SMTP_USERNAME", ""),
            smtp_password=data.get("smtp_password") or os.getenv("SMTP_PASSWORD", ""),
            email_from=data.get("email_from") or os.getenv("EMAIL_FROM", ""),
            email_to=data.get("email_to") or os.getenv("EMAIL_TO", ""),
            email_subject_prefix=data.get("email_subject_prefix") or os.getenv("EMAIL_SUBJECT_PREFIX", "[NoteFlow]"),
            enable_loopback=enable_loopback,
            auto_call_detection=auto_call_detection,
            default_meeting_title_prefix=default_meeting_title_prefix,
            notes_dir=notes_dir,
            sessions_dir=sessions_dir,
            allow_online_model_download=allow_online_model_download,
            enable_email=enable_email,
            ui_mode=ui_mode,
            web_host=web_host,
            web_port=web_port,
            enable_map_reduce=enable_map_reduce,
            _env_path=env_path
        )

    def get_notes_dir(self) -> Path:
        p = Path(self.notes_dir)
        if not p.is_absolute():
            p = (Path.cwd() / p).resolve()
        p.mkdir(parents=True, exist_ok=True)
        return p

    def get_sessions_dir(self) -> Path:
        p = Path(self.sessions_dir)
        if not p.is_absolute():
            p = (Path.cwd() / p).resolve()
        p.mkdir(parents=True, exist_ok=True)
        return p

    def _save_to_yaml(self) -> None:
        if not self._env_path:
            return
        
        is_yaml = Path(self._env_path).suffix in (".yaml", ".yml")
        if not is_yaml:
            from dotenv import set_key
            set_key(str(self._env_path), "THEME", self.theme.value)
            set_key(str(self._env_path), "TRANSCRIPTION_MODE", self.transcription_mode.value)
            set_key(str(self._env_path), "UI_MODE", self.ui_mode.value)
            set_key(str(self._env_path), "OLLAMA_TIMEOUT", str(self.ollama_timeout))
            set_key(str(self._env_path), "OLLAMA_MAX_RETRIES", str(self.ollama_max_retries))
            set_key(str(self._env_path), "ENABLE_LOOPBACK", "true" if self.enable_loopback else "false")
            set_key(str(self._env_path), "AUTO_CALL_DETECTION", "true" if self.auto_call_detection else "false")
            set_key(str(self._env_path), "DEFAULT_MEETING_TITLE_PREFIX", self.default_meeting_title_prefix)
            set_key(str(self._env_path), "NOTES_DIR", self.notes_dir)
            set_key(str(self._env_path), "SESSIONS_DIR", self.sessions_dir)
            set_key(str(self._env_path), "ALLOW_ONLINE_MODEL_DOWNLOAD", "true" if self.allow_online_model_download else "false")
            set_key(str(self._env_path), "ENABLE_EMAIL", "true" if self.enable_email else "false")
            set_key(str(self._env_path), "ENABLE_MAP_REDUCE", "true" if self.enable_map_reduce else "false")
            return
        
        data = {}
        if Path(self._env_path).exists():
            try:
                with open(self._env_path, "r", encoding="utf-8") as f:
                    data = yaml.safe_load(f) or {}
            except Exception:
                pass
                
        data["theme"] = self.theme.value
        data["transcription_mode"] = self.transcription_mode.value
        data["whisper_model"] = self.whisper_model
        data["whisper_device"] = self.whisper_device
        data["chunk_duration_secs"] = self.chunk_duration_secs
        data["vad_threshold"] = self.vad_threshold
        data["enable_loopback"] = self.enable_loopback
        data["auto_call_detection"] = self.auto_call_detection
        data["default_meeting_title_prefix"] = self.default_meeting_title_prefix
        data["notes_dir"] = self.notes_dir
        data["sessions_dir"] = self.sessions_dir
        data["allow_online_model_download"] = self.allow_online_model_download
        data["enable_email"] = self.enable_email
        data["enable_map_reduce"] = self.enable_map_reduce
        data["ollama_host"] = self.ollama_host
        data["ollama_port"] = self.ollama_port
        data["ollama_model"] = self.ollama_model
        data["ollama_timeout"] = self.ollama_timeout
        data["ollama_max_retries"] = self.ollama_max_retries
        data["smtp_host"] = self.smtp_host
        data["smtp_port"] = self.smtp_port
        data["smtp_use_tls"] = self.smtp_use_tls
        data["smtp_username"] = self.smtp_username
        data["smtp_password"] = self.smtp_password
        data["email_from"] = self.email_from
        data["email_to"] = self.email_to
        data["email_subject_prefix"] = self.email_subject_prefix
        data["ui_mode"] = self.ui_mode.value
        data["web_host"] = self.web_host
        data["web_port"] = self.web_port
        
        try:
            with open(self._env_path, "w", encoding="utf-8") as f:
                yaml.safe_dump(data, f, default_flow_style=False, sort_keys=False)
        except Exception as e:
            logger.error(f"Failed to save settings to YAML: {e}")

    def save_enable_email(self, enable: bool) -> None:
        self.enable_email = enable
        self._save_to_yaml()

    def save_allow_online_model_download(self, allow: bool) -> None:
        self.allow_online_model_download = allow
        self._save_to_yaml()

    def save_theme(self, theme: Theme) -> None:
        self.theme = theme
        self._save_to_yaml()

    def save_mode(self, mode: TranscriptionMode) -> None:
        self.transcription_mode = mode
        self._save_to_yaml()

    def save_ui_mode(self, mode: UIMode) -> None:
        self.ui_mode = mode
        self._save_to_yaml()

    def save_ollama_timeout(self, timeout: int) -> None:
        self.ollama_timeout = timeout
        self._save_to_yaml()

    def save_ollama_max_retries(self, retries: int) -> None:
        self.ollama_max_retries = retries
        self._save_to_yaml()

    def save_enable_loopback(self, enable: bool) -> None:
        self.enable_loopback = enable
        self._save_to_yaml()

    def save_auto_call_detection(self, enable: bool) -> None:
        self.auto_call_detection = enable
        self._save_to_yaml()

    def save_default_meeting_title_prefix(self, prefix: str) -> None:
        self.default_meeting_title_prefix = prefix
        self._save_to_yaml()

    def save_enable_map_reduce(self, enable: bool) -> None:
        self.enable_map_reduce = enable
        self._save_to_yaml()
