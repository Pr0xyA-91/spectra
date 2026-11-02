# SPECTRA — Software & Hardware Dependencies

Comprehensive dependency specifications, runtime requirements, and driver compatibility for all editions of **Universal Hardware Telemetry & Logic Board Diagnostics (SPECTRA)**.

---

## 1. Editions & Dependency Matrix

| Edition | Primary Target | Runtime Requirements | Mandatory Dependencies | Optional Dependencies | Primary UI |
| :--- | :--- | :---: | :--- | :--- | :--- |
| **`spectra` (`main`)** | Linux (Multi-Manufacturer & Rust Hybrid) | `Python >= 3.10`<br>`Rust >= 1.80` *(for native crates)* | **None** *(Zero pip packages for core)* | `PyGObject` (GTK3 desktop UI)<br>`pyserial >= 3.5` (UART fallback)<br>`cargo` (Rust hybrid build) | 5-Paradigm Web Workstation / GTK3 Desktop / CLI |
| **`spectra-win` (`windows`)** | Windows 10 / 11 (Multi-Manufacturer & Rust Hybrid) | `Python >= 3.10` *(embedded in installer)* | `pyserial >= 3.5` *(bundled in setup/launcher)* | None *(Standalone .exe and Web UI are self-contained)* | Browser Web Workstation / Standalone Launcher / CLI |

---

## 2. Edition Details

### A. Linux Multi-Manufacturer Edition (`spectra` — branch `main`)
Built from the ground up for high reliability in Linux field environments, desktop workstations, and embedded single-board computers (Raspberry Pi, industrial PCs).

* **Core Multi-Manufacturer Diagnostics Engine**:
  * Runs using **100% Python Standard Library**:
    * `termios`, `fcntl`, `select` (Native direct POSIX TTY serial communication with exclusive flock protection)
    * `os`, `sys`, `time`, `re`, `json`, `argparse`, `glob`, `unittest`, `struct`
  * Zero pip packages required for core CLI diagnostic routines.
* **5-Paradigm Web Workstation (`run_ui.sh` / `web_server.py`)**:
  * Native Python HTTP & REST API server serving production Vite React assets from `web/dist/`.
  * Real-time telemetry streaming, interactive P&ID industrial diagrams, oscilloscope strip charts, and memory matrix.
* **3-Layer Rust Workspace (`crates/`)**:
  * High-performance native workspace:
    * `crates/spectra-hal`: POSIX & async serial HAL.
    * `crates/spectra-core`: Zero-allocation state machine, `@`-cipher, and EEPROM mapper.
    * `crates/spectra-agent`: Tauri v2 async backend & WebSocket daemon.
    * `crates/spectra-py`: PyO3 native extension (`spectra_py.so`).
* **Desktop GTK3 GUI (`gui.py`)**:
  * Optional: Uses system PyGObject (`python3-gi`, `gir1.2-gtk-3.0`).
  * Package manager installation:
    * **Debian / Ubuntu**: `sudo apt install python3-gi python3-gi-cairo gir1.2-gtk-3.0`
    * **Arch / Manjaro / Omarchy**: `sudo pacman -S python-gobject gtk3`
    * **Fedora**: `sudo dnf install python3-gobject gtk3`

---

### B. Windows Edition (`spectra-win` — branch `windows`)
Tailored for Windows 10 (1809+) and Windows 11 (64-bit) field laptops and workshop benches.

* **Native Windows Standalone Binaries**:
  * `bin/spectra.exe`: Single-file PE32+ standalone launcher (22 MB) embedding isolated Python 3.12 runtime and PySerial.
  * `dist/spectra_setup_build*.exe`: Native PE32+ offline installer (44 MB) compiled via Zig and LLVM-RC.
  * `dist/spectra_update_build*.exe`: Fast in-place application updater (884 KB).
* **Multi-Manufacturer Support**:
  * Full driver support for Jura, Nivona, Lamanti-KL (Kalerm), and Lamanti-JN (Jetinno).
  * Auto-discovers Windows `COM*` ports.
* **Web Workstation (`gui_web.py` / `web_server.py`)**:
  * Zero additional setup required! Automatically opens in Microsoft Edge, Google Chrome, Firefox, or Brave at `http://127.0.0.1:8080`.

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

# Arch Linux / Manjaro / Omarchy
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
# 1. Clone private repository
git clone https://github.com/Pr0xyA-91/spectra_dev.git
cd spectra_dev

# 2. (Optional) Install GTK3 GUI dependencies if running desktop environment
sudo apt update && sudo apt install -y python3-gi python3-gi-cairo gir1.2-gtk-3.0

# 3. Launch Web Workstation or CLI
./run_ui.sh
python3 cli.py
```

### Arch Linux / Manjaro / Omarchy
```bash
# 1. Launch Web Workstation (Recommended)
./run_ui.sh

# 2. Or launch GTK3 desktop GUI
./run.sh
```

### Windows 10 / 11
Run the native offline installer `dist/spectra_setup_build20261102.1605.exe` or execute `bin/spectra.exe`.
