from __future__ import annotations

import queue
import threading
import numpy as np
import sounddevice as sd

def list_audio_devices() -> list[dict]:
    """Returns a list of available audio devices."""
    try:
        devices = sd.query_devices()
        return [dict(d) for d in devices]
    except sd.PortAudioError:
        return []

class AudioCapture:
    """Captures audio from the microphone in chunks."""
    
    def __init__(self, chunk_duration_secs: int = 3, sample_rate: int = 16000, device_id: int | None = None):
        self.chunk_duration_secs = chunk_duration_secs
        self.sample_rate = sample_rate
        self.device_id = device_id
        
        self._audio_queue: queue.Queue = queue.Queue(maxsize=50)
        self._stream: sd.InputStream | None = None
        self._stop_event: threading.Event = threading.Event()
        
        self._dropped_chunks: int = 0
        self._chunk_count: int = 0
        self._batch_buffer: list[np.ndarray] = []
        self._is_batch_mode: bool = False

    def start(self, batch_mode: bool = False) -> None:
        self._is_batch_mode = batch_mode
        self._stop_event.clear()
        self._dropped_chunks = 0
        self._chunk_count = 0
        self._batch_buffer.clear()
        
        # Clear the queue
        while not self._audio_queue.empty():
            try:
                self._audio_queue.get_nowait()
            except queue.Empty:
                break

        blocksize = int(self.sample_rate * self.chunk_duration_secs)
        self._stream = sd.InputStream(
            samplerate=self.sample_rate,
            device=self.device_id,
            channels=1,
            dtype='float32',
            blocksize=blocksize,
            callback=self._audio_callback
        )
        self._stream.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._stream is not None:
            self._stream.stop()
            self._stream.close()
            self._stream = None

    def get_chunk(self, timeout: float = 1.0) -> np.ndarray | None:
        if self._stop_event.is_set() and self._audio_queue.empty():
            return None
        try:
            return self._audio_queue.get(timeout=timeout)
        except queue.Empty:
            return None

    def get_full_audio(self) -> np.ndarray:
        if not self._batch_buffer:
            return np.array([], dtype='float32')
        return np.concatenate(self._batch_buffer, axis=0)

    def get_stats(self) -> dict:
        total_chunks = self._chunk_count
        chunk_samples = self.sample_rate * self.chunk_duration_secs
        total_bytes = total_chunks * chunk_samples * 4
        return {
            'chunk_count': self._chunk_count,
            'dropped_chunks': self._dropped_chunks,
            'approx_size_mb': total_bytes / (1024 * 1024)
        }

    def _audio_callback(self, indata: np.ndarray, frames: int, time_info: dict, status: sd.CallbackFlags) -> None:
        if self._stop_event.is_set():
            raise sd.CallbackStop()

        data_copy = indata.copy()
        self._chunk_count += 1
        
        if self._is_batch_mode:
            self._batch_buffer.append(data_copy)
        else:
            try:
                self._audio_queue.put(data_copy, block=False)
            except queue.Full:
                self._dropped_chunks += 1
