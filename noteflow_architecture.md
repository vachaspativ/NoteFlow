# NoteFlow — Complete Architecture Documentation

> **Reverse-engineered from codebase** | Version 0.1.0 | Last updated: 2026-08-27

---

## 1. System Overview

NoteFlow is a **100% offline, AI-powered meeting note-taker** for Windows, Linux, and macOS. It captures real-time audio from microphones and WASAPI speaker loopback, transcribes speech using locally-shipped `faster-whisper` models (with automatic CUDA/CPU fallback), synthesizes structured executive meeting notes via a local `Ollama` LLM (supporting single-pass and Map-Reduce architectures), and optionally dispatches them via SMTP email.

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
        WEB["Web UI<br/>(FastAPI + Vanilla JS SPA)"]
        TUI["Terminal TUI<br/>(Textual)"]
    end

    subgraph "Entry Point"
        CLI["main.py<br/>(Click CLI)"]
    end

    subgraph "Core Engine"
        CTRL["SessionController<br/>(Orchestrator)"]
        CFG["Settings<br/>(config.py + config.yaml)"]
    end

    subgraph "Audio Pipeline"
        MIC["Microphone Input<br/>(sounddevice)"]
        LOOP["WASAPI Loopback<br/>(Speaker Audio)"]
        ACAP["AudioCapture<br/>(Dual-Stream Mixer)"]
    end

    subgraph "AI Pipeline"
        WHISPER["WhisperTranscriber<br/>(faster-whisper, local + CUDA auto-fallback)"]
        TSTORE["TranscriptStore<br/>(Thread-Safe)"]
        LLM["LLMClient<br/>(Ollama HTTP + Map-Reduce)"]
    end

    subgraph "Output Pipeline"
        EMAIL["EmailSender<br/>(SMTP + HTML Template)"]
        JSON_OUT["Session Archive<br/>(JSON)"]
        MD_OUT["Markdown Notes<br/>(*.md)"]
    end

    subgraph "Background Services"
        DAEMON["CallDetectorDaemon<br/>(Ranked Signal Waterfall)"]
        LOG_WATCH["TeamsLogWatcher<br/>(SlimCore / Classic Logs)"]
        NET_MON["CallNetworkMonitor<br/>(psutil UDP + Media CIDRs)"]
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

    DAEMON --> LOG_WATCH
    DAEMON --> NET_MON
    DAEMON -->|Process-Scoped Window Scan| CTRL

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

    daemon --> config
    daemon --> log_watcher["log_watcher.py"]
    daemon --> network_monitor["network_monitor.py"]

    web_server --> controller
    web_server --> config
    web_server --> audio_capture

    display --> controller
    display --> config

    llm_client --> prompts["prompts/meeting_notes_prompt.md"]
    llm_client --> map_prompt["prompts/map_prompt.md"]
    llm_client --> reduce_prompt["prompts/reduce_prompt.md"]

    email_sender --> templates["templates/email_template.html"]

    style main fill:#1f6feb,color:#fff
    style controller fill:#1f6feb,color:#fff
    style config fill:#d29922,color:#fff
    style daemon fill:#f85149,color:#fff
