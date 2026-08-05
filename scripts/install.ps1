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
pip install -e '.[dev]'

# Check Ollama
$ollama = Get-Command ollama -ErrorAction SilentlyContinue
if ($ollama) {
    Write-Host '✅ Ollama found' -ForegroundColor Green
    ollama pull llama3
} else {
    Write-Host '⚠️ Ollama not found. Install from https://ollama.com' -ForegroundColor Yellow
}

# Copy .env
if (-not (Test-Path '.env')) { Copy-Item '.env.example' '.env'; Write-Host '📝 Created .env — please edit with your credentials' }

Write-Host '✅ Installation complete!' -ForegroundColor Green
