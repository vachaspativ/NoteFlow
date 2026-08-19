import queue
import numpy as np
import pytest
from noteflow.audio_capture import AudioCapture, list_audio_devices

def test_start_opens_stream(mocker):
    mock_sd = mocker.patch('noteflow.audio_capture.sd')
    mock_stream = mocker.MagicMock()
    mock_sd.InputStream.return_value = mock_stream

    cap = AudioCapture(enable_loopback=False)
    cap.start(batch_mode=False)

    mock_sd.InputStream.assert_called_once()
    mock_stream.start.assert_called_once()
    assert cap._is_batch_mode is False

def test_stop_closes_stream(mocker):
    mock_sd = mocker.patch('noteflow.audio_capture.sd')
    mock_stream = mocker.MagicMock()
    mock_sd.InputStream.return_value = mock_stream

    cap = AudioCapture(enable_loopback=False)
    cap.start()
    cap.stop()

    mock_stream.stop.assert_called_once()
    mock_stream.close.assert_called_once()
    assert cap._stream is None
    assert cap._stop_event.is_set()

def test_loopback_stream_creation(mocker):
    mock_sd = mocker.patch('noteflow.audio_capture.sd')
    mock_stream = mocker.MagicMock()
    mock_sd.InputStream.return_value = mock_stream

    cap = AudioCapture(enable_loopback=True)
    cap.start()
    assert mock_sd.InputStream.call_count >= 1

def test_audio_callback_puts_chunk_on_queue(mocker):
    mocker.patch('noteflow.audio_capture.sd')
    cap = AudioCapture()
    cap.start(batch_mode=False)

    mock_data = np.zeros((16000 * 3, 1), dtype='float32')
    cap._audio_callback(mock_data, len(mock_data), None, None)

    assert not cap._audio_queue.empty()
    chunk = cap._audio_queue.get_nowait()
    np.testing.assert_array_equal(chunk, mock_data)
    assert cap._chunk_count == 1

def test_batch_mode_accumulates_chunks(mocker):
    mocker.patch('noteflow.audio_capture.sd')
    cap = AudioCapture()
    cap.start(batch_mode=True)

    mock_data1 = np.ones((100, 1), dtype='float32')
    mock_data2 = np.ones((100, 1), dtype='float32') * 2

    cap._audio_callback(mock_data1, len(mock_data1), None, None)
    cap._audio_callback(mock_data2, len(mock_data2), None, None)

    assert cap._audio_queue.empty()
    full_audio = cap.get_full_audio()
    assert full_audio.shape == (200, 1)
    assert cap._chunk_count == 2

def test_batch_concat_produces_correct_shape(mocker):
    mocker.patch('noteflow.audio_capture.sd')
    cap = AudioCapture()
    cap.start(batch_mode=True)
    
    for _ in range(3):
        data = np.zeros((50, 1), dtype='float32')
        cap._audio_callback(data, 50, None, None)
        
    full = cap.get_full_audio()
    assert full.shape == (150, 1)

def test_queue_overflow_increments_dropped_counter(mocker):
    mocker.patch('noteflow.audio_capture.sd')
    cap = AudioCapture()
    cap.start(batch_mode=False)
    cap._audio_queue.maxsize = 2 # small maxsize for test

    mock_data = np.zeros((10, 1), dtype='float32')
    cap._audio_callback(mock_data, 10, None, None)
    cap._audio_callback(mock_data, 10, None, None)
    cap._audio_callback(mock_data, 10, None, None) # should drop

    assert cap._chunk_count == 3
    assert cap._dropped_chunks == 1

def test_get_stats_returns_correct_counts(mocker):
    mocker.patch('noteflow.audio_capture.sd')
    cap = AudioCapture(chunk_duration_secs=1, sample_rate=1000)
    cap.start(batch_mode=False)
    cap._chunk_count = 5
    cap._dropped_chunks = 1
    
    stats = cap.get_stats()
    assert stats['chunk_count'] == 5
    assert stats['dropped_chunks'] == 1
    assert stats['approx_size_mb'] == 20000 / (1024 * 1024)

def test_get_chunk_returns_none_on_timeout(mocker):
    mocker.patch('noteflow.audio_capture.sd')
    cap = AudioCapture()
    cap.start()
    
    chunk = cap.get_chunk(timeout=0.01)
    assert chunk is None

def test_list_audio_devices(mocker):
    mock_sd = mocker.patch('noteflow.audio_capture.sd')
    mock_sd.query_devices.return_value = [{'name': 'Microphone'}]
    devices = list_audio_devices()
    assert devices == [{'name': 'Microphone'}]