```

---

## 4. Project Directory Structure

```
NoteFlow/
├── noteflow/                    # Core Python package
│   ├── __init__.py              # HF Hub env var suppression + version
│   ├── main.py                  # Click CLI entry point
│   ├── config.py                # Settings dataclass + YAML persistence
│   ├── controller.py            # SessionController orchestrator
│   ├── audio_capture.py         # Dual-stream mic + WASAPI loopback capture
│   ├── transcription.py         # faster-whisper STT wrapper + CUDA/CPU fallback
│   ├── llm_client.py            # Ollama HTTP client + Map-Reduce pipeline
│   ├── network_monitor.py       # UDP socket & media relay IP monitor (psutil)
│   ├── log_watcher.py           # SlimCore & Classic Teams log tailer
│   ├── daemon.py                # CallDetectorDaemon (3-layer signal waterfall)
│   ├── email_sender.py          # SMTP email sender + HTML templates
│   ├── display.py               # Textual TUI screens
│   ├── session_metadata.py      # Session ID, timestamps, filename generation
│   ├── transcript_store.py      # Thread-safe segment store
│   ├── web_server.py            # FastAPI app, REST endpoints, WebSocket
│   ├── web/                     # Web UI static files
│   │   ├── index.html           # SPA with HUD, Stepper, and Settings modal
│   │   ├── style.css            # Dark/light theme design tokens
│   │   ├── app.js               # Client-side state machine & WS streaming
│   │   └── logo.png             # NoteFlow logo asset
│   ├── templates/
│   │   └── email_template.html  # HTML email template
│   └── prompts/
│       ├── meeting_notes_prompt.md
│       ├── map_prompt.md
│       └── reduce_prompt.md
├── models/                      # Pre-shipped faster-whisper model weights
│   └── models--Systran--faster-whisper-base.en/
├── prompts/
│   ├── meeting_notes_prompt.md  # Externalized standard synthesis prompt
│   ├── map_prompt.md            # Chunk analysis prompt (Map phase)
│   └── reduce_prompt.md         # Master aggregation prompt (Reduce phase)
├── scripts/
│   ├── install.ps1              # Windows installer
│   ├── install.sh               # Linux/macOS installer
│   ├── check_prereqs.py         # Prerequisite checker
│   └── preload_models.py        # Model weight downloader
├── tests/                       # 132 automated unit tests (mock-everything)
│   ├── test_network_monitor.py  # UDP inspection & IP CIDR tests
│   ├── test_log_watcher.py      # Teams log marker state machine tests
│   ├── test_daemon.py           # Daemon waterfall & PID filter tests
│   └── ...                      # Full test suite covering all modules
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

## 6. Auto Call Detection — Daemon Sequence & Ranked Signal Waterfall

NoteFlow features a **Ranked Signal Waterfall** architecture to eliminate false-positive recording triggers caused by background notifications, audio endpoint toggling, or non-communication browser tabs.

```mermaid
sequenceDiagram
    participant Daemon as CallDetectorDaemon (_monitor_loop)
    participant Log as TeamsLogWatcher (Layer 1)
    participant Net as CallNetworkMonitor (Layer 2)
    participant Win32 as Window Title Check (Layer 3)
    participant Ctrl as SessionController

    loop Every 3 Seconds
        Note over Daemon: 1. Evaluate Signal Waterfall
        
        alt Layer 1: Teams Log Marker Found
            Daemon->>Log: check()
            Log-->>Daemon: True (callConnected / InACall)
            Note over Daemon: Immediate trigger (active_streak not required)
            Daemon->>Daemon: active = True
        else Layer 2: Network Media Relay Active
            Daemon->>Net: check_call_active()
            Net-->>Daemon: True (≥2 UDP conns to Teams/Meet CIDRs or 3478-3481)
            Daemon->>Daemon: active = True
        else Layer 3: Process-Scoped Window Found
            Daemon->>Win32: _signal_window()
            Win32-->>Daemon: True (comm-app PID owning meeting window)
            Daemon->>Daemon: active = True
        else No signals
            Daemon->>Daemon: active = False
        end

        Note over Daemon: 2. Streak & State Resolution

        alt active = True
            Daemon->>Daemon: _active_streak++, _silence_streak = 0
            alt _active_streak ≥ daemon_active_streak_required AND not recording AND past cooldown
                Daemon->>Ctrl: start_session(auto_title, is_auto_started=True)
                Note over Daemon: is_in_call = True, _is_auto_session = True
            end
        else active = False
            Daemon->>Daemon: _silence_streak++, _active_streak = 0
            alt _silence_streak ≥ 4 AND is_in_call AND _is_auto_session
                Daemon->>Ctrl: stop_session()
                Note over Daemon: is_in_call = False, _is_auto_session = False
                alt Empty transcript
                    Daemon->>Daemon: Enter 15s cooldown
                end
            end
        end
    end
```

### 6.1 Waterfall Detection Layers

