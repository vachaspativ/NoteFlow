# NoteFlow Application Launcher
param(
    [Parameter(ValueFromRemainingArguments=$true)]
    [string[]]$Args
)

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8

Write-Host "========================================================" -ForegroundColor Cyan
Write-Host " [NoteFlow] Starting 100% Offline AI Meeting Notetaker" -ForegroundColor Cyan
Write-Host "========================================================" -ForegroundColor Cyan
Write-Host ""

$VenvPython = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"

if (-not (Test-Path $VenvPython)) {
    Write-Host "[ERROR] Virtual environment not found." -ForegroundColor Red
    Write-Host "Please run the installation script first:" -ForegroundColor Yellow
    Write-Host "  powershell -ExecutionPolicy Bypass -File scripts\install.ps1" -ForegroundColor Yellow
    Write-Host ""
    Read-Host -Prompt "Press Enter to exit"
    exit 1
}

& $VenvPython -m noteflow.main $Args
