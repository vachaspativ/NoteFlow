from __future__ import annotations

import json
import logging
import re
import time
import httpx
from typing import Dict, Any

logger = logging.getLogger(__name__)

class OllamaNotAvailableError(Exception):
    """Exception raised when Ollama service is not reachable."""
    pass

class LLMClient:
    """Client for generating meeting notes using a local Ollama instance."""
    
    def __init__(
        self,
        host: str = 'http://localhost',
        port: int = 11434,
        model: str = 'llama3.2',
        timeout: int = 300,
        max_retries: int = 1
    ):
        self.base_url = f"{host.rstrip('/')}:{port}"
        self.model = model
        self.timeout = timeout
        self.max_retries = max_retries
        
    def check_available(self) -> bool:
        """Check if the Ollama service is running and the configured model is pulled."""
        try:
            with httpx.Client(timeout=5.0) as client:
                response = client.get(f"{self.base_url}/api/version")
                if response.status_code != 200:
                    return False
                
                tags_response = client.get(f"{self.base_url}/api/tags")
                if tags_response.status_code == 200:
                    data = tags_response.json()
                    models = data.get("models", [])
                    
                    cfg_model = self.model.strip()
                    cfg_model_with_latest = cfg_model if ":" in cfg_model else f"{cfg_model}:latest"
                    cfg_model_base = cfg_model.split(":")[0]
                    
                    for m in models:
                        m_name = m.get("name", "").strip()
                        m_name_with_latest = m_name if ":" in m_name else f"{m_name}:latest"
                        m_base = m_name.split(":")[0]
                        
                        if m_name == cfg_model or m_name_with_latest == cfg_model_with_latest:
                            return True
                        if m_base == cfg_model_base:
                            return True
                    return False
                return True
        except httpx.RequestError:
            return False
            
    def check_availability(self) -> bool:
        """Alias for check_available for backwards compatibility."""
        return self.check_available()
            
    def generate_notes(self, transcript: str, title: str = '', duration: str = '') -> dict:
        """
        Generate structured meeting notes from a transcript with retry logic.
        
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
        
        attempts = 0
        last_error: Exception | None = None

        while attempts <= self.max_retries:
            try:
                with httpx.Client(timeout=self.timeout) as client:
                    response = client.post(f"{self.base_url}/api/generate", json=payload)
                    response.raise_for_status()
                    data = response.json()
                
                raw_text = data.get("response", "")
                if not raw_text.strip():
                    raise OllamaNotAvailableError("Ollama returned an empty response.")

                # Try to parse the response as JSON
                try:
                    parsed_data = json.loads(raw_text)
                except json.JSONDecodeError:
                    json_match = re.search(r'```(?:json)?\s*(.*?)\s*```', raw_text, re.DOTALL)
                    if json_match:
                        try:
                            parsed_data = json.loads(json_match.group(1))
                        except json.JSONDecodeError:
                            parsed_data = self._fallback_notes(raw_text)
                    else:
                        parsed_data = self._fallback_notes(raw_text)

                return self._validate_notes(parsed_data)

            except httpx.TimeoutException as e:
                last_error = OllamaNotAvailableError(
                    f"Ollama request timed out after {self.timeout}s while generating notes. You can increase OLLAMA_TIMEOUT in Settings or try a lighter model like phi3."
                )
            except httpx.RequestError as e:
                last_error = OllamaNotAvailableError(f"Ollama service is not available at {self.base_url}. Error: {e}")
            except httpx.HTTPStatusError as e:
                if e.response.status_code == 404:
                    last_error = OllamaNotAvailableError(
                        f"Ollama model '{self.model}' not found. Please run 'ollama pull {self.model}' in your terminal to download it first."
                    )
                else:
                    err_msg = f"Ollama returned HTTP error {e.response.status_code}"
                    try:
                        err_data = e.response.json()
                        if "error" in err_data:
                            err_msg += f": {err_data['error']}"
                    except Exception:
                        if e.response.text:
                            err_msg += f": {e.response.text}"
                    last_error = OllamaNotAvailableError(err_msg)
            except Exception as e:
                last_error = e

            attempts += 1
            if attempts <= self.max_retries:
                logger.warning(f"Ollama note generation attempt {attempts} failed: {last_error}. Retrying ({attempts}/{self.max_retries})...")
                time.sleep(1)

        if last_error:
            raise last_error
        raise OllamaNotAvailableError("LLM generation failed after maximum retry attempts.")
        
    def _load_prompt_template(self) -> str:
        """Load the prompt template from external Markdown file or fallback."""
        from pathlib import Path
        possible_paths = [
            Path("prompts/meeting_notes_prompt.md"),
            Path(__file__).parent / "prompts" / "meeting_notes_prompt.md",
        ]
        for path in possible_paths:
            if path.exists():
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        return f.read().strip()
                except Exception as e:
                    logger.warning(f"Could not read prompt template from {path}: {e}")

        return """You are an elite, executive-level Chief of Staff and AI Meeting Intelligence Specialist.
Your objective is to analyze raw speech transcripts from business meetings, technical discussions, and strategy sessions, and distill them into highly structured, executive-grade meeting intelligence.

Meeting Context:
- Title: {meeting_title}
- Duration: {meeting_duration}