| Layer | Module / Technology | Target Apps | How It Works | Latency / Behavior |
|---|---|---|---|---|
| **Layer 1** | `TeamsLogWatcher`<br/>(`noteflow/log_watcher.py`) | Microsoft Teams (SlimCore & Classic) | Tails `%LOCALAPPDATA%\\...\\MSTeamsNM_SlimCore_*.log` and classic `logs.txt` for `callConnected`, `InACall`, `callEnded` markers. | **Instant (<1s)** on Windows. Fires immediately on the first positive poll without requiring streak confirmation. |
| **Layer 2** | `CallNetworkMonitor`<br/>(`noteflow/network_monitor.py`) | MS Teams, Google Meet (via Chrome) | Inspects `psutil.net_connections(kind='udp')` for communication processes. Matches Microsoft media CIDRs (`13.107.64.0/18`, `52.112.0.0/14`, `52.122.0.0/15`) and Google WebRTC ranges (`74.125.0.0/16`, `142.250.0.0/15`). | **Primary cross-platform gate (2–4s)**. Requires $\ge 2$ simultaneous UDP relay connections across $N$ consecutive polls. |
| **Layer 3** | `win32gui` + `win32process` + `psutil`<br/>(`noteflow/daemon.py`) | Teams, Zoom, Webex, Slack, Discord | Enumerates visible windows strictly filtered by owning process PID against communication executables. Matches confirmed meeting keywords (`"Meeting \|"`, `"Zoom Meeting"`, `"Discord Call"`). | **Windows fallback (3–6s)**. Completely immune to non-communication browser tabs and reminders. |

### 6.2 Corporate VPN & VDI Fallback Handling
- **Direct Internet**: Layer 2 inspects destination IP addresses against verified Microsoft Azure CDN and Google ASN prefixes.
- **Corporate VPN / TURN Gateway**: When corporate routing tunnels traffic through an internal VPN gateway, the remote IP belongs to the enterprise proxy rather than Microsoft. In this case, Layer 2 automatically falls back to **STUN/TURN UDP Port Matching** (`3478`, `3479`, `3480`, `3481`).
- **Loopback & Local Exclusion**: All loopback (`127.0.0.0/8`), unspecified (`0.0.0.0/8`), and non-communication process UDP traffic are strictly excluded before port evaluation.

### 6.3 Manual vs. Auto Session Segregation
- **Daemon Auto-Started (`is_auto_started=True`)**: Monitored by the daemon; when all signals go silent for 4 consecutive polls (~12 seconds), the daemon automatically stops recording and synthesizes notes.
- **Manual UI / TUI Session (`is_auto_started=False`)**: The user retains full lifecycle control. Even if `auto_call_detection: true` is configured and no external call is detected, manual sessions will **never** be auto-terminated by the daemon.

### 6.4 Debounce & Cooldown Timers

| Timer | Default Duration | Purpose |
|---|---|---|
| **Start Streak Threshold** | 2 consecutive polls (~6s) | Configurable via `daemon_active_streak_required`. Eliminates false spikes. |
| **Stop Silence Threshold** | 4 consecutive polls (~12s) | Prevents premature session termination during momentary call pauses. |
| **Empty Session Cooldown** | 15 seconds | Prevents infinite re-triggering after empty transcript sessions. |
| **Manual Stop Cooldown** | 30 seconds | Prevents daemon from immediately re-detecting after a user manually stops. |

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

## 9. Whisper Transcription & Hardware Fallback

```mermaid
flowchart TD
    START["WhisperTranscriber.__init__()"] --> ENV["Set HF_HUB_OFFLINE=1<br/>Set TRANSFORMERS_OFFLINE=1"]
    ENV --> RESOLVE["_resolve_whisper_model_path()"]
    
    RESOLVE --> CHECK1{"models/base.en/<br/>model.bin exists?"}
    CHECK1 -->|Yes| DIRECT["Use direct path:<br/>models/base.en/"]
    CHECK1 -->|No| CHECK2{"HF snapshot dir exists?<br/>models/models--Systran--<br/>faster-whisper-base.en/<br/>snapshots/&lt;hash&gt;/"}
    CHECK2 -->|Yes| SNAPSHOT["Use snapshot path"]
    CHECK2 -->|No| FALLBACK["Use model name string:<br/>'base.en'"]

    DIRECT --> LOAD["WhisperModel(<br/>target_model,<br/>device=auto/cuda/cpu,<br/>compute_type=float16/int8)"]
    SNAPSHOT --> LOAD
    FALLBACK --> LOAD

    LOAD --> DEV_CHECK{"device == 'cuda'?"}
    DEV_CHECK -->|Yes| CUDA_PROBE["CUDA Execution Probe<br/>(Transcribe 100ms dummy buffer to force<br/>lazy cublas64_12.dll load)"]
    DEV_CHECK -->|No| DONE["✅ Model Ready (CPU)"]

    CUDA_PROBE --> PROBE_OK{"DLLs & CUDA<br/>runtime OK?"}
    PROBE_OK -->|Yes| CUDA_READY["✅ Model Ready (CUDA float16)"]
    PROBE_OK -->|No / DLL missing| CPU_FALLBACK["⚠️ Warning Logged<br/>Auto fallback to CPU int8<br/>Reload WhisperModel on CPU"]
    CPU_FALLBACK --> DONE

    LOAD --> SUCCESS{"Load<br/>successful?"}
    SUCCESS -->|No, allow_online=True| ONLINE["WhisperModel(<br/>model_name,<br/>local_files_only=False)"]
    SUCCESS -->|No, allow_online=False| ERROR["❌ RuntimeError<br/>(offline mode enforced)"]
    ONLINE --> DEV_CHECK

    style CUDA_READY fill:#3fb950,color:#fff
    style DONE fill:#3fb950,color:#fff
    style CPU_FALLBACK fill:#d29922,color:#fff
    style ERROR fill:#f85149,color:#fff
```

