@echo off
setlocal
cd /d "%~dp0"
title SPECTRA CLI Diagnostics

where python >nul 2>nul
if %errorlevel% neq 0 (
    echo [!] Python is not found in PATH.
    pause
    exit /b 1
)

python cli.py %*
if "%~1"=="" (
    pause
)
