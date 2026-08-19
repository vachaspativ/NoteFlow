from __future__ import annotations

import threading
import time


class TranscriptStore:
    """Thread-safe transcript store for holding audio transcription segments."""

    def __init__(self) -> None:
        self._segments: list[tuple[float, str]] = []
        self._lock = threading.Lock()
        self._start_time: float = time.time()

    def append(self, text: str) -> None:
        """Appends a new transcript segment."""
        text = text.strip()
        if not text:
            return
        
        with self._lock:
            timestamp = time.time() - self._start_time
            self._segments.append((timestamp, text))

    def get_full_transcript(self) -> str:
        """Returns all segments' text joined by spaces."""
        with self._lock:
            return " ".join(text for _, text in self._segments)

    def get_full_text(self) -> str:
        """Alias for get_full_transcript."""
        return self.get_full_transcript()

    def get_timestamped_transcript(self) -> str:
        """Returns segments formatted as '[MM:SS] text' per segment."""
        with self._lock:
            formatted = []
            for timestamp, text in self._segments:
                minutes = int(timestamp // 60)
                seconds = int(timestamp % 60)
                formatted.append(f"[{minutes:02d}:{seconds:02d}] {text}")
            return "\n".join(formatted)

    def get_display_segments(self, last_n: int = 20) -> list[str]:
        """Returns the text of the last N segments."""
        with self._lock:
            return [text for _, text in self._segments[-last_n:]]

    def segment_count(self) -> int:
        """Returns number of segments."""
        with self._lock:
            return len(self._segments)

    def clear(self) -> None:
        """Clears all segments."""
        with self._lock:
            self._segments.clear()

    def reset(self) -> None:
        """Clears segments and resets start_time."""
        with self._lock:
            self._segments.clear()
            self._start_time = time.time()