### 9.1 CUDA Runtime DLL Auto-Fallback
On Windows systems with NVIDIA GPUs, CTranslate2 dynamically loads CUDA runtime libraries (`cublas64_12.dll`, `cublasLt64_12.dll`, `cudnn_ops_infer64_8.dll`) upon the first tensor inference. If the user's system lacks these specific DLLs in its Windows PATH:
1. The initial constructor test catches the missing symbol error.
2. NoteFlow logs an informative warning: `CUDA execution test failed (likely missing runtime DLLs). Automatically falling back to CPU mode.`
3. Re-instantiates `WhisperModel(device='cpu', compute_type='int8')` to ensure uninterrupted transcription.

---

## 10. LLM Note Generation & Map-Reduce Pipeline

NoteFlow provides two interchangeable note synthesis pipelines depending on transcript length and configuration:

```mermaid
flowchart TD
    START["controller._generate_and_send()"] --> CHECK_LEN{"enable_map_reduce == true<br/>AND words > 1,200?"}

    subgraph "Standard Single-Pass Pipeline"
        CHECK_LEN -->|No| SINGLE["Load prompts/meeting_notes_prompt.md"]
        SINGLE --> CLIP["Clip transcript to 16,000 chars (BAU)"]
        CLIP --> OLLAMA_SINGLE["POST /api/generate<br/>(format: 'json')"]
        OLLAMA_SINGLE --> PARSE_SINGLE["_validate_notes()"]
    end

    subgraph "Native Map-Reduce Pipeline (Long Meetings)"
        CHECK_LEN -->|Yes| CHUNK["_chunk_transcript()<br/>(800–1,200 word blocks with 10% overlap)"]
        CHUNK --> MAP_LOOP["Map Phase (prompts/map_prompt.md)<br/>Analyze each chunk independently"]
        MAP_LOOP --> REDUCE["Reduce Phase (prompts/reduce_prompt.md)<br/>Aggregate chunk summaries, deduplicate actions & decisions"]
        REDUCE --> PARSE_REDUCE["_validate_notes()<br/>(Enforce top-10 caps)"]
    end

    PARSE_SINGLE --> OUT["Validated NoteFlow JSON Output"]
    PARSE_REDUCE --> OUT

    style OUT fill:#3fb950,color:#fff
    style CHUNK fill:#a371f7,color:#fff
    style SINGLE fill:#1f6feb,color:#fff
```

### 10.1 Map-Reduce Processing for Long Calls
- **Motivation**: When meeting transcripts exceed 15–30 minutes, feeding 20,000+ characters into Ollama running on consumer CPUs causes extreme token prefill latency and memory ballooning.
- **Map Phase**: Each chunk is analyzed separately to extract key points, preliminary action items, and decisions.
- **Reduce Phase**: A master prompt aggregates all chunk outputs into a unified, high-level Chief of Staff summary, deduplicating repeated items.

### 10.2 LLM Output Schema

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

