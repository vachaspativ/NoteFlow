from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


def generate_session_id() -> str:
    """Generate an 8-character hex string for session id."""
    return uuid.uuid4().hex[:8]


@dataclass
class SessionMetadata:
    """Metadata for a NoteFlow recording session."""
    title: str
    transcription_mode: str
    theme: str
    session_id: str = field(default_factory=generate_session_id)
    start_time: datetime = field(default_factory=datetime.now)
    end_time: datetime | None = None
    duration_seconds: float = 0.0

    def mark_stopped(self) -> None:
        """Mark the session as stopped, setting end_time and computing duration."""
        self.end_time = datetime.now()
        self.duration_seconds = (self.end_time - self.start_time).total_seconds()

    def duration_display(self) -> str:
        """Format duration as '1h 2m 3s', omitting leading zeros."""
        s = int(self.duration_seconds)
        h = s // 3600
        m = (s % 3600) // 60
        sec = s % 60
        
        parts = []
        if h > 0:
            parts.append(f"{h}h")
            parts.append(f"{m}m")
            parts.append(f"{sec}s")
        elif m > 0:
            parts.append(f"{m}m")
            parts.append(f"{sec}s")
        else:
            parts.append(f"{sec}s")
            
        return " ".join(parts)

    def to_dict(self) -> dict[str, Any]:
        """Convert metadata to a JSON-serializable dictionary."""
        return {
            "session_id": self.session_id,
            "title": self.title,
            "transcription_mode": self.transcription_mode,
            "theme": self.theme,
            "start_time": self.start_time.isoformat(),
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "duration_seconds": self.duration_seconds
        }

    def sanitized_filename(self) -> str:
        """Return a filename-safe version of the title."""
        # Remove anything that's not alphanumeric, space, or hyphen
        s = re.sub(r'[^a-zA-Z0-9\s-]', '', self.title)
        # Replace spaces with underscores
        s = s.replace(' ', '_')
        # Truncate to 50 characters
        return s[:50]

    def archive_filename(self) -> str:
        """Return the archive filename format based on start time and title."""
        date_str = self.start_time.strftime("%Y-%m-%d")
        return f"{date_str}_{self.sanitized_filename()}_{self.session_id}.json"
