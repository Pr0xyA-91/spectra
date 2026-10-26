<#
.SYNOPSIS
    Automated Windows Setup & Dependency Installer for SPECTRA
    Part of Universal Hardware Telemetry & Logic Board Diagnostics (SPECTRA) Windows Edition

.DESCRIPTION
    Checks Python 3 environment, upgrades pip, installs required dependencies (pyserial),
    verifies serial drivers, scans available hardware COM ports, and optionally creates
    a Desktop shortcut for the SPECTRA Web Dashboard.

.NOTES
    Author: Google Antigravity (Agy / DeepMind) & SPECTRA Community
    Requires: Windows 10/11, Python 3.10+
#>

[CmdletBinding()]
param(
    [switch]$NonInteractive,
    [switch]$SkipShortcut
)

$ErrorActionPreference = "Stop"

function Write-Banner {
    Write-Host ""
    Write-Host "===============================================================================" -ForegroundColor Cyan
    Write-Host "       SPECTRA — Universal Hardware Telemetry & Logic Board Diagnostics — Windows Setup" -ForegroundColor Yellow
    Write-Host "            Automated Diagnostic Suite & Hardware Installer" -ForegroundColor Cyan
    Write-Host "===============================================================================" -ForegroundColor Cyan
    Write-Host ""
}

function Test-CommandExists {
    param([string]$CommandName)
    $cmd = Get-Command $CommandName -ErrorAction SilentlyContinue
    return ($null -ne $cmd)
}

function Get-PythonExecutable {
    if (Test-CommandExists "python") {
        return "python"
    }
    if (Test-CommandExists "py") {
        return "py"
    }
    return $null
}

# --- 1. Display Header ---
Write-Banner

# --- 2. Locate Python Executable ---
Write-Host "[*] Checking for Python installation..." -ForegroundColor Cyan
$pythonExe = Get-PythonExecutable

if ($null -eq $pythonExe) {
    Write-Host ""
    Write-Host "[!] ERROR: Python 3 was not found in your system PATH!" -ForegroundColor Red
    Write-Host ""
    Write-Host "To resolve this:" -ForegroundColor Yellow
    Write-Host "  1. Download Python 3.10+ from: https://www.python.org/downloads/" -ForegroundColor White
    Write-Host "  2. Run the installer and CRITICALLY check the box:" -ForegroundColor White
    Write-Host "     [X] Add python.exe to PATH" -ForegroundColor Yellow
    Write-Host "  3. Restart PowerShell and re-run this script." -ForegroundColor White
    Write-Host ""
    if (-not $NonInteractive) {
        Read-Host "Press Enter to exit..."
    }
    exit 1
}

# Retrieve Python version
$pyVersionRaw = & $pythonExe -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}')"
Write-Host "    [✓] Found Python $pyVersionRaw ($pythonExe)" -ForegroundColor Green

# Check version threshold (>= 3.8 mandatory, >= 3.10 recommended)
$pyMajor, $pyMinor, $pyMicro = $pyVersionRaw.Split(".") | ForEach-Object { [int]$_ }
if ($pyMajor -lt 3 -or ($pyMajor -eq 3 -and $pyMinor -lt 8)) {
    Write-Host "[!] WARNING: Python version is older than 3.8. SPECTRA recommends Python 3.10 or higher." -ForegroundColor Red
}

# --- 3. Upgrade pip and Install Dependencies ---
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
$reqFile = Join-Path $scriptDir "requirements-win.txt"

Write-Host "`n[*] Upgrading pip packaging tool..." -ForegroundColor Cyan
& $pythonExe -m pip install --upgrade pip --quiet

Write-Host "[*] Installing Windows dependencies from requirements-win.txt..." -ForegroundColor Cyan
if (Test-Path $reqFile) {
    & $pythonExe -m pip install -r $reqFile
} else {
    Write-Host "    [!] requirements-win.txt not found, installing pyserial directly..." -ForegroundColor Yellow
    & $pythonExe -m pip install "pyserial>=3.5"
}

# Verify pyserial import
try {
    $serialVer = & $pythonExe -c "import serial; print(serial.__version__)"
    Write-Host "    [✓] pyserial $serialVer installed and verified successfully!" -ForegroundColor Green
} catch {
    Write-Host "[!] ERROR: Failed to import pyserial after installation." -ForegroundColor Red
    exit 1
}