GUIDELINES FOR SYNTHESIS:
1. Accuracy & Truthfulness: Rely STRICTLY on the information stated in the transcript. Do NOT fabricate metrics, names, deadlines, or decisions.
2. Executive Tone: Use clear, formal, executive business English. Avoid colloquialisms or casual phrasing.
3. Structure: Return a single, valid JSON object containing exactly seven key properties: "summary", "action_items", "decisions", "risks", "dependencies", "recommendations", and "stakeholders".

KEYS & FORMAT REQUIREMENTS:

1. "summary" (string): A MECE Executive Debrief summarizing the core agenda, strategic context, and high-level outcomes of the meeting. Format it strictly as 3 to 6 bullet-pointed takeaways (each bullet starting with a dash "- ").

2. "action_items" (array of objects): Extract all distinct tasks, deliverables, and follow-ups. Limit: Up to a MAXIMUM of 10.
   Each object MUST contain:
     * "owner": Responsible name/team, or "Unassigned".
     * "action": Clear actionable task description.
     * "deadline": Specific date, milestone, or "Not specified".

3. "decisions" (array of strings): Concrete strategic or architectural choices and consensus points. Limit: Up to a MAXIMUM of 10.

4. "risks" (array of strings): Potential blocker issues, architectural vulnerabilities, resource constraints, or business risks. Limit: Up to a MAXIMUM of 10.

5. "dependencies" (array of strings): External timelines, blocking tasks, or technical requirements from other teams/systems. Limit: Up to a MAXIMUM of 10.

6. "recommendations" (array of strings): Concrete strategic paths forward and recommendations advised by participants. Limit: Up to a MAXIMUM of 10.

7. "stakeholders" (array of objects): Mapping of key stakeholders, participants, or teams discussed or present. Limit: Up to a MAXIMUM of 10.
   Each object MUST contain:
     * "name": Person or team name.
     * "role": Their role, interest, or perspective in the meeting.
     * "sentiment": Their sentiment or stance (exactly one of: "Supportive", "Neutral", "Concerned").

---TRANSCRIPT START---
{processed_transcript}
---TRANSCRIPT END---

Respond ONLY with the raw JSON object. Do not include any preamble, markdown wrappers outside JSON, or conversational commentary."""

    def _build_prompt(self, transcript: str, title: str, duration: str) -> str:
        """Build the structured prompt using the external Markdown prompt template."""
        meeting_title = title if title else "Untitled Meeting"
        meeting_duration = duration if duration else "Unknown"
        
        max_len = 16000
        if len(transcript) > max_len:
            processed_transcript = transcript[:8000] + "\n\n[... transcript middle section truncated for length to prevent LLM timeout ...]\n\n" + transcript[-7000:]
        else:
            processed_transcript = transcript
        
        template = self._load_prompt_template()
        try:
            return template.format(
                meeting_title=meeting_title,
                meeting_duration=meeting_duration,
                processed_transcript=processed_transcript
            )
        except Exception as e:
            logger.error(f"Error formatting prompt template: {e}")
            return f"Analyze transcript and return JSON:\n{processed_transcript}"

    def _fallback_notes(self, raw_text: str) -> dict:
        """Return fallback notes when JSON parsing entirely fails."""
        return {
            "summary": raw_text.strip(),
            "action_items": [],
            "highlights": [],
            "decisions": [],
            "risks": [],
            "dependencies": [],
            "recommendations": [],
            "stakeholders": []
        }
        
    def _validate_notes(self, data: dict) -> dict:
        """Validate the returned dictionary, enforce top-10 caps, and fill missing keys with defaults."""
        if not isinstance(data, dict):
            data = {"summary": str(data)}
            
        action_items = data.get("action_items", [])
        if isinstance(action_items, list):
            action_items = action_items[:10]
        else:
            action_items = []

        highlights = data.get("highlights", [])
        if isinstance(highlights, list):
            highlights = highlights[:10]
        else:
            highlights = []

        decisions = data.get("decisions", [])
        if isinstance(decisions, list):
            decisions = decisions[:10]
        else:
            decisions = []

        risks = data.get("risks", [])
        if isinstance(risks, list):
            risks = risks[:10]
        else:
            risks = []

        dependencies = data.get("dependencies", [])
        if isinstance(dependencies, list):
            dependencies = dependencies[:10]
        else:
            dependencies = []

        recommendations = data.get("recommendations", [])
        if isinstance(recommendations, list):
            recommendations = recommendations[:10]
        else:
            recommendations = []

        stakeholders = data.get("stakeholders", [])
        if isinstance(stakeholders, list):
            valid_stakeholders = []
            for s in stakeholders[:10]:
                if isinstance(s, dict):
                    valid_stakeholders.append({
                        "name": str(s.get("name", "Unknown")),
                        "role": str(s.get("role", "Participant")),
                        "sentiment": str(s.get("sentiment", "Neutral"))
                    })
                else:
                    valid_stakeholders.append({
                        "name": str(s),
                        "role": "Participant",
                        "sentiment": "Neutral"
                    })
            stakeholders = valid_stakeholders
        else:
            stakeholders = []

        validated = {
            "summary": data.get("summary", ""),
            "action_items": action_items,
            "highlights": highlights,
            "decisions": decisions,
            "risks": risks,
            "dependencies": dependencies,
            "recommendations": recommendations,
            "stakeholders": stakeholders
        }
        
        if not isinstance(validated["summary"], str):
            validated["summary"] = str(validated["summary"])
            
        return validated
