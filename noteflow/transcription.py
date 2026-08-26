from __future__ import annotations

import os
os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"

# Dynamically add nvidia pip package DLL directories to Windows search path
if os.name == 'nt':
    try:
        import nvidia.cublas
        import nvidia.cudnn
        # Walk and register directories containing DLLs
        for pkg in [nvidia.cublas, nvidia.cudnn]:
            pkg_path = os.path.dirname(pkg.__file__)
            for root, dirs, files in os.walk(pkg_path):
                if any(f.endswith('.dll') for f in files):
                    try:
                        os.add_dll_directory(os.path.abspath(root))
                    except Exception:
                        pass
    except ImportError:
        pass

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

def _resolve_whisper_model_path(models_dir: Path, model_name: str) -> str:
    """Resolves local directory or HF snapshot path for faster-whisper."""
    # Check 1: Direct subdirectory (e.g. models/base.en)
    direct_path = models_dir / model_name
    if direct_path.exists() and (direct_path / "model.bin").exists():
        return str(direct_path)

    # Check 2: HF cache snapshot directory (e.g. models/models--Systran--faster-whisper-base.en/snapshots/<hash>)
    for hf_folder in models_dir.glob(f"*faster-whisper-{model_name}*"):
        snapshots_dir = hf_folder / "snapshots"
        if snapshots_dir.exists():
            snapshots = list(snapshots_dir.glob("*"))
            if snapshots:
                return str(snapshots[0])

    # Default to model_name for standard faster-whisper / HF hub lookup
    return model_name

class WhisperTranscriber:
    """Whisper Speech-to-Text wrapper using faster-whisper."""

    def __init__(self, model_name: str = 'base.en', device: str = 'auto', vad_threshold: float = 0.5, allow_online: bool = False):
        if not HAS_FASTER_WHISPER:
            raise ImportError("faster-whisper is not installed. Please install it to use WhisperTranscriber.")
            
        self._lock = threading.Lock()
        self._last_context = ""
        
        # Configure HuggingFace environment variables to prevent unauthenticated network calls
        os.environ["HF_HUB_DISABLE_IMPLICIT_TOKEN_WARNING"] = "1"
        os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"
        if not allow_online:
            os.environ["HF_HUB_OFFLINE"] = "1"
            os.environ["TRANSFORMERS_OFFLINE"] = "1"
        else:
            os.environ.pop("HF_HUB_OFFLINE", None)
            os.environ.pop("TRANSFORMERS_OFFLINE", None)

        if device == 'auto':
            device = _detect_device()
            
        compute_type = 'float16' if device == 'cuda' else 'int8'
        
        # Check for in-project models/ directory
        models_dir = Path("models").resolve()
        if not models_dir.exists():
            models_dir.mkdir(parents=True, exist_ok=True)
            
        target_model = _resolve_whisper_model_path(models_dir, model_name)
        local_files_only = not allow_online
        
        try:
            self._model = WhisperModel(
                target_model,
                device=device,
                compute_type=compute_type,
                download_root=str(models_dir),
                local_files_only=local_files_only
            )
        except Exception as e:
            if allow_online:
                # If online downloads are allowed, try fallback to online model name
                self._model = WhisperModel(
                    model_name,
                    device=device,
                    compute_type=compute_type,
                    download_root=str(models_dir),
                    local_files_only=False
                )
            else:
                raise RuntimeError(
                    f"Failed to load Whisper model '{model_name}' locally from '{models_dir}'. "
                    f"Online downloads are currently disabled (allow_online_model_download: false). Error: {e}"
                )

        # Test if CUDA inference works (forces lazy library loading of cublas64_12.dll)
        if device == 'cuda':
            try:
                import numpy as np
                dummy_audio = np.zeros(1600, dtype=np.float32)
                # Force iterator evaluation to trigger library loading
                list(self._model.transcribe(dummy_audio))
            except Exception as e:
                import logging
                logger = logging.getLogger("noteflow")
                logger.warning(
                    f"CUDA execution failed (likely missing runtime DLLs like cublas64_12.dll): {e}. "
                    f"Automatically falling back to CPU mode."
                )
                device = 'cpu'
                compute_type = 'int8'
                try:
                    self._model = WhisperModel(
                        target_model,
                        device=device,
                        compute_type=compute_type,
                        download_root=str(models_dir),
                        local_files_only=local_files_only
                    )
                except Exception as ex:
                    if allow_online:
                        self._model = WhisperModel(
                            model_name,
                            device=device,
                            compute_type=compute_type,
                            download_root=str(models_dir),
                            local_files_only=False
                        )
                    else:
                        raise ex

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
