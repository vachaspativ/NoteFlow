from __future__ import annotations

import json
import pytest
import httpx
from noteflow.llm_client import LLMClient, OllamaNotAvailableError

@pytest.fixture
def client():
    return LLMClient()

def test_check_available_returns_true_when_running(mocker, client):
    mock_response_version = mocker.Mock(spec=httpx.Response)
    mock_response_version.status_code = 200
    
    mock_response_tags = mocker.Mock(spec=httpx.Response)
    mock_response_tags.status_code = 200
    mock_response_tags.json.return_value = {"models": [{"name": "llama3.2:latest"}]}
    
    mock_get = mocker.patch("httpx.Client.get", side_effect=[mock_response_version, mock_response_tags])
    
    assert client.check_available() is True
    assert mock_get.call_count == 2

def test_check_available_returns_false_when_model_missing(mocker, client):
    mock_response_version = mocker.Mock(spec=httpx.Response)
    mock_response_version.status_code = 200
    
    mock_response_tags = mocker.Mock(spec=httpx.Response)
    mock_response_tags.status_code = 200
    mock_response_tags.json.return_value = {"models": [{"name": "mistral:latest"}]}
    
    mock_get = mocker.patch("httpx.Client.get", side_effect=[mock_response_version, mock_response_tags])
    
    assert client.check_available() is False
    assert mock_get.call_count == 2

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
        "decisions": ["We decided this"],
        "risks": ["Risk point"],
        "dependencies": ["Dependency point"],
        "recommendations": ["Recommendation point"],
        "stakeholders": [{"name": "John", "role": "Host", "sentiment": "Supportive"}]
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
    assert notes["risks"] == []
    assert notes["dependencies"] == []
    assert notes["recommendations"] == []
    assert notes["stakeholders"] == []

def test_ollama_not_running_raises(mocker, client):
    mocker.patch("httpx.Client.post", side_effect=httpx.RequestError("Failed to connect"))
    
    with pytest.raises(OllamaNotAvailableError):
        client.generate_notes("Transcript")

def test_validate_notes_fills_missing_keys(client):
    incomplete_data = {
        "summary": "Just a summary"
        # Missing action_items, highlights, decisions, risks, etc.
    }
    
    validated = client._validate_notes(incomplete_data)
    
    assert validated["summary"] == "Just a summary"
    assert validated["action_items"] == []
    assert validated["highlights"] == []
    assert validated["decisions"] == []
    assert validated["risks"] == []
    assert validated["dependencies"] == []
    assert validated["recommendations"] == []
    assert validated["stakeholders"] == []

def test_ollama_timeout_raises_descriptive_error(mocker, client):
    mocker.patch("httpx.Client.post", side_effect=httpx.TimeoutException("Read timed out"))
    with pytest.raises(OllamaNotAvailableError, match="Ollama request timed out"):
        client.generate_notes("Transcript")

def test_long_transcript_prompt_truncation(client):
    long_transcript = "A" * 35000
    prompt = client._build_prompt(long_transcript, "Title", "Duration")
    assert "truncated for length" in prompt
    assert len(prompt) < 35000

def test_generate_notes_retries_on_failure_then_succeeds(mocker):
    from noteflow.llm_client import LLMClient
    client = LLMClient(max_retries=1)

    mock_ok_response = mocker.Mock(spec=httpx.Response)
    mock_ok_response.status_code = 200
    mock_ok_response.json.return_value = {
        "response": json.dumps({
            "summary": "Retried summary",
            "action_items": [],
            "highlights": [],
            "decisions": [],
            "risks": [],
            "dependencies": [],
            "recommendations": [],
            "stakeholders": []
        })
    }

    mock_post = mocker.patch(
        "httpx.Client.post",
        side_effect=[httpx.TimeoutException("Initial timeout"), mock_ok_response]
    )

    notes = client.generate_notes("Transcript", "Title", "Duration")
    assert notes["summary"] == "Retried summary"
    assert mock_post.call_count == 2

def test_externalized_prompt_template_loaded(client):
    prompt = client._build_prompt("Sample transcript", "Q3 Review", "15m")
    assert "Q3 Review" in prompt
    assert "Sample transcript" in prompt
    assert "Chief of Staff" in prompt

def test_chunk_transcript(client):
    transcript = "Hello. " * 3000  # 3000 words
    chunks = client.chunk_transcript(transcript, max_words=1000)
    assert len(chunks) == 3
    for c in chunks:
        assert len(c.split()) <= 1000

def test_generate_notes_map_reduce_flow(mocker, client):
    mock_map_1 = mocker.Mock(spec=httpx.Response)
    mock_map_1.status_code = 200
    mock_map_1.json.return_value = {
        "response": json.dumps({
            "summary": "Summary part 1",
            "action_items": [],
            "highlights": [],
            "decisions": [],
            "risks": [],
            "dependencies": [],
            "recommendations": [],
            "stakeholders": []
        })
    }

    mock_map_2 = mocker.Mock(spec=httpx.Response)
    mock_map_2.status_code = 200
    mock_map_2.json.return_value = {
        "response": json.dumps({
            "summary": "Summary part 2",
            "action_items": [],
            "highlights": [],
            "decisions": [],
            "risks": [],
            "dependencies": [],
            "recommendations": [],
            "stakeholders": []
        })
    }

    mock_reduce = mocker.Mock(spec=httpx.Response)
    mock_reduce.status_code = 200
    mock_reduce.json.return_value = {
        "response": json.dumps({
            "summary": "Consolidated Summary",
            "action_items": [{"owner": "John", "action": "Do map-reduce", "deadline": "Now"}],
            "highlights": [],
            "decisions": [],
            "risks": [],
            "dependencies": [],
            "recommendations": [],
            "stakeholders": []
        })
    }

    mock_post = mocker.patch(
        "httpx.Client.post",
        side_effect=[mock_map_1, mock_map_2, mock_reduce]
    )

    long_transcript = "Word. " * 1500
    notes = client.generate_notes(
        long_transcript,
        title="Map-Reduce test",
        duration="10m",
        enable_map_reduce=True
    )

    assert notes["summary"] == "Consolidated Summary"
    assert notes["action_items"][0]["owner"] == "John"
    assert mock_post.call_count == 3
