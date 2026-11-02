# SPECTRA Diagnostics Suite — Changelog

All notable changes and architectural milestones for SPECTRA are documented here.
In accordance with SPECTRA edition guidelines, releases are identified strictly by **Build Numbers** (`Build YYYYMMDD.HHMM`).

---

## [Build 20261102.1738] — 2026-11-02

### 🚀 Highlights & Major Capabilities

#### 1. Windows Native Standalone Suite, Offline Installer & Fast In-Place Updater
- **Offline Standalone Installer (`dist/spectra_setup_build20261102.1738.exe`)**:
  - Fully self-contained PE32+ native installer compiled via Zig + LLVM-RC.
  - Bundles embedded Python 3.12 64-bit runtime, pre-configured `pyserial`, React SPA assets, and profile definitions.
  - Installs to `%LOCALAPPDATA%\Programs\SPECTRA`, creates Start Menu and Desktop shortcuts with high-resolution vector-rendered icons, and registers in Windows *Add or Remove Programs* with clean uninstallation.
- **Fast In-Place Updater (`dist/spectra_update_build20261102.1738.exe`)**:
  - Ultra-lightweight (~885 KB) updater that updates Python logic, drivers, React frontend bundles, and device profiles in-place without re-downloading the Python runtime.
- **Zero-Dependency Launcher (`bin/spectra.exe`)**:
  - Standalone Win32 PE32+ executable that auto-locates the runtime, spins up the telemetry engine on a dynamically allocated port, and launches the default browser interface.

#### 2. Windows Serial & Web Server Stability Hardening
- **Resolved `ConnectionAbortedError [WinError 10053]`**:
  - Handled client socket aborts and resets across `_send_json`, `_serve_static`, and file responses in `web_server.py` and `gui_web.py`.
- **Eliminated 20 Hz Win32 `SetCommTimeouts` Driver Thrashing**:
  - Refactored `serial_io.py:read()` to cache applied timeouts, eliminating redundant `SetCommTimeouts` Win32 syscalls during tight 50ms polling iterations that previously caused USB UART buffer stalls.
- **Stateful Error Debouncing & Session Persistence**:
  - Added consecutive error tracking (`_consecutive_sensor_errors`) in `/api/sensors`. Transient single-packet serial glitches no longer tear down `_active_session` or close the COM port. Cached nominal telemetry is retained during transient jitter.
- **Frontend Polling Queue Guard**:
  - Added `inFlightPollRef` in `SpectraWorkspace.jsx` to drop overlapping auto-poll requests if a prior serial query is still awaiting hardware response, preventing socket pileup and client-side aborts.
  - Added `pollFailCountRef` to suppress spurious red warning banner flashes during transient network or serial retries.

#### 3. 3-Layer Rust / Tauri v2 / PyO3 Hybrid Architecture
- **`crates/spectra-hal`**:
  - Universal hardware abstraction layer supporting direct RS-232/UART and Android ADB `/dev/ttyS*` bridge streaming with strict path validation and POSIX baud configuration.
- **`crates/spectra-core`**:
  - High-performance, zero-allocation protocol decoders and state machines for Jura (Plain ASCII & `@`-cipher), Nivona, Lamanti-KL (Kalerm Modbus RTU), and Lamanti-JN (Jetinno custom binary frames).
  - Differential EEPROM mappers and J.O.E. auto-correlators.
- **`crates/spectra-agent`**:
  - Tauri v2 async IPC backend connecting native desktop surfaces to real-time hardware telemetry.
- **`crates/spectra-py`**:
  - PyO3 native C-extension (`spectra_py.so`) bridging high-speed Rust decoders to Python runtimes.

#### 4. Multi-Manufacturer Telemetry Engine & Legacy Jura SW Recovery
- **Unified Multi-Vendor Driver Support**:
  - Integrated drivers for Jura, Nivona (NICR series), Lamanti-KL / Kalerm (Modbus RTU), and Lamanti-JN / Jetinno (binary serial).
- **Optical Infrared Bean Hopper Sensor (`AS:`)**:
  - Dynamic reflection delta calculation ($\Delta = \text{ON\_ADC} - \text{OFF\_ADC}$) with configurable threshold ($115 \pm 5$) and hysteresis band ($110 \dots 120$ counts) for thermal drift compensation.
- **Physical Safety Invariants & Diagnostic Gating**:
  - Physical `machine_ready` gating based strictly on live `HZ:` physical sensors (Thermoblock $\ge 80^\circ\text{C}$, Drip Tray inserted, Water Tank full, Grounds container not full, appliance idle), decoupling readiness from historical non-volatile EEPROM fault latches (`RE:0028`, `RE:01B4`).
  - Added `CS:` and `CS$:` diagnostic checksum validation, loader version interrogation (`TL:` / `TL$:`), and Renesas RL78 EEPROM layout decoding for modern Jura commercial lines (WE8, XJ5, Z10).
- **Field Capture & Correlator Tool (`spectra_probe.py`)**:
  - Automated field diagnostic captures with J.O.E. CSV auto-correlation for rapid protocol reverse engineering.

#### 5. Build-Number-Only Branding Invariant
- Deprecated semantic version strings across all UI badges, CLI banners, Tauri configurations, and installer headers.
- Standardized metadata on build timestamp: `Build 20261102.1738`.

---
