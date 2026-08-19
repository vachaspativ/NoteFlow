import logging
import queue
import sys
import threading
import numpy as np
import sounddevice as sd

logger = logging.getLogger(__name__)

def list_audio_devices() -> list[dict]:
    """Returns a list of available audio devices."""
    try:
        devices = sd.query_devices()
        return [dict(d) for d in devices]
    except sd.PortAudioError:
        return []

class AudioCapture:
    """Captures audio from the microphone and optional WASAPI speaker loopback."""
    
    def __init__(
        self,
        chunk_duration_secs: int = 3,
        sample_rate: int = 16000,
        device_id: int | None = None,
        enable_loopback: bool = True
    ):
        self.chunk_duration_secs = chunk_duration_secs
        self.sample_rate = sample_rate
        self.device_id = device_id
        self.enable_loopback = enable_loopback
        
        self._audio_queue: queue.Queue = queue.Queue(maxsize=50)
        self._loopback_queue: queue.Queue = queue.Queue(maxsize=50)
        
        self._stream: sd.InputStream | None = None
        self._loopback_stream: sd.InputStream | None = None
        self._stop_event: threading.Event = threading.Event()
        
        self._dropped_chunks: int = 0
        self._chunk_count: int = 0
        self._batch_buffer: list[np.ndarray] = []
        self._is_batch_mode: bool = False
        self.is_loopback_active: bool = False

    def start(self, batch_mode: bool = False) -> None:
        self._is_batch_mode = batch_mode
        self._stop_event.clear()
        self._dropped_chunks = 0
        self._chunk_count = 0
        self._batch_buffer.clear()
        self.is_loopback_active = False
        
        # Clear queues
        for q in (self._audio_queue, self._loopback_queue):
            while not q.empty():
                try:
                    q.get_nowait()
                except queue.Empty:
                    break

        blocksize = int(self.sample_rate * self.chunk_duration_secs)
        
        # 1. Start primary microphone input stream
        self._stream = sd.InputStream(
            samplerate=self.sample_rate,
            device=self.device_id,
            channels=1,
            dtype='float32',
            blocksize=blocksize,
            callback=self._audio_callback
        )
        self._stream.start()

        # 2. Optionally start WASAPI loopback output stream (Windows only)
        if self.enable_loopback and sys.platform.startswith('win'):
            try:
                wasapi_settings = sd.WasapiSettings(auto_convert=True)
                self._loopback_stream = sd.InputStream(
                    samplerate=self.sample_rate,
                    channels=1,
                    dtype='float32',
                    blocksize=blocksize,
                    extra_settings=wasapi_settings,
                    callback=self._loopback_callback
                )
                self._loopback_stream.start()
                self.is_loopback_active = True
                logger.info("WASAPI Loopback capture started successfully (Two-Way Call Audio enabled).")
            except Exception as e:
                logger.debug(f"WASAPI Loopback stream unavailable: {e}. Using standard single microphone capture.")
                self._loopback_stream = None
                self.is_loopback_active = False

    def stop(self) -> None:
        self._stop_event.set()
        for stream_attr in ('_stream', '_loopback_stream'):
            stream = getattr(self, stream_attr, None)
            if stream is not None:
                try:
                    stream.stop()
                    stream.close()
                except Exception:
                    pass
                setattr(self, stream_attr, None)
        self.is_loopback_active = False

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
            'approx_size_mb': total_bytes / (1024 * 1024),
            'loopback_active': self.is_loopback_active
        }

    def _loopback_callback(self, indata: np.ndarray, frames: int, time_info: dict, status: sd.CallbackFlags) -> None:
        if self._stop_event.is_set():
            raise sd.CallbackStop()
        try:
            self._loopback_queue.put(indata.copy(), block=False)
        except queue.Full:
            pass

    def _audio_callback(self, indata: np.ndarray, frames: int, time_info: dict, status: sd.CallbackFlags) -> None:
        if self._stop_event.is_set():
            raise sd.CallbackStop()

        mic_data = indata.copy()
        
        # Mix microphone + speaker loopback if loopback audio is available
        loopback_data = None
        if self.is_loopback_active:
            try:
                loopback_data = self._loopback_queue.get_nowait()
            except queue.Empty:
                pass

        if loopback_data is not None and len(loopback_data) == len(mic_data):
            mixed_data = (mic_data + loopback_data) / 2.0
        else:
            mixed_data = mic_data

        self._chunk_count += 1
        
        if self._is_batch_mode:
            self._batch_buffer.append(mixed_data)
        else:
            try:
                self._audio_queue.put(mixed_data, block=False)
            except queue.Full:
                self._dropped_chunks += 1
