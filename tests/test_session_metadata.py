import pytest
from datetime import datetime, timedelta
from noteflow.session_metadata import SessionMetadata

def test_start_time_set_on_create():
    now = datetime.now()
    sm = SessionMetadata(title="Test", transcription_mode="live", theme="dark")
    # Start time should be within a second of 'now'
    assert (sm.start_time - now).total_seconds() < 1
    assert isinstance(sm.start_time, datetime)

def test_end_time_initially_none():
    sm = SessionMetadata(title="Test", transcription_mode="live", theme="dark")
    assert sm.end_time is None

def test_mark_stopped_sets_end_time():
    sm = SessionMetadata(title="Test", transcription_mode="live", theme="dark")
    sm.mark_stopped()
    assert sm.end_time is not None
    assert isinstance(sm.end_time, datetime)

def test_duration_computed_on_stop():
    sm = SessionMetadata(title="Test", transcription_mode="live", theme="dark")
    # Fake start time 10 seconds in the past
    sm.start_time = datetime.now() - timedelta(seconds=10)
    sm.mark_stopped()
    assert 9.5 < sm.duration_seconds < 10.5

def test_duration_display_hours_minutes_seconds():
    sm = SessionMetadata(title="Test", transcription_mode="live", theme="dark")
    sm.duration_seconds = 3723
    assert sm.duration_display() == "1h 2m 3s"

def test_duration_display_minutes_seconds_only():
    sm = SessionMetadata(title="Test", transcription_mode="live", theme="dark")
    sm.duration_seconds = 154
    assert sm.duration_display() == "2m 34s"

def test_duration_display_seconds_only():
    sm = SessionMetadata(title="Test", transcription_mode="live", theme="dark")
    sm.duration_seconds = 5
    assert sm.duration_display() == "5s"

def test_to_dict_has_all_fields():
    sm = SessionMetadata(title="Test", transcription_mode="live", theme="dark")
    d = sm.to_dict()
    assert "session_id" in d
    assert "title" in d
    assert "transcription_mode" in d
    assert "theme" in d
    assert "start_time" in d
    assert "end_time" in d
    assert "duration_seconds" in d

def test_to_dict_datetimes_are_iso_strings():
    sm = SessionMetadata(title="Test", transcription_mode="live", theme="dark")
    sm.mark_stopped()
    d = sm.to_dict()
    assert isinstance(d["start_time"], str)
    assert isinstance(d["end_time"], str)
    # verify iso parseable
    datetime.fromisoformat(d["start_time"])
    datetime.fromisoformat(d["end_time"])

def test_sanitized_filename_removes_special_chars():
    sm = SessionMetadata(title="Q3 Planning / Roadmap!", transcription_mode="live", theme="dark")
    assert sm.sanitized_filename() == "Q3_Planning__Roadmap"

def test_sanitized_filename_truncates_long_titles():
    long_title = "A" * 60
    sm = SessionMetadata(title=long_title, transcription_mode="live", theme="dark")
    assert len(sm.sanitized_filename()) == 50

def test_archive_filename_format():
    sm = SessionMetadata(title="Test Archive", transcription_mode="live", theme="dark")
    sm.start_time = datetime(2026, 8, 4)
    sm.session_id = "abcdef12"
    assert sm.archive_filename() == "2026-08-04_Test_Archive_abcdef12.json"
