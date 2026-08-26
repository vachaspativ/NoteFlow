from __future__ import annotations

import asyncio
import json
import logging
import os
import threading
import time
import webbrowser
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import uvicorn

from noteflow.config import Settings, TranscriptionMode, Theme, UIMode
from noteflow.controller import SessionController
from noteflow.audio_capture import list_audio_devices

logger = logging.getLogger(__name__)


class StartSessionRequest(BaseModel):
    title: str = "Untitled Meeting"
    mode: str = "live"
    theme: str = "dark"
    device_id: int | None = None


class UpdateSettingsRequest(BaseModel):
    theme: str | None = None
    transcription_mode: str | None = None
    ui_mode: str | None = None
    whisper_model: str | None = None
    whisper_device: str | None = None
    allow_online_model_download: bool | None = None
    enable_email: bool | None = None
    ollama_host: str | None = None
    ollama_port: int | None = None
    ollama_model: str | None = None
    ollama_timeout: int | None = None
    ollama_max_retries: int | None = None
    enable_loopback: bool | None = None
    auto_call_detection: bool | None = None
    default_meeting_title_prefix: str | None = None
    smtp_host: str | None = None
    smtp_port: int | None = None
    smtp_use_tls: bool | None = None
    smtp_username: str | None = None
    smtp_password: str | None = None
    email_from: str | None = None
    email_to: str | None = None
    email_subject_prefix: str | None = None
    enable_map_reduce: bool | None = None


class ResendEmailRequest(BaseModel):
    email_to: str | None = None


