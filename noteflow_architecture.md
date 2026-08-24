# NoteFlow — Complete Architecture Documentation

> **Reverse-engineered from codebase** | Version 0.1.0 | Last updated: 2026-08-24

---

## 1. System Overview

NoteFlow is a **100% offline, AI-powered meeting note-taker** for Windows, Linux, and macOS. It captures real-time audio from microphones and WASAPI speaker loopback, transcribes speech using locally-shipped `faster-whisper` models, synthesizes structured executive meeting notes via a local `Ollama` LLM, and optionally dispatches them via SMTP email.

> [!IMPORTANT]
> **Core Design Principle**: All audio capture, speech-to-text, and LLM inference execute entirely on the user's local machine. No data leaves the device (except the optional SMTP email feature).

---

## 2. High-Level System Architecture

```mermaid
graph TB
    subgraph "User Layer"
        USER["👤 User"]
    end

    subgraph "UI Layer"
        WEB["Web UI<br/>(FastAPI + Vanilla JS)"]
        TUI["Terminal TUI<br/>(Textual)"]
    end

    subgraph "Entry Point"
        CLI["main.py<br/>(Click CLI)"]
    end

    subgraph "Core Engine"
        CTRL["SessionController<br/>(Orchestrator)"]
        CFG["Settings<br/>(config.py)"]
    end

    subgraph "Audio Pipeline"
        MIC["Microphone Input<br/>(sounddevice)"]
        LOOP["WASAPI Loopback<br/>(Speaker Audio)"]
        ACAP["AudioCapture<br/>(Dual-Stream Mixer)"]
    end

    subgraph "AI Pipeline"
        WHISPER["WhisperTranscriber<br/>(faster-whisper, local)"]
        TSTORE["TranscriptStore<br/>(Thread-Safe)"]
        LLM["LLMClient<br/>(Ollama HTTP)"]
    end

    subgraph "Output Pipeline"
        EMAIL["EmailSender<br/>(SMTP + HTML Template)"]
        JSON_OUT["Session Archive<br/>(JSON)"]
        MD_OUT["Markdown Notes<br/>(*.md)"]
    end

    subgraph "Background Services"
        DAEMON["CallDetectorDaemon<br/>(pycaw + win32gui)"]
    end

    subgraph "External Services"
        OLLAMA["Ollama Server<br/>(localhost:11434)"]
        SMTP["SMTP Server<br/>(Gmail / Custom)"]
    end

    USER --> WEB
    USER --> TUI
    USER --> CLI

    CLI --> CFG
    CLI --> CTRL
    CLI --> WEB
    CLI --> TUI

    WEB <-->|REST + WebSocket| CTRL
    TUI <--> CTRL

    CTRL --> ACAP
    CTRL --> WHISPER
    CTRL --> TSTORE
    CTRL --> LLM
    CTRL --> EMAIL
    CTRL --> JSON_OUT
    CTRL --> MD_OUT
    CTRL --> DAEMON

    ACAP --> MIC
    ACAP --> LOOP

    LLM -->|HTTP POST| OLLAMA
    EMAIL -->|SMTP/TLS| SMTP

    DAEMON -->|WASAPI Peak Meter| MIC
    DAEMON -->|Window Title Scan| CTRL

    style CTRL fill:#1f6feb,color:#fff,stroke:#1f6feb
    style DAEMON fill:#f85149,color:#fff
    style WHISPER fill:#3fb950,color:#fff
    style LLM fill:#a371f7,color:#fff
    style ACAP fill:#d29922,color:#fff
```

---

## 3. Module Dependency Graph

```mermaid
graph LR
    main["main.py"] --> config["config.py"]
    main --> controller["controller.py"]
    main --> display["display.py"]
    main --> web_server["web_server.py"]
    main --> audio_capture["audio_capture.py"]
    main --> daemon["daemon.py"]

    controller --> config
    controller --> session_metadata["session_metadata.py"]
    controller --> transcript_store["transcript_store.py"]
    controller --> llm_client["llm_client.py"]
    controller --> email_sender["email_sender.py"]
    controller --> audio_capture
    controller --> transcription["transcription.py"]
    controller --> daemon

    web_server --> controller
    web_server --> config
    web_server --> audio_capture

    display --> controller
    display --> config

    daemon --> controller

    llm_client --> prompts["prompts/meeting_notes_prompt.md"]

    email_sender --> templates["templates/email_template.html"]

    style main fill:#1f6feb,color:#fff
    style controller fill:#1f6feb,color:#fff
    style config fill:#d29922,color:#fff
```

