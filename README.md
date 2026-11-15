# SPECTRA — Universal Hardware Telemetry & Logic Board Diagnostics

<p align="center">
  <img src="docs/brand/spectra_banner.svg" alt="SPECTRA Diagnostic Suite" width="100%">
</p>

[![Build: 20261114.0020](https://img.shields.io/badge/build-20261114.0020-blue.svg)](https://github.com/Pr0xyA-91/spectra)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Rust: 1.80+](https://img.shields.io/badge/rust-1.80+-orange.svg)](https://www.rust-lang.org/)
[![GUI: Native Shell | Web | CLI](https://img.shields.io/badge/GUI-Native%20Shell%20%7C%20Web%20%7C%20CLI-green.svg)](https://www.gtk.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Platforms: Linux & Windows](https://img.shields.io/badge/Platforms-Linux%20%7C%20Windows-06B6D4.svg)](https://kernel.org)

> [!NOTE]
> **Project Status: Build 20261114.0020 (Phase 3 Rust Hybrid Gateway & Multi-Manufacturer Suite)** — Unified Diagnostic Platform.
> **SPECTRA** is an extensible appliance hardware telemetry and logic board diagnostic platform supporting **Jura**, **Nivona**, **Lamanti-KL (Kalerm)**, and **Lamanti-JN (Jetinno)**. It combines a single-window native Rust desktop shell (`spectra-shell`), embedded Rust HTTP/1.1 gateway (`spectra-agent`), deterministic Rust protocol/math codecs (`spectra-core` + `spectra-py`), a 9-tab React workstation, an opt-in default-OFF **Local AI** engine with CSV/screenshot **EEPROM Offset Calibration**, a unified **172-machine profile library**, opt-in **GitHub community sync**, and an **ELF/APK/MCU Firmware Inspector**.

---

## 📖 Documentation & Illustrated Guides

- **[Illustrated Operator & Field Technician Guide (`docs/USER_GUIDE.md`)](docs/USER_GUIDE.md)** — Complete visual step-by-step manual covering installation (Windows & Linux), hardware wiring, Local AI model setup, fixing EEPROM offsets from J.O.E. CSV/screenshots, Machine Library overrides, and connecting GitHub.
- **[Jura EEPROM & Sub-Bus Memory Map (`docs/JURA_MEMORY_MAP.md`)](docs/JURA_MEMORY_MAP.md)** — Register-level hardware protocol documentation (`RT:`, `RE:`, `HZ:`, `CS:`, `AS:`, `$:` display sub-bus).
- **[Field Capture & J.O.E. Correlation Guide (`docs/FIELD_CAPTURE_GUIDE.md`)](docs/FIELD_CAPTURE_GUIDE.md)** — Capturing anonymized dumps for new models.
- **[Release Changelog (`CHANGELOG.md`)](CHANGELOG.md)** — Full build history and diff summary.

<p align="center">
  <a href="docs/USER_GUIDE.md">
    <img src="docs/images/spectra_overview_workflow.svg" alt="SPECTRA Workstation Overview and 9 Diagnostic Tabs" width="100%">
  </a>
</p>

---

## 🌟 Overview

The legacy coffee service tools (from 2016 and earlier) were built around 32-bit Windows, lacked support for modern electronic architectures, and only recognized obsolete machines with frozen databases. Newer appliances trigger protocol rejections, encrypted handshake requirements, or locked logic boards.

**SPECTRA** runs natively on both **Linux** and **Windows** (`windows` branch with offline `spectra_setup.exe` / `spectra_update.exe` installers) and provides a unified, vendor-agnostic architecture:
1. **Jura Diagnostics Engine**:
   - **Plain-ASCII Optical Protocol**: Interrogates machines via the official **JURA USB Scanner N 010** or direct 5V TTL optical/UART connections. Features optical loopback echo stripping, deterministic wire pacing (`8 ms` / `16 ms`), and full EEPROM block interrogation (`RT:0000`–`RT:01F0`, `RE:`, `CS:`, `IC:`, `HZ:`).
   - **Encrypted Smart Connect Protocol**: Speaks the native `@`-protocol with 4:1 wire carrier modulation (`0xDB` base byte), recovered nibble-permutation S-box cipher, and complete challenge-response handshake (`@T0` $\rightarrow$ `@T1` $\rightarrow$ `@t2` $\rightarrow$ `@T3` $\rightarrow$ `@t3`).
2. **Nivona CafeRomatica Driver**: Native support for NICR 5xx/6xx/7xx/8xx/9xx/10xx and NIVO 810x series over Eugster/Frismag AG electronic architecture (`9600 baud, 8N1`).
3. **Lamanti-KL (Kalerm Platform) Driver**: Full diagnostics and live telemetry for Kalerm K95, KLM1601/2601, and commercial platforms.
4. **Lamanti-JN (Jetinno Platform) Driver**: Commercial HORECA telemetry for Jetinno JLTT, JL08, JL10, JL15, JL28, and JL500 vending series via binary framing and CRC16 validation.
5. **Phase 3 Hybrid Rust Architecture**: Single-window native `tao` + `wry` desktop shell (`spectra-shell`), embedded async Rust HTTP/1.1 gateway (`spectra-agent`), deterministic protocol codecs (`spectra-core` / `spectra-hal`), and native PyO3 C extension (`spectra_py.so` / `spectra_py.pyd`).

<p align="center">
  <img src="docs/images/spectra_architecture_phase3.svg" alt="SPECTRA Phase 3 Hybrid Rust + Python Architecture" width="100%">
</p>

---

## ✨ Features

- **Single-Window Native Desktop App (`spectra-shell`)**: Launches cleanly with zero stray console or duplicate windows, native window & taskbar branding, focused OS Save/Open file dialogs, and persistent maximized/window geometry (`window_state.json`). Includes `--pure-rust` standalone mode for lightweight inspection without spawning a Python sidecar.
- **9-Tab Diagnostic Workstation**:
  - `01 // OVERVIEW`: Machine health scorecard, beverage mix analytics, opt-in Local AI Triage & Customer Summary, and inline CSV/screenshot Offset Calibrator.
  - `02 // SENSORS & OSCILLOSCOPE`: Live P&ID Digital Twin schematic, `TB1`/`TB2` temperature strip-chart oscilloscope, hydraulic flow meter, and `AS:` NTC shunt self-test.
  - `03 // BEVERAGES`: Complete decoded preparation counters, `[2x]` flags, and share percentages.
  - `04 // MAINTENANCE`: Cleanings, descalings, CLARIS filter status, grinder cycles, and interval gauges.
  - `05 // ALERTS`: Clean separation between active physical lockouts and historical EEPROM fault latches (`RE:0028`, `0x01B0`–`0x01B6`).
  - `06 // IDENTITY`: 14-digit factory barcode/serial number, production date, article number, country code, and Display Sub-MCU (`EF518D` / `FlashDisplayZeta`) detection.
  - `07 // COMMAND INJECTOR`: Serialized read-safe UART command terminal.
  - `08 // MEM MAPPER`: Read-only 512/1024-word EEPROM register matrix, differential snapshot scope, raw sensor bitfield mapper, and inline model JSON updater.
  - `09 // FIRMWARE INSPECTOR`: Multi-format `ELF32`, `APK`, and `MCU .bin` analyzer, 3-tier localization auditor, and non-destructive lab patcher.
- **Default-OFF Local AI & Adaptive Engine (`CONFIG -> Local AI & Models`)**:
  - Consumes `0 MB RAM` / `0% CPU` until explicitly enabled.
  - Auto-installs a user-space portable AI runtime (`127.0.0.1:11434`) on demand with native OS TLS / Windows SChannel support (`tls_utils.py`) and pulls models such as `qwen2.5:0.5b`, `gemma3:1b`, `gemma2:2b`, or vision-capable `gemma3:4b`.
- **CSV / Screenshot EEPROM Offset Calibrator & 172-Machine Library (`machine_library.py`)**:
  - Upload a J.O.E. CSV, legacy Jura diagnostic CSV, or screenshot (`.png`/`.jpg`) to match counters (`16-bit BE` and `32-bit CDAB`) via Rust (`correlate_with_joe_ranked`) + Local AI.
  - Save instant local overrides (`eeprom_overrides.json` with strict precedence: `Local Override > Verified Model Spec > Built-in Profile`), export/import portable `.spectra-offset.json` patches, or contribute directly to `Pr0xyA-91/spectra-captures`.
- **Opt-In GitHub Account Sync (`CONFIG -> GitHub Connection`)**:
  - Connects via OAuth 2.0 Device Flow, Personal Access Token (`public_repo` + `gist`), or CLI environment tokens (`SPECTRA_GITHUB_TOKEN`, `GITHUB_TOKEN`, `gh auth token`).
- **Multi-Format Export & Hardware Simulation**: Export `.txt`, `.json`, or `.csv` via focused native OS Save As dialogs, and test safely offline with built-in Demo/Simulation profiles.

---

## 🚀 Quick Start

### 1. Launch Native Desktop Workstation (Recommended)
- **Linux**:
  ```bash
  ./run_ui.sh
  # (Or ./run.sh — launches native spectra-shell desktop app)
  ```
- **Windows**: Double-click **`spectra.exe`** (installed via **`spectra_setup.exe`**, or upgraded via **`spectra_update.exe`**).

### 2. Alternate Launch Modes
```bash
# Linux: Browser tab mode or Vite interactive hot-reload dev workspace
./run_ui.sh --browser
./run_ui.sh --dev

# Standalone Pure-Rust Shell (no Python sidecar)
cargo run -p spectra-shell -- --pure-rust

# Legacy GTK 3 Desktop GUI (Linux)
./run.sh --legacy-gtk
```

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

# List detected serial ports or supported machine models
./run.sh --cli --list-ports
./run.sh --cli --list-models
```

---

## 🏗️ Phase 3 Hybrid Rust Architecture

SPECTRA combines a multi-crate Rust workspace with Python domain orchestrators:

| Crate | Purpose | Core Responsibilities |
|---|---|---|
| [`crates/spectra-shell`](crates/spectra-shell) | Native Desktop Shell | `tao` + `wry` single-window WebView2 / WebKitGTK host, `.ico` RGBA window & taskbar icon loader, persistent `window_state.json`, Python sidecar supervisor & `--pure-rust` launcher. |
| [`crates/spectra-agent`](crates/spectra-agent) | Embedded HTTP Gateway & Daemon | Async Rust HTTP/1.1 control plane (`http_gateway.rs`) serving `web/dist/`, `/api/version`, `/api/app/heartbeat`, `/api/debug/*`, native `--pure-rust` routes (`/api/ports`, `/api/machines`, `/api/command`), and loopback sidecar reverse-proxy. |
| [`crates/spectra-core`](crates/spectra-core) | Protocol & Calibration Core | Zero-allocation byte-level state machine, 4:1 UART codec, `@`-cipher encoder/decoder, 0.1 °C NTC/date decoders, `correlate_with_joe_ranked`, machine matching, and differential EEPROM mapper. |
| [`crates/spectra-hal`](crates/spectra-hal) | Hardware Abstraction Layer | POSIX/Win32 serial driver, `tokio-serial` async UART transport, cross-platform port discovery, and Android ADB `/dev/ttyS*` bridge. |
| [`crates/spectra-py`](crates/spectra-py) | PyO3 Native Extension | Bridges deterministic Rust core parsers & codecs directly into Python (`spectra_py.so` on Linux, `spectra_py.pyd` on Windows). |

To verify and compile the Rust workspace and tests:
```bash
cargo check --workspace
cargo test --workspace
python3 -m unittest discover -s .
```

---

## 🔌 Hardware Connection Guide

> [!CAUTION]
> **Galvanic Isolation Required on Direct UART Connections**: Legacy coffee appliance boards often run capacitive/non-isolated Mains dropper power supplies, leaving serial `GND` live relative to Earth. Always use an optical transceiver (`JURA USB Scanner N 010`) or insert an **`ADuM3160` / `ADuM4160` USB isolator** between your computer and any 5V USB-to-UART adapter.

### Option A: Official JURA USB Scanner (N 010)
Connect the USB scanner to any USB port (`COMx` on Windows, `/dev/ttyUSB0` on Linux). Attach the optical head to the machine's front optical port.

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
1. Jura Pin 1 (`GND`) $\rightarrow$ Bus Pirate `GND`
2. Jura Pin 2 (`TX`) $\rightarrow$ Bus Pirate `MISO` (BP RX)
3. Jura Pin 3 (`RX`) $\rightarrow$ Bus Pirate `MOSI` (BP TX)
4. Set UART mode to 9600 8N1, macro `(3)` for transparent bridge.

---

## 🔒 Permissions on Linux

Serial adapters (`/dev/ttyUSB*`) belong to the `uucp` group on Arch Linux (or `dialout` on Debian/Ubuntu):
```bash
# Arch / Omarchy
sudo usermod -aG uucp "$USER"

# Ubuntu / Debian
sudo usermod -aG dialout "$USER"
```
*(Log out and log back in for group membership to take effect).*

---

## 📁 Repository Structure

```
.
├── Cargo.toml                  # Rust hybrid workspace manifest
├── crates/
│   ├── spectra-shell/          # Native WebView2 / WebKitGTK desktop shell
│   ├── spectra-agent/          # Embedded HTTP/1.1 gateway & WS broadcaster
│   ├── spectra-core/           # Protocol state machine, cipher & J.O.E. correlator
│   ├── spectra-hal/            # Serial & tokio async transport HAL
│   └── spectra-py/             # PyO3 native extension (spectra_py.so / .pyd)
├── drivers/                    # Unified multi-manufacturer driver suite
│   ├── base.py                 # Common appliance driver abstraction
│   ├── jura/                   # Jura optical & Smart Connect driver
│   ├── nivona/                 # Nivona CafeRomatica driver
│   ├── lamanti_kl/             # Lamanti Kalerm platform driver
│   └── lamanti_jn/             # Lamanti Jetinno HORECA driver
├── web/                        # 9-Tab React + Vite Workstation UI
│   ├── src/                    # Components (Workstation, ConfigModal, MemMapper, HMI)
│   └── dist/                   # Production compiled UI bundle
├── run.sh                      # Native desktop app & CLI launcher (Linux)
├── run_ui.sh                   # Desktop app, browser & Vite dev launcher (Linux)
├── SPECTRA.desktop             # Portable Linux desktop entry launcher
├── spectra_app.py              # Standalone desktop supervisor & window launcher
├── web_server.py               # Python domain backend API server (ThreadingHTTPServer)
├── cli.py                      # Command-line interface runner
├── stats_collector.py          # Telemetry orchestrator & report exporters
├── spectra_ai.py               # Default-OFF Local AI triage, summary & Vision OCR
├── machine_library.py          # Unified 172-machine catalog & offset patch resolver
├── profiles_db.py              # Machine profile database & local override store
├── profiles_data.json          # Built-in database of 172 machine profiles
├── hmi_inspector.py            # Universal ELF/APK/MCU firmware auditor & AI runtime installer
├── github_auth.py              # GitHub Device Flow, PAT & keyring/0600 credential manager
├── tls_utils.py                # Cross-platform TLS root cert & Windows SChannel resolver
├── memory_mapper.py            # Differential EEPROM memory mapper & logic scope
├── spectra_probe.py            # Field capture & J.O.E. auto-correlator
├── docs/                       # Operator manual, diagrams & protocol documentation
│   ├── USER_GUIDE.md           # Illustrated operator & technician guide
│   ├── images/                 # SVG architectural & workflow diagrams
│   ├── JURA_MEMORY_MAP.md      # Master EEPROM & telemetry register map
│   ├── FIELD_CAPTURE_GUIDE.md  # Field telemetry capture workflow
│   └── models/                 # Verified model-specific hardware specifications
├── CHANGELOG.md                # Release changelog (tracked by Build YYYYMMDD.HHMM)
├── DEPENDENCIES.md             # Runtime requirements & dependency reference
├── LICENSE                     # MIT License
└── README.md                   # Platform overview
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