def create_app(controller: SessionController) -> FastAPI:
    # Active websocket connections
    active_websockets: set[WebSocket] = set()
    loop: asyncio.AbstractEventLoop | None = None

    def on_segment(segment_data: dict[str, Any]) -> None:
        if not active_websockets:
            return
        payload = json.dumps({"type": "segment", "data": segment_data})
        for ws in list(active_websockets):
            try:
                if loop and loop.is_running():
                    asyncio.run_coroutine_threadsafe(ws.send_text(payload), loop)
            except Exception as e:
                logger.debug(f"Error sending segment to websocket: {e}")

    def on_status(message: str, progress: float) -> None:
        if not active_websockets:
            return
        payload = json.dumps({"type": "status", "data": {"message": message, "progress": progress}})
        for ws in list(active_websockets):
            try:
                if loop and loop.is_running():
                    asyncio.run_coroutine_threadsafe(ws.send_text(payload), loop)
            except Exception as e:
                logger.debug(f"Error sending status to websocket: {e}")

    controller.add_segment_callback(on_segment)
    controller.set_status_callback(on_status)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        nonlocal loop
        loop = asyncio.get_running_loop()
        yield
        active_websockets.clear()

    app = FastAPI(title="NoteFlow Web UI", version="0.1.0", lifespan=lifespan)

    # Static files & templates
    web_dir = Path(__file__).parent / "web"
    app.mount("/static", StaticFiles(directory=str(web_dir)), name="static")

    @app.get("/")
    def serve_index():
        return FileResponse(web_dir / "index.html")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # API Endpoints
    @app.get("/api/status")
    def get_status() -> dict[str, Any]:
        component_status = controller.initialize()
        return {
            "status": "online",
            "components": component_status,
            "is_recording": controller.is_recording(),
            "auto_call_detection": getattr(controller.settings, "auto_call_detection", False),
            "daemon_running": controller._call_daemon.is_running() if getattr(controller, "_call_daemon", None) else False,
            "active_session": controller.get_current_session_info(),
        }

    @app.get("/api/devices")
    def get_devices() -> list[dict[str, Any]]:
        try:
            return list_audio_devices()
        except Exception as e:
            logger.error(f"Error listing audio devices: {e}")
            return []

    @app.get("/api/settings")
    def get_settings() -> dict[str, Any]:
        s = controller.settings
        return {
            "theme": s.theme.value,
            "transcription_mode": s.transcription_mode.value,
            "ui_mode": s.ui_mode.value,
            "whisper_model": s.whisper_model,
            "whisper_device": s.whisper_device,
            "allow_online_model_download": getattr(s, "allow_online_model_download", False),
            "enable_email": getattr(s, "enable_email", True),
            "enable_loopback": getattr(s, "enable_loopback", True),
            "auto_call_detection": getattr(s, "auto_call_detection", False),
            "default_meeting_title_prefix": getattr(s, "default_meeting_title_prefix", "[NoteFlow] Meeting"),
            "chunk_duration_secs": s.chunk_duration_secs,
            "vad_threshold": s.vad_threshold,
            "ollama_host": s.ollama_host,
            "ollama_port": s.ollama_port,
            "ollama_model": s.ollama_model,
            "ollama_timeout": s.ollama_timeout,
            "ollama_max_retries": s.ollama_max_retries,
            "smtp_host": s.smtp_host,
            "smtp_port": s.smtp_port,
            "smtp_use_tls": s.smtp_use_tls,
            "smtp_username": s.smtp_username,
            "email_from": s.email_from,
            "email_to": s.email_to,
            "email_subject_prefix": s.email_subject_prefix,
            "enable_map_reduce": getattr(s, "enable_map_reduce", False),
            "web_port": s.web_port,
        }

    @app.post("/api/settings")
    def update_settings(req: UpdateSettingsRequest) -> dict[str, Any]:
        s = controller.settings
        if req.theme:
            t = Theme(req.theme)
            s.save_theme(t)
        if req.transcription_mode:
            m = TranscriptionMode(req.transcription_mode)
            s.save_mode(m)
        if req.ui_mode:
            u = UIMode(req.ui_mode)
            s.save_ui_mode(u)
        if req.whisper_model:
            s.whisper_model = req.whisper_model
        if req.whisper_device:
            s.whisper_device = req.whisper_device
        if req.allow_online_model_download is not None:
            s.save_allow_online_model_download(req.allow_online_model_download)
        if req.enable_email is not None:
            s.save_enable_email(req.enable_email)
        if req.enable_loopback is not None:
            s.save_enable_loopback(req.enable_loopback)
        if req.auto_call_detection is not None:
            s.save_auto_call_detection(req.auto_call_detection)
        if req.default_meeting_title_prefix:
            s.default_meeting_title_prefix = req.default_meeting_title_prefix
        if req.ollama_host:
            s.ollama_host = req.ollama_host
        if req.ollama_port:
            s.ollama_port = req.ollama_port
        if req.ollama_model:
            s.ollama_model = req.ollama_model
        if req.ollama_timeout is not None:
            s.save_ollama_timeout(req.ollama_timeout)
        if req.ollama_max_retries is not None:
            s.save_ollama_max_retries(req.ollama_max_retries)
        if req.email_to:
            s.email_to = req.email_to
        if req.smtp_host:
            s.smtp_host = req.smtp_host
        if req.smtp_port:
            s.smtp_port = req.smtp_port
        if req.smtp_username:
            s.smtp_username = req.smtp_username
        if req.smtp_password:
            s.smtp_password = req.smtp_password
        if req.enable_map_reduce is not None:
            s.save_enable_map_reduce(req.enable_map_reduce)

        controller.sync_daemon_state()
        return {"success": True, "settings": get_settings()}

    @app.post("/api/session/start")
    def start_session(req: StartSessionRequest) -> dict[str, Any]:
        if controller.is_recording():
            raise HTTPException(status_code=400, detail="Session is already recording")

        mode = TranscriptionMode(req.mode) if req.mode in [m.value for m in TranscriptionMode] else TranscriptionMode.LIVE
        theme = Theme(req.theme) if req.theme in [t.value for t in Theme] else Theme.DARK

        session = controller.start_session(
            title=req.title.strip() or "Untitled Meeting",
            mode=mode,
            theme=theme,
            device_id=req.device_id
        )

        return {
            "success": True,
            "session_id": session.session_id,
            "title": session.title,
            "mode": session.transcription_mode,
            "start_time": session.start_time.isoformat(),
        }

    @app.post("/api/session/stop")
    def stop_session() -> dict[str, Any]:
        notes = controller.stop_session()
        return {"success": True, "notes": notes}

    @app.get("/api/session/current")
    def get_current_session() -> dict[str, Any]:
        return controller.get_current_session_info()

    @app.get("/api/session/transcript")
    def get_transcript() -> dict[str, Any]:
        store = controller.get_transcript_store()
        return {
            "full_transcript": store.get_full_transcript(),
            "timestamped_transcript": store.get_timestamped_transcript(),
            "segment_count": store.segment_count(),
        }

    @app.get("/api/sessions")
    def get_history_sessions() -> list[dict[str, Any]]:
        return controller.get_history_sessions()

    @app.get("/api/sessions/{session_id}")
    def get_session_detail(session_id: str) -> dict[str, Any]:
        detail = controller.get_session_details(session_id)
        if not detail:
            raise HTTPException(status_code=404, detail="Session not found")
        return detail

    @app.post("/api/sessions/{session_id}/resend")
    def resend_email(session_id: str, req: ResendEmailRequest) -> dict[str, Any]:
        success = controller.resend_session_email(session_id, email_to=req.email_to)
        if not success:
            raise HTTPException(status_code=500, detail="Failed to resend email. Check SMTP settings.")
        return {"success": True, "message": "Email sent successfully"}

    @app.get("/api/sessions/{session_id}/markdown")
    def get_session_markdown(session_id: str) -> PlainTextResponse:
        notes_dir = controller.settings.get_notes_dir()
        if notes_dir.exists():
            for f in notes_dir.glob("*.md"):
                if session_id in f.name:
                    with open(f, "r", encoding="utf-8") as md_file:
                        return PlainTextResponse(md_file.read(), media_type="text/markdown")
        raise HTTPException(status_code=404, detail="Markdown file not found")

    @app.post("/api/session/regenerate")
    def regenerate_current_session_notes() -> dict[str, Any]:
        try:
            notes = controller.regenerate_notes()
            return {"success": True, "notes": notes}
        except Exception as e:
            logger.error(f"Notes regeneration failed: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    @app.post("/api/sessions/{session_id}/regenerate")
    def regenerate_session_notes(session_id: str) -> dict[str, Any]:
        try:
            notes = controller.regenerate_notes(session_id=session_id)
            return {"success": True, "notes": notes}
        except Exception as e:
            logger.error(f"Notes regeneration failed for session {session_id}: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    @app.get("/api/sessions/{session_id}/transcript/download")
    def download_session_transcript(session_id: str) -> PlainTextResponse:
        detail = controller.get_session_details(session_id)
        if not detail:
            raise HTTPException(status_code=404, detail="Session not found")
        content = detail.get("timestamped_transcript") or detail.get("transcript") or detail.get("notes", {}).get("transcript", "")
        return PlainTextResponse(content, media_type="text/plain", headers={"Content-Disposition": f"attachment; filename=transcript_{session_id}.txt"})

    @app.websocket("/ws/live")
    async def websocket_endpoint(websocket: WebSocket) -> None:
        await websocket.accept()
        active_websockets.add(websocket)
        try:
            # Send initial state
            await websocket.send_text(json.dumps({
                "type": "init",
                "data": {
                    "is_recording": controller.is_recording(),
                    "session_info": controller.get_current_session_info(),
                    "transcript": controller.get_transcript_store().get_timestamped_transcript(),
                }
            }))
            while True:
                # Keep alive and listen for ping/commands
                data = await websocket.receive_text()
                msg = json.loads(data)
                if msg.get("type") == "ping":
                    await websocket.send_text(json.dumps({
                        "type": "pong",
                        "data": {
                            "session_info": controller.get_current_session_info(),
                            "audio_stats": controller.get_audio_stats(),
                        }
                    }))
        except WebSocketDisconnect:
            active_websockets.discard(websocket)
        except Exception as e:
            logger.debug(f"WebSocket closed: {e}")
            active_websockets.discard(websocket)

    # Static web app files
    web_dir = Path(__file__).parent / "web"
    if web_dir.exists():
        app.mount("/static", StaticFiles(directory=str(web_dir)), name="static")

        @app.get("/")
        def serve_index() -> FileResponse:
            return FileResponse(web_dir / "index.html")

    return app


def start_web_server(controller: SessionController, host: str = "127.0.0.1", port: int = 5000, auto_open: bool = True) -> None:
    """Starts the Uvicorn web server and optionally opens the browser."""
    app = create_app(controller)
    url = f"http://{host}:{port}"
    print(f"\n========================================================")
    print(f"🎙️  NoteFlow Local Web UI is running at:")
    print(f"👉  {url}")
    print(f"========================================================\n")

    if auto_open:
        def open_tab():
            time.sleep(1.0)
            webbrowser.open(url)
        threading.Thread(target=open_tab, daemon=True).start()

    config = uvicorn.Config(app, host=host, port=port, log_level="warning")
    server = uvicorn.Server(config)
    server.run()