# --- 4. Scan Hardware Serial & COM Ports ---
Write-Host "`n[*] Scanning for connected serial / optical diagnostic adapters..." -ForegroundColor Cyan
$comPorts = @()

try {
    $pnpPorts = Get-CimInstance -ClassName Win32_PnPEntity -Filter "PNPClass = 'Ports'" -ErrorAction SilentlyContinue
    if ($pnpPorts) {
        foreach ($port in $pnpPorts) {
            $name = $port.Name
            $caption = $port.Caption
            $comPorts += "$caption"
            Write-Host "    [+] Detected Port: $caption" -ForegroundColor Green
        }
    }
} catch {
    # Fallback to .NET System.IO.Ports
    $rawPorts = [System.IO.Ports.SerialPort]::GetPortNames()
    foreach ($p in $rawPorts) {
        $comPorts += $p
        Write-Host "    [+] Detected Port: $p" -ForegroundColor Green
    }
}

if ($comPorts.Count -eq 0) {
    Write-Host "    [-] No active COM ports detected." -ForegroundColor DarkYellow
    Write-Host "        (Plug in your USB optical adapter or use DEMO simulation mode)" -ForegroundColor Gray
}

# --- 5. Optional Desktop Shortcut Creation ---
if (-not $SkipShortcut) {
    $createShortcut = $true
    if (-not $NonInteractive) {
        Write-Host ""
        $answer = Read-Host "[?] Create a Desktop Shortcut for the SPECTRA Web Dashboard? [Y/n]"
        if ($answer.Trim().ToLower() -eq "n") {
            $createShortcut = $false
        }
    }

    if ($createShortcut) {
        try {
            $desktopPath = [System.Environment]::GetFolderPath([System.Environment+SpecialFolder]::Desktop)
            $shortcutPath = Join-Path $desktopPath "SPECTRA Diagnostic Dashboard.lnk"
            $targetBat = Join-Path $scriptDir "run_web.bat"
            $iconPath = Join-Path $scriptDir "icon.png"

            $wscriptShell = New-Object -ComObject WScript.Shell
            $shortcut = $wscriptShell.CreateShortcut($shortcutPath)
            $shortcut.TargetPath = $targetBat
            $shortcut.WorkingDirectory = $scriptDir
            $shortcut.Description = "Launch SPECTRA Coffee Machine Diagnostic Web Dashboard"
            if (Test-Path $iconPath) {
                $shortcut.IconLocation = $iconPath
            }
            $shortcut.Save()
            Write-Host "    [✓] Desktop shortcut created: $shortcutPath" -ForegroundColor Green
        } catch {
            Write-Host "    [-] Notice: Could not create desktop shortcut ($($_.Exception.Message))" -ForegroundColor Gray
        }
    }
}

# --- 6. Success Summary & Next Steps ---
Write-Host ""
Write-Host "===============================================================================" -ForegroundColor Green
Write-Host "[✓] SETUP COMPLETE: SPECTRA is ready to use!" -ForegroundColor Green
Write-Host "===============================================================================" -ForegroundColor Green
Write-Host ""
Write-Host "Quick Launch Commands (from this directory):" -ForegroundColor White
Write-Host "  - Web Dashboard  : .\run_web.bat   (or: $pythonExe gui_web.py)" -ForegroundColor Cyan
Write-Host "  - CLI Tool       : .\run_cli.bat   (or: $pythonExe cli.py --port COM3)" -ForegroundColor Cyan
Write-Host "  - Offline Demo   : .\run_demo.bat  (or: $pythonExe cli.py --demo)" -ForegroundColor Cyan
Write-Host "  - Model Dumper   : $pythonExe contrib\dump_machine_spec.py --port COM3" -ForegroundColor Cyan
Write-Host ""
Write-Host "Documentation & Guides:" -ForegroundColor White
Write-Host "  - Windows Guide  : INSTALL_WINDOWS.md" -ForegroundColor Gray
Write-Host "  - Dependencies   : DEPENDENCIES.md" -ForegroundColor Gray
Write-Host "  - Memory Map     : docs\JURA_MEMORY_MAP.md" -ForegroundColor Gray
Write-Host "===============================================================================" -ForegroundColor Green
Write-Host ""

if (-not $NonInteractive) {
    Read-Host "Press Enter to exit..."
}
