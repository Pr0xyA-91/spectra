# SPECTRA Diagnostics Suite — Changelog

All notable changes and architectural milestones for SPECTRA are documented here.
In accordance with SPECTRA edition guidelines, releases are identified strictly by **Build Numbers** (`Build YYYYMMDD.HHMM`).

---

## [Build 20261104.1418] — 2026-11-04

### 🚀 Highlights & Digital Twin Thermoblock Range Fix

#### 1. Digital Twin Thermoblock Readiness Range Normalization
- **Thermoblock Status Evaluator Fix (`DigitalTwinSchematic.jsx`)**:
  - Eliminated the artificial `tb1Temp <= 100` ceiling that caused nominal operating temperatures (e.g. `100.5 °C`) to falsely evaluate as `'HEATING'` in Box 2 (`OPERATING STATUS`).
  - Standardized `tb1` status to `tb1Temp >= 80 && tb1Temp <= 115 ? 'READY' : (tb1Temp > 115 ? 'OVERHEAT' : 'HEATING')`, matching Jura operating specifications (nominal brew ready threshold $\ge 80.0^\circ\text{C}$).
- **Hardware Interrogation Sub-Bus Proof**:
  - Verified live Display MCU `EF518D V02.04` responses across 28 commands: `RT$:00..F0` (`rt$:0000...00`), `RE$:00..0F` (`re$:0000`), confirming `TP$:1..4` and `T1$:..T3$:` are Zeta-only extensions not implemented on commercial `EF518D`.

---

## [Build 20261104.1350] — 2026-11-04

### 🚀 Highlights & Display Sub-Bus Interrogation

#### 1. Exhaustive Live Interrogation of Display Sub-Bus (`EF518D V02.04`)
- **Direct Serial Probing on Active Physical Machine in "Fill Beans"**:
  - `CS$:`: Consistently returned `cs$:1418` across multiple samples, completely invariant between Ready and Fill Beans states (firmware checksum invariant).
  - `RE$:0000..0029` and `RT$:0000..0020`: Returned all zeroes on Display MCU memory space.
  - `IC$:`, `HZ$:`, `AS$:`: Unsupported on `EF518D V02.04` (`[NO_REPLY]`).
  - Binary inspection of Jura Service Suite `P518Ani.exe`: confirmed `TS$:4,02` string presence and zero hidden bean queries to the display sub-bus.

#### 2. UI Microswitch & Digital Twin Display Fix
- **Bean Hopper Tile Status Resolution (`SpectraWorkspace.jsx`)**:
  - Dynamically extracts `beansSw` from `liveData?.switches`.
  - Tile 7 now prominently displays `'LOCAL (EF518D)'` badge and subtitle `"Monitored Locally by Display MCU (EF518D)"` when connected to commercial dual-MCU hardware, eliminating hardcoded `'Hopper Charged'`.
- **Digital Twin Schematic Integration (`DigitalTwinSchematic.jsx`)**:
  - Schematics `beans` node dynamically reflects `beansSw?.details` and hardware provenance (`Front Display MCU EF518D Local Phototransistor`).

---

## [Build 20261104.1305] — 2026-11-04

### 🚀 Highlights & Complete Physical Elimination Ledger

#### 1. Definitive 512-Word EEPROM Diff & Architecture Proof
- **Complete Elimination Ledger**:
  - Captured exhaustive 512-word active EEPROM block scan (`RT:0000..01F0`) and live telemetry (`HZ:`, `CS:`, `CS$:`, `IC:`, `AS:`) on live physical Jura IMPRESSA XJ5 (`EF518M V02.20`, Display `EF518D V02.04`):
    * Only 6 drink/grinder counters (`0001`, `000A`, `000E`, `000F`, `0015`, `0020`) and rolling checksum (`00CE`) incremented.
    * `CS[39:43] == 3FF0`, `CS$ == 1418`, `HZ[0][3] == '1'`, and `AS == 1.060 ratio` remained completely unchanged when the appliance transitioned from "Ready" to "Fill Beans" on the front display upon pressing a coffee product.
    * Conclusive proof: on commercial `EF518` architecture, the optical bean barrier circuit is strictly local to the `EF518D` front display MCU and is not exposed over serial to the main board MCU `EF518M` or to Jura's official Service Suite (`P518Ani.exe` tests `#669/#670/#738/#739` require human visual check of the LCD).
