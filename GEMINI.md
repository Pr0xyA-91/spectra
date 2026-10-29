# SPECTRA — Universal Hardware Telemetry & Logic Board Diagnostics (`spectra` Main Edition Guidelines)

> **IMPORTANT FOR AGY (ANTIGRAVITY) ON ANY DEVICE**:
> Always read [`COWORKER_CONTEXT.md`](./COWORKER_CONTEXT.md) and [`SESSION_NOTES.md`](./SESSION_NOTES.md) at the start of a session for complete coworker handoff status, hardware testbench details, protocol register mappings, architectural decisions, and multi-device setup instructions.
> `COWORKER_CONTEXT.md`, `GEMINI.md` and `SESSION_NOTES.md` are **strictly private** (`origin`: `spectra_dev.git` only) and must **NEVER** be pushed to the public repository (`spectra.git`).

## 1. Quick Reference & Entry Points
- **Entry Point**: Run via `./run.sh` (GTK3 GUI) or `python3 cli.py` (CLI), or via `SPECTRA.desktop`.
- **Unit Tests**: Run `python3 -m unittest discover -s .` (10/10 tests must pass).
- **Self-Contained**: All scripts, database files (`profiles_data.json`), and tools for the main Linux Jura edition reside inside this directory (`/home/a91/Projects/spectra/` on primary workstation).

## 2. Repository & Branch Topology (3-Branch Architecture)
The private repository (`https://github.com/Pr0xyA-91/spectra_dev.git`) hosts three active branches, each checked out in its own dedicated directory on the primary workstation:
1. **`main` (`spectra/`)** — Linux Jura-only Edition (`v0.5.1`).
   - Remotes: `origin` (`spectra_dev.git` — private) and `public` (`spectra.git` — public distribution via sanitized `public-main` branch using `./publish_release.sh`).
2. **`multi-manufacturer` (`spectra-mm/`)** — Linux Multi-Manufacturer Suite (`v0.5.1_mm`: Jura, Nivona, Lamanti-KL/Kalerm, Lamanti-JN/Jetinno, plus Web UI `gui_web.py`).
   - Remote: `origin` (`spectra_dev.git` ONLY — **NEVER** push to `public`).
3. **`windows` (`spectra-win/`)** — Windows Cross-Platform Multi-Manufacturer Suite (`v0.5.1_win`: includes `.bat` launchers, `install_windows.ps1`, `COM*` auto-discovery, zero-dependency Web UI fallback).
   - Remote: `origin` (`spectra_dev.git` ONLY — **NEVER** push to `public`).

## 3. Core Technical & Protocol Rules
- **Hardware Port**: Auto-detects `/dev/ttyUSB*` and `/dev/ttyACM*` (9600 baud, 8N1).
- **Offline / Simulation Mode**: Built-in mock devices (`Jura S8`, `E8`, `Z10`, `S8 Smart Connect`) allow full testing without physical hardware.
- **Dual-Mode Interrogation Engine**:
  * **ASCII Optical/Service Port Protocol**: 4-byte UART carrier (`8ms` inter-bit, `16ms` inter-char pacing), optical loopback echo stripping, `RT:` / `RE:` EEPROM reads, and `HZ:` / `CS:` / `IC:` live sensor telemetry.
  * **Encrypted Smart Connect (`@`-Protocol)**: 4:1 wire carrier, `&`-framing, and recovered nibble cipher.
- **Live Readiness vs. Historical EEPROM Faults**:
  * **NEVER** gate live operational readiness (`machine_ready`) on non-volatile EEPROM registers (`RE:0028` last fault latch or `RE:01B4` lifetime flowmeter timeouts).
  * `machine_ready` depends strictly on 5 real-time physical inputs from `HZ:`: Drip Tray inserted, Water Tank full, Grounds Container not full, Coffee Thermoblock $\ge 80.0\,^\circ\text{C}$, and Appliance idle (`parts[0][0] == '0'`).
  * `parts[7][3]` in `HZ:` is a 1 Hz MCU heartbeat clock tick, **not** an alarm bit.
- **Fast Auto-Poll (`fast_poll=True`)**: Queries only dynamic `HZ:` telemetry (~50ms latency) and omits static EEPROM settings (`water_hardness_dh` from `RE:00C3`) so the UI never overwrites verified static settings with fallback defaults.
- **Optical Infrared Bean Hopper Sensor (`AS:`) & Firmware Lazy-Update**:
  * **Photodiode Reflection Delta**: Evaluates net ambient-subtracted pulsed IR reflection ($\\Delta = \\text{ON\\_ADC} - \\text{OFF\\_ADC}$).
    - **Covered / Beans Present**: $\\Delta \\le 89\\text{ counts}$ (live calibrated at $86$–$89$). Appliance clears lockout immediately and displays *"Ready"*.
    - **Uncovered / Empty Hopper**: $\\Delta \\ge 91\\text{ counts}$ (live calibrated at $91$–$96$).
  * **Firmware Lazy Update Invariant**: When beans run out, the appliance CPU defers updating the front LCD until a beverage is selected. Only when a brew button is pressed does the MCU check `AS:`, abort the grind, and prompt *"Fill beans"*. SPECTRA detects this proactively from `AS:` before the user attempts a brew.
  * **Schmitt Trigger Deadband**: The boundary between $89$ and $91$ counts ($90\\text{ counts}$) latches the previous state to eliminate 1-second boundary flickering.
  * **Never Override with Unverified HZ Bits**: Do not gate `beans_ok` solely on `HZ[0][3]`; `AS:` is the physical ground truth on optical-equipped models.
- **Legacy Preservation**: Never alter `/home/a91/Projects/Jura SW/` (the legacy 2016 suite).

## 4. Multi-Agent Teamwork & Pre-Commit Synchronization Protocol
- **MANDATORY PRE-COMMIT CHECK**: Since two AGY agents collaborate on this repository across two devices, **ALWAYS fetch and check what was done before committing**. Run `git fetch origin` and `git log -n 5 --oneline origin/<branch>` before starting work or committing.
- **Inspect Coworker Activity**: Always check [`COWORKER_CONTEXT.md`](./COWORKER_CONTEXT.md) and [`SESSION_NOTES.md`](./SESSION_NOTES.md) to understand what your coworker has recently implemented, tested, or changed.
- **Pull / Rebase First**: If remote commits are present, integrate them (`git pull --rebase origin <branch>`) and verify all test suites before committing new changes.
- **Mutual Handoff Logging**: After every work session, log your progress, attached hardware status, and next pending steps in [`COWORKER_CONTEXT.md`](./COWORKER_CONTEXT.md) so your coworker agent stays fully up to date.
- **Push Strictly to Private `origin` (`spectra_dev.git`)**: Never push directly to `public` (`spectra.git`). Releases are published exclusively via `./publish_release.sh`.
