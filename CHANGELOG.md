# Changelog

All notable changes to the NoteFlow project will be documented in this file.

## [0.1.0] - Initial Release (Project Scaffolding & Implementation)

### Added
- **Core TUI Framework**: Implemented interactive Terminal UI using `textual` featuring Setup, Recording, and Processing screens.
- **Audio Capture Engine**: Built `audio_capture.py` using `sounddevice` to support both streaming chunks (Live mode) and aggregated arrays (Batch mode).
- **Transcription Wrapper**: Implemented `transcription.py` wrapping `faster-whisper`.
  - Added thread-safe batch transcription for offline bulk processing.
  - Added rolling context window (last 50 words) to ensure accurate continuity during live chunked transcription.
- **LLM Pipeline**: Implemented `llm_client.py` to communicate with local `Ollama` instances.
  - Enforces strict JSON output for: Summary, Action Items, Highlights, Decisions.
  - Added regex fallbacks if the LLM produces malformed JSON.
- **Email Delivery**: Built `email_sender.py` to dispatch HTML-styled reports via `smtplib` using TLS/SSL.
- **Data Persistence**:
  - `session_metadata.py` to track timestamps, duration, theme, and mode.
  - Automatically saves raw `.json` archives in `/sessions/` and readable `.md` backups in `/notes/`.
- **Configuration Management**: Introduced `config.py` parsing a `.env` file via `python-dotenv`. Added UI-to-disk write-back for Theme and Mode toggles.
- **Comprehensive Testing**: Added 100+ tests using `pytest` and `pytest-mock` to isolate dependencies (audio hardware, network requests).
- **Cross-Platform Scripts**: Created bash (`install.sh`), PowerShell (`install.ps1`), and Python prerequisite checkers (`check_prereqs.py`).

### Project Walkthrough Notes
The complete implementation plan was executed sequentially:
1. **Scaffolding**: pyproject.toml and directories created.
2. **Foundational Modules**: Config, SessionMetadata, TranscriptStore, LLMClient, EmailSender, and AudioCapture built by parallel subagents.
3. **Core Integration**: Whisper Transcription, Controller Orchestrator, Textual Display built and wired.
4. **Testing**: Prerequisite checks run successfully, verifying module linkages, CLI functionality, and dependency installation in virtual environments.
