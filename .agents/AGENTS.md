# Agent Instructions for NoteFlow

Welcome, fellow agent. This file contains the primary directives, context, and structural layout for the NoteFlow repository. Read this carefully before making any modifications to the codebase.

## Project Context
NoteFlow is an offline, AI-powered meeting note-taker. 
- **Tech Stack**: Python 3.10+, `textual` (TUI), `faster-whisper` (STT), `Ollama` (local LLM), `sounddevice` (Audio).
- **Core Principle**: 100% offline data processing (excluding the SMTP email sending feature). No external cloud APIs (like OpenAI) are used for transcription or summarization to guarantee data privacy.

## Codebase Architecture
All core logic is contained within the `noteflow/` directory:
1. **display.py**: The `textual` app. Contains `SetupScreen`, `RecordingScreen`, and `ProcessingScreen`. Do not add heavy blocking operations here; use `worker` threads for background tasks.
2. **controller.py**: Orchestrates the flow between UI events and data processing. It manages the threads for audio capture and whisper transcription.
3. **audio_capture.py**: Captures microphone chunks via `sounddevice`. Uses thread-safe Queues.
4. **transcription.py**: Wraps `faster-whisper`. IMPORTANT: `faster-whisper` models are NOT thread-safe. A `threading.Lock` must be acquired before calling `transcribe`.
5. **llm_client.py**: Connects to `Ollama` via HTTP POST. Extracts strict JSON.
6. **email_sender.py**: HTML template rendering and SMTP delivery.

## Integration & Modification Guidelines
When tasked with updating or adding features, adhere to the following rules:

### 1. Adding Dependencies
- If you add a new library, update `pyproject.toml` under `dependencies` and run `pip install -e '.[dev]'`.

### 2. Modifying the UI
- NoteFlow uses `textual`. Styling MUST be separated into the `.tcss` files located in `noteflow/css/`.
- Do not hardcode colors if possible; respect the global `THEME` toggle (Dark/Light).

### 3. Modifying the LLM Prompts
- The LLM prompt is hardcoded in `noteflow/llm_client.py` inside `_build_prompt()`.
- If you add a new required output field (e.g. "Action Items"), you MUST also update `_validate_notes()` in the same file to provide a default fallback empty list if the LLM fails to generate it.

### 4. Testing
- The project mandates a strict mock-everything approach in tests. 
- You MUST mock `sounddevice`, `faster-whisper`, `httpx`, and `smtplib` in your tests to ensure they run quickly and without hardware/network dependencies in CI environments.
- Run tests via `pytest tests/`.

### 5. Config Changes
- Any new environment variables must be:
  1. Added to `.env.example`
  2. Parsed inside `noteflow/config.py` within the `Settings` dataclass.

Follow these conventions precisely to ensure a stable, deterministic environment.
