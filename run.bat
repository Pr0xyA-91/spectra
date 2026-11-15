@echo off
setlocal
cd /d "%~dp0"
title SPECTRA Standalone Desktop Application

where pythonw >nul 2>nul
if %errorlevel% equ 0 (
    start "" pythonw spectra_app.py %*
    exit /b 0
)

where python >nul 2>nul
if %errorlevel% neq 0 (
    echo [!] Python is not found in PATH. Please run install_windows.bat first.
    pause
    exit /b 1
)

echo [*] Launching SPECTRA Standalone Desktop Application...
python spectra_app.py %*
if %errorlevel% neq 0 (
    echo.
    echo [!] Application closed with exit code %errorlevel%.
    pause
)
