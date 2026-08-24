from __future__ import annotations

import os
os.environ["HF_HUB_DISABLE_IMPLICIT_TOKEN_WARNING"] = "1"
os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"

import click
from noteflow.config import Settings, TranscriptionMode, Theme, UIMode
from noteflow.controller import SessionController
from noteflow.display import NoteFlowApp
from noteflow.web_server import start_web_server
from noteflow.audio_capture import list_audio_devices


@click.command()
@click.option('--ui', type=click.Choice(['node', 'tui', 'web'], case_sensitive=False), default=None, help='Interface type: "node" (modern local web UI) or "tui" (terminal UI). Default: node')
@click.option('--tui', 'use_tui', is_flag=True, help='Launch terminal TUI interface')
@click.option('--node', 'use_node', is_flag=True, help='Launch modern local Node/Web UI interface (default)')
@click.option('--web', 'use_web', is_flag=True, help='Alias for --node')
@click.option('--mode', type=click.Choice(['live', 'batch']), default=None, help='Transcription mode: "live" or "batch"')
@click.option('--theme', type=click.Choice(['dark', 'light']), default=None, help='UI theme: "dark" or "light"')
@click.option('--model', default=None, help='Whisper model name (e.g. base.en, tiny.en, small.en)')
@click.option('--to', 'email_to', default=None, help='Default recipient email address')
@click.option('--config', 'config_path', default=None, type=click.Path(), help='Path to custom .env file')
@click.option('--port', default=None, type=int, help='Port for Node/Web UI server (default: 5000)')
@click.option('--host', default=None, type=str, help='Host for Node/Web UI server (default: 127.0.0.1)')
@click.option('--no-browser', is_flag=True, help='Do not automatically open browser on Web UI launch')
@click.option('--dry-run', is_flag=True, help='Skip email sending, save locally only')
@click.option('--daemon', 'use_daemon', is_flag=True, help='Launch background call auto-detection daemon')
@click.option('--list-devices', is_flag=True, help='List available audio microphone devices and exit')
@click.option('--device-id', default=None, type=int, help='Microphone device index to capture from')
def main(
    ui: str | None,
    use_tui: bool,
    use_node: bool,
    use_web: bool,
    mode: str | None,
    theme: str | None,
    model: str | None,
    email_to: str | None,
    config_path: str | None,
    port: int | None,
    host: str | None,
    no_browser: bool,
    dry_run: bool,
    use_daemon: bool,
    list_devices: bool,
    device_id: int | None
) -> None:
    """NoteFlow — Offline AI Meeting Note-Taker with Node Web UI and TUI interfaces."""
    # If --list-devices, print devices and exit
    if list_devices:
        devices = list_audio_devices()
        click.echo("\n🎙️ Available Audio Input Devices:")
        for i, d in enumerate(devices):
            channels = d.get('max_input_channels', 0)
            if channels > 0:
                click.echo(f"  [{i}] {d.get('name', 'Unknown')} ({channels} in)")
        click.echo("")
        return
    
    # Load settings
    settings = Settings.from_env(config_path)
    
    # Apply CLI overrides
    if mode:
        settings.transcription_mode = TranscriptionMode(mode.lower())
    if theme:
        settings.theme = Theme(theme.lower())
    if model:
        settings.whisper_model = model
    if email_to:
        settings.email_to = email_to
    if dry_run:
        settings.dry_run = True
    if use_daemon:
        settings.auto_call_detection = True
    if device_id is not None:
        settings.device_id = device_id
    if port is not None:
        settings.web_port = port
    if host is not None:
        settings.web_host = host

    # Determine UI mode: precedence flags > --ui > settings default (NODE)
    chosen_ui = settings.ui_mode
    if use_tui:
        chosen_ui = UIMode.TUI
    elif use_node or use_web:
        chosen_ui = UIMode.NODE
    elif ui:
        ui_val = ui.lower()
        if ui_val == 'tui':
            chosen_ui = UIMode.TUI
        else:
            chosen_ui = UIMode.NODE

    # Create controller
    controller = SessionController(settings)

    # Start Call Auto-Detection Daemon if enabled
    if getattr(settings, 'auto_call_detection', False):
        from noteflow.daemon import CallDetectorDaemon
        daemon = CallDetectorDaemon(controller)
        daemon.start()

    if chosen_ui == UIMode.TUI:
        # Launch Textual TUI
        app = NoteFlowApp(settings=settings, controller=controller)
        app.run()
    else:
        # Launch Local Web / Node UI
        start_web_server(
            controller=controller,
            host=settings.web_host,
            port=settings.web_port,
            auto_open=not no_browser
        )


if __name__ == '__main__':
    main()