---

## 4. Project Directory Structure

```
NoteFlow/
├── noteflow/                    # Core Python package
│   ├── __init__.py              # HF Hub env var suppression + version
│   ├── main.py                  # Click CLI entry point
│   ├── config.py                # Settings dataclass + YAML persistence
│   ├── controller.py            # SessionController orchestrator (637 LOC)
│   ├── audio_capture.py         # Dual-stream mic + WASAPI loopback capture
│   ├── transcription.py         # faster-whisper STT wrapper
│   ├── llm_client.py            # Ollama HTTP client + prompt builder
│   ├── email_sender.py          # SMTP email sender + HTML templates
│   ├── daemon.py                # CallDetectorDaemon (pycaw + win32gui)
│   ├── display.py               # Textual TUI screens
│   ├── session_metadata.py      # Session ID, timestamps, filename generation
│   ├── transcript_store.py      # Thread-safe segment store
│   ├── web_server.py            # FastAPI app, REST endpoints, WebSocket
│   ├── web/                     # Web UI static files
│   │   ├── index.html           # SPA (535+ lines)
│   │   ├── style.css            # 1400+ lines, dark/light themes
│   │   ├── app.js               # 1000+ lines, full client-side logic
│   │   └── logo.png             # NoteFlow logo asset
│   ├── templates/
│   │   └── email_template.html  # HTML email template
│   └── prompts/
│       └── meeting_notes_prompt.md
├── models/                      # Pre-shipped faster-whisper model weights
│   └── models--Systran--faster-whisper-base.en/
├── prompts/
│   └── meeting_notes_prompt.md  # Externalized LLM prompt
├── scripts/
│   ├── install.ps1              # Windows installer
│   ├── install.sh               # Linux/macOS installer
│   ├── check_prereqs.py         # Prerequisite checker
│   └── preload_models.py        # Model weight downloader
├── tests/                       # 107 unit tests (mock-everything)
├── config.yaml                  # User configuration
├── pyproject.toml               # Package metadata + dependencies
├── start.bat / start.ps1 / start.sh  # One-click launchers
└── README.md
```

---

## 5. Data Flow Architecture

### 5.1 Live Transcription Mode — End-to-End Pipeline

```mermaid
sequenceDiagram
    participant User
    participant WebUI as Web UI / TUI
    participant Ctrl as SessionController
    participant AC as AudioCapture
    participant Mic as Microphone
    participant Loop as WASAPI Loopback
    participant TS as TranscriptStore
    participant Whisper as WhisperTranscriber
    participant WS as WebSocket (/ws/live)

    User->>WebUI: Click "Start Recording"
    WebUI->>Ctrl: POST /api/session/start
    Ctrl->>AC: start(batch_mode=False)
    AC->>Mic: Open InputStream (16kHz, mono)
    AC->>Loop: Open WASAPI Loopback Stream
    Ctrl->>Ctrl: Spawn _processing_thread

    loop Every 3-Second Chunk
        Mic-->>AC: Raw PCM chunk (mic)
        Loop-->>AC: Raw PCM chunk (speaker)
        AC->>AC: Mix: (mic + loopback) / 2.0
        AC->>AC: Put mixed chunk → audio_queue
        Ctrl->>AC: get_chunk(timeout=0.5)
        AC-->>Ctrl: mixed_audio_chunk
        Ctrl->>Whisper: transcribe_chunk(chunk)
        Whisper-->>Ctrl: "transcribed text"
        Ctrl->>TS: append(text)
        Ctrl->>WS: broadcast_segment(timestamp, text)
        WS-->>WebUI: {"type":"segment","data":{...}}
        WebUI->>WebUI: Render live transcript
    end

    User->>WebUI: Click "Stop Recording"
    WebUI->>Ctrl: POST /api/session/stop
    Ctrl->>AC: stop()
    Ctrl->>Ctrl: Drain remaining chunks
    Note over Ctrl: _generate_and_send()
    Ctrl->>Whisper: (drain final chunks)
    Ctrl->>TS: get_full_transcript()
    Ctrl->>Ctrl: Build LLM prompt
    Ctrl->>Ctrl: Call Ollama → generate_notes()
    Ctrl->>Ctrl: Save JSON archive + Markdown
    Ctrl->>Ctrl: Send SMTP email (if enabled)
    Ctrl-->>WebUI: {"notes": {...}}
    WebUI->>User: Display Executive Report
```

