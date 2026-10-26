# SPECTRA Windows Installation & Configuration Guide

A complete, step-by-step installation guide for running **Universal Hardware Telemetry & Logic Board Diagnostics (SPECTRA)** on Microsoft Windows 10 and Windows 11.

---

## 1. Prerequisites

### A. Operating System
* Windows 10 (Version 1809 or later, 64-bit)
* Windows 11 (64-bit)

### B. Python 3.10+ Installation
1. Download the official 64-bit installer from [python.org/downloads](https://www.python.org/downloads/).
2. Run the installer:
   > [!IMPORTANT]
   > On the very first setup screen, you **MUST** check the box:
   > **`☑ Add python.exe to PATH`**
   > Failing to check this box will prevent Windows from locating Python in the command line.
3. Click **Install Now**.
4. At the completion screen, click **Disable path length limit** (if prompted), then click **Close**.

### C. Hardware Diagnostic Interface
* **Jura USB Scanner N 010** (Official FTDI-based optical adapter), or
* **Generic USB-to-UART Optical Interface** (CH340 / CP2102 / FTDI FT232R).

---

## 2. Installation Methods

Choose any of the three installation methods below:

### Method 1: Automated PowerShell Script (Recommended)
This script automatically checks Python, upgrades `pip`, installs `pyserial`, scans for connected COM ports, and creates an optional Desktop shortcut.

1. Open File Explorer and navigate to your `spectra-win` folder.
2. Right-click in the empty space, hold `Shift`, and select **Open PowerShell window here** (or **Open in Terminal**).
3. Run the following command:
   ```powershell
   Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
   .\install_windows.ps1
   ```
4. Follow the interactive prompts.

---

### Method 2: One-Click Batch Installer
1. Navigate to the `spectra-win` folder.
2. Double-click **`install_windows.bat`**.
3. A command prompt window will open, verify Python, and install dependencies automatically.
4. Press any key when finished.

---

### Method 3: Manual Command Line
1. Open **Command Prompt** (`cmd.exe`) or **PowerShell** in the `spectra-win` directory.
2. Run:
   ```cmd
   python -m pip install --upgrade pip
   pip install -r requirements-win.txt
   ```
3. Test that the environment is working:
   ```cmd
   python -c "import serial; print('pyserial version:', serial.__version__)"
   ```

---

## 3. Hardware Adapter Setup & Driver Verification

### Checking Your COM Port
1. Plug your USB optical diagnostic cable into a USB port on your PC.
2. Press `Win + X` and select **Device Manager** (or press `Win + R`, type `devmgmt.msc`, and hit Enter).
3. Expand the **Ports (COM & LPT)** category.
4. Look for an entry such as:
   * `USB Serial Port (COM3)` (FTDI FT232R / Jura Scanner)
   * `USB-SERIAL CH340 (COM4)` (WCH CH340 adapter)
   * `Silicon Labs CP210x USB to UART Bridge (COM5)` (CP2102)
5. Note the COM port number (e.g. `COM3`).

### Driver Downloads (if yellow triangle appears)
* **FTDI Chipset**: Windows Update installs this automatically. For manual install: [ftdichip.com/drivers/vcp-drivers/](https://ftdichip.com/drivers/vcp-drivers/)
* **WCH CH340 Chipset**: Download `CH341SER.EXE` from [wch-ic.com](https://www.wch-ic.com/downloads/CH341SER_EXE.html).
* **Silicon Labs CP210x**: Download VCP drivers from [silabs.com](https://www.silabs.com/developers/usb-to-uart-bridge-vcp-drivers).

---

## 4. Launching SPECTRA

SPECTRA provides multiple ways to run diagnostics on Windows:

### A. Web Dashboard (Recommended GUI)
The modern, zero-dependency browser interface.
* **Option 1**: Double-click **`run_web.bat`**.
* **Option 2**: From PowerShell/CMD:
  ```cmd
  python gui_web.py
  ```
* Your default web browser will automatically open `http://127.0.0.1:8080`.
* Select your COM port from the drop-down menu and click **Connect**.

### B. Command-Line Interface (CLI)
* Double-click **`run_cli.bat`** (prompts for COM port), or run:
  ```cmd
  python cli.py --port COM3
  ```
* Export JSON diagnostic report:
  ```cmd
  python cli.py --port COM3 --export-json diagnostic_report.json
  ```
* Compare machine against baseline specification:
  ```cmd
  python cli.py --port COM3 --diff EF518
  ```

### C. Offline Demo / Simulation
To explore SPECTRA without physical hardware connected:
* Double-click **`run_demo.bat`**, or run:
  ```cmd
  python cli.py --demo
  ```

### D. Community Machine Specification Dumper
To dump complete EEPROM memory and contribute a new machine specification to GitHub:
```cmd
python contrib\dump_machine_spec.py --port COM3
```

---

## 5. Troubleshooting & FAQ

### Q1: `python is not recognized as an internal or external command`
* **Cause**: Python was installed without checking "Add python.exe to PATH".
* **Solution**: Re-run the Python installer from [python.org](https://www.python.org/downloads/), select **Modify**, and make sure **Add python.exe to PATH** is checked. Alternatively, manually add `C:\Users\<YourUser>\AppData\Local\Programs\Python\Python3xx\` to your Windows System PATH.

### Q2: `PermissionError: [Errno 13] Access is denied: 'COM3'`
* **Cause**: Another application is currently holding the COM port open (e.g., Cura, Arduino IDE, PuTTY, Jura Service Tool, or an existing Python session).
* **Solution**: Close any software using the serial port, unplug the USB cable, plug it back in, and retry.

### Q3: `Timeout connecting to machine` / `No response`
* **Cause**: Optical alignment issue or baud rate mismatch.
* **Solution**:
  1. Verify the optical transceiver is correctly seated against the machine's optical port. On Jura machines, the optical port is hidden behind the front Jura emblem or an oval cap on the top lid.
  2. Ensure the optical head is clean and free of ground coffee dust.
  3. Verify the machine is switched ON and showing "Ready" or "Select Product".

### Q4: PowerShell execution policy error (`File cannot be loaded because running scripts is disabled...`)
* **Solution**: Run the following in PowerShell before executing the installer:
  ```powershell
  Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
  ```
