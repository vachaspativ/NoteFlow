from __future__ import annotations

import os
os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"

import threading
from typing import Optional
import numpy as np

try:
    from faster_whisper import WhisperModel
    HAS_FASTER_WHISPER = True
except ImportError:
    HAS_FASTER_WHISPER = False

def _detect_device() -> str:
    """Detect if CUDA is available, otherwise return CPU."""
    try:
        import torch
        if torch.cuda.is_available():
            return 'cuda'
    except ImportError:
        pass
    return 'cpu'

from pathlib import Path

class WhisperTranscriber:
    """Whisper Speech-to-Text wrapper using faster-whisper."""

    def __init__(self, model_name: str = 'base.en', device: str = 'auto', vad_threshold: float = 0.5, allow_online: bool = False):
        if not HAS_FASTER_WHISPER:
            raise ImportError("faster-whisper is not installed. Please install it to use WhisperTranscriber.")
            
        self._lock = threading.Lock()
        self._last_context = ""
        
        if device == 'auto':
            device = _detect_device()
            
        compute_type = 'float16' if device == 'cuda' else 'int8'
        
        # Check for in-project models/ directory
        models_dir = Path("models").resolve()
        if not models_dir.exists():
            models_dir.mkdir(parents=True, exist_ok=True)
            
        local_model_path = models_dir / model_name
        target_model = str(local_model_path) if local_model_path.exists() else model_name
        
        local_files_only = not allow_online
        
        try:
            self._model = WhisperModel(
                target_model,
                device=device,
                compute_type=compute_type,
                download_root=str(models_dir),
                local_files_only=local_files_only
            )
        except Exception:
            # Fall back to remote download if model is not pre-cached locally yet
            self._model = WhisperModel(
                target_model,
                device=device,
                compute_type=compute_type,
                download_root=str(models_dir),
                local_files_only=False
            )

    def transcribe_chunk(self, audio: np.ndarray, sample_rate: int = 16000) -> str:
        """Transcribes a short chunk of audio, keeping context from previous chunks."""
        if hasattr(audio, "ndim") and isinstance(getattr(audio, "ndim", None), int) and audio.ndim > 1:
            audio = audio.flatten()
        with self._lock:
            segments, info = self._model.transcribe(
                audio,
                language='en',
                vad_filter=True,
                vad_parameters={'min_silence_duration_ms': 500},
                initial_prompt=self._last_context
            )
            
            text_parts = []
            for segment in segments:
                text_parts.append(segment.text)
                
            full_text = " ".join(text_parts).strip()
            
            # Update last context with last 50 words for continuous transcription
            words = full_text.split()
            if words:
                self._last_context = " ".join(words[-50:])
            
            return full_text

    def transcribe_full(self, audio: np.ndarray, sample_rate: int = 16000) -> str:
        """Transcribes a complete audio recording in batch mode."""
        if hasattr(audio, "ndim") and isinstance(getattr(audio, "ndim", None), int) and audio.ndim > 1:
            audio = audio.flatten()
        with self._lock:
            segments, info = self._model.transcribe(
                audio,
                language='en',
                vad_filter=True,
                vad_parameters={'min_silence_duration_ms': 500}
            )
            
            text_parts = []
            for segment in segments:
                text_parts.append(segment.text)
                
            return " ".join(text_parts).strip()

    def is_model_loaded(self) -> bool:
        """Returns True if the underlying model is successfully loaded."""
        return hasattr(self, '_model') and self._model is not None
