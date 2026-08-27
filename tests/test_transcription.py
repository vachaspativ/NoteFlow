from __future__ import annotations

import sys
from unittest.mock import MagicMock

# Mock faster_whisper before importing transcription
class MockSegment:
    def __init__(self, text):
        self.text = text

class MockWhisperModel:
    def __init__(self, *args, **kwargs):
        pass
    def transcribe(self, *args, **kwargs):
        return [MockSegment("Hello"), MockSegment("world")], None

mock_faster_whisper = MagicMock()
mock_faster_whisper.WhisperModel = MockWhisperModel
sys.modules['faster_whisper'] = mock_faster_whisper

import pytest
import numpy as np
from noteflow.transcription import WhisperTranscriber

def test_transcribe_chunk_returns_text(mocker):
    mocker.patch('noteflow.transcription.HAS_FASTER_WHISPER', True)
    mocker.patch('noteflow.transcription.WhisperModel', MockWhisperModel)
    
    transcriber = WhisperTranscriber(device='cpu')
    audio = np.zeros(16000, dtype=np.float32)
    
    text = transcriber.transcribe_chunk(audio)
    assert text == "Hello world"

def test_transcribe_full_returns_text(mocker):
    mocker.patch('noteflow.transcription.HAS_FASTER_WHISPER', True)
    mocker.patch('noteflow.transcription.WhisperModel', MockWhisperModel)
    
    transcriber = WhisperTranscriber(device='cpu')
    audio = np.zeros(16000, dtype=np.float32)
    
    text = transcriber.transcribe_full(audio)
    assert text == "Hello world"

def test_context_updated_after_chunk(mocker):
    mocker.patch('noteflow.transcription.HAS_FASTER_WHISPER', True)
    
    mock_model_class = MagicMock()
    mock_instance = MagicMock()
    words = [f"word{i}" for i in range(100)]
    mock_instance.transcribe.return_value = ([MockSegment(" ".join(words))], None)
    mock_model_class.return_value = mock_instance
    mocker.patch('noteflow.transcription.WhisperModel', mock_model_class)
    
    transcriber = WhisperTranscriber(device='cpu')
    transcriber.transcribe_chunk(np.zeros(16000, dtype=np.float32))
    
    expected_context = " ".join(words[-50:])
    assert transcriber._last_context == expected_context
    
def test_thread_safety_lock_acquired(mocker):
    mocker.patch('noteflow.transcription.HAS_FASTER_WHISPER', True)
    mocker.patch('noteflow.transcription.WhisperModel', MockWhisperModel)
    
    transcriber = WhisperTranscriber(device='cpu')
    mock_lock = MagicMock()
    transcriber._lock = mock_lock
    
    audio = np.zeros(1600, dtype=np.float32)
    transcriber.transcribe_chunk(audio)
    
    mock_lock.__enter__.assert_called_once()
    
def test_auto_device_selection(mocker):
    mocker.patch('noteflow.transcription.HAS_FASTER_WHISPER', True)
    mock_model = mocker.patch('noteflow.transcription.WhisperModel')
    mock_model.return_value.transcribe.return_value = ([], mocker.Mock())
    
    # Test CPU fallback
    mocker.patch('noteflow.transcription._detect_device', return_value='cpu')
    WhisperTranscriber(device='auto')
    assert mock_model.call_args.kwargs['device'] == 'cpu'
    assert mock_model.call_args.kwargs['compute_type'] == 'int8'
    
    # Test CUDA detection
    mocker.patch('noteflow.transcription._detect_device', return_value='cuda')
    WhisperTranscriber(device='auto')
    assert mock_model.call_args.kwargs['device'] == 'cuda'
    assert mock_model.call_args.kwargs['compute_type'] == 'float16'

def test_missing_faster_whisper(mocker):
    mocker.patch('noteflow.transcription.HAS_FASTER_WHISPER', False)
    with pytest.raises(ImportError, match="faster-whisper is not installed"):
        WhisperTranscriber(device='cpu')

def test_transcribe_chunk_handles_2d_array(mocker):
    mocker.patch('noteflow.transcription.HAS_FASTER_WHISPER', True)
    mocker.patch('noteflow.transcription.WhisperModel', MockWhisperModel)
    
    transcriber = WhisperTranscriber(device='cpu')
    audio = np.zeros((16000, 1), dtype=np.float32)
    
    text = transcriber.transcribe_chunk(audio)
    assert text == "Hello world"

def test_transcribe_full_handles_2d_array(mocker):
    mocker.patch('noteflow.transcription.HAS_FASTER_WHISPER', True)
    mocker.patch('noteflow.transcription.WhisperModel', MockWhisperModel)
    
    transcriber = WhisperTranscriber(device='cpu')
    audio = np.zeros((16000, 1), dtype=np.float32)
    
    text = transcriber.transcribe_full(audio)
    assert text == "Hello world"
