from __future__ import annotations

import json
import re
import httpx
from typing import Dict, Any

class OllamaNotAvailableError(Exception):
    """Exception raised when Ollama service is not reachable."""
    pass

class LLMClient:
    """Client for generating meeting notes using a local Ollama instance."""
    
    def __init__(
        self,
        host: str = 'http://localhost',
        port: int = 11434,
        model: str = 'llama3',
        timeout: int = 120
    ):
        self.base_url = f"{host.rstrip('/')}:{port}"
        self.model = model
        self.timeout = timeout
        
    def check_available(self) -> bool:
        """Check if the Ollama service is running and accessible."""
        try:
            with httpx.Client(timeout=5.0) as client:
                response = client.get(f"{self.base_url}/api/version")
                return response.status_code == 200
        except httpx.RequestError:
            return False
            
    def generate_notes(self, transcript: str, title: str = '', duration: str = '') -> dict:
        """
        Generate structured meeting notes from a transcript.
        
        Args:
            transcript: The raw meeting transcript text.
            title: The meeting title.
            duration: The meeting duration string.
            
        Returns:
            A dictionary containing summary, action_items, highlights, and decisions.
        """
        prompt = self._build_prompt(transcript, title, duration)
        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "format": "json"
        }
        
        try:
            with httpx.Client(timeout=self.timeout) as client:
                response = client.post(f"{self.base_url}/api/generate", json=payload)
                response.raise_for_status()
                data = response.json()
        except httpx.RequestError as e:
            raise OllamaNotAvailableError(f"Ollama service is not available at {self.base_url}. Error: {e}")
        except httpx.HTTPStatusError as e:
            raise OllamaNotAvailableError(f"Ollama returned HTTP error {e.response.status_code}")
            
        raw_text = data.get("response", "")
        
        # Try to parse the response as JSON
        try:
            parsed_data = json.loads(raw_text)
        except json.JSONDecodeError:
            # Try to extract JSON block using regex if it returned markdown wrappers
            json_match = re.search(r'```(?:json)?\s*(.*?)\s*```', raw_text, re.DOTALL)
            if json_match:
                try:
                    parsed_data = json.loads(json_match.group(1))
                except json.JSONDecodeError:
                    parsed_data = self._fallback_notes(raw_text)
            else:
                parsed_data = self._fallback_notes(raw_text)
                
        return self._validate_notes(parsed_data)
        
    def _build_prompt(self, transcript: str, title: str, duration: str) -> str:
        """Build the structured prompt for the LLM."""
        meeting_title = title if title else "Untitled Meeting"
        meeting_duration = duration if duration else "Unknown"
        
        return f"""You are a professional meeting note-taker. You receive a raw, unedited speech transcript and output a structured JSON object. Be concise, formal, and accurate. Do not invent information not present in the transcript.

Meeting context:
- Title: {meeting_title}
- Duration: {meeting_duration}

Below is a raw meeting transcript. Please analyze it and return a single JSON object with exactly these four keys:

1. "summary": A 3-5 sentence formal paragraph summarizing the meeting's purpose, main topics discussed, and overall outcome.
2. "action_items": A JSON array of objects, each with "owner" (string, name if mentioned or "Unassigned"), "action" (string, what needs to be done), and "deadline" (string, if mentioned, else "Not specified").
3. "highlights": A JSON array of strings, each being a key insight, important data point, or notable statement made during the meeting.
4. "decisions": A JSON array of strings, each describing a concrete decision that was agreed upon.

---TRANSCRIPT START---
{transcript}
---TRANSCRIPT END---

Respond ONLY with the JSON object. No preamble, no explanation."""

    def _fallback_notes(self, raw_text: str) -> dict:
        """Return fallback notes when JSON parsing entirely fails."""
        return {
            "summary": raw_text.strip(),
            "action_items": [],
            "highlights": [],
            "decisions": []
        }
        
    def _validate_notes(self, data: dict) -> dict:
        """Validate the returned dictionary and fill missing keys with defaults."""
        if not isinstance(data, dict):
            data = {"summary": str(data)}
            
        validated = {
            "summary": data.get("summary", ""),
            "action_items": data.get("action_items", []),
            "highlights": data.get("highlights", []),
            "decisions": data.get("decisions", [])
        }
        
        if not isinstance(validated["summary"], str):
            validated["summary"] = str(validated["summary"])
            
        if not isinstance(validated["action_items"], list):
            validated["action_items"] = []
            
        if not isinstance(validated["highlights"], list):
            validated["highlights"] = []
            
        if not isinstance(validated["decisions"], list):
            validated["decisions"] = []
            
        return validated
