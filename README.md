# SPECTRA — Universal Hardware Telemetry & Logic Board Diagnostics

<p align="center">
  <img src="docs/brand/spectra_banner.svg" alt="SPECTRA Diagnostic Suite" width="100%">
</p>

[![Build: 20261102.1605](https://img.shields.io/badge/build-20261102.1605-blue.svg)](https://github.com/Pr0xyA-91/spectra)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Rust: 1.80+](https://img.shields.io/badge/rust-1.80+-orange.svg)](https://www.rust-lang.org/)
[![GUI: GTK 3 | Web](https://img.shields.io/badge/GUI-GTK%203%20%7C%20Web-green.svg)](https://www.gtk.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Platform: Linux](https://img.shields.io/badge/Platform-Linux-orange.svg)](https://kernel.org)

> [!NOTE]
> **Project Status: Build 20261102.1605 (Linux Multi-Manufacturer & Rust Hybrid Suite)** — Unified Diagnostic Platform.
> **SPECTRA** is an extensible appliance hardware telemetry and logic board diagnostic engine supporting **Jura**, **Nivona**, **Lamanti-KL (Kalerm)**, and **Lamanti-JN (Jetinno)**. Features a 3-layer Rust hybrid workspace (`spectra-hal`, `spectra-core`, `spectra-agent`, `spectra-py`), 5-paradigm web workstation, GTK 3 desktop GUI, headless CLI, dynamic model profiling, EEPROM differential mapping, and automated field capture tools.

---

## 🌟 Overview

The legacy coffee service tools (from 2016 and earlier) were built around 32-bit Windows, lacked support for modern electronic architectures, and only recognized obsolete machines with frozen databases. Newer appliances trigger protocol rejections, encrypted handshake requirements, or locked logic boards.

**SPECTRA** runs natively on modern Linux systems and provides a unified, vendor-agnostic architecture:
1. **Jura Diagnostics Engine**:
   - **Plain-ASCII Optical Protocol**: Interrogates machines via the official **JURA USB Scanner N 010** or direct optical serial connections. Features optical loopback echo stripping, hardware pacing calibration (~16ms/char), and full EEPROM block interrogation (`RT:0000`–`RT:0030`, `RE:`, `CS:`, `IC:`, `HZ:`).
   - **Encrypted Smart Connect Protocol**: Speaks the native `@`-protocol with 4:1 wire carrier modulation (`0xDB` base byte), recovered nibble-permutation S-box cipher, and complete challenge-response handshake (`@T0` $\rightarrow$ `@T1` $\rightarrow$ `@t2` $\rightarrow$ `@T3` $\rightarrow$ `@t3`).
2. **Nivona CafeRomatica Driver**: Native support for NICR 5xx/6xx/7xx/8xx/9xx/10xx and NIVO 810x series over Eugster/Frismag AG electronic architecture (9600 baud, 8N1).
3. **Lamanti-KL (Kalerm Platform) Driver**: Full diagnostics and live telemetry for Kalerm K95, KLM1601/2601, and commercial platforms.
4. **Lamanti-JN (Jetinno Platform) Driver**: Commercial HORECA telemetry for Jetinno JLTT, JL08, JL10, JL15, JL28, and JL500 vending series via binary framing and CRC16 validation.
5. **3-Layer Rust Hybrid Architecture**: Ultra-low-latency HAL, deterministic protocol parsing, Tauri v2 async backend, and native PyO3 C extension (`spectra_py.so`).

---

## ✨ Features

- **5 Interactive UI Paradigms & Web Workstation**:
  - **Engineering Telemetry**: High-density gauges, strip charts, and component state trees.
  - **Industrial Process**: Piping & Instrumentation (P&ID) schematics with active solenoid/heater animations.
  - **Executive KPI**: High-level maintenance readiness, beverage yields, and lifecycle summaries.
  - **Diagnostic Scopes**: Real-time temperature oscilloscope and live hydraulic flow rate monitoring.
  - **Memory Matrix**: Real-time EEPROM memory cell viewer with byte-by-byte differential heatmaps.
- **Native GTK 3 Desktop Application**: Fast, dark-mode GTK 3 desktop application with KPI summary cards, sortable beverage tables, maintenance progress bars, and dedicated live sensor inspection.
- **Full Headless CLI**: Command-line interface with colored output, progress bar, multi-format export, and rapid sensor polling.
- **Accurate Sensor Decoding & Safety Systems**:
  - **Tenths-of-a-Degree Celsius (°C) Decoding**: Accurately translates raw Jura NTC sensor readings into 0.1 °C precision for Coffee Thermoblock (`TB1`), Steam Thermoblock (`TB2`), and Ambient/Intake NTCs.
  - **Dual-Heater Accommodation**: Built-in architecture detection seamlessly accommodates dual-thermoblock models (e.g. Z10, GIGA) and single-thermoblock models (e.g. E8, S8) with clean `Not Installed (Single Heater Model)` indicators.
  - **Bean Hopper Optical Sensor (`AS:`)**: Net reflection delta ($\Delta = \text{ON} - \text{OFF}$) thermal calibration ($115 \pm 5$ counts) with hysteresis band ($110 < \Delta < 120$).
  - **Physical Microswitches & Contacts**: Interrogates water tank level float, drip tray presence switch, machine readiness state, and CLARIS water filter configuration in real time (`HZ:`).
  - **Trip Counters & Fault Latches**: Decodes hardware fault registers (`RE:0028`) and lifetime trip counters (`0x01B0`–`0x01B6`).
- **170+ Machine Profiles**: Unified database recognizing all generations of Jura machines (Gen 7+, E/ENA/D/S/J/Z/C/X/W/WE/GIGA series, and classic TOP-tronic).
- **Multi-Format Export**: Export clean diagnostic reports to formatted text (`.txt`), structured JSON (`.json`), or CSV (`.csv`).
- **Hardware Simulation Modes**: Built-in mock devices allow full testing across all vendors without physical hardware.

---

## 🚀 Quick Start

### 1. Launch Next-Gen Web Workstation (Recommended)
```bash
./run_ui.sh
```
Opens the 5-paradigm interface automatically at `http://127.0.0.1:8080`.

### 2. Launch Native GTK 3 Desktop GUI
```bash
./run.sh
```
*(Or launch **SPECTRA** from your desktop application launcher / menu).*

### 3. Run from the Command Line (CLI)
```bash
# Read diagnostics from connected machine
./run.sh --cli -p /dev/ttyUSB0

# Read live hardware sensors only
./run.sh --cli -p /dev/ttyUSB0 --sensors

# Run with simulated demo machine (no hardware required)
./run.sh --cli --demo --demo-model S8

# Export diagnostic report
./run.sh --cli -p /dev/ttyUSB0 -o diagnostic_report.txt
./run.sh --cli -p /dev/ttyUSB0 -o telemetry.json --format json
./run.sh --cli -p /dev/ttyUSB0 -o counters.csv --format csv

# List detected serial ports
./run.sh --cli --list-ports

# List all supported machine models
./run.sh --cli --list-models
```

---

## 🏗️ 3-Layer Rust Hybrid Architecture

SPECTRA features a high-performance native Rust core integrated via PyO3:

| Crate | Purpose | Core Responsibilities |
|---|---|---|
| [`crates/spectra-hal`](crates/spectra-hal) | Hardware Abstraction Layer | POSIX termios serial driver, `tokio-serial` async UART transport, cross-platform port discovery, Android ADB `/dev/ttyS*` bridge. |
| [`crates/spectra-core`](crates/spectra-core) | Protocol & Memory Core | Zero-allocation byte-level state machine, optical loopback echo stripper, `@`-cipher encoder/decoder, differential EEPROM mapper, bean hopper thermal calibration. |
| [`crates/spectra-agent`](crates/spectra-agent) | IPC & WebSocket Daemon | High-speed telemetry broadcaster and Tauri v2 async backend. |
| [`crates/spectra-py`](crates/spectra-py) | PyO3 Native Extension | Bridges high-performance Rust parsing directly into Python (`spectra_py.so`). |

To verify and compile the Rust workspace:
```bash
cargo check --workspace
cargo test --workspace
```

---

## 🔌 Hardware Connection Guide

### Option A: Official JURA USB Scanner (N 010)
Connect the USB scanner to any USB port. The FTDI chip is recognized automatically on Linux as `/dev/ttyUSB0`. Attach the optical head to the machine's front optical port.

### Option B: 5V USB-to-UART Adapter (FTDI FT232R, CP2102, CH340)
For machines with internal or external 4-pin service ports:
- **Baud Rate**: `9600 Baud`, 8 Data Bits, No Parity, 1 Stop Bit (`9600 8-N-1`).
- **Signal Logic**: 5V TTL UART.
- **Pinout (typical 4-pin port)**:
  - Pin 1: `GND` $\rightarrow$ Adapter `GND`
  - Pin 2: `TX` (out of machine) $\rightarrow$ Adapter `RX`
  - Pin 3: `RX` (into machine) $\rightarrow$ Adapter `TX`
  - Pin 4: `+5V VCC` $\rightarrow$ *(Leave disconnected if using USB adapter to prevent ground loops)*.

### Option C: Dangerous Prototypes Bus Pirate v3.6
The Bus Pirate v3.6 can be used as a transparent 5V-tolerant UART bridge:
1. Jura Pin 1 (`GND`) $\rightarrow$ Bus Pirate `GND`
2. Jura Pin 2 (`TX`) $\rightarrow$ Bus Pirate `MISO` (BP RX)
3. Jura Pin 3 (`RX`) $\rightarrow$ Bus Pirate `MOSI` (BP TX)
4. Set UART mode to 9600 8N1, macro `(3)` for transparent bridge.

---

## 🔒 Permissions on Linux

Serial adapters (`/dev/ttyUSB*`) belong to the `uucp` group on Arch Linux (or `dialout` on Debian/Ubuntu):
```bash
# Arch / Omarchy
sudo usermod -aG uucp $USER

# Ubuntu / Debian
sudo usermod -aG dialout $USER
```
*(Log out and log back in for group membership to take effect).*

---

## 📁 Repository Structure

```
.
├── Cargo.toml              # Rust 3-layer workspace manifest
├── crates/
│   ├── spectra-hal/        # Serial POSIX & tokio async transport
│   ├── spectra-core/       # Jura protocol state machine & cipher
│   ├── spectra-agent/      # Tauri v2 async backend & WS broadcaster
│   └── spectra-py/         # PyO3 native spectra_py.so extension
├── drivers/                # Unified multi-manufacturer driver suite
│   ├── base.py             # Common appliance driver abstraction
│   ├── jura/               # Jura optical & Smart Connect driver
│   ├── nivona/             # Nivona CafeRomatica driver
│   ├── lamanti_kl/         # Lamanti Kalerm platform driver
│   └── lamanti_jn/         # Lamanti Jetinno HORECA driver
├── web/                    # 5-Paradigm React + Vite Web UI
│   ├── src/                # Modern telemetry & P&ID components
│   └── dist/               # Production compiled UI bundle
├── run.sh                  # GTK 3 GUI & CLI launcher script
├── run_ui.sh               # 5-Paradigm Web UI & API server launcher
├── SPECTRA.desktop         # Linux desktop entry launcher
├── icon.png                # Desktop icon
├── gui.py                  # GTK 3 desktop application
├── gui_web.py              # Lightweight fallback web dashboard
├── web_server.py           # 5-paradigm API & static file web server
├── cli.py                  # Command-line interface runner
├── stats_collector.py      # Telemetry orchestrator & report exporters
├── memory_mapper.py        # Differential EEPROM memory mapper & logic scope
├── spectra_probe.py        # J.O.E. auto-correlator & diagnostic probe
├── profiles_db.py          # Machine profile resolver & database engine
├── profiles_data.json      # Database of 170+ machine profiles & memory maps
├── docs/                   # Reverse-engineering protocol & memory documentation
│   ├── JURA_MEMORY_MAP.md  # Master EEPROM & telemetry register map
│   └── models/             # Verified model-specific hardware specifications
├── DEPENDENCIES.md         # Runtime requirements & dependency reference
├── LICENSE                 # MIT License
└── README.md               # Unified platform documentation
```

---

## 📜 Credits & Acknowledgements

This project builds upon the shared knowledge, protocol analysis, and reverse-engineering contributions of the open-source coffee telemetry and home automation community:

- **CM-P ([jura-coffee-machine](https://github.com/CM-P/jura-coffee-machine))**: Foundational documentation and reverse-engineering of the Jura optical port, cleartext command structure (`TY:`, `RT:`, `RE:`, `AN:`, `FA:`), baud timing, and optical pinout mapping.
- **Hajo Noerenberg ([hn/jura-coffee-machine](https://github.com/hn/jura-coffee-machine)) & c't Magazin / Heise ("Kaffeemaschine gehackt")**: Pioneer research on Jura optical transceivers, `cmd2jura` bit-banging gateway routines, and embedded serial communication.
- **Jutta-Proto Project ([Jutta-Proto/protocol-cpp](https://github.com/Jutta-Proto/protocol-cpp))**: C++ reverse-engineering and protocol implementations for optical/serial and modern Bluetooth/WiFi Smart Connect communication, de-obfuscation layers, and technician test modes.
- **Ryan Alden ([ryanalden/esphome-jura-component](https://github.com/ryanalden/esphome-jura-component))**: ESPHome Jura component research for physical contact monitoring, microswitch status bit decoding, tray/tank alerts, and home automation integration.
- **AlexxIT ([AlexxIT/Jura](https://github.com/AlexxIT/Jura))**: Home Assistant custom component researching Jura Bluetooth communication, GATT protocols, and command framing.
- **makefu ([makefu/jura-connect-hass](https://github.com/makefu/jura-connect-hass)) & `jura-connect` researchers**: Reverse-engineering of Jura Wi-Fi protocol, status alert bitfields (`@TF:`), beverage parameter structures, and live maintenance indicators.
- **Otto Winter & the [ESPHome](https://esphome.io/) Project**: Research and implementation of embedded Jura UART communication and protocol timing.
- **tinaught ([Jura-Coffee-Machine-Home-Assistant](https://github.com/tinaught/Jura-Coffee-Machine-Home-Assistant)) & bpeoples**: Home Assistant integration, EEPROM word mapping, and beverage counter offsets.
- **Smart Connect Protocol Researchers**: Reverse-engineering of modern Jura bus communication, 4:1 wire carrier modulation (`0xDB` base byte), and dongle challenge-response handshake sequence.
- **Dangerous Prototypes**: Creators of the Bus Pirate hardware tool used for multi-protocol bus debugging.
- **Google Antigravity (Agy / DeepMind)**: Advanced reverse-engineering, 3-layer Rust hybrid workspace, dynamic Brew Unit position tracking, optical infrared bean hopper sensor (`AS:`) decoding, real-time multi-manufacturer telemetry architectures, and Windows cross-platform implementation.
- **Kaffee-Welt & Kaffeevollautomaten Forum communities**: Pioneer technician insights into the classic Jura filling loop (*"System füllen Endlosschleife"*), thermoblock NTC temperature registers, and hydraulic diagnostic fault codes.

---

## 📄 License

This project is licensed under the [MIT License](LICENSE).
