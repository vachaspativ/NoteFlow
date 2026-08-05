from __future__ import annotations

import threading
import time

from noteflow.transcript_store import TranscriptStore


def test_append_and_get_full_transcript() -> None:
    store = TranscriptStore()
    store.append("Hello")
    store.append("World")
    assert store.get_full_transcript() == "Hello World"


def test_append_strips_whitespace() -> None:
    store = TranscriptStore()
    store.append("  Testing  ")
    assert store.get_full_transcript() == "Testing"


def test_append_ignores_empty_text() -> None:
    store = TranscriptStore()
    store.append("Hello")
    store.append("   ")
    store.append("")
    assert store.segment_count() == 1
    assert store.get_full_transcript() == "Hello"


def test_get_display_segments_returns_last_n() -> None:
    store = TranscriptStore()
    for i in range(30):
        store.append(f"Segment {i}")
    
    display = store.get_display_segments(10)
    assert len(display) == 10
    assert display[0] == "Segment 20"
    assert display[-1] == "Segment 29"


def test_get_timestamped_transcript_format() -> None:
    store = TranscriptStore()
    
    # Manually set start time to control the timestamps
    store._start_time = time.time() - 65  # 1 min 5 seconds ago
    store.append("Test segment")
    
    transcript = store.get_timestamped_transcript()
    assert "[01:05] Test segment" in transcript


def test_segment_count() -> None:
    store = TranscriptStore()
    assert store.segment_count() == 0
    store.append("A")
    assert store.segment_count() == 1
    store.append("B")
    assert store.segment_count() == 2


def test_clear() -> None:
    store = TranscriptStore()
    store.append("A")
    store.clear()
    assert store.segment_count() == 0
    assert store.get_full_transcript() == ""


def test_concurrent_appends() -> None:
    store = TranscriptStore()
    
    def worker() -> None:
        for i in range(100):
            store.append(f"Item {i}")
            time.sleep(0.001)

    threads = [threading.Thread(target=worker) for _ in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
        
    assert store.segment_count() == 1000


def test_get_full_transcript_preserves_order() -> None:
    store = TranscriptStore()
    store.append("a")
    store.append("b")
    store.append("c")
    assert store.get_full_transcript() == "a b c"
