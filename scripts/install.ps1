# NoteFlow Installer for Windows
Write-Host '🎙️ NoteFlow Installer' -ForegroundColor Cyan

# Check Python
$python = Get-Command python -ErrorAction SilentlyContinue
if (-not $python) { Write-Host '❌ Python not found' -ForegroundColor Red; exit 1 }
$version = python --version 2>&1
Write-Host "✅ $version" -ForegroundColor Green

# Create venv
if (-not (Test-Path '.venv')) { python -m venv .venv }
.venv\Scripts\Activate.ps1

# Install
pip install -e .[dev]

# Pre-download Whisper STT model weights
python scripts/preload_models.py base.en

# Check Ollama
$ollama = Get-Command ollama -ErrorAction SilentlyContinue
if ($ollama) {
    Write-Host '✅ Ollama found' -ForegroundColor Green
    ollama pull llama3
} else {
    Write-Host '⚠️ Ollama not found. Install from https://ollama.com' -ForegroundColor Yellow
}

# Check config.yaml
if (-not (Test-Path 'config.yaml')) {
    Write-Host '⚠️ config.yaml not found. Please ensure it is present in the project root.' -ForegroundColor Yellow
} else {
    Write-Host '📝 config.yaml initialized — please edit with your credentials (Ollama model, SMTP, etc.)' -ForegroundColor Cyan
}

Write-Host '✅ Installation complete!' -ForegroundColor Green
