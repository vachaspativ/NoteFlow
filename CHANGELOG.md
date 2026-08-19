# Changelog

All notable changes to the NoteFlow project will be documented in this file.

## [0.2.0] - Local Node/Web UI & Interface Switching Flag

### Added
- **Default Local Web / Node UI**: Built a modern, reactive single-page web dashboard (`noteflow/web/`) with dark & light theme support, audio waveform visualizer, live streaming speech feed, interactive action items checklist, meeting history drawer, and settings configuration modal.
- **FastAPI / Uvicorn Real-Time Server**: Built `noteflow/web_server.py` supporting REST API endpoints and real-time WebSockets for streaming live transcription segments and processing pipeline progress.
- **UI Mode CLI Switching**: Added `--ui [node|tui|web]`, `--tui`, `--node`, `--web`, `--port`, `--host`, and `--no-browser` flags to `noteflow/main.py`. The application defaults to the Node/Web UI and opens the browser automatically.
- **Configuration Updates**: Added `UI_MODE`, `WEB_HOST`, and `WEB_PORT` variables to `config.py`, `.env.example`, and `.env` with persistence.
- **Controller Streaming Hooks**: Added `add_segment_callback`, session queries, `get_history_sessions`, `get_session_details`, and `resend_session_email` to `SessionController`.
- **Standalone Node.js Support**: Created `node_ui/` folder with `package.json` and `server.js` Express proxy.
- **Comprehensive API Tests**: Added `tests/test_web_server.py` covering all REST endpoints and static file serving.

## [0.1.0] - Initial Release (Project Scaffolding & Core Architecture)

### Added
- **Core TUI Framework**: Implemented interactive Terminal UI using `textual` featuring Setup, Recording, and Processing screens.
- **Audio Capture Engine**: Built `audio_capture.py` using `sounddevice` for streaming chunks (Live mode) and aggregated audio buffers (Batch mode).
- **Whisper Transcription**: Implemented `transcription.py` wrapping `faster-whisper` with thread safety and rolling context memory.
- **LLM Pipeline**: Implemented `llm_client.py` for structured local note generation with `Ollama`.
- **Email Delivery**: Built `email_sender.py` with HTML email templates and SMTP delivery.
- **Data Persistence**: `session_metadata.py` with JSON archives in `/sessions/` and Markdown files in `/notes/`.
- **Automated Test Suite**: 80+ unit tests across all foundation modules.