### 5.2 Batch Transcription Mode — End-to-End Pipeline

```mermaid
sequenceDiagram
    participant User
    participant WebUI as Web UI / TUI
    participant Ctrl as SessionController
    participant AC as AudioCapture
    participant TS as TranscriptStore
    participant Whisper as WhisperTranscriber
    participant LLM as LLMClient (Ollama)

    User->>WebUI: Start Recording (Batch Mode)
    WebUI->>Ctrl: POST /api/session/start {mode: "batch"}
    Ctrl->>AC: start(batch_mode=True)
    Note over AC: Audio chunks accumulate in _batch_buffer<br/>No real-time transcription

    loop Entire Meeting Duration
        AC->>AC: Append mic+loopback chunks to _batch_buffer
    end

    User->>WebUI: Stop Recording
    WebUI->>Ctrl: POST /api/session/stop
    Ctrl->>AC: stop()
    Ctrl->>AC: get_full_audio()
    AC-->>Ctrl: Full concatenated audio (numpy array)
    Ctrl->>Whisper: transcribe_full(full_audio)
    Whisper-->>Ctrl: Complete transcript text
    Ctrl->>TS: append(full_text)
    Ctrl->>LLM: generate_notes(transcript)
    LLM-->>Ctrl: {summary, action_items, highlights, decisions}
    Ctrl->>Ctrl: Save JSON + Markdown
    Ctrl->>Ctrl: Send SMTP email
    Ctrl-->>WebUI: {"notes": {...}}
```

---

## 6. Auto Call Detection — Daemon Sequence

```mermaid
sequenceDiagram
    participant Daemon as CallDetectorDaemon
    participant WASAPI as pycaw (WASAPI Sessions)
    participant Win32 as win32gui (Window Titles)
    participant Ctrl as SessionController

    loop Every 3 Seconds
        Daemon->>WASAPI: GetAllSessions()
        WASAPI-->>Daemon: Audio sessions list
        Daemon->>Daemon: Filter by TARGET_COMMUNICATION_KEYWORDS
        Daemon->>WASAPI: QueryInterface(IAudioMeterInformation)
        WASAPI-->>Daemon: GetPeakValue()

        alt Peak > 0.01 (Active Audio)
            Daemon->>Daemon: _active_streak++
        else Peak ≤ 0.01
            Daemon->>Win32: EnumWindows()
            Win32-->>Daemon: Visible window titles

            alt Meeting/call keyword found in title
                Daemon->>Daemon: _active_streak++
            else No call indicators
                Daemon->>Daemon: _silence_streak++
            end
        end

        alt _active_streak ≥ 2 AND not is_in_call AND past cooldown
            Daemon->>Ctrl: start_session(auto_title, mode, theme)
            Note over Daemon: is_in_call = True
        end

        alt _silence_streak ≥ 4 AND is_in_call
            Daemon->>Ctrl: stop_session()
            Note over Daemon: is_in_call = False
            alt Empty transcript
                Daemon->>Daemon: Enter 15s cooldown
            end
        end
    end
```

### Detection Layers

| Layer | Technology | What It Checks | Threshold |
|-------|-----------|----------------|-----------|
| **L1** | `pycaw` WASAPI `IAudioMeterInformation` | Real-time audio peak volume of Teams/Zoom/Webex process | `GetPeakValue() > 0.01` |
| **L2** | `win32gui.EnumWindows()` | Visible window titles for meeting/call keywords | Title contains `"meeting \|"`, `"call with"`, `"in a call"`, etc. |

### Debounce & Cooldown Timers

| Timer | Duration | Purpose |
|-------|----------|---------|
| **Start Debounce** | 2 consecutive polls (6s) | Prevents false triggers from brief audio spikes |
| **Stop Debounce** | 4 consecutive polls (12s) | Prevents premature session termination during call silence |
| **Empty Session Cooldown** | 15 seconds | Prevents infinite re-triggering after empty transcript sessions |
| **Manual Stop Cooldown** | 30 seconds | Prevents daemon from immediately re-detecting after user manually stops |

---

## 7. Web UI Architecture

