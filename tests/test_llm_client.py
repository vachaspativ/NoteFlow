from __future__ import annotations

import json
import pytest
import httpx
from noteflow.llm_client import LLMClient, OllamaNotAvailableError

@pytest.fixture
def client():
    return LLMClient()

def test_check_available_returns_true_when_running(mocker, client):
    mock_response = mocker.Mock(spec=httpx.Response)
    mock_response.status_code = 200
    
    mock_get = mocker.patch("httpx.Client.get", return_value=mock_response)
    
    assert client.check_available() is True
    mock_get.assert_called_once_with("http://localhost:11434/api/version")

def test_check_available_returns_false_when_not_running(mocker, client):
    mocker.patch("httpx.Client.get", side_effect=httpx.RequestError("Connection refused"))
    assert client.check_available() is False

def test_prompt_contains_transcript(client):
    prompt = client._build_prompt("Hello world", "", "")
    assert "---TRANSCRIPT START---\nHello world\n---TRANSCRIPT END---" in prompt

def test_prompt_contains_title_and_duration(client):
    prompt = client._build_prompt("Text", "Team Sync", "30 mins")
    assert "- Title: Team Sync" in prompt
    assert "- Duration: 30 mins" in prompt

def test_valid_json_response(mocker, client):
    expected_notes = {
        "summary": "This is a summary.",
        "action_items": [{"owner": "John", "action": "Do something", "deadline": "Tomorrow"}],
        "highlights": ["Important point"],
        "decisions": ["We decided this"]
    }
    
    mock_response = mocker.Mock(spec=httpx.Response)
    mock_response.json.return_value = {"response": json.dumps(expected_notes)}
    
    mocker.patch("httpx.Client.post", return_value=mock_response)
    
    notes = client.generate_notes("Transcript text", "Title", "Duration")
    
    assert notes == expected_notes

def test_malformed_json_fallback(mocker, client):
    raw_text = "I failed to generate JSON. Here is some text instead."
    
    mock_response = mocker.Mock(spec=httpx.Response)
    mock_response.json.return_value = {"response": raw_text}
    
    mocker.patch("httpx.Client.post", return_value=mock_response)
    
    notes = client.generate_notes("Transcript", "Title", "Duration")
    
    assert notes["summary"] == raw_text
    assert notes["action_items"] == []
    assert notes["highlights"] == []
    assert notes["decisions"] == []

def test_ollama_not_running_raises(mocker, client):
    mocker.patch("httpx.Client.post", side_effect=httpx.RequestError("Failed to connect"))
    
    with pytest.raises(OllamaNotAvailableError):
        client.generate_notes("Transcript")

def test_validate_notes_fills_missing_keys(client):
    incomplete_data = {
        "summary": "Just a summary"
        # Missing action_items, highlights, decisions
    }
    
    validated = client._validate_notes(incomplete_data)
    
    assert validated["summary"] == "Just a summary"
    assert validated["action_items"] == []
    assert validated["highlights"] == []
    assert validated["decisions"] == []
