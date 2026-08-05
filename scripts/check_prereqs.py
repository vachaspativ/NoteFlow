from __future__ import annotations

import sys
from pathlib import Path
from typing import Tuple

def check_python() -> Tuple[bool, str]:
    if sys.version_info >= (3, 10):
        return True, f"Python {sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro} found"
    return False, f"Python 3.10+ required, found {sys.version_info.major}.{sys.version_info.minor}"

def check_sounddevice() -> Tuple[bool, str]:
    try:
        import sounddevice as sd
        return True, "sounddevice (PortAudio) found"
    except ImportError:
        return False, "sounddevice not found. Ensure PortAudio is installed."

def check_faster_whisper() -> Tuple[bool, str]:
    try:
        import faster_whisper
        return True, "faster_whisper found"
    except ImportError:
        return False, "faster_whisper not found"

def check_ollama() -> Tuple[bool, str]:
    try:
        import httpx
        try:
            resp = httpx.get("http://localhost:11434/api/version", timeout=3.0)
            if resp.status_code == 200:
                return True, f"Ollama reachable: {resp.json().get('version', 'unknown')}"
            return False, f"Ollama HTTP error: {resp.status_code}"
        except Exception as e:
            return False, f"Ollama unreachable at localhost:11434 - {e}"
    except ImportError:
        return False, "httpx not found, cannot test Ollama"

def check_env() -> Tuple[bool, str]:
    possible_paths = [Path(".env"), Path(__file__).parent.parent / ".env"]
    for p in possible_paths:
        if p.exists():
            return True, f".env file found at {p.resolve()}"
    return False, ".env file not found"

def check_mic() -> Tuple[bool, str]:
    try:
        import sounddevice as sd
        devices = sd.query_devices(kind='input')
        if devices:
            return True, "Microphone found"
        return False, "No input devices found"
    except Exception as e:
        return False, f"Failed to query microphones - {e}"

def main():
    checks = [
        ("Python Version", check_python),
        ("sounddevice", check_sounddevice),
        ("faster_whisper", check_faster_whisper),
        ("Ollama", check_ollama),
        (".env File", check_env),
        ("Microphone", check_mic)
    ]

    print("🎙️ NoteFlow Prerequisite Check")
    print("-" * 50)
    
    all_passed = True
    for name, func in checks:
        passed, msg = func()
        if passed:
            print(f"[\033[92mPASS\033[0m] {name}: {msg}")
        else:
            print(f"[\033[91mFAIL\033[0m] {name}: {msg}")
            all_passed = False

    print("-" * 50)
    if all_passed:
        print("\033[92mAll critical checks passed!\033[0m")
        sys.exit(0)
    else:
        print("\033[91mSome critical checks failed.\033[0m")
        sys.exit(1)

if __name__ == "__main__":
    main()
