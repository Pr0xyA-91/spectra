@echo off
setlocal
cd /d "%~dp0"
title SPECTRA Offline Simulation Demo

echo ===============================================================================
echo   SPECTRA — Offline Simulation Mode (Jura S8 Demo Model)
echo ===============================================================================
echo.
echo [*] Testing simulated live microswitches and sensor contacts...
python cli.py --demo --sensors
echo.
echo [*] Reading full simulated diagnostic statistics and beverage counts...
python cli.py --demo
echo.
echo ===============================================================================
echo [✓] Demo run complete! Press any key to exit.
echo ===============================================================================
pause
