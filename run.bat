@echo off
setlocal
cd /d "%~dp0"
title SPECTRA Telemetry Suite

where python >nul 2>nul
if %errorlevel% neq 0 (
    echo [!] Python is not found in PATH. Please run install_windows.bat first.
    pause
    exit /b 1
)

echo [*] Launching SPECTRA Telemetry Suite...
python gui.py %*
if %errorlevel% neq 0 (
    echo.
    echo [!] GUI closed with exit code %errorlevel%.
    pause
)
