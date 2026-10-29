@echo off
setlocal enabledelayedexpansion
title SPECTRA — Windows Executable Builder

echo ===============================================================================
echo   SPECTRA — Standalone Executable Compiler (PyInstaller)
echo ===============================================================================
echo.

where python >nul 2>nul
if %errorlevel% neq 0 (
    echo [!] Error: Python 3 is not found in PATH.
    echo     Please install Python 3.10+ from python.org and check "Add python.exe to PATH".
    pause
    exit /b 1
)

echo [*] Checking and installing build dependencies (pyinstaller, pyserial)...
python -m pip install --upgrade pip
python -m pip install pyinstaller pyserial

if %errorlevel% neq 0 (
    echo [!] Failed to install dependencies.
    pause
    exit /b 1
)

echo.
echo [*] Compiling standalone spectra.exe using spectra.spec...
python -m PyInstaller --clean --noconfirm spectra.spec

if %errorlevel% neq 0 (
    echo.
    echo [!] PyInstaller build failed. Check error output above.
    pause
    exit /b 1
)

echo.
echo ===============================================================================
echo [✓] SUCCESS! Standalone executable created:
echo     dist\spectra.exe
echo ===============================================================================
echo.
echo You can now copy dist\spectra.exe anywhere or create a desktop shortcut.
echo No Python installation or scripts are required to run spectra.exe.
echo.
pause
