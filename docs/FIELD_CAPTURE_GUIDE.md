# SPECTRA Field Telemetry Capture & Remote Archetype Probe Guide

This guide explains how remote field technicians and colleagues can use `spectra_probe.py` to capture complete diagnostic telemetry and EEPROM dumps from Jura machines encountered in the wild.

When an unknown or misbehaving machine is found, this tool allows remote colleagues to capture everything the engineering team needs to add full support and verify numerical parity **offline without requiring the physical machine**.

---

## 1. Prerequisites
- A Jura diagnostic USB-serial cable connected to the machine's service port and laptop (`/dev/ttyUSB0` on Linux, `COMx` on Windows).
- Python 3.8+ installed.
- (Optional but Recommended) An official **JURA Operating Experience (J.O.E.)** app export `.csv` file from an iOS or Android device connected to the machine via Smart Connect / Bluetooth.

> [!IMPORTANT]
> If the main SPECTRA GUI application or Web Server is currently running, close it before running `spectra_probe.py` so the serial port lock is released.

---

## 2. Quick Start

### A. Interactive Mode (Simplest for Technicians)
Simply open a terminal in the SPECTRA directory and run:

```bash
# Linux / macOS
./spectra_probe.py

# Windows
python spectra_probe.py
```

The probe will:
1. Scan for connected serial ports and prompt you to choose one (e.g. `1`).
2. Check if a J.O.E. `.csv` file is available in your Downloads folder or current directory (or ask for an optional file path).
3. Safely sweep the machine's EEPROM and query all hardware gateways.
4. Auto-correlate ground-truth counts with the raw memory cells.
5. Save a `.json` dump bundle and human-readable `.txt` report.

---

### B. Automated / Scripted CLI Mode

```bash
# With a ground-truth J.O.E. CSV export:
python3 spectra_probe.py --port /dev/ttyUSB0 --joe /home/a91/Downloads/WE8.csv

# On Windows:
python spectra_probe.py --port COM3 --joe C:\Users\Tech\Downloads\WE8.csv

# Without J.O.E. export (pure hardware dump):
python3 spectra_probe.py --port /dev/ttyUSB0

# Custom output prefix:
python3 spectra_probe.py --port /dev/ttyUSB0 --out customer_we8_office
```

---

## 3. What the Tool Generates

After the sweep completes (~15–30 seconds), two files are generated:

1. **`spectra_capture_<MODEL>_<TIMESTAMP>.json`**:
   - Complete machine snapshot containing:
     - All hardware bus gateway responses (`TY:`, `TL:`, `TY$:`, `TL$:`, `IC:`, `CS$:`, `HZ:`, `AS:`).
     - Full 512-word or 1024-word EEPROM array (all addresses in hex and decimal).
     - Decoded serial number, appliance number, production date, and factory article number.
     - Auto-generated Python `MockJuraMachine` simulation seed code.
     - J.O.E. correlation map mapping every beverage, cleaning cycle, and life percentage to its exact EEPROM word address.

2. **`spectra_capture_<MODEL>_<TIMESTAMP>.txt`**:
   - Human-readable summary for technicians and service logs showing matched beverage registers, maintenance cycles, and non-zero register tables.

---

## 4. What Remote Colleagues Should Send

Simply email, attach, or upload the **`.json`** bundle file to the engineering team.

With this file, the engineering team can:
1. Replay the machine's exact memory in SPECTRA's offline simulation engine.
2. Verify all beverage and maintenance registers.
3. Add the model specification to `docs/models/` and update `stats_collector.py`.
4. Deploy the update with 100% confidence without ever needing physical access to the machine.

---

## 5. Safety Guarantee
`spectra_probe.py` is strictly **read-only**:
- Only issues safe read queries: `TY:`, `TL:`, `TY$:`, `TL$:`, `IC:`, `CS$:`, `HZ:`, `AS:`, `RT:`, `RE:`.
- **NEVER** issues destructive write commands (`WE:`, `FA:`, `DA:`, `@tw:` etc.).
- Safe to run on customer and warranty machines.
