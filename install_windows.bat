@echo off
setlocal
title W.R.A.T. Windows Setup
echo ===============================================================================
echo   W.R.A.T. — WhiteRat Asynchronous Telemetry — Windows Setup
echo ===============================================================================
echo.

where python >nul 2>nul
if %errorlevel% neq 0 (
    echo [!] Error: Python 3 is not installed or not in system PATH.
    echo [*] Please install Python 3.10+ from https://www.python.org/downloads/
    echo [*] Make sure to check "Add Python to PATH" during installation.
    echo.
    pause
    exit /b 1
)

echo [*] Upgrading pip and installing dependencies...
python -m pip install --upgrade pip
python -m pip install -r requirements-win.txt

echo.
echo ===============================================================================
echo [✓] Setup completed successfully!
echo [*] You can now run:
echo     - 'run.bat'      : Launches GUI (Web dashboard / GTK)
echo     - 'run_web.bat'  : Launches zero-dependency browser dashboard
echo     - 'run_cli.bat'  : Launches command-line diagnostic tool
echo     - 'run_demo.bat' : Runs instant offline simulation without hardware
echo ===============================================================================
echo.
pause
