# SPECTRA — Universal Hardware Telemetry & Logic Board Diagnostics (`spectra` Main Edition Guidelines)

> **IMPORTANT FOR AGY (ANTIGRAVITY) ON ANY DEVICE**:
> Always read [`COWORKER_CONTEXT.md`](./COWORKER_CONTEXT.md) and [`SESSION_NOTES.md`](./SESSION_NOTES.md) at the start of a session for complete coworker handoff status, hardware testbench details, protocol register mappings, architectural decisions, and multi-device setup instructions.
> `COWORKER_CONTEXT.md`, `GEMINI.md` and `SESSION_NOTES.md` are **strictly private** (`origin`: `spectra_dev.git` only) and must **NEVER** be pushed to the public repository (`spectra.git`).

## 1. Quick Reference & Entry Points
- **Entry Points**:
  - Desktop / CLI / Web: `./run.sh` (GTK3 GUI), `./run_ui.sh` (5-Paradigm Web UI + API server), `python3 cli.py` (CLI), `python3 spectra_probe.py` (Field Capture & J.O.E. Auto-Correlator).
  - 3-Layer Rust Hybrid Workspace: `crates/spectra-hal` (UART & Android ADB `/dev/ttyS*` HAL), `crates/spectra-core` (Jura protocol state machine, `@`-cipher, differential EEPROM mapper), `crates/spectra-agent` (Tauri v2 async IPC backend), and `crates/spectra-py` (PyO3 native `spectra_py.so` bridge).
- **Verification Gates (Both Must Pass Before Committing)**:
  - Python Test Suite: `python3 -m unittest discover -s .` (38/38 tests).
  - Rust Workspace: `cargo check --workspace` and `cargo test --workspace` (0 errors, 0 warnings).
- **Branding Invariant (Build Numbers Only)**:
  - Semantic version strings (`v0.5.1`, `v0.6.0-alpha`, etc.) are **deprecated and forbidden** across all UI badges, window titles, CLI banners, Tauri configs, and export headers.
  - Use **build numbers only** (`Build YYYYMMDD.HHMM` / `BUILD YYYYMMDD.HHMM`, managed via `__build__` in `version.py`). Whenever `web/src/` branding or components change, recompile `web/dist/` via `npm run build`.
- **Self-Contained**: All scripts, database files (`profiles_data.json`), and tools for the main Linux Jura edition reside inside this directory (`/home/a91/Projects/spectra/` on primary workstation).

## 2. Repository & Branch Topology (2-Branch Architecture)
The private repository (`https://github.com/Pr0xyA-91/spectra_dev.git`) hosts two active branches, each checked out in its own dedicated directory on the primary workstation:
1. **`main` (`spectra/`)** — Unified Linux Multi-Manufacturer Suite (Jura, Nivona, Lamanti-KL/Kalerm, Lamanti-JN/Jetinno) & 3-Layer Rust/Tauri/PyO3 Hybrid Workspace (Build-number versioned via `version.py`).
   - Remotes: `origin` (`spectra_dev.git` — private) and `public` (`spectra.git` — public distribution via sanitized `public-main` branch using `./publish_release.sh`).
   - *Note*: Former `multi-manufacturer` branch has been consolidated into `main` and deleted.
2. **`windows` (`spectra-win/`)** — Windows Cross-Platform Multi-Manufacturer Suite & 3-Layer Rust/Tauri/PyO3 Hybrid Workspace (includes native Win32 C PE32+ offline installer `dist/spectra_setup_build*.exe` and fast updater `dist/spectra_update_build*.exe` compiled via Zig + LLVM-RC, standalone launcher `bin/spectra.exe`, `COM*` auto-discovery, zero-dependency Web UI fallback).
   - Remote: `origin` (`spectra_dev.git` ONLY — **NEVER** push to `public`).

## 3. Core Technical & Protocol Rules
- **Hardware Port**: Auto-detects `/dev/ttyUSB*` and `/dev/ttyACM*` (9600 baud, 8N1).
- **Offline / Simulation Mode**: Built-in mock devices (`Jura S8`, `E8`, `Z10`, `S8 Smart Connect`) allow full testing without physical hardware.
- **Dual-Mode Interrogation Engine**:
  * **ASCII Optical/Service Port Protocol**: 4-byte UART carrier (`8ms` inter-bit, `16ms` inter-char pacing), optical loopback echo stripping, `RT:` / `RE:` EEPROM reads, and `HZ:` / `CS:` / `IC:` live sensor telemetry.
  * **Encrypted Smart Connect (`@`-Protocol)**: 4:1 wire carrier, `&`-framing, and recovered nibble cipher.
- **Serial Bus Concurrency & Machine Power Safety**:
  * **Never Query Hardware Concurrently**: Multiple processes opening `/dev/ttyUSB*` simultaneously cause ASCII character interleaving on the TX line. Interleaved commands can accidentally produce `AN:\r\n` (Jura standby toggle command), unexpectedly powering off the machine.
  * **Exclusive File Locking**: Always acquire an exclusive non-blocking lock (`fcntl.flock(fd, LOCK_EX | LOCK_NB)`) before issuing serial commands on hardware ports. Background scripts must release the port or fail gracefully if the GUI is active.
