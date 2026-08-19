# Agent Instructions for NoteFlow

Welcome, fellow agent. This file contains the primary directives, context, and structural layout for the NoteFlow repository. Read this carefully before making any modifications to the codebase.

## Project Context
NoteFlow is an offline, AI-powered meeting note-taker. 
- **Tech Stack**: Python 3.10+, `fastapi` & `uvicorn` (Web UI API), `textual` (TUI), `faster-whisper` (STT), `Ollama` (local LLM), `sounddevice` (Audio).
- **Core Principle**: 100% offline data processing (excluding the SMTP email sending feature). No external cloud APIs (like OpenAI) are used for transcription or summarization to guarantee data privacy.

## Dual UI Architecture
NoteFlow provides two interchangeable user interfaces managed by a unified CLI:
1. **Local Web / Node UI (Default)**: Served natively by `noteflow/web_server.py` at `http://127.0.0.1:5000` with static files in `noteflow/web/`. It connects via REST and WebSockets for real-time speech streaming.
2. **Textual Terminal TUI**: Accessible via `noteflow --tui` or `noteflow --ui tui`, implemented in `noteflow/display.py`.

## Codebase Architecture
All core logic is contained within the `noteflow/` directory:
1. **main.py**: CLI entry point with Click. Handles flags `--ui [node|tui|web]`, `--tui`, `--node`, `--web`, `--port`, `--host`, `--dry-run`.
2. **web_server.py**: FastAPI application with REST endpoints and WebSocket broadcasting on `/ws/live`.
3. **web/**: Vanilla HTML5, CSS3, and modern ES6 JS single page app.
4. **controller.py**: Central orchestrator. Manages thread synchronization between audio capture, whisper transcription, LLM invocation, and saving to disk.
5. **display.py**: The `textual` TUI app. Contains `SetupScreen`, `RecordingScreen`, and `ProcessingScreen`.
6. **audio_capture.py**: Captures microphone chunks via `sounddevice`. Uses thread-safe Queues.
7. **transcription.py**: Wraps `faster-whisper`. IMPORTANT: `faster-whisper` models are NOT thread-safe. A `threading.Lock` must be acquired before calling `transcribe`.
8. **llm_client.py**: Connects to `Ollama` via HTTP POST. Extracts strict JSON.
9. **email_sender.py**: HTML template rendering and SMTP delivery.
10. **node_ui/**: Standalone Node.js Express proxy package.

## Integration & Modification Guidelines
When tasked with updating or adding features, adhere to the following rules:

### 1. Adding Dependencies
- If you add a new Python library, update `pyproject.toml` under `dependencies` and run `pip install -e .`.

### 2. Modifying the Web UI
- The Web UI lives in `noteflow/web/` (`index.html`, `style.css`, `app.js`).
- It communicates with the Python backend via `/api/*` REST endpoints and `/ws/live` WebSockets.
- Always preserve dark and light theme token compatibility in `style.css`.

### 3. Modifying the LLM Prompts
- The LLM prompt is in `noteflow/llm_client.py` inside `_build_prompt()`.
- If you add a new required output field (e.g. "Sentiment"), update `_validate_notes()` in the same file to provide a default fallback empty list or string if the LLM fails to generate it.

### 4. Testing
- The project mandates a strict mock-everything approach in unit tests.
- Always run `pytest tests/` before completing tasks. All 90+ tests must pass.
