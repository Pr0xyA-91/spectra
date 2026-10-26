# W.R.A.T. & wrat-sniffer — Comprehensive Context & Session Notes for Agy
**Updated**: October 26, 2026 | **Current Status**: Production / Verified Working

> **PRIVACY NOTICE**: This file (`SESSION_NOTES.md`) and `GEMINI.md` are **strictly private** to `https://github.com/Pr0xyA-91/wrat-sniffer_dev.git` (`origin`). They must **NEVER** be pushed to the public repository (`https://github.com/Pr0xyA-91/wrat-sniffer.git`).

---

## 1. Multi-Device Onboarding & Setup for Agy

When cloning or resuming work on a new machine, the private repository `wrat-sniffer_dev.git` contains **3 independent branches** that correspond to the 3 editions of the project:

| Local Directory | Git Branch | Version | Edition Description | Allowed Remotes |
| :--- | :--- | :--- | :--- | :--- |
| `~/Projects/wrat-sniffer` | `main` | `v0.3.4` | Linux Jura-Only Edition (also source for sanitized `public-main`) | `origin` (`wrat-sniffer_dev`) & `public` (`wrat-sniffer` via `./publish_release.sh`) |
| `~/Projects/WRAT` | `multi-manufacturer` | `v0.3.4_mm` | Linux Multi-Manufacturer Suite (Jura, Nivona, Kalerm, Jetinno + Web UI) | `origin` (`wrat-sniffer_dev` **ONLY**) |
| `~/Projects/WRAT_win` | `windows` | `v0.1` | Windows Cross-Platform Multi-Manufacturer Suite (`.bat` launchers + `COM*` support) | `origin` (`wrat-sniffer_dev` **ONLY**) |

### Cloning on a New Device
```bash
mkdir -p ~/Projects && cd ~/Projects

# 1. Main Linux Jura-only edition:
git clone -b main https://github.com/Pr0xyA-91/wrat-sniffer_dev.git wrat-sniffer

# 2. Linux Multi-Manufacturer edition:
git clone -b multi-manufacturer https://github.com/Pr0xyA-91/wrat-sniffer_dev.git WRAT

# 3. Windows Cross-Platform edition:
git clone -b windows https://github.com/Pr0xyA-91/wrat-sniffer_dev.git WRAT_win
```

### Quick Verification Commands
```bash
# Run unit tests in wrat-sniffer (8/8 tests must pass):
cd ~/Projects/wrat-sniffer && python3 -m unittest discover -s .

# Run unit tests in WRAT / WRAT_win (16/16 tests must pass):
cd ~/Projects/WRAT && python3 -m unittest discover -s .

# Run live telemetry diagnostic against connected physical Jura machine:
python3 -c '
import serial_io, stats_collector
conn = serial_io.JuraSerialConnection("/dev/ttyUSB0")
res = stats_collector.query_live_sensors("/dev/ttyUSB0", conn=conn, fast_poll=False)
for sw in res["switches"]:
    print(f"{sw[\"id\"]}: {sw[\"badge\"]} - {sw[\"status\"]}")
print("Hardness:", res["telemetry"].get("water_hardness_dh"), "°dH | Temp:", res["telemetry"].get("heater_coffee_str"))
conn.close()
'
```

---

## 2. Connected Hardware & Physical Testbench
* **Model**: Jura IMPRESSA XJ5 Professional GII (`EF518M V02.20`)
* **Serial Port**: `/dev/ttyUSB0` (FTDI / CH340 diagnostic adapter, 9600 baud, 8N1)
* **Live Operating Conditions**:
  - Machine physically hot: Coffee Thermoblock ~98.0 °C to 101.5 °C (`parts[4]` in `HZ:`).
  - Water tank: Full (`parts[7][2] == '0'`, `parts[9][1] == '0'`).
  - Drip tray: Inserted (`parts[7][0] == '0'`, `parts[9][0] == '0'`).
  - Grounds container: Inserted and empty (`parts[7][1] == '0'`).
  - Configured Water Hardness (`RE:00C3`): `re:1E32` $\rightarrow$ `(0x1E32 >> 8) & 0xFF` = **30 °dH**.
  - Flowmeter constant: DigiMesa turbine = **2.366 pulses per ml** (~422 pulses / dl).
  - Machine operational state: **Ready to Brew** (`ready_ok = True`).

---

## 3. Project Architecture & Codebase Map

### A. `wrat-sniffer` (`~/Projects/wrat-sniffer` — `main` branch, `v0.3.4`)
* **Files**:
  - `serial_io.py`: 4-byte UART bit-banging encoder/decoder (`8ms` inter-bit, `16ms` inter-char pacing), optical loopback echo stripping, Smart Connect `@`-protocol cipher, and mock devices (`DEMO:S8`, `DEMO:E8`, `DEMO:Z10`, `DEMO:S8_SC`).
  - `jura_protocol.py`: EEPROM layout decoder, 16-bit/32-bit word extraction, alert bitmasks.
  - `profiles_db.py` & `profiles_data.json`: Database of 170+ Jura machine profiles (`EF518M`, `S8`, `E8`, `Z10`, `GIGA`, etc.).
  - `stats_collector.py`: High-level interrogation, `RT:`/`RE:` counter mapping, `HZ:`/`CS:`/`IC:` live telemetry parser, text/CSV report formatting.
  - `gui.py`: GTK3 dark-themed desktop application.
  - `cli.py`: Interactive/non-interactive CLI tool with `--export-txt`, `--export-csv`, `--export-json`.
  - `publish_release.sh`: Synchronizes `main` $\rightarrow$ `public-main`, strips `GEMINI.md` and `SESSION_NOTES.md`, scrubs `/home/<user>` paths from `.desktop` files, and pushes `public-main:main` to `public`.