- **Non-Intrusive Readiness Gating (`stats_collector.py`)**:
  - Gated `machine_ready` strictly on the 5 physical inputs (Tray, Tank, Grounds, Coffee Thermoblock $\ge 80.0^\circ\text{C}$, Appliance Idle).
  - Evaluates `beans_ok` via universal physical puck-compression thickness fallback (`not (0 < cake_thickness_ticks <= 14)`), preventing any false "Fill Beans" software lockouts.
  - Switch `bean_hopper` clearly notes: `"Monitored Locally by Display MCU (EF518D)"`.
  - Preserved ultra-fast ~50ms auto-polling (`fast_poll=True`, `HZ:` only).
  - Maintained `AS:` Coffee Heater NTC $+6.0\%$ Shunt Self-Test (`heater_ntc_diagnostic_sensor`).

---

## [Build 20261103.1925] — 2026-11-03

### 🚀 Highlights & Architectural Discovery

#### 1. Display MCU Sub-Bus Static Disassembly & Direct LCD Readout
- **Detailed Reverse-Engineering of Display MCU Commands**:
  - Fully disassembled `#RB$` (`0x1652`), `TP$` (`0x175C`), `TS$` (`0x1578`), `ST$` (`0x15C2`), `T1$` (`0x142A`), `T2$` (`0x148A`), `T3$` (`0x14FA`), and `TY$` (`0x126E`) from `DE_EN_FlashDisplayZetaV4.0.4.LoaderV3.0.TextsV1.1.4.Common.bin` (`EF518D`, Renesas R8C).
  - `#RB$:XXXX\r\n`: arbitrary 16-bit memory / SFR port read over the serial sub-bus, responding `rb:%04X\r\n`.
  - `TP$:X\r\n`: line parameter query, reading the active message rendered on LCD line `X` (`1..4`) from parameter buffer `0xE88C`, responding `tp:%s\r\n`.
  - `TS$:L,NN\r\n`: Text Set command writing string `NN` to display line `L`, responding `ok:\r\n`.
  - `ST$:\r\n`: display communication status test, responding `ok:\r\n`.
  - `T1$:`, `T2$:`, `T3$:`: live telemetry query handlers responding `t1:%02X\r\n`, `t2:%02X\r\n`, `t3:%02X\r\n`.
