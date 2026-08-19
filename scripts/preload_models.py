from __future__ import annotations

import os
import sys

# Suppress Hugging Face symlinks warning on Windows
os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"

from pathlib import Path

def preload_whisper_model(model_size: str = "base.en") -> None:
    models_dir = Path("models").resolve()
    models_dir.mkdir(parents=True, exist_ok=True)
    print(f"⬇️ Pre-downloading Whisper STT model weights ('{model_size}') into local project folder '{models_dir}'...")
    try:
        from faster_whisper import WhisperModel
        WhisperModel(model_size, device="cpu", compute_type="int8", download_root=str(models_dir))
        print(f"✅ Whisper model '{model_size}' preloaded into '{models_dir}' successfully!")
    except Exception as e:
        print(f"⚠️ Could not pre-download Whisper model '{model_size}': {e}")

if __name__ == "__main__":
    model_name = sys.argv[1] if len(sys.argv) > 1 else "base.en"
    preload_whisper_model(model_name)
