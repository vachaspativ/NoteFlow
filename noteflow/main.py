from __future__ import annotations

import click
from noteflow.config import Settings, TranscriptionMode, Theme
from noteflow.controller import SessionController
from noteflow.display import NoteFlowApp
from noteflow.audio_capture import list_audio_devices

@click.command()
@click.option('--mode', type=click.Choice(['live', 'batch']), default=None, help='Transcription mode')
@click.option('--theme', type=click.Choice(['dark', 'light']), default=None, help='UI theme')
@click.option('--model', default=None, help='Whisper model name')
@click.option('--to', 'email_to', default=None, help='Recipient email')
@click.option('--config', 'config_path', default=None, type=click.Path(), help='Path to .env file')
@click.option('--dry-run', is_flag=True, help='Skip email, print notes to terminal')
@click.option('--list-devices', is_flag=True, help='List audio devices and exit')
@click.option('--device-id', default=None, type=int, help='Microphone device index')
def main(mode: str | None, theme: str | None, model: str | None, email_to: str | None, config_path: str | None, dry_run: bool, list_devices: bool, device_id: int | None) -> None:
    """NoteFlow — Offline AI Meeting Note-Taker"""
    # If --list-devices, print devices and exit
    if list_devices:
        devices = list_audio_devices()
        for i, d in enumerate(devices):
            click.echo(f"  [{i}] {d.get('name', 'Unknown')} (in: {d.get('max_input_channels', 0)})")
        return
    
    # Load settings
    settings = Settings.from_env(config_path)
    
    # Apply CLI overrides
    if mode:
        settings.transcription_mode = TranscriptionMode(mode)
    if theme:
        settings.theme = Theme(theme)
    if model:
        settings.whisper_model = model
    if email_to:
        settings.email_to = email_to
    if dry_run:
        settings.dry_run = True  # Add dry_run field to Settings if not present
    if device_id is not None:
        settings.device_id = device_id
    
    # Create controller and app
    controller = SessionController(settings)
    app = NoteFlowApp(settings=settings, controller=controller)
    app.run()

if __name__ == '__main__':
    main()
