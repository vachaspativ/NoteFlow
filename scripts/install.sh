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

# Check Ollama
if command -v ollama &> /dev/null; then
    echo -e "\e[32m✅ Ollama found\e[0m"
    ollama pull llama3
else
    echo -e "\e[33m⚠️ Ollama not found. Install from https://ollama.com\e[0m"
fi

# Copy .env
if [ ! -f ".env" ]; then
    if [ -f ".env.example" ]; then
        cp .env.example .env
        echo -e "\e[32m📝 Created .env — please edit with your credentials\e[0m"
    fi
fi

echo -e "\e[32m✅ Installation complete!\e[0m"
