# W.R.A.T. — WhiteRat Asynchronous Telemetry (`WRAT_win` Windows Edition Guidelines)

> **IMPORTANT FOR AGY (ANTIGRAVITY) ON ANY DEVICE**:
> Always read [`SESSION_NOTES.md`](./SESSION_NOTES.md) at the start of a session for complete hardware testbench details, driver architecture, protocol register mappings, and multi-device setup instructions.
> This branch (`windows`) and its `GEMINI.md` / `SESSION_NOTES.md` files are **strictly private** (`origin`: `wrat-sniffer_dev.git` only) and must **NEVER** be pushed to the public repository (`wrat-sniffer.git`).

## 1. Quick Reference & Entry Points
- **Entry Point (Windows)**: Run via `run.bat` (auto-detects GTK3 or falls back to Web Dashboard), `run_web.bat` (Web Dashboard on `http://127.0.0.1:8080`), `run_cli.bat` (CLI), or `run_demo.bat` (Offline Simulation).
- **Entry Point (Linux)**: Run via `./run.sh` (GTK3 GUI / `--web` / `--cli`).
- **Unit Tests**: Run `python3 -m unittest discover -s .` (16/16 tests must pass across `test_multi_manufacturer.py` and `test_thermal_and_dual_heaters.py`).
- **Self-Contained**: All scripts, multi-vendor drivers (`drivers/`), session engine (`wrat_engine.py`), database files (`profiles_data.json`), and Windows batch launchers reside inside this directory (`/home/a91/Projects/WRAT_win/` on primary workstation).

## 2. Repository & Branch Topology (3-Branch Architecture)
The private repository (`https://github.com/Pr0xyA-91/wrat-sniffer_dev.git`) hosts three active branches, each checked out in its own dedicated directory on the primary workstation:
1. **`windows` (`WRAT_win/`)** — Windows Cross-Platform Multi-Manufacturer Suite (`v0.1`).
   - Remote: `origin` (`wrat-sniffer_dev.git` ONLY — **NEVER** push to `public`).
2. **`multi-manufacturer` (`WRAT/`)** — Linux Multi-Manufacturer Suite (`v0.3.4_mm`).
   - Remote: `origin` (`wrat-sniffer_dev.git` ONLY — **NEVER** push to `public`).
3. **`main` (`wrat-sniffer/`)** — Linux Jura-only Edition (`v0.3.4`).
   - Remotes: `origin` (`wrat-sniffer_dev.git` — private) and `public` (`wrat-sniffer.git` — public distribution via sanitized `public-main` branch).

## 3. Supported Manufacturers & Drivers (`drivers/`)
- **`jura`** (`drivers/jura_driver.py`): Native TOP-tronic ASCII (`RT:`/`RE:`/`HZ:`/`CS:`/`IC:`) + Smart Connect `@`-protocol across 170+ Jura profiles.
- **`nivona`** (`drivers/nivona_driver.py`): Eugster/Frismag ASCII/NICR gateway protocol (`AN:01`, `TY:`, `RT:`, `RE:`, `HZ:`, `IC:`).
- **`lamanti-kl`** (`drivers/kalerm_driver.py`): Kalerm commercial Modbus/framed binary protocol (`0xAA`/`0x55` framing with XOR/CRC validation).
- **`lamanti-jn`** (`drivers/jetinno_driver.py`): Jetinno Vending MDB/CC2 IO protocol (`0x02` STX / `0x03` ETX framing).

## 4. Core Technical & Protocol Rules
- **Hardware Port**: Auto-detects `COM*` ports on Windows (`pyserial` `list_ports`) and `/dev/ttyUSB*`, `/dev/ttyACM*` on Linux (9600 baud, 8N1). Avoids POSIX-only `termios` calls on Windows.
- **Offline / Simulation Mode**: Built-in mock devices across all 4 supported vendors (`Jura S8/E8/Z10`, `Nivona NICR768`, `Lamanti-KL X680C`, `Lamanti-JN JL300`) allow full testing without hardware.
- **Live Readiness vs. Historical EEPROM Faults**:
  * **NEVER** gate live operational readiness (`machine_ready`) on non-volatile EEPROM registers (`RE:0028` last fault latch or `RE:01B4` lifetime flowmeter timeouts).
  * `machine_ready` depends strictly on 5 real-time physical inputs from `HZ:`: Drip Tray inserted, Water Tank full, Grounds Container not full, Coffee Thermoblock $\ge 80.0\,^\circ\text{C}$, and Appliance idle (`parts[0][0] == '0'`).
  * `parts[7][3]` in `HZ:` is a 1 Hz MCU heartbeat clock tick, **not** an alarm bit.
- **Fast Auto-Poll (`fast_poll=True`)**: Queries only dynamic `HZ:` telemetry (~50ms latency) and omits static EEPROM settings (`water_hardness_dh` from `RE:00C3`) so the UI never overwrites verified static settings with fallback defaults.
- **Legacy Preservation**: Never alter `/home/a91/Projects/Jura SW/` (the legacy 2016 suite).