```mermaid
graph TB
    subgraph "Browser Client (SPA)"
        HTML["index.html<br/>(5 Views)"]
        CSS["style.css<br/>(Dark/Light Themes)"]
        JS["app.js<br/>(State Machine)"]
    end

    subgraph "FastAPI Server"
        REST["REST API<br/>(/api/*)"]
        WSS["WebSocket<br/>(/ws/live)"]
        STATIC["Static Files<br/>(/static/*)"]
    end

    JS -->|fetch()| REST
    JS <-->|Real-time segments| WSS
    HTML -->|Load| STATIC

    subgraph "SPA Views"
        V1["Setup View<br/>(Title, Mode, Mic, Start)"]
        V2["Recording HUD<br/>(Timer, Waveform, Live Feed)"]
        V3["Processing View<br/>(Progress Steps)"]
        V4["Results View<br/>(Summary, Actions, Highlights)"]
        V5["Settings Modal<br/>(All Config Options)"]
    end

    HTML --> V1
    HTML --> V2
    HTML --> V3
    HTML --> V4
    HTML --> V5

    style JS fill:#d29922,color:#fff
    style WSS fill:#3fb950,color:#fff
```

### REST API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/status` | System health, component status, daemon state |
| `GET` | `/api/devices` | List audio input devices |
| `GET` | `/api/settings` | Read all configuration settings |
| `POST` | `/api/settings` | Update settings + persist to `config.yaml` |
| `POST` | `/api/session/start` | Start recording session |
| `POST` | `/api/session/stop` | Stop recording + generate notes |
| `GET` | `/api/session/current` | Get real-time session info |
| `GET` | `/api/session/transcript` | Get current transcript |
| `POST` | `/api/session/regenerate` | Re-run LLM on current session |
| `GET` | `/api/sessions` | List all past session archives |
| `GET` | `/api/sessions/{id}` | Get full session detail |
| `POST` | `/api/sessions/{id}/resend` | Re-send email for past session |
| `POST` | `/api/sessions/{id}/regenerate` | Re-generate notes for past session |
| `GET` | `/api/sessions/{id}/markdown` | Download markdown notes |
| `GET` | `/api/sessions/{id}/transcript/download` | Download raw transcript |
| `WS` | `/ws/live` | Real-time segment + status streaming |

---

## 8. Audio Capture — Dual-Stream Architecture

```mermaid
graph LR
    subgraph "Hardware Layer"
        MIC["🎤 Microphone<br/>(Default or Selected)"]
        SPK["🔊 Speakers/Headset<br/>(Default Render)"]
    end

    subgraph "AudioCapture Module"
        IS["sd.InputStream<br/>(Mic Callback)"]
        LS["sd.InputStream<br/>(WASAPI Loopback)"]
        MQ["audio_queue<br/>(Queue, max=50)"]
        LQ["loopback_queue<br/>(Queue, max=50)"]
        MIX["Audio Mixer<br/>(mic + loopback) / 2.0"]
    end

    subgraph "Output"
        LIVE["Live Mode:<br/>Queue → Whisper"]
        BATCH["Batch Mode:<br/>_batch_buffer[]"]
    end

    MIC -->|16kHz mono PCM| IS
    SPK -->|WASAPI Loopback| LS
    IS -->|callback| MQ
    LS -->|callback| LQ
    MQ --> MIX
    LQ --> MIX
    MIX --> LIVE
    MIX --> BATCH

    style MIX fill:#d29922,color:#fff
    style IS fill:#3fb950,color:#fff
    style LS fill:#a371f7,color:#fff
```

---

## 9. Whisper Transcription — Model Resolution

```mermaid
flowchart TD
    START["WhisperTranscriber.__init__()"] --> ENV["Set HF_HUB_OFFLINE=1<br/>Set TRANSFORMERS_OFFLINE=1"]
    ENV --> RESOLVE["_resolve_whisper_model_path()"]
    
    RESOLVE --> CHECK1{"models/base.en/<br/>model.bin exists?"}
    CHECK1 -->|Yes| DIRECT["Use direct path:<br/>models/base.en/"]
    CHECK1 -->|No| CHECK2{"HF snapshot dir exists?<br/>models/models--Systran--<br/>faster-whisper-base.en/<br/>snapshots/&lt;hash&gt;/"}
    CHECK2 -->|Yes| SNAPSHOT["Use snapshot path"]
    CHECK2 -->|No| FALLBACK["Use model name string:<br/>'base.en'"]

    DIRECT --> LOAD["WhisperModel(<br/>target_model,<br/>local_files_only=True,<br/>download_root='models/')"]
    SNAPSHOT --> LOAD
    FALLBACK --> LOAD

    LOAD --> SUCCESS{"Load<br/>successful?"}
    SUCCESS -->|Yes| DONE["✅ Model Ready"]
    SUCCESS -->|No, allow_online=True| ONLINE["WhisperModel(<br/>model_name,<br/>local_files_only=False)"]
    SUCCESS -->|No, allow_online=False| ERROR["❌ RuntimeError<br/>(offline mode enforced)"]
    ONLINE --> DONE

    style DONE fill:#3fb950,color:#fff
    style ERROR fill:#f85149,color:#fff
    style ENV fill:#d29922,color:#fff
```

