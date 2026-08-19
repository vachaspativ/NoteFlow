# Agent Instructions for NoteFlow

Welcome, fellow agent. This file contains the primary directives, context, and structural layout for the NoteFlow repository. Read this carefully before making any modifications to the codebase.

## Project Context
NoteFlow is an offline, AI-powered meeting note-taker. 
- **Tech Stack**: Python 3.10+, `fastapi` & `uvicorn` (Web UI API), `textual` (TUI), `faster-whisper` (STT), `Ollama` (local LLM), `sounddevice` (Audio), `pycaw` (WASAPI loopback & session monitoring), `pyyaml` (Config).
- **Core Principle**: 100% offline data processing (excluding the SMTP email sending feature). No external cloud APIs (like OpenAI) are used for transcription or summarization to guarantee data privacy.

## Dual UI Architecture
NoteFlow provides two interchangeable user interfaces managed by a unified CLI:
1. **Local Web / Node UI (Default)**: Served natively by `noteflow/web_server.py` at `http://127.0.0.1:5000` with static files in `noteflow/web/`. It connects via REST and WebSockets for real-time speech streaming.
2. **Textual Terminal TUI**: Accessible via `noteflow --tui` or `noteflow --ui tui`, implemented in `noteflow/display.py`.

## Codebase Architecture
All core logic is contained within the `noteflow/` directory:
1. **main.py**: CLI entry point with Click. Handles flags `--ui [node|tui|web]`, `--tui`, `--node`, `--web`, `--port`, `--host`, `--dry-run`, `--daemon`.
2. **web_server.py**: FastAPI application with REST endpoints and WebSocket broadcasting on `/ws/live`.
3. **web/**: Vanilla HTML5, CSS3, and modern ES6 JS single page app with logo assets in `logo.png`.
4. **controller.py**: Central orchestrator. Manages thread synchronization between audio capture, whisper transcription, LLM invocation, and saving to disk.
5. **display.py**: The `textual` TUI app. Contains `SetupScreen`, `RecordingScreen`, and `ProcessingScreen`.
6. **audio_capture.py**: Captures microphone audio and optional WASAPI speaker loopback (for Bluetooth headsets / caller audio). Uses thread-safe Queues.
7. **transcription.py**: Wraps `faster-whisper`. IMPORTANT: `faster-whisper` models are NOT thread-safe. A `threading.Lock` must be acquired before calling `transcribe`.
8. **llm_client.py**: Connects to `Ollama` via HTTP POST. Loads prompt templates from `prompts/meeting_notes_prompt.md`.
9. **daemon.py**: Background listener service monitoring active Windows audio sessions (Teams, Zoom, Webex) to auto-trigger recording sessions.
10. **email_sender.py**: HTML template rendering and SMTP delivery.
