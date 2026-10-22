# Jura Modern Diagnostics & Statistics Suite

[![Version: 0.1-alpha](https://img.shields.io/badge/version-0.1--alpha-blue.svg)](https://github.com/Pr0xyA-91/diag_sw-alpha_J)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![GTK 3](https://img.shields.io/badge/GUI-GTK%203-green.svg)](https://www.gtk.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Platform: Linux](https://img.shields.io/badge/Platform-Linux-orange.svg)](https://kernel.org)

> [!NOTE]
> **Project Status: Alpha (v0.1-alpha)** — Active reverse-engineering and protocol integration. Supports live diagnostic reading from classic TOP-tronic and modern Smart Connect machines.

A native Linux diagnostic, telemetry, and statistics extraction suite for **Jura automatic coffee machines** (both modern Generation 7+ / Smart Connect machines and classic TOP-tronic machines) that are unsupported by legacy Windows diagnostic software.

---

## 🌟 Overview

The legacy Jura Service Software (from 2016 and earlier) was built around Delphi for 32-bit Windows and only supported older machines with hardcoded databases up to early 2016. Newer machines either trigger permission errors or refuse to yield statistical data.

This application runs natively on Linux (no Wine or Windows VM required) and implements a **Dual-Mode Interrogation Engine**:
1. **Plain-ASCII Optical Protocol**: Interrogates machines via the official **JURA USB Scanner N 010** or direct optical serial connections. Features optical loopback echo stripping, hardware pacing calibration (~16ms/char), and EEPROM memory block reading (`RT:0000`–`RT:0030`).
2. **Encrypted Smart Connect Protocol**: Speaks the modern native `@`-protocol with 4:1 wire carrier modulation (`0xDB` base byte), recovered nibble-permutation S-box cipher, and complete dongle challenge-response handshake (`@T0` $\rightarrow$ `@T1` $\rightarrow$ `@t2` $\rightarrow$ `@T3` $\rightarrow$ `@t3`).

---

## ✨ Features

- **Native Linux Desktop Application**: Fast, dark-mode GTK 3 desktop application with KPI summary cards, sortable beverage breakdown tables, maintenance cycle progress bars, active alert bitfield inspection, and a live communication console.
- **Full Headless CLI**: Command-line interface with colored output, progress bar, and multi-format export capabilities.
- **170+ Machine Profiles**: Unified database recognizing all generations of Jura machines:
  - **Modern Gen 7+**: E4, E6, E8, ENA 4/8, D4/D6, S8, J6/J8/J10, Z6/Z8/Z10, C3/C8, Commercial X4/X6/X8/X10, W4/W8, WE6/WE8, and GIGA series (5, 6, 10, W10, X3, X7, X8, X9).
  - **Classic / Professional**: IMPRESSA XJ5, XJ6, XJ9, XF50, XS90, F50, J9, C5, and WJ500.
- **Telemetry & Operational Metrics**:
  - **Beverage Counters**: Grand Total cups dispensed, single vs. double preparations, and per-specialty drink counts.
  - **Hygiene & Maintenance**: Cleaning cycles, descaling cycles, filter replacements, and rinse counts.
  - **Lifetime Telemetry**: Active grinder operating time (hours/minutes/seconds), total water throughput in Liters, descaling fluid consumed in Liters, cycles since last service intervention, and hardware appliance identification codes.
  - **System Alerts**: Decodes live alarm and status bitfields (`@TF:`).
- **Multi-Format Export**: Export clean diagnostic reports to formatted text (`.txt`), structured JSON (`.json`), or CSV (`.csv`).
- **Offline Hardware Simulation**: Built-in mock devices (Jura S8, E8, Z10) allow full testing and UI exploration without physical hardware attached.

---

## 🚀 Quick Start

### 1. Launch the Desktop GUI
```bash
./run.sh
```
*(Or launch **Jura Modern Diagnostics** from your desktop application launcher / menu).*

### 2. Run from the Command Line (CLI)
Read diagnostics from a connected machine:
```bash
./run.sh --cli -p /dev/ttyUSB0
```

Read in Demo / Simulation mode (no hardware required):
```bash
./run.sh --cli --demo --demo-model S8
```

Export report directly to a file:
```bash
./run.sh --cli -p /dev/ttyUSB0 -o diagnostic_report.txt
./run.sh --cli -p /dev/ttyUSB0 -o telemetry.json --format json
./run.sh --cli -p /dev/ttyUSB0 -o counters.csv --format csv
```

List detected serial ports:
```bash
./run.sh --cli --list-ports
```

List all 170+ supported machine models:
```bash
./run.sh --cli --list-models
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

1. **Wiring**:
   - Jura Pin 1 (`GND`) $\rightarrow$ Bus Pirate `GND`
   - Jura Pin 2 (`TX` machine) $\rightarrow$ Bus Pirate `MISO` (BP RX - 5V tolerant)
   - Jura Pin 3 (`RX` machine) $\rightarrow$ Bus Pirate `MOSI` (BP TX)
   - *(Optional for 5V pullup)*: Jura Pin 4 (`+5V`) $\rightarrow$ Bus Pirate `VPU` (Pullup voltage input).

2. **Configure Transparent UART Bridge Mode on Bus Pirate**:
   Connect via serial terminal at 115200 baud (e.g., `picocom -b 115200 /dev/ttyUSB0`):
   ```
   HiZ> m              (Select mode)
   3. UART             (Select UART)
   Set speed: 3 (9600 bps)
   Data bits and parity: 1 (8/N)
   Stop bits: 1 (1)
   Receive polarity: 1 (Idle 1)
   Output type: 1 (Normal 3.3V) or 2 (Open drain with VPU connected to 5V)
   UART> (3)           (Macro 3: Transparent UART bridge with flow control)
   Are you sure? y
   ```
   Exit your terminal (`Ctrl+A, Ctrl+X`). The Bus Pirate is now a transparent 9600-baud UART bridge. Run `./run.sh --cli -p /dev/ttyUSB0`.

---

## 🔒 Permissions on Linux

Serial adapters (`/dev/ttyUSB*`) belong to the `uucp` group on Arch Linux (or `dialout` on Debian/Ubuntu). Grant your user access:
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
├── run.sh                  # Application launcher script (CLI & GUI)
├── JuraModernDiag.desktop  # Desktop entry launcher
├── icon.png                # Application desktop icon
├── gui.py                  # GTK 3 desktop application
├── cli.py                  # Command-line interface runner
├── stats_collector.py      # Dual-mode diagnostics orchestrator & report exporters
├── jura_protocol.py        # 4:1 wire carrier encoder/decoder & cipher routines
├── serial_io.py            # Native POSIX termios serial driver & port discovery
├── profiles_db.py          # Machine profile resolver & database lookup engine
├── profiles_data.json      # Database of 170+ Jura machine profiles & memory maps
├── LICENSE                 # MIT License
└── README.md               # Documentation & hardware guide
```

---

## 📜 Credits & Acknowledgements

This project builds upon the shared knowledge, protocol analysis, and reverse-engineering contributions of the open-source coffee telemetry and home automation community:

- **CM-P ([jura-coffee-machine](https://github.com/CM-P/jura-coffee-machine))**: Foundational documentation and reverse-engineering of the Jura optical port, cleartext command structure (`TY:`, `RT:`, `RE:`, `AN:`, `FA:`), baud timing, and optical pinout mapping.
- **Otto Winter & the [ESPHome](https://esphome.io/) Project**: Research and implementation of embedded Jura UART communication and protocol timing.
- **c't Magazin / Heise & hn ("Kaffeemaschine gehackt")**: Pioneer research on Jura optical transceivers and serial protocol decoding.
- **tinaught ([Jura-Coffee-Machine-Home-Assistant](https://github.com/tinaught/Jura-Coffee-Machine-Home-Assistant)) & bpeoples**: Home Assistant integration, EEPROM word mapping, and beverage counter offsets.
- **Smart Connect Protocol Researchers**: Reverse-engineering of modern Jura bus communication, 4:1 wire carrier modulation (`0xDB` base byte), and dongle challenge-response handshake sequence.
- **Dangerous Prototypes**: Creators of the Bus Pirate hardware tool used for multi-protocol bus debugging.

---

## 📄 License

This project is licensed under the [MIT License](LICENSE).
