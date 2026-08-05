import pytest
from unittest.mock import MagicMock
from noteflow.display import NoteFlowApp, SetupScreen
from noteflow.config import Settings, Theme, TranscriptionMode
from textual.widgets import Button, Switch

@pytest.fixture
def mock_settings():
    settings = MagicMock(spec=Settings)
    settings.theme = Theme.DARK
    return settings

@pytest.fixture
def mock_controller():
    controller = MagicMock()
    return controller

@pytest.mark.asyncio
async def test_app_starts_on_setup_screen(mock_settings, mock_controller):
    app = NoteFlowApp(settings=mock_settings, controller=mock_controller)
    async with app.run_test() as pilot:
        assert isinstance(app.screen, SetupScreen)

@pytest.mark.asyncio
async def test_start_button_exists(mock_settings, mock_controller):
    app = NoteFlowApp(settings=mock_settings, controller=mock_controller)
    async with app.run_test() as pilot:
        button = app.screen.query_one("#start-btn", Button)
        assert button is not None
        assert str(button.label) == "▶ Start Recording"

@pytest.mark.asyncio
async def test_mode_toggle_exists(mock_settings, mock_controller):
    app = NoteFlowApp(settings=mock_settings, controller=mock_controller)
    async with app.run_test() as pilot:
        switch = app.screen.query_one("#mode-switch", Switch)
        assert switch is not None

@pytest.mark.asyncio
async def test_theme_toggle_changes_dark_mode(mock_settings, mock_controller):
    app = NoteFlowApp(settings=mock_settings, controller=mock_controller)
    async with app.run_test() as pilot:
        assert app.dark is True
        
        # Click the switch to toggle to Light mode
        await pilot.click("#theme-switch")
        assert app.dark is False
        mock_settings.save_theme.assert_called_once()