> All arrays are strictly validated and capped at **10 items maximum** by `_validate_notes()`.

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
| `whisper_model` | `string` | `base.en` | Whisper model size (`tiny.en`, `base.en`, `small.en`, `medium.en`) |
| `whisper_device` | `string` | `auto` | Compute device (`auto`, `cuda`, `cpu`) with dynamic fallback |
| `chunk_duration_secs` | `int` | `3` | Audio chunk window (seconds) |
| `vad_threshold` | `float` | `0.5` | Voice activity detection threshold (Silero VAD) |
| `enable_loopback` | `bool` | `true` | Two-way WASAPI speaker capture |
| `auto_call_detection` | `bool` | `false` | Background Teams/Zoom/Meet call listener |
| `default_meeting_title_prefix` | `string` | `[NoteFlow] Meeting` | Auto-session title prefix |
| `allow_online_model_download` | `bool` | `false` | Permit HF Hub network access |
| `enable_email` | `bool` | `true` | Enable automatic SMTP dispatch |
| `enable_map_reduce` | `bool` | `false` | Native chunked Map-Reduce pipeline for long transcripts |
| `daemon_network_check_enabled` | `bool` | `true` | Layer 2: Network UDP media relay monitor |
| `daemon_log_watch_enabled` | `bool` | `true` | Layer 1: Teams SlimCore/Classic log file watcher |
| `daemon_window_check_enabled` | `bool` | `true` | Layer 3: Process-scoped meeting window title check |
| `daemon_active_streak_required` | `int` | `2` | Consecutive positive polls before auto-starting session |
| `daemon_min_udp_connections` | `int` | `2` | Minimum simultaneous UDP media connections |
| `notes_dir` | `string` | `../noteflow_notes` | Markdown output directory |
| `sessions_dir` | `string` | `../noteflow_sessions` | JSON archive directory |
| `ollama_host` | `string` | `http://localhost` | Ollama server host |
| `ollama_port` | `int` | `11434` | Ollama server port |
| `ollama_model` | `string` | `llama3.2` | LLM model for note synthesis |
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
    DAEMON -->|poll every 3s| STOP

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
|---|---|---|
| **CUDA runtime DLL missing (`cublas64_12.dll`)** | Catches dynamic library symbol failure upon probe | Automatically falls back to CPU `int8` quantization without crashing the session |
| **Corporate VPN / VDI media routing** | Target IP masked by VPN gateway | Layer 2 auto-falls back to STUN/TURN UDP port inspection (`3478–3481`) |
| **Manual UI session with daemon running** | `is_auto_started: false` | Daemon ignores call inactivity; session will never be prematurely stopped |
| **Ollama not running** | `check_available()` returns `False` | Status pill turns red; transcript still saved; notes generation skipped |
| **Whisper model missing locally** | `RuntimeError` if `allow_online=False` | Error displayed in UI; user must run install scripts |
| **Microphone unavailable** | `sd.PortAudioError` caught | Status pill turns red; recording cannot start |
| **WASAPI loopback fails** | Exception caught silently | Falls back to single-mic capture (no caller audio) |
| **LLM timeout on long transcripts** | Retries up to `max_retries` | Error card in UI with one-click "Retry" button; transcript preserved |
| **SMTP failure** | Exception logged | `email_sent: false`; notes + transcript still saved to disk |
| **Empty transcript** | Detected before LLM call | Skips LLM generation; logs warning; saves empty session |
| **Daemon false trigger** | Streak filter + cooldown timers | 6s start debounce, 12s stop debounce, 15s/30s cooldowns |

---

## 17. Technology Stack Summary

| Layer | Technology | Purpose |
|---|---|---|
| **CLI** | `click` | Command-line interface and argument parsing |
| **Web Server** | `FastAPI` + `uvicorn` | REST API + WebSocket streaming server |
| **Web UI** | Vanilla HTML5 / CSS3 / ES6 JS | Responsive single-page application |
| **Terminal UI** | `textual` | Rich keyboard-driven terminal interface |
| **Audio Capture** | `sounddevice` (PortAudio) | Multi-channel microphone and loopback audio streams |
| **Call Detection** | `psutil` + `win32gui` + File Tailing | Ranked Signal Waterfall for Teams, Zoom, Webex, and Meet |
| **STT** | `faster-whisper` (CTranslate2) | Offline speech-to-text with auto CUDA/CPU fallback |
| **LLM Synthesis** | `Ollama` (HTTP POST) | Local LLM inference (llama3.2) + Map-Reduce orchestrator |
| **Config** | `PyYAML` + `python-dotenv` | Two-way synchronized YAML & environment configuration |
| **Email** | `smtplib` + `email` | Responsive HTML and plain-text SMTP email delivery |
| **Testing** | `pytest` + `pytest-mock` | 132 automated unit tests (mock-everything approach) |

---

*Architecture documentation updated to NoteFlow v0.1.0 codebase.*
