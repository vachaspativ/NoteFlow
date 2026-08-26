# NoteFlow Installer for Windows
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8

Write-Host "========================================================" -ForegroundColor Cyan
Write-Host " [NoteFlow] Installer for Windows" -ForegroundColor Cyan
Write-Host "========================================================" -ForegroundColor Cyan
Write-Host ""

# Check Python
$python = Get-Command python -ErrorAction SilentlyContinue
if (-not $python) {
    Write-Host "[ERROR] Python not found in PATH." -ForegroundColor Red
    exit 1
}
$version = python --version 2>&1
Write-Host "[OK] $version" -ForegroundColor Green

# Create venv
if (-not (Test-Path '.venv')) {
    Write-Host "[INFO] Creating virtual environment (.venv)..." -ForegroundColor Cyan
    python -m venv .venv
}

Write-Host "[INFO] Installing NoteFlow dependencies..." -ForegroundColor Cyan
.venv\Scripts\python.exe -m pip install -e .[dev]

# Check for NVIDIA GPU to install CUDA runtimes
$gpu = Get-CimInstance Win32_VideoController -ErrorAction SilentlyContinue | Where-Object { $_.Name -like "*NVIDIA*" }
if ($gpu) {
    Write-Host "[INFO] NVIDIA GPU detected ($($gpu.Name)). Installing CUDA 12 support libraries..." -ForegroundColor Cyan
    .venv\Scripts\python.exe -m pip install nvidia-cublas-cu12 nvidia-cudnn-cu12
} else {
    Write-Host "[INFO] No NVIDIA GPU detected. Skipping CUDA support libraries (CPU fallback will be used)." -ForegroundColor Cyan
}

# Pre-download Whisper STT model weights
Write-Host "[INFO] Pre-downloading Whisper STT base model weights..." -ForegroundColor Cyan
.venv\Scripts\python.exe scripts/preload_models.py base.en

# Check Ollama
$ollama = Get-Command ollama -ErrorAction SilentlyContinue
if ($ollama) {
    Write-Host "[OK] Ollama found in PATH" -ForegroundColor Green
    Write-Host "[INFO] Pulling llama3.2 model (optimized for CPU)..." -ForegroundColor Cyan
    ollama pull llama3.2
} else {
    Write-Host "[WARN] Ollama not found in PATH. Install from https://ollama.com to enable AI note synthesis." -ForegroundColor Yellow
}

# Check config.yaml
if (-not (Test-Path 'config.yaml')) {
    Write-Host "[WARN] config.yaml not found in project root." -ForegroundColor Yellow
} else {
    Write-Host "[OK] config.yaml initialized" -ForegroundColor Cyan
}

Write-Host ""
Write-Host "========================================================" -ForegroundColor Green
Write-Host "[OK] NoteFlow Installation Complete!" -ForegroundColor Green
Write-Host "Run 'start.bat' or '.\start.ps1' to launch NoteFlow." -ForegroundColor Green
Write-Host "========================================================" -ForegroundColor Green