---

## 10. LLM Note Generation Pipeline

```mermaid
sequenceDiagram
    participant Ctrl as SessionController
    participant LLM as LLMClient
    participant Template as Prompt Template
    participant Ollama as Ollama Server

    Ctrl->>LLM: generate_notes(transcript, title, duration)
    LLM->>Template: _load_prompt_template()
    Note over Template: Load from prompts/meeting_notes_prompt.md<br/>or fallback embedded template
    Template-->>LLM: Template string
    LLM->>LLM: _build_prompt()<br/>Truncate transcript to 16K chars if needed
    LLM->>Ollama: POST /api/generate<br/>{model, prompt, stream:false, format:"json"}

    alt Success (HTTP 200)
        Ollama-->>LLM: {"response": "{...JSON...}"}
        LLM->>LLM: Parse JSON response
        LLM->>LLM: _validate_notes() — enforce top-10 caps
        LLM-->>Ctrl: {summary, action_items[], highlights[], decisions[]}
    end

    alt Timeout
        Ollama-->>LLM: TimeoutException
        LLM->>LLM: Retry (up to max_retries)
        LLM-->>Ctrl: OllamaNotAvailableError
    end

    alt JSON Parse Failure
        LLM->>LLM: Try regex extraction from ```json blocks
        LLM->>LLM: _fallback_notes(raw_text)
        LLM-->>Ctrl: {summary: raw_text}
    end
```

### LLM Output Schema

```json
{
  "summary": "Executive bullet-pointed summary (3-6 points)",
  "action_items": [
    {"owner": "John", "action": "Prepare Q3 report", "deadline": "Friday EOD"}
  ],
  "highlights": ["Key insight statement 1", "..."],
  "decisions": ["Decision statement 1", "..."]
}
```

> All arrays are capped at **10 items maximum** by `_validate_notes()`.

---

## 11. Email Delivery Pipeline

```mermaid
flowchart TD
    START["controller._generate_and_send()"] --> CHECK{"dry_run?<br/>OR enable_email=false?<br/>OR no email_to?"}

    CHECK -->|Yes| SKIP["Skip email.<br/>Log reason."]
    CHECK -->|No| BUILD["EmailSender.send()"]

    BUILD --> PLAIN["build_plain_text()"]
    BUILD --> HTML["build_html()<br/>(Load templates/email_template.html)"]
    PLAIN --> MSG["MIMEMultipart('alternative')"]
    HTML --> MSG

    MSG --> PORT{"Port 465?"}
    PORT -->|Yes| SSL["SMTP_SSL()"]
    PORT -->|No| TLS["SMTP() + STARTTLS"]

    SSL --> LOGIN["Login (username, password)"]
    TLS --> LOGIN
    LOGIN --> SEND["sendmail(from, to, msg)"]
    SEND --> DONE["✅ Email Sent"]

    style DONE fill:#3fb950,color:#fff
    style SKIP fill:#d29922,color:#fff
```

---

## 12. Configuration Architecture

```mermaid
flowchart LR
    subgraph "Configuration Sources (Priority Order)"
        CLI["CLI Flags<br/>(--mode, --model, --tui)"]
        YAML["config.yaml<br/>(Primary)"]
        ENV[".env file<br/>(Legacy)"]
        DEFAULTS["Hardcoded Defaults"]
    end

    CLI -->|Highest Priority| SETTINGS["Settings Dataclass"]
    YAML --> SETTINGS
    ENV --> SETTINGS
    DEFAULTS -->|Lowest Priority| SETTINGS

    SETTINGS -->|Persist changes| YAML
    SETTINGS --> CTRL["SessionController"]
    SETTINGS --> WEBUI["Web UI Settings Modal"]
    SETTINGS --> TUI_SET["TUI Setup Screen"]

    style SETTINGS fill:#1f6feb,color:#fff
    style CLI fill:#3fb950,color:#fff
