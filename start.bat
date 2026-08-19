@echo off
title NoteFlow - 100%% Offline AI Notetaker
echo.
echo ========================================================
echo  🎙️  Starting NoteFlow (100%% Offline AI Meeting Notetaker)
echo ========================================================
echo.

IF NOT EXIST ".venv\Scripts\python.exe" (
    echo [ERROR] Virtual environment not found.
    echo Please run the installation script first:
    echo   powershell -ExecutionPolicy Bypass -File scripts\install.ps1
    echo.
    pause
    exit /b 1
)

.venv\Scripts\python.exe -m noteflow.main %*

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo NoteFlow stopped.
    pause
)