### B. `WRAT` (`~/Projects/WRAT` — `multi-manufacturer` branch, `v0.3.4_mm`)
* Adds multi-vendor architecture on top of the core telemetry engine:
  - `wrat_engine.py`: Unified `WRATSession` dispatcher and report formatter (`format_text_summary`, `format_csv_summary`).
  - `drivers/base_driver.py`: Abstract driver interface & normalized diagnostic schema.
  - `drivers/jura_driver.py`: Wraps Jura ASCII & Smart Connect `@`-protocol.
  - `drivers/nivona_driver.py`: Eugster/Frismag ASCII/NICR protocol (`DEMO:NICR768`).
  - `drivers/kalerm_driver.py`: Lamanti-KL / Kalerm commercial `0xAA`/`0x55` framed binary protocol (`DEMO:X680C`).
  - `drivers/jetinno_driver.py`: Lamanti-JN / Jetinno Vending MDB/CC2 `0x02` STX framed protocol (`DEMO:JL300`).
  - `gui_web.py`: Zero-dependency responsive dark-mode HTTP Web Dashboard (`./run.sh --web`, `http://127.0.0.1:8080`) with live polling, brand filter, and `.txt`/`.csv`/`.json` report export.

### C. `WRAT_win` (`~/Projects/WRAT_win` — `windows` branch, `v0.1`)
* Cross-platform Windows adaptation of `WRAT`:
  - Windows `COM*` port auto-discovery via `serial.tools.list_ports.comports()` without POSIX `termios` dependencies.
  - Windows batch launchers: `install_windows.bat`, `run.bat` (auto-detects GTK3 or falls back to Web UI), `run_web.bat`, `run_cli.bat`, `run_demo.bat`.

---

## 4. Key Protocol Nuances & Hard-Won Knowledge

### 1. Separation of Live Readiness vs. Historical EEPROM Faults
* **Non-volatile EEPROM registers** (`RE:0028` last fault latch, `RE:01B4` lifetime flowmeter timeouts) store historical events that do **NOT** clear when the machine enters ready state.
* **RULE**: Never gate live operational readiness (`machine_ready`) on `RE:0028` or `RE:01B4`.
* Live operational readiness is determined strictly from real-time physical inputs:
  - Drip Tray inserted (`tray_ok`)
  - Water Tank present (`water_ok`)
  - Grounds Container not full (`not grounds_full`)
  - Coffee Thermoblock at brewing temperature ($\ge 80.0$ °C)
  - Appliance idle (`not is_busy`, `parts[0][0] == '0'`)
* When all 5 physical conditions are met, the appliance is **Ready to Brew / Nominal (READY)**.
* Historical faults remain displayed where they belong: in the **Hardware Diagnostics** tree view.

### 2. Periodic MCU Heartbeat Bit vs. Alarm Prompts
* In the Jura `HZ:` frame, `parts[7][3]` alternates between `0` and `1` every ~1 second (`000000` $\leftrightarrow$ `000100`).
* **RULE**: `parts[7][3]` is an internal MCU clock/timer tick, **NOT** an alarm or "Press Maintenance" indicator.
* Never apply a debounce or decay window to periodic oscillator bits.

### 3. Decoupling Auto-Poll from Static EEPROM Parameters
* Fast continuous polling (`fast_poll=True`, 1–2s intervals) queries **only dynamic volatile state** (`HZ:`), caching `_cached_ef` and `_cached_val_r28` on the connection. This reduces cycle latency to ~50ms and prevents serial buffer contention.
* Static settings (e.g. water hardness `RE:00C3`, filter configuration `RE:0029`) are queried **only during manual refresh** (`fast_poll=False`).
* In `fast_poll`, `water_hardness_dh` is omitted from the telemetry dictionary so the GUI never overwrites verified configuration values with default fallbacks.

### 4. DigiMesa Live Flow Rate Calculation
* Computed using flowmeter turbine pulse deltas between sequential polling samples:
  $$\text{Flow Rate (ml/s)} = \frac{\Delta P}{2.366 \times \Delta t}$$
* Accumulated cycle volume:
  $$\text{Volume (ml)} = \frac{P_{\text{cycle}}}{2.366}$$

---

## 5. Security & Privacy Guardrails
1. `GEMINI.md` and `SESSION_NOTES.md` contain internal project guidelines and must **NEVER** be pushed to public repositories (`wrat-sniffer.git`).
2. Only `wrat-sniffer` (`main` branch via `./publish_release.sh` $\rightarrow$ `public-main`) may ever be synced to the public `wrat-sniffer.git` repository. `WRAT` (`multi-manufacturer`) and `WRAT_win` (`windows`) are strictly private.
3. On any new device where `wrat-sniffer` is cloned and a `public` remote is added, ensure `.git/hooks/pre-push` is installed to block any push to `public` that is not `public-main` or that contains `GEMINI.md`, `SESSION_NOTES.md`, `drivers/`, `wrat_engine.py`, `gui_web.py`, `.bat`, or `/home/` paths.
4. Local versioned backups on the primary workstation are stored in `~/Projects/backup/` (`wrat-sniffer-v0.3.4.tar.gz`, `WRAT-v0.3.4_mm.tar.gz`, `WRAT_win-v0.1.tar.gz`).
