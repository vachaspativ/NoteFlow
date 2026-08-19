#!/bin/bash
# NoteFlow Installer for Linux/macOS

echo -e "\e[36m🎙️ NoteFlow Installer\e[0m"

# Check Python
if ! command -v python3 &> /dev/null; then
    echo -e "\e[31m❌ Python 3 not found\e[0m"
    exit 1
fi
VERSION=$(python3 --version 2>&1)
echo -e "\e[32m✅ $VERSION\e[0m"

# Create venv
if [ ! -d ".venv" ]; then
    python3 -m venv .venv
fi
source .venv/bin/activate

# Install
pip install -e '.[dev]'

# Pre-download Whisper STT model weights
python3 scripts/preload_models.py base.en

# Check Ollama
if command -v ollama &> /dev/null; then
    echo -e "\e[32m✅ Ollama found\e[0m"
    ollama pull llama3
else
    echo -e "\e[33m⚠️ Ollama not found. Install from https://ollama.com\e[0m"
fi

# Check config.yaml
if [ ! -f "config.yaml" ]; then
    echo -e "\e[33m⚠️ config.yaml not found. Please ensure it is present in the project root.\e[0m"
else
    echo -e "\e[36m📝 config.yaml initialized — please edit with your credentials (Ollama model, SMTP, etc.)\e[0m"
fi

echo -e "\e[32m✅ Installation complete!\e[0m"