- **Live Readiness vs. Historical EEPROM Faults**:
  * **NEVER** gate live operational readiness (`machine_ready`) on non-volatile EEPROM registers (`RE:0028` last fault latch or `RE:01B4` lifetime flowmeter timeouts).
  * `machine_ready` depends strictly on 5 real-time physical inputs from `HZ:`: Drip Tray inserted, Water Tank full, Grounds Container not full, Coffee Thermoblock $\ge 80.0\,^\circ\text{C}$, and Appliance idle (`parts[0][0] == '0'`).
  * `parts[7][3]` in `HZ:` is a 1 Hz MCU heartbeat clock tick, **not** an alarm bit.
- **Fast Auto-Poll (`fast_poll=True`)**: Queries only dynamic `HZ:` telemetry (~50ms latency) and omits static EEPROM settings (`water_hardness_dh` from `RE:00C3`) so the UI never overwrites verified static settings with fallback defaults.
- **Optical Infrared Bean Hopper Sensor (`AS:`) & Thermal Drift Invariant**:
  * **Photodiode Reflection Delta & Gain**: Fixed optical/circuit gain $\frac{\text{ON}}{\text{OFF}} \approx 1.060 \pm 0.001$. Net reflection delta $\Delta = \text{ON\_ADC} - \text{OFF\_ADC}$ drifts from $85$ counts (cold) up to $105$ counts at operating temperature ($96^\circ\text{C}$).
  * **Nominal Calibration Threshold ($115 \pm 5$ counts)**:
    - **Covered / Beans Present**: $\Delta \le 110\text{ counts}$ (nominal operating band $85 \dots 105$). UI reports solid green *"Beans OK (Hopper Charged)"*.
    - **Uncovered / Empty Hopper**: $\Delta \ge 120\text{ counts}$ (bare funnel reflection). UI reports *"Fill Beans"*.
    - **Hysteresis Band**: $110 < \Delta < 120$ counts retains previous latch state to eliminate thermal fluttering.
  * **Asymmetric Latching State Architecture**:
    - **Active Recovery**: When *"Fill Beans"* is active on the physical machine, the MCU actively monitors the sensor; covering it or adding beans clears the warning immediately to *"Ready"*.
    - **Lazy Brew-Time Verification**: When *"Ready"*, the MCU does not instantly trigger *"Fill Beans"* at idle if uncovered (preventing false trips from bean tumbling or opening the hopper lid). Verification occurs during active grinding and puck compression.
  * **Never Override with Unverified HZ Bits**: Do not gate `beans_ok` on `HZ[0][3]` (grinder triac) or `parts[8]` (puck thickness); `AS:` is physical ground truth on optical-equipped models.
- **Windows Standalone Executable (`spectra.exe`) Architecture**:
  * **Zero Script Dependency**: Windows default execution policies restrict `.ps1` and environment PATH issues break `.bat` launchers. The primary Windows distribution target is a single-file standalone executable (`dist\spectra.exe`) generated via PyInstaller (`spectra.spec`).
  * **Dual CLI / Web UI Entrypoint**: Double-clicking `spectra.exe` with no flags automatically spins up `gui_web.py` and opens `http://127.0.0.1:8080`. Passing flags (e.g. `--port COM3`, `--demo`) runs CLI diagnostic routines.
  * **Asset Path Resolution (`sys._MEIPASS`)**: All resources (`profiles_data.json`, `spectra_logo.svg`, `icon.ico`) must use `sys._MEIPASS` when frozen, falling back to executable directory or `__file__`.
- **Legacy Preservation**: Never alter `/home/a91/Projects/Jura SW/` (the legacy 2016 suite).

## 4. Multi-Agent Teamwork & Pre-Commit Synchronization Protocol
- **MANDATORY PRE-COMMIT CHECK**: Since two AGY agents collaborate on this repository across two devices, **ALWAYS fetch and check what was done before committing**. Run `git fetch origin` and `git log -n 5 --oneline origin/<branch>` before starting work or committing.
- **Inspect Coworker Activity**: Always check [`COWORKER_CONTEXT.md`](./COWORKER_CONTEXT.md) and [`SESSION_NOTES.md`](./SESSION_NOTES.md) to understand what your coworker has recently implemented, tested, or changed.
- **Pull / Rebase First**: If remote commits are present, integrate them (`git pull --rebase origin <branch>`) and verify all test suites before committing new changes.
- **Mutual Handoff Logging**: After every work session, log your progress, attached hardware status, and next pending steps in [`COWORKER_CONTEXT.md`](./COWORKER_CONTEXT.md) so your coworker agent stays fully up to date.
- **Push Strictly to Private `origin` (`spectra_dev.git`)**: Never push directly to `public` (`spectra.git`). Releases are published exclusively via `./publish_release.sh`.
- **GitHub Workflow File Scope Constraint**: Avoid creating or modifying files in `.github/workflows/` unless the active Git credentials/token explicitly include the `workflow` OAuth scope. Pushes containing workflow changes will be rejected by GitHub when using standard repo-scoped tokens.
