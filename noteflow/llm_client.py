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
            
    def _run_ollama_generate(self, prompt: str) -> str:
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
                return raw_text

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
                logger.warning(f"Ollama call attempt {attempts} failed: {last_error}. Retrying...")
                time.sleep(1)

        if last_error:
            raise last_error
        raise OllamaNotAvailableError("Ollama HTTP generation failed after maximum retries.")

    def chunk_transcript(self, text: str, max_words: int = 1500) -> list[str]:
        """Split transcript into chunks of up to max_words, keeping sentence boundaries if possible."""
        sentences = re.split(r'(?<=[.!?])\s+', text)
        chunks = []
        current_chunk = []
        current_words = 0
        
        for sentence in sentences:
            sentence_words = len(sentence.split())
            if current_words + sentence_words > max_words and current_chunk:
                chunks.append(" ".join(current_chunk))
                current_chunk = [sentence]
                current_words = sentence_words
            else:
                current_chunk.append(sentence)
                current_words += sentence_words
                
        if current_chunk:
            chunks.append(" ".join(current_chunk))
            
        return chunks

    def generate_notes(self, transcript: str, title: str = '', duration: str = '', enable_map_reduce: bool = False) -> dict:
        """
        Generate structured meeting notes from a transcript.
        If enable_map_reduce is enabled and transcript is long, executes a Native Map-Reduce pipeline.
        Otherwise, runs standard BAU single-request logic.
        """
        word_count = len(transcript.split())
        
        # We define long transcript threshold as 1200 words
        is_long = word_count > 1200
        
        if enable_map_reduce and is_long:
            logger.info(f"Long transcript detected ({word_count} words). Initiating Native Map-Reduce Orchestrator...")
            chunks = self.chunk_transcript(transcript, max_words=1000)
            logger.info(f"Split transcript into {len(chunks)} chunks for mapping.")
            
            chunk_outputs = []
            for i, chunk in enumerate(chunks):
                logger.info(f"Mapping chunk {i+1}/{len(chunks)}...")
                map_prompt = self._load_map_prompt_template().format(
                    meeting_title=title or "Untitled Meeting",
                    processed_transcript=chunk
                )
                try:
                    raw_res = self._run_ollama_generate(map_prompt)
                    parsed_chunk = json.loads(raw_res)
                    chunk_outputs.append(parsed_chunk)
                except Exception as e:
                    logger.warning(f"Map phase failed for chunk {i+1}: {e}. Skipping chunk.")
            
            if not chunk_outputs:
                raise ValueError("Map-Reduce failed: all chunks failed to transcribe.")
                
            # Synthesize map outputs into an aggregated report
            reports_str = ""
            for idx, chunk_notes in enumerate(chunk_outputs):
                reports_str += f"\nReport from Segment {idx+1}:\n"
                reports_str += json.dumps(chunk_notes, indent=2) + "\n"
                
            logger.info("Reducing mapped chunks to final debrief...")
            reduce_prompt = self._load_reduce_prompt_template().format(
                meeting_title=title or "Untitled Meeting",
                meeting_duration=duration or "Unknown",
                aggregated_reports=reports_str
            )
            
            try:
                raw_reduce = self._run_ollama_generate(reduce_prompt)
                parsed_reduce = json.loads(raw_reduce)
                return self._validate_notes(parsed_reduce)
            except Exception as e:
                logger.error(f"Reduce phase failed: {e}. Falling back to standard fallback notes.")
                return self._fallback_notes(f"Reduce phase failed: {e}")
                
        else:
            # BAU Flow
            prompt = self._build_prompt(transcript, title, duration)
            try:
                raw_text = self._run_ollama_generate(prompt)
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
            except Exception as e:
                logger.error(f"LLM generation failed: {e}")
                raise e

    def _load_map_prompt_template(self) -> str:
        from pathlib import Path
        possible_paths = [
            Path("prompts/map_prompt.md"),
            Path(__file__).parent / "prompts" / "map_prompt.md",
        ]
        for path in possible_paths:
            if path.exists():
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        return f.read().strip()
                except Exception as e:
                    logger.warning(f"Could not read map prompt template from {path}: {e}")
        return """You are an elite, executive-level Chief of Staff and AI Meeting Intelligence Specialist.
Your objective is to analyze a PARTIAL segment of a raw speech transcript from a meeting and extract structured intelligence.

Meeting Context:
- Title: {meeting_title}

GUIDELINES FOR SYNTHESIS:
1. Rely strictly on the information stated in this segment. Do NOT fabricate details.
2. Structure: Return a single, valid JSON object containing exactly seven key properties: "summary", "action_items", "decisions", "risks", "dependencies", "recommendations", and "stakeholders".

KEYS & FORMAT REQUIREMENTS:
1. "summary" (string): A bullet-pointed summary of the main points discussed in this segment.
2. "action_items" (array of objects): Extract all tasks, follow-ups mentioned in this segment. Each object contains: "owner", "action", "deadline".
3. "decisions" (array of strings): Decisions agreed upon in this segment.
4. "risks" (array of strings): Risks or issues raised in this segment.
5. "dependencies" (array of strings): Technical or project dependencies mentioned in this segment.
6. "recommendations" (array of strings): Strategic paths forward recommended in this segment.
7. "stakeholders" (array of objects): Key participants mentioned or present in this segment, with "name", "role", and "sentiment" (Supportive, Neutral, Concerned).

---TRANSCRIPT SEGMENT START---
{processed_transcript}
---TRANSCRIPT SEGMENT END---

Respond ONLY with the raw JSON object."""

    def _load_reduce_prompt_template(self) -> str:
        from pathlib import Path
        possible_paths = [
            Path("prompts/reduce_prompt.md"),
            Path(__file__).parent / "prompts" / "reduce_prompt.md",
        ]
        for path in possible_paths:
            if path.exists():
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        return f.read().strip()
                except Exception as e:
                    logger.warning(f"Could not read reduce prompt template from {path}: {e}")
        return """You are an elite, executive-level Chief of Staff and AI Meeting Intelligence Specialist.
Your objective is to synthesize multiple partial analyses of meeting transcript chunks into a single, cohesive, non-redundant, MECE executive meeting debrief.

Meeting Context:
- Title: {meeting_title}
- Duration: {meeting_duration}

Below are the JSON reports generated from each segment of the meeting transcript:
{aggregated_reports}

YOUR GOAL:
Consolidate and synthesize these reports into a single, valid JSON object with the following keys:
1. "summary" (string): A synthesized MECE Executive Summary written as 3 to 6 structured, bullet-pointed key takeaways (each bullet starting with a dash "- "). Deduplicate and present the high-level strategy and outcomes.
2. "action_items" (array of objects): A consolidated list of all action items, removing duplicates. Limit to a MAXIMUM of 10 items. Each object contains: "owner", "action", "deadline".
3. "decisions" (array of strings): A consolidated list of all decisions, removing duplicates. Limit to a MAXIMUM of 10 items.
4. "risks" (array of strings): A consolidated list of all risks, removing duplicates. Limit to a MAXIMUM of 10 items.
5. "dependencies" (array of strings): A consolidated list of all dependencies, removing duplicates. Limit to a MAXIMUM of 10 items.
6. "recommendations" (array of strings): A consolidated list of strategic recommendations, removing duplicates. Limit to a MAXIMUM of 10 items.
7. "stakeholders" (array of objects): A consolidated stakeholder mapping, merging duplicate stakeholders and reporting their overall role/interest and prevailing sentiment (Supportive, Neutral, Concerned). Limit to a MAXIMUM of 10 stakeholders.

Respond ONLY with the raw JSON object."""
        
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