```

### Configuration Keys

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `theme` | `dark\|light` | `dark` | UI color theme |
| `transcription_mode` | `live\|batch` | `live` | Real-time vs post-meeting transcription |
| `whisper_model` | `string` | `base.en` | Whisper model size |
| `whisper_device` | `string` | `cpu` | Compute device (`cpu`/`cuda`) |
| `chunk_duration_secs` | `int` | `3` | Audio chunk window (seconds) |
| `vad_threshold` | `float` | `0.5` | Voice activity detection threshold |
| `enable_loopback` | `bool` | `true` | Two-way WASAPI speaker capture |
| `auto_call_detection` | `bool` | `false` | Background Teams/Zoom call listener |
| `default_meeting_title_prefix` | `string` | `[NoteFlow] Meeting` | Auto-session title prefix |
| `allow_online_model_download` | `bool` | `false` | Permit HF Hub network access |
| `enable_email` | `bool` | `true` | Enable automatic SMTP dispatch |
| `notes_dir` | `string` | `../noteflow_notes` | Markdown output directory |
| `sessions_dir` | `string` | `../noteflow_sessions` | JSON archive directory |
| `ollama_host` | `string` | `http://localhost` | Ollama server host |
| `ollama_port` | `int` | `11434` | Ollama server port |
| `ollama_model` | `string` | `llama3` | LLM model for note synthesis |
| `ollama_timeout` | `int` | `300` | LLM request timeout (seconds) |
| `ollama_max_retries` | `int` | `1` | LLM retry count on failure |

---

## 13. Thread Architecture

```mermaid
graph TB
    subgraph "Main Thread"
        MAIN["main.py<br/>(Click CLI)"]
        UVICORN["Uvicorn Event Loop<br/>(FastAPI + WebSocket)"]
    end

    subgraph "Audio Threads (sounddevice callbacks)"
        MIC_CB["Microphone Callback<br/>(sd.InputStream)"]
        LOOP_CB["Loopback Callback<br/>(sd.InputStream WASAPI)"]
    end

    subgraph "Processing Thread"
        PROC["_processing_loop<br/>(Live Mode Only)"]
    end

    subgraph "Daemon Thread"
        DAEMON["CallDetectorDaemon<br/>_monitor_loop()"]
    end

    subgraph "Thread-Safe Shared State"
        AQ["audio_queue<br/>(Queue, max=50)"]
        LQ["loopback_queue<br/>(Queue, max=50)"]
        TS["TranscriptStore<br/>(Lock-protected)"]
        STOP["_stop_event<br/>(threading.Event)"]
        WLOCK["Whisper Lock<br/>(threading.Lock)"]
    end

    MAIN --> UVICORN
    MAIN --> DAEMON

    MIC_CB -->|put_nowait()| AQ
    LOOP_CB -->|put_nowait()| LQ
    PROC -->|get(timeout=0.5)| AQ
    PROC -->|transcribe_chunk()| WLOCK
    PROC -->|append()| TS
    DAEMON -->|check every 3s| STOP

    style WLOCK fill:#f85149,color:#fff
    style TS fill:#3fb950,color:#fff
    style AQ fill:#d29922,color:#fff
```

> [!WARNING]
> **Thread Safety Critical**: The `faster-whisper` model is **NOT thread-safe**. A `threading.Lock` (`self._lock`) must be acquired in `WhisperTranscriber.transcribe_chunk()` before every `self._model.transcribe()` call.

---

## 14. Output File Formats

### 14.1 JSON Session Archive

```
../noteflow_sessions/2026-08-24_NoteFlow_Meeting_a1b2c3d4.json
```

```json
{
  "session_id": "a1b2c3d4",
  "title": "[NoteFlow] Meeting 2026-08-24 14:30:00",
  "mode": "live",
  "theme": "dark",
  "start_time": "2026-08-24T14:30:00",
  "end_time": "2026-08-24T15:15:00",
  "duration_seconds": 2700,
  "duration_display": "45m 0s",
  "notes": {
    "summary": "- Key point 1\n- Key point 2",
    "action_items": [{"owner": "...", "action": "...", "deadline": "..."}],
    "highlights": ["..."],
    "decisions": ["..."]
  },
  "transcript": "Full plain text transcript",
  "timestamped_transcript": "[00:00] First segment\n[00:03] Second segment"
}
```

