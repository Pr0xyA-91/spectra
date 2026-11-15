@echo off
setlocal
cd /d "%~dp0"
title SPECTRA Standalone App

where pythonw >nul 2>nul
if %errorlevel% equ 0 (
    start "" pythonw spectra_app.py %*
    exit /b 0
)

where python >nul 2>nul
if %errorlevel% neq 0 (
    echo [!] Python is not found in PATH.
    pause
    exit /b 1
)

echo [*] Launching SPECTRA Standalone Desktop Application...
python spectra_app.py %*
