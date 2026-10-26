# SPECTRA — Software & Hardware Dependencies

Comprehensive dependency specifications, runtime requirements, and driver compatibility for all editions of **Universal Hardware Telemetry & Logic Board Diagnostics (SPECTRA)**.

---

## 1. Editions & Dependency Matrix

| Edition | Primary Target | Python Requirement | Mandatory Dependencies | Optional Dependencies | Primary UI |
| :--- | :--- | :---: | :--- | :--- | :--- |
| **`spectra`** | Linux (Jura Dedicated) | `Python >= 3.8` | **None** *(Zero pip packages)* | `PyGObject` (GTK3 desktop UI)<br>`pyserial >= 3.5` (UART fallback) | CLI / GTK3 Desktop |
| **`spectra-mm`** | Linux (Multi-Manufacturer) | `Python >= 3.8` | **None** *(Zero pip packages)* | `PyGObject` (GTK3 desktop UI)<br>`pyserial >= 3.5` (UART fallback) | Browser Web Dashboard / GTK3 |
| **`spectra-win`** | Windows 10 / 11 (Multi-Manufacturer) | `Python >= 3.10` | `pyserial >= 3.5` | None *(Web dashboard is zero-dependency)* | Browser Web Dashboard / CLI |

---

## 2. Edition Details

### A. Linux Jura Edition (`spectra`)
Built from the ground up for zero-dependency reliability in Linux field environments and embedded single-board computers (Raspberry Pi, Orange Pi, industrial PCs).

* **Core Diagnostics & Memory Dumper**:
  * Runs using **100% Python Standard Library**:
    * `termios`, `fcntl`, `select` (Native direct POSIX TTY serial communication)
    * `os`, `sys`, `time`, `re`, `json`, `argparse`, `glob`, `unittest`
  * No `pip install` commands required.
* **Optional Desktop GUI (`gui.py`)**:
  * Requires PyGObject for GTK3 rendering.
  * System package manager installation:
    * **Debian / Ubuntu**: `sudo apt install python3-gi python3-gi-cairo gir1.2-gtk-3.0`
    * **Arch / Manjaro**: `sudo pacman -S python-gobject gtk3`
    * **Fedora**: `sudo dnf install python3-gobject gtk3`
* **Optional Serial Fallback**:
  * `pyserial >= 3.5` (auto-detected if installed, but POSIX termios is preferred).

---

### B. Linux Multi-Manufacturer Edition (`spectra-mm`)
Adds multi-vendor engine abstraction supporting Jura, Nivona, Lamanti-KL (Kalerm Modbus RTU), and Lamanti-JN (Colet binary protocol).

* **CLI & Web Dashboard (`gui_web.py`)**:
  * **Zero external dependencies**:
    * Built-in HTTP server (`http.server`, `socketserver`)
    * Embedded WebSocket streaming (`socket`, `struct`, `binascii`)
    * Automatically opens your default web browser (`webbrowser`)
    * Fully offline — loads local HTML5/CSS/JavaScript with zero CDNs or cloud queries.
* **Desktop GTK3 GUI (`gui.py`)**:
  * Optional: Uses system PyGObject (`python3-gi`, `gir1.2-gtk-3.0`).

---

### C. Windows Edition (`spectra-win`)
Tailored for Windows 10 (1809+) and Windows 11 (64-bit) field laptops and workshop benches.

* **Core Dependencies**:
  * `Python >= 3.10` (from [python.org](https://www.python.org/downloads/))
  * `pyserial >= 3.5` (provides cross-platform COM port access on Windows):
    ```cmd
    pip install -r requirements-win.txt
    ```
* **Web Dashboard (`gui_web.py`)**:
  * Zero additional pip packages! Uses standard library HTTP/WebSocket server.
  * Runs inside Microsoft Edge, Google Chrome, Mozilla Firefox, or Brave at `http://127.0.0.1:8080`.
* **Automated Setup**:
  * Automated PowerShell installer: `install_windows.ps1`
  * One-click batch installer: `install_windows.bat`

---

## 3. Hardware & Serial Driver Dependencies

SPECTRA interfaces with coffee machine logic boards through USB-to-UART optical diagnostic transceivers.

### Supported USB-UART Bridge Chips

| Interface Adapter / Cable | Chipset | Linux Kernel Driver | Windows Driver | Notes |
| :--- | :--- | :--- | :--- | :--- |
| **Jura USB Scanner N 010** | FTDI FT232R / FT232RL | `ftdi_sio` *(built-in kernel)* | FTDI VCP / Windows Update | Official optical interface (bidirectional loopback) |
| **Generic Optical Cable** | WCH CH340 / CH341 | `ch341` *(built-in kernel)* | WCH CH341SER.EXE | Budget community diagnostic cables |
| **DIY / Breadboard Adapter** | Silicon Labs CP2102 / CP2104 | `cp210x` *(built-in kernel)* | SiLabs CP210x VCP Driver | Common for custom optocoupler circuits |
| **USB CDC-ACM** | Microchip / STM32 / Raspberry Pi Pico | `cdc_acm` *(built-in kernel)* | Microsoft usbser.sys *(built-in)* | Custom microcontroller transceivers |

### Linux Device Node Permissions (`udev`)
On Linux systems, access to `/dev/ttyUSB*` and `/dev/ttyACM*` requires membership in the `dialout` or `uucp` group:
```bash
# Ubuntu / Debian
sudo usermod -aG dialout $USER

# Arch Linux / Manjaro
sudo usermod -aG uucp $USER

# Log out and log back in for changes to take effect
```

### Windows COM Port Verification
Open **Device Manager** (`devmgmt.msc`) and expand **Ports (COM & LPT)**:
* Look for:
  * `USB Serial Port (COM3)` (FTDI)
  * `USB-SERIAL CH340 (COM4)` (CH340)
  * `Silicon Labs CP210x USB to UART Bridge (COM5)` (CP2102)

---

## 4. Quick Installation by Platform

### Debian / Ubuntu / Raspberry Pi OS
```bash
# 1. Clone repository
git clone https://github.com/Pr0xyA-91/spectra_dev.git
cd spectra_dev

# 2. (Optional) Install GTK3 GUI dependencies if running desktop environment
sudo apt update && sudo apt install -y python3-gi python3-gi-cairo gir1.2-gtk-3.0

# 3. Launch CLI or Web Dashboard
python3 cli.py
```

### Arch Linux / Manjaro / Omarchy
```bash
# 1. Clone repository
git clone https://github.com/Pr0xyA-91/spectra_dev.git
cd spectra_dev

# 2. (Optional) Install GTK3 dependencies
sudo pacman -S python-gobject gtk3

# 3. Launch
./run.sh
```

### Windows 10 / 11
```powershell
# Open PowerShell in the spectra-win folder and run:
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\install_windows.ps1
```