### 14.2 Markdown Notes

```
../noteflow_notes/2026-08-24_NoteFlow_Meeting_a1b2c3d4.md
```

```markdown
# 📝 [NoteFlow] Meeting 2026-08-24

**Duration:** 45m 0s | **Recorded:** 2026-08-24 15:15:00

---

## 📋 Executive Summary
- Key point 1
- Key point 2

## ✅ Action Items
- [ ] **John**: Prepare Q3 report *(Due: Friday EOD)*

## 💡 Key Highlights
- Notable insight from the discussion

## 🎯 Decisions Made
- Agreed to proceed with Option B

## 🎙️ Transcript
[00:00] First segment of speech...
[00:03] Second segment of speech...

---
*Generated by NoteFlow (100% Offline AI)*
```

---

## 15. Startup & Initialization Sequence

```mermaid
sequenceDiagram
    participant User
    participant CLI as main.py (Click)
    participant CFG as Settings
    participant CTRL as SessionController
    participant DAEMON as CallDetectorDaemon
    participant WEB as FastAPI/Uvicorn
    participant Browser

    User->>CLI: python -m noteflow.main [--flags]
    CLI->>CFG: Settings.from_env(config.yaml)
    Note over CFG: Parse YAML → Settings dataclass<br/>Apply CLI overrides

    CLI->>CTRL: SessionController(settings)
    CTRL->>CTRL: Init LLMClient, EmailSender
    CTRL->>DAEMON: CallDetectorDaemon(self)

    alt auto_call_detection = True
        CLI->>DAEMON: daemon.start()
        DAEMON->>DAEMON: Spawn _monitor_loop thread
    end

    alt UI Mode = WEB (default)
        CLI->>WEB: start_web_server(controller, host, port)
        WEB->>WEB: create_app(controller)
        WEB->>WEB: Register REST endpoints + WebSocket
        WEB->>WEB: Mount static files (noteflow/web/)
        WEB->>Browser: webbrowser.open(http://127.0.0.1:5000)
        Note over WEB: uvicorn.Server.run() — blocks main thread
    end

    alt UI Mode = TUI
        CLI->>CLI: NoteFlowApp(settings, controller).run()
        Note over CLI: Textual app blocks main thread
    end
```

---

## 16. Error Handling & Resilience

| Scenario | Behavior | Fallback |
|----------|----------|----------|
| **Ollama not running** | `check_available()` returns `False` | Status pill turns red; transcript still saved; notes generation skipped |
| **Whisper model missing locally** | `RuntimeError` if `allow_online=False` | Error displayed in UI; user must run install scripts |
| **Microphone unavailable** | `sd.PortAudioError` caught | Status pill turns red; recording cannot start |
| **WASAPI loopback fails** | Exception caught silently | Falls back to single-mic capture (no caller audio) |
| **LLM timeout** | Retry up to `max_retries` | Error message in notes; transcript preserved |
| **SMTP failure** | Exception logged | `email_sent: false`; notes + transcript still saved to disk |
| **Empty transcript** | Detected before LLM call | Skips LLM generation; logs warning; saves empty session |
| **Daemon false trigger** | Debounce + cooldown timers | 6s start debounce, 12s stop debounce, 15s/30s cooldowns |

---

## 17. Technology Stack Summary

| Layer | Technology | Purpose |
|-------|-----------|---------|
| **CLI** | `click` | Command-line interface and argument parsing |
| **Web Server** | `FastAPI` + `uvicorn` | REST API + WebSocket server |
| **Web UI** | Vanilla HTML5 / CSS3 / ES6 JS | Single-page application |
| **Terminal UI** | `textual` | Rich terminal interface |
| **Audio** | `sounddevice` (PortAudio) | Microphone input streams |
| **WASAPI** | `pycaw` + `sounddevice` | Speaker loopback capture + call detection |
| **STT** | `faster-whisper` (CTranslate2) | Offline speech-to-text |
| **LLM** | `Ollama` (HTTP POST) | Local LLM inference (llama3) |
| **Config** | `PyYAML` + `python-dotenv` | YAML/env file configuration |
| **Email** | `smtplib` | SMTP email delivery |
| **Testing** | `pytest` + `pytest-mock` | 107 unit tests, mock-everything |

---

*Architecture documentation reverse-engineered from NoteFlow v0.1.0 codebase.*
