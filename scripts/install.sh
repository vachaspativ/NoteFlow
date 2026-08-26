#!/usr/bin/env bash
# NoteFlow Installer for Linux/macOS
set -e

echo -e "\e[36m========================================================\e[0m"
echo -e "\e[36m [NoteFlow] Installer for Linux/macOS\e[0m"
echo -e "\e[36m========================================================\e[0m"
echo ""

# Check Python
if ! command -v python3 &> /dev/null; then
    echo -e "\e[31m[ERROR] Python 3 not found\e[0m"
    exit 1
fi
VERSION=$(python3 --version 2>&1)
echo -e "\e[32m[OK] $VERSION\e[0m"

# Create venv
if [ ! -d ".venv" ]; then
    echo -e "\e[36m[INFO] Creating virtual environment (.venv)...\e[0m"
    python3 -m venv .venv
fi
source .venv/bin/activate

# Install
echo -e "\e[36m[INFO] Installing NoteFlow dependencies...\e[0m"
pip install -e '.[dev]'

# Pre-download Whisper STT model weights
echo -e "\e[36m[INFO] Pre-downloading Whisper STT base model weights...\e[0m"
python3 scripts/preload_models.py base.en

# Check Ollama
if command -v ollama &> /dev/null; then
    echo -e "\e[32m[OK] Ollama found in PATH\e[0m"
    ollama pull llama3.2
else
    echo -e "\e[33m[WARN] Ollama not found. Install from https://ollama.com to enable AI note synthesis.\e[0m"
fi

# Check config.yaml
if [ ! -f "config.yaml" ]; then
    echo -e "\e[33m[WARN] config.yaml not found in project root.\e[0m"
else
    echo -e "\e[36m[OK] config.yaml initialized\e[0m"
fi

echo ""
echo -e "\e[32m========================================================\e[0m"
echo -e "\e[32m[OK] NoteFlow Installation Complete!\e[0m"
echo -e "\e[32mRun './start.sh' to launch NoteFlow.\e[0m"
echo -e "\e[32m========================================================\e[0m"