- **Top-Tronic XML Script Deobfuscation (`Serv_EF518_V2.t3s`)**:
  - Solved the Top-Tronic line rotation cipher (`shift = ord(first_char) - 32`) on UTF-16 XML service definitions.
  - Verified `00B3` bit `0x0040` (`Powder_Settings`) controls the pre-ground bypass chute lock (`STATTEXT.txt` #2164/#2163).
  - Mapped functional test #135 (`0x87DD` in `TextsV1.1.4`): `'F%02u beantest'` / `'F%02u Beantest'`.
- **Hardware Telemetry Resolution Strategy**:
  - On `EF518`, the empty bean barrier blocks button presses at the front display before the main board grinder ever runs, explaining why puck thickness fallback alone cannot detect "Fill Beans" when idle.
  - Morning hardware reconnection plan: query `TP$:4\r\n` for live LCD messages ("BEANS" / "BOHNEN" / "ZRNA") and probe `#RB$:00E0` - `#RB$:00E5` for the direct SFR phototransistor input pin.

---

## [Build 20261103.1806] — 2026-11-03

### 🚀 Highlights & Architectural Clarifications

#### 1. Removal of Volatile Serial Bean Lockouts & UI Cleanup
- **Reverted Per-Session Brew Flag Lockouts**:
  - Live hardware testing established that `HZ[0][3]`, `HZ[3]` (flow pulses), `HZ[8]` (puck ticks), and `CS[39:43]` (`3FF0`) are per-power-session volatile states on Renesas MCU architectures that reset to `0` / empty on power-off and only activate after brewing an initial coffee.
  - Removed forced serial lockouts (`CS[39:43]`, `RE:0029`, `HZ[0][3]`) from `stats_collector.py` and `crates/spectra-core/src/jura.rs` to prevent false "Fill Beans" appliance readiness deadlocks.
  - Standardized bean hopper charge evaluation on physical puck-compression thickness fallback (`0 < cake_thickness_ticks <= 14`).
  - Preserved ultra-fast auto-polling (`fast_poll=True`) querying only dynamic `HZ:` frames (~50ms latency) without serial bus contention.
  - Removed obsolete `optical_bean_sensor` false "EMPTY" card from UI sensor list, keeping the verified `heater_ntc_diagnostic_sensor` (`AS:` Coffee Heater NTC $+6.0\%$ Shunt Self-Test).

#### 2. Display Sub-Bus (`$:`) Protocol & Renesas R8C Reverse-Engineering
- **Display MCU Command Jump Table**:
  - Reverse-engineered front display microcontroller firmware `DE_EN_FlashDisplayZetaV4.0.4.LoaderV3.0.TextsV1.1.4.Common.bin` (`EF518D`, Renesas R8C) at offset `0x002634`.
  - Discovered full `$:` diagnostic command family: `TY$:` (`0x126E`), `TL$:` (`tl$:R8C Loader V2.0`), `TS$:` (`0x1578`), `ST$:` (`0x15C2`), `CP$:` (`0x15F8`), `TP$:` (`0x175C`), `#PO$:` (`0x1726`), `#RB$:` (`0x1652`).
  - Proved `TS$:` queries live display line text (`TS$:4,01` -> `ts$:   JAZYK`, `TS$:4,02` -> `ts$:  CESKY`, `TS$:4,03` -> `ts$:PRIPRAVEN`).
- **Physical Bean Hopper Circuit Architecture on `EF518`**:
  - Proved that on `EF518` (IMPRESSA XJ5/XJ9), the IR bean barrier phototransistor connects directly to the front display board (`EF518D`, R8C) and is not exposed over serial to the main board (`EF518M`).
  - Confirmed via `P518Ani.exe` strings `#669/#670/#738/#739` and `ALPHA.tcr` / `EF528.tcr` that even official Jura Service Suite factory test mode does not read an electronic hopper status byte over UART, but relies on an operator visual test ("BEANS FULL" appears on screen, technician clicks Continue).
  - Decoded `STATTEXT.txt` strings `2162/2163/2164` (`00B3` bit `0x0040`), confirming it controls the pre-ground bypass powder chute release/lock, not the optical hopper.

---

## [Build 20261103.1330] — 2026-11-03

### 🚀 Highlights & Bug Fixes

#### 1. Ground Truth Bean Status Latch (`RE:0029`) & Real-Time Auto-Poll Gating
- **Resolved "Fill Beans" vs. "Charged" Display Discrepancy**:
  - Addressed customer issue where Jura IMPRESSA XJ5 (`EF518M`) physical display reported *"Fill Beans"* (*"Doplňte kávová zrna"*), but SPECTRA Web UI still reported *"Charged"*.
  - **Root Cause**: On Renesas MCU microcode, `HZ:` frame bit `parts[0][3]` does not immediately clear to `'0'` at appliance idle when beans run low; it remained `'1'` (`hz:010101100000`). Because the Web UI polls with `fast_poll=True`, non-volatile register `RE:0029` was omitted from queries, and `beans_ok` was wrongly computed as `True` from `parts[0][3] == '1'`.
- **Periodic Fast Polling of `RE:0029`**:
  - In `stats_collector.py`, added ~1.0s periodic polling of `RE:0029` during `fast_poll` on commercial models (`EF518M` XJ5, GIGA, or where `_as_supported` is True).
  - Evaluated `RE:0029` bit `0x0040` (`0x004C` = Charged, `0x000C` = Empty) as the definitive ground truth latch. When bit `0x0040` is cleared, `beans_ok` is immediately evaluated as `False`, `machine_ready` transitions to `False` (*"Not Ready (Fill Beans)"*), and the Web UI displays *"Fill Beans"* / *"EMPTY"*.
- **Comprehensive Test Coverage**:
  - Added test case `mock_xj5_empty_r29` in `test_thermal_and_dual_heaters.py` verifying that when `HZ[0][3]` is `'1'` but `RE:0029` is `0x000C`, `beans_ok` is `False` and `machine_ready` is blocked.
  - Verified against live physical hardware on `/dev/ttyUSB0` via `/api/sensors` fast-poll endpoint.

---

## [Build 20261103.1225] — 2026-11-03

### 🚀 Highlights & Major Capabilities

#### 1. Hardware-Verified IMPRESSA XJ5 Bean Hopper State & Readiness Architecture
- **Direct Physical State Detection via `HZ` Telemetry**:
  - Live bean hopper level on commercial optical-equipped Jura lines (`EF518M` XJ5, GIGA) is driven directly by bit 3 of the `HZ:` status word (`parts[0][3] == '1'` -> Beans OK / Charged; `parts[0][3] == '0'` -> Fill Beans / Hopper Empty).
  - Physical machine readiness (`machine_ready`) is strictly gated on `beans_ok`: when `parts[0][3] == '0'`, the UI immediately reports **"Fill Beans"** and blocks readiness.
  - On standard domestic lines (`S8`, `E8`, `A1`, `D4`), the proven puck-compression thickness ($\le 14$ ticks) and `@TF:` alert fallback logic is cleanly preserved.
- **Non-Volatile Confirmation via `RE:0029`**:
  - Parsed non-volatile register `RE:0029` bit `0x0040` (`0x004C` = Charged, `0x000C` = Empty) on full interrogation polls as non-volatile EEPROM confirmation of the bean charge latch.
  - Complete `RE:0029` bitmask documented: `0x0001` External Filter active, `0x0010` CLARIS Filter active, `0x0020` Grinder calibration offset, `0x0040` Bean hopper charged latch, `0x0480` Factory hydraulic fill flag, `0x1000` First-use commissioning flag.

#### 2. Reverse-Engineering of Jura Service Suite (`P518Ani.exe`) & Reclassification of `AS:`
- **Disassembly of Check Sensor (`VA 0x004E6E28`)**:
  - Reverse-engineered Delphi routine in `P518Ani.exe` querying `AS:` (`as:VREF,OFF,0000,VREF,ON,0001`).
  - Proved that `AS:` does **not** query an optical bean hopper sensor, but is the **Coffee Heater NTC Diagnostic Sensor $+6.0\%$ Shunt Self-Test**.
  - Correlated with `Endtest.txt` String ID 251 (`0xFB`): `"-Sensor Kaffee-Heizung meldet falsche Werte !"` / `"-Coffee heater sensor notifies false values !"`.
  - Valid window verified: `180 < off_adc < 17000`, with nominal $+6.0\%$ internal Renesas MCU calibration shunt ratio $\text{ON}/\text{OFF} \approx 1.060 \pm 0.010$.
  - Reclassified `AS:` telemetry across Python backend, Rust `crates/spectra-core` (`OpticalSensorReading` with `shunt_ratio` and `is_ntc_self_test_valid`), and Web UI (`SpectraWorkspace.jsx`, `DigitalTwinSchematic.jsx`, `MemMapperTab.jsx`), while preserving backward-compatible aliases.

#### 3. Diagnostic Commands Discovery (`FA:01` & `RR:`)
- **`FA:01` Hardware Fault Latch Reset**:
  - Probed Jura `FA:` command table entry (`VA 0x004D5180`).
  - Discovered that `FA:01` performs an active diagnostic fault reset (`Fehlerspeicher löschen`), clearing `RE:0028` non-volatile error latch and transitioning the machine safely to standby.
- **RAM Interrogation (`RR:`)**:
  - Probed `RR:` (Read RAM, index 3). Hardware probing confirmed Renesas microcode on EF518M restricts direct RAM dumps via `RR:`, directing volatile telemetry queries through `HZ:`, `CS:`, and `RT:` blocks.

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
