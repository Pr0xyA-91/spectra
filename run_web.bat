@echo off
setlocal
cd /d "%~dp0"
title W.R.A.T. Web Dashboard

where python >nul 2>nul
if %errorlevel% neq 0 (
    echo [!] Python is not found in PATH.
    pause
    exit /b 1
)

echo [*] Launching W.R.A.T. Universal Web Dashboard on http://127.0.0.1:8080 ...
python gui_web.py %*
