# SPECTRA — Comprehensive Context & Session Notes for Agy
**Updated**: October 26, 2026 | **Current Status**: Production / Verified Working (v0.5.1)

> **PRIVACY NOTICE**: This file (`SESSION_NOTES.md`) and `GEMINI.md` are **strictly private** to `https://github.com/Pr0xyA-91/spectra_dev.git` (`origin`). They must **NEVER** be pushed to the public repository (`https://github.com/Pr0xyA-91/spectra.git`).

---

## 1. Multi-Device Onboarding & Setup for Agy

When cloning or resuming work on a new machine, the private repository `spectra_dev.git` contains **3 independent branches** that correspond to the 3 editions of the project:

| Local Directory | Git Branch | Version | Edition Description | Allowed Remotes |
| :--- | :--- | :--- | :--- | :--- |
| `~/Projects/spectra` | `main` | `v0.5.1` | Linux Jura-Only Edition (also source for sanitized `public-main`) | `origin` (`spectra_dev`) & `public` (`spectra` via `./publish_release.sh`) |
| `~/Projects/spectra-mm` | `multi-manufacturer` | `v0.5.1_mm` | Linux Multi-Manufacturer Suite (Jura, Nivona, Kalerm, Jetinno + Web UI) | `origin` (`spectra_dev` **ONLY**) |
| `~/Projects/spectra-win` | `windows` | `v0.5.1_win` | Windows Cross-Platform Multi-Manufacturer Suite (`.bat` launchers + `COM*` support) | `origin` (`spectra_dev` **ONLY**) |

### Cloning on a New Device
```bash
mkdir -p ~/Projects && cd ~/Projects

# 1. Main Linux Jura-only edition:
git clone -b main https://github.com/Pr0xyA-91/spectra_dev.git spectra

# 2. Linux Multi-Manufacturer edition:
git clone -b multi-manufacturer https://github.com/Pr0xyA-91/spectra_dev.git spectra-mm

# 3. Windows Cross-Platform edition:
git clone -b windows https://github.com/Pr0xyA-91/spectra_dev.git spectra-win
```

### Quick Verification Commands
```bash
# Run unit tests in spectra (10/10 tests must pass):
cd ~/Projects/spectra && python3 -m unittest discover -s .

# Run unit tests in spectra-mm / spectra-win (18/18 tests must pass):
cd ~/Projects/spectra-mm && python3 -m unittest discover -s .
cd ~/Projects/spectra-win && python3 -m unittest discover -s .

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

### A. `spectra` (`~/Projects/spectra` — `main` branch, `v0.4.2`)
* **Files**:
  - `serial_io.py`: 4-byte UART bit-banging encoder/decoder (`8ms` inter-bit, `16ms` inter-char pacing), optical loopback echo stripping, Smart Connect `@`-protocol cipher, and mock devices (`DEMO:S8`, `DEMO:E8`, `DEMO:Z10`, `DEMO:S8_SC`).
  - `jura_protocol.py`: EEPROM layout decoder, 16-bit/32-bit word extraction, alert bitmasks.
  - `profiles_db.py` & `profiles_data.json`: Database of 170+ Jura machine profiles (`EF518M`, `S8`, `E8`, `Z10`, `GIGA`, etc.).
  - `stats_collector.py`: High-level interrogation, `RT:`/`RE:` counter mapping, `HZ:`/`CS:`/`IC:` live telemetry parser, text/CSV report formatting.
  - `gui.py`: GTK3 dark-themed desktop application.
  - `cli.py`: Interactive/non-interactive CLI tool with `--export-txt`, `--export-csv`, `--export-json`.
  - `docs/JURA_MEMORY_MAP.md`: Master cross-platform universal EEPROM and telemetry register map with scope tags (`[UNIVERSAL]`, `[FAMILY-SHARED]`, `[MODEL-SPECIFIC]`).
  - `docs/models/`: Dedicated model-specific specifications directory (`README.md` template/index, `EF518_IMPRESSA_XJ5.md`).
  - `publish_release.sh`: Synchronizes `main` $\rightarrow$ `public-main`, strips `GEMINI.md` and `SESSION_NOTES.md`, scrubs `/home/<user>` paths from `.desktop` files, and pushes `public-main:main` to `public`.

### B. `spectra-mm` (`~/Projects/spectra-mm` — `multi-manufacturer` branch, `v0.4.2_mm`)
* Adds multi-vendor architecture on top of the core telemetry engine:
  - `spectra_engine.py`: Unified `SpectraSession` dispatcher and report formatter (`format_text_summary`, `format_csv_summary`). Includes `wrat_engine.py` compatibility shim.
  - `drivers/base.py`: Abstract driver interface & normalized diagnostic schema.
  - `drivers/jura/`: Wraps Jura ASCII & Smart Connect `@`-protocol.
  - `drivers/nivona/`: Eugster/Frismag ASCII/NICR protocol (`DEMO:NICR768`).
  - `drivers/lamanti_kl/`: Lamanti-KL / Kalerm commercial `0xAA`/`0x55` framed binary protocol (`DEMO:X680C`).
  - `drivers/lamanti_jn/`: Lamanti-JN / Jetinno Vending MDB/CC2 `0x02` STX framed protocol (`DEMO:JL300`).
  - `gui_web.py`: Zero-dependency responsive dark-mode HTTP Web Dashboard (`./run.sh --web`, `http://127.0.0.1:8080`) with live polling, brand filter, and `.txt`/`.csv`/`.json` report export.

### C. `spectra-win` (`~/Projects/spectra-win` — `windows` branch, `v0.2.2`)
* Cross-platform Windows adaptation of `spectra-mm`:
  - Windows `COM*` port auto-discovery via `serial.tools.list_ports.comports()` without POSIX `termios` dependencies.
  - Windows batch launchers: `install_windows.bat`, `run.bat` (auto-detects GTK3 or falls back to Web UI), `run_web.bat`, `run_cli.bat`, `run_demo.bat`.

---

## 4. Key Protocol Nuances & Hard-Won Knowledge

### 1. Separation of Live Readiness vs. Historical EEPROM Faults
* **Non-volatile EEPROM registers** (`RE:0028` last fault latch, `RE:01B4` lifetime flowmeter timeouts) store historical events that do **NOT** clear when the machine enters ready state.
* **RULE**: Never gate live operational readiness (`machine_ready`) on `RE:0028` or `RE:01B4`.
* Live operational readiness is determined strictly from real-time physical inputs and active mechanical states:
  - Drip Tray inserted (`tray_ok`)
  - Water Tank present (`water_ok`)
  - Grounds Container not full (`not grounds_full`)
  - Bean Hopper charged (`beans_ok`, evaluated via optical sensor `AS:` reading and `cake_thickness_ticks`)
  - Coffee Thermoblock at brewing temperature ($\ge 80.0$ °C)
  - Appliance idle (`not is_busy`, `parts[0][0] == '0'`, `flow_ml_s == 0.0`, Brew Unit at Home `bu_stroke_pct < 15`, `not mv_busy`)
* When all physical conditions are met, the appliance is **Ready to Brew / Nominal (READY)**; during active cycles it dynamically reports **Brewing / Extracting**, **Brewing / Compressing**, **Dispensing / Rinsing**, **Brew Unit Active**, or **Positioning Multiway Valve**.
* Historical faults remain displayed where they belong: in the **Hardware Diagnostics** tree view.

### 2. Optical Infrared Bean Hopper Sensor (`AS:`) & Puck Measurement (`HZ[8]`)
* **Multi-Layer Bean Hopper Detection Architecture**:
  - **Optical IR Sensor (`AS:`)**: Continuous photodiode telemetry (`off_adc`, `on_adc`, $\Delta$). Net delta $\Delta = (\text{ON\_ADC} - \text{OFF\_ADC})$ eliminates ambient room light offsets (calibrated live on IMPRESSA XJ5):
    - **Through-Beam Architecture**: Emitter and receiver terminals across bean chute. Coffee beans physically block the infrared beam.
    - **Covered / Interrupted / Beans Present**: $\Delta \le 92$ counts (live values: $85$–$91$ counts, nominal $\sim 87$ counts). Machine immediately updates to Ready.
    - **Uncovered / Open / Empty Hopper**: $\Delta \ge 96$ counts (live values: $96$–$119$ counts, nominal $\sim 101$ counts when lid open or empty). The appliance CPU defers LCD update until brew/product selection, at which point it refuses to grind and prompts Fill Beans.
    - **Hysteresis Deadband ($93$–$95$ counts)**: Schmitt trigger latches previous state, completely eliminating boundary fluttering.
  - **Firmware Status Register (`HZ[0][3]`) Separation**: On `EF518M` and optical machines, `parts[0][3]` remains `'1'` during active thermal regulation and does NOT indicate hopper lockout. Optical `AS:` is the sole physical ground truth.
  - **Grinder Dose Puck Measurement (`HZ[8]`)**: Compressed puck thickness $\le 14$ ticks indicates grinder ran empty during the dose cycle (acts as fallback if optical sensor is absent).

### 3. Brew Unit Mechanical Position & Stroke Zones
* Evaluated dynamically from live encoder ticks (`HZ[2]` current, `HZ[1]` upper reference, `RE:0041` mill target):
  - **Home / Mill Position**: `~226–230` ticks (`0%` stroke).
  - **Tamping / Pre-Brew Travel**: `~250–450` ticks (`15%–55%` stroke).
  - **Brewing / Compression**: `~460–610` ticks (`55%–90%` stroke).
  - **Upper / Eject & Rinse**: `~647–650` ticks (`100%` stroke).
  - Dynamic movement arrow (`Moving ▲` / `Moving ▼`) indicates active mechanical transit ($\ge 4$ ticks/sec delta).

### 4. Periodic MCU Heartbeat Bit vs. Alarm Prompts
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

### 5. `HZ:` Fields `parts[1]` and `parts[2]` are Brew Unit Encoder Positions (NOT Ambient NTC)
* In the Jura `HZ:` frame (`hz:010001100000,0287,00E3,0078,03DE,0802,3,000000,0000,00`):
  - `parts[1]` (`0x0287` = `647` ticks) is the **Brew Unit Upper / Reference Encoder Position** (`Copy(hz_payload, 14, 4)` in Jura's `WaterControl`).
  - `parts[2]` (`0x00E3` = `227` ticks) is the **Brew Unit Current / Lower (Mill) Encoder Position** (`Copy(hz_payload, 19, 4)` in Jura's `WaterControl`, calibrated against `RE:0041 = 0x00E6` = `230` ticks).
* **RULE**: Never decode `parts[2]` as an ambient/water-intake temperature (`227 / 10 = 22.7 °C`). Single-heater Jura machines (`EF518M` etc.) have only one NTC sensor (`parts[4]` Coffee Thermoblock); dual-heater machines add `parts[5]` (Steam Thermoblock).

### 6. Complete `EF518M` / `EF518D` Sensor, Register & Sub-Bus (`$:`) Map
* **Dual-MCU Architecture**:
  - `TY:` $\rightarrow$ `ty:EF518M V02.20` (Main Logic Board Firmware)
  - `TL:` $\rightarrow$ `tl:R8Cx Loader V2.0` (Main Logic Board Bootloader)
  - `TY$:` $\rightarrow$ `ty$:EF518D V02.04` (Display / Front Panel MCU Firmware on `$` sub-bus)
  - `TL$:` $\rightarrow$ `tl$:R8C Loader V2.0` (Display / Front Panel MCU Bootloader)
  - `CS$:` $\rightarrow$ `cs$:181C` (Display MCU Flash/ROM Checksum `0x181C`)
  - `DI$:` $\rightarrow$ Triggers the built-in **Display Pixel Check** on the `EF518D` Display Unit (and re-homes the Brew Unit encoder / resets cycle flowmeter counter). Do **not** include `DI$:` in passive read-only polling.
  - `AS:` $\rightarrow$ `as:077106810000,077106E40001` (Main Board Analog Sensor Check from `P518Ani.exe`).
* **`HZ:` Bitfield Breakdown (`hz:010001100000,0287,00E3,0078,03DE,0802,3,000100,0000,00`)**:
  - `parts[0][0]` (`cut="1,1"`): Busy / Operation active (`0` = Idle/Ready, `1` = Busy/Steam-out)
  - `parts[0][1]` (`cut="2,1"`): Brew Unit Initialized & Positioned OK (`1` = OK, `0` = Fault 248)
  - `parts[0][2]` (`cut="3,1"`): Multiway Valve Moving / Busy (`0` = Idle, `1` = Moving)
  - `parts[0][3]` (`cut="4,1"`): **Bean Charge / Fill Beans Sensor** (`0` = Beans OK / Hopper Charged, `1` = Fill Beans / Hopper Empty; mirrored in EEPROM `RE:0029` bit `0x0040`: `0x004C` when OK vs `0x000C` when empty)
  - `parts[0][5]` (`cut="6,1"`): Coffee Thermoblock Temperature Ready (`1` = Ready, `0` = Heating/Fault 708)
  - `parts[0][6]` (`cut="7,1"`): Multiway Valve Initialized OK (`1` = OK)
  - `parts[1]` (`cut="14,4"`): Brew Unit Upper / Reference Encoder Position (`0x0287` = `647` ticks)
  - `parts[2]` (`cut="19,4"`): Brew Unit Current / Lower (Mill) Encoder Position (`0x00E3` = `227` ticks)
  - `parts[3]` (`cut="24,4"`): DigiMesa Flowmeter Turbine Pulse Counter (`2.366 pulses/ml`)
  - `parts[4]` (`cut="29,4"`): Coffee Thermoblock NTC Sensor (`0.1 °C` resolution, e.g. `0x03DE` = `99.0 °C`)
  - `parts[5]` (`cut="34,4"`): Steam Thermoblock NTC (`0x0802` = `2050` open pull-up on single-heater models)
  - `parts[6]` (`cut="39,1"`): Selector State (`3` on `EF518M`; front-panel rotary/buttons are handled locally on `EF518D`)
  - `parts[7][0]` (`cut="41,1"`): Drip Tray Microswitch (`0` = Inserted, `1` = Missing)
  - `parts[7][1]` (`cut="42,1"`): Grounds Container Full (`0` = OK, `1` = Full)
  - `parts[7][2]` (`cut="43,1"`): Water Tank Float/Reed Sensor (`0` = Water OK, `1` = Empty)
  - `parts[7][3]` (`cut="44,1"`): 1 Hz MCU Internal Heartbeat Oscillator (`0` $\leftrightarrow$ `1`)
  - `parts[7][4..5]` (`cut="45,2"`): Auxiliary input bits (`00`)
  - `parts[8]` (`cut="48,4"`): Key Matrix (`0000`)
  - `parts[9][0..1]` (`cut="53,2"`): Hardware Interlock Mirrors (Tray `parts[9][0]`, Tank `parts[9][1]`)
* **Brew Unit Calibration & Subsystem Registers**:
  - `RE:0040`: `0x050C` (`1292` ticks, Brew Unit mechanical upper limit)
  - `RE:0041`: `0x00E6` (`230` ticks, Brew Unit calibrated Mill/Grind Target Position)
  - `RE:0042`..`RE:0044`: `0x010A` (`266`), `0x0208` (`520`), `0x0222` (`546`) intermediate travel targets
  - `RE:0056`: `0x00AF` (`175` cycles, Brew Unit Initialization Counter)

---

## 5. Security & Privacy Guardrails
1. `GEMINI.md` and `SESSION_NOTES.md` contain internal project guidelines and must **NEVER** be pushed to public repositories (`spectra.git`).
2. Only `spectra` (`main` branch via `./publish_release.sh` $\rightarrow$ `public-main`) may ever be synced to the public `spectra.git` repository. `spectra-mm` (`multi-manufacturer`) and `spectra-win` (`windows`) are strictly private.
3. On any new device where `spectra` is cloned and a `public` remote is added, ensure `.git/hooks/pre-push` is installed to block any push to `public` that is not `public-main` or that contains `GEMINI.md`, `SESSION_NOTES.md`, `drivers/`, `wrat_engine.py`, `gui_web.py`, `.bat`, or `/home/` paths.
4. Local versioned backups on the primary workstation are stored in `~/Projects/backup/` (`spectra-v0.4.1.tar.gz`, `spectra-mm-v0.4.1.tar.gz`, `spectra-win-v0.2.1.tar.gz`).

---

## 6. Community Auto-Dumping, Dependencies & Windows Installer Implementation (Session 2026-10-26)
* **Community Auto-Dumping Script (`contrib/dump_machine_spec.py`)**:
  - Automatically queries all 8 ASCII gateways (`TY:`, `TL:`, `TY$:`, `TL$:`, `CS$:`, `IC:`, `HZ:`, `AS:`).
  - Dumps complete 512-word EEPROM memory space (`0x0000`–`0x01FF`) using 32 blocks of 16 words (`RT:0000`–`RT:01F0`), with automatic per-word fallback (`RE:xxxx`) for protected or unreturned blocks (e.g. `0x0000` on EF518).
  - Classifies platform universal registers vs model-specific/unmapped registers.
  - Generates both machine-readable JSON (`docs/models/<EF>_<MODEL>.json`) and human-readable Markdown (`docs/models/<EF>_<MODEL>.md`) ready for GitHub pull requests.
  - Tested live against connected Jura IMPRESSA XJ5 (`EF518M V02.20`): read 512 words in 41 seconds, generated `docs/models/EF518M_IMPRESSA_XJ5_Professional_GII.json` and `.md`.
* **Universal Dependency Specifications (`DEPENDENCIES.md`)**:
  - Detailed matrix across Linux Jura (`wrat-sniffer`), Linux Multi-Manufacturer (`WRAT`), and Windows (`WRAT_win`).
  - Outlined zero-pip design of CLI, telemetry engine, and Web Dashboard.
  - Documented kernel drivers (`ftdi_sio`, `ch341`, `cp210x`, `cdc_acm`), serial permissions (`dialout`/`uucp`), and Windows COM port verification.
* **Windows Installation Guide & Automated PowerShell Setup**:
  - `WRAT_win/INSTALL_WINDOWS.md`: Complete guide covering Python install (PATH checkbox requirement), FTDI/CH340 drivers, Device Manager COM verification, and running scripts.
  - `WRAT_win/install_windows.ps1`: Automated PowerShell installer handling execution policy bypass, python/pip check, installing `pyserial`, testing COM ports, and optional desktop shortcut creation.
* **Version Alignment & Synchronization**:
  - Updated versions and banners: `v0.4.1` (`spectra`), `v0.4.1_mm` (`spectra-mm`), `v0.2.1` (`spectra-win`).
  - Mirrored all tools, documentation, model specs, and test enhancements across all three repositories.
  - All 46 unit tests passing across all test suites (`10/10` in `spectra`, `18/18` in `spectra-mm`, `18/18` in `spectra-win`).
* **Project Rebranding to SPECTRA**:
  - Successfully transitioned project identity from W.R.A.T. to **SPECTRA** (*Universal Hardware Telemetry & Logic Board Diagnostics*).
  - Renamed desktop launcher entries to `SPECTRA.desktop`.
  - Updated all banners, web dashboard UI headers, docstrings, and documentation.
  - Renamed local project working directories to `~/Projects/spectra`, `~/Projects/spectra-mm`, and `~/Projects/spectra-win`.
  - Updated application icon (`icon.png`) to the cyberpunk obsidian refraction prism.

---

## 7. GTK3 Hitbox & Active Zone Desync Resolution (Session 2026-10-26)
* **Root Cause Diagnosis**:
  1. **Window Horizontal Overflow / Surface Desync**:
     - `_create_sensors_tab()` placed 9 diagnostic sensor badges horizontally inside a single `Gtk.Box(spacing=6)` configured with `homogeneous=True`.
     - Because each badge had a natural width of ~150px, this forced the minimum preferred width of the entire window to **1,398 px**.
     - On displays constrained by fractional scaling (e.g. 1600x900 @ 1.25x = 1280x698 logical space on Hyprland), the Wayland compositor clamped the window surface to 1,280 px.
     - Because GTK3's internal layout could not shrink below 1,398 px, the compositor's pointer event coordinate space and GTK's rendered widget buffer became severely desynced, particularly towards the right side of the window where `btn_read` ("Read Statistics") is placed.
  2. **Ambiguous CheckButton Hit Area**:
     - "Auto-Poll (2s)" was implemented as a `Gtk.CheckButton`, which in modern dark themes has an ambiguous hit target (a small checkbox indicator plus plain text without a bounded button box).
  3. **Button Alignment & CSS Feedback**:
     - Action buttons lacked explicit vertical centering (`set_valign(Gtk.Align.CENTER)`), causing variable event box heights inside the horizontal header panel and control bar.
     - `button.primary-btn` lacked `:active` and `:disabled` visual feedback states.
* **Implemented Fixes**:
  1. **2-Row Responsive Grid Layout**:
     - Replaced the single-row horizontal box in `_create_sensors_tab()` with a responsive 2-row `Gtk.Grid(column_homogeneous=True)`.
     - Row 0 (5 columns): Machine State, Brew Unit, Water Tank, Drip Tray, Bean Hopper.
     - Row 1 (4 columns): Coffee Thermoblock, Steam Thermoblock, Water Flow, Water Filter (spanning 2 columns).
     - Reduced window minimum preferred width from **1,398 px down to 1,042 px** (`1,195 px` in multi-manufacturer edition), easily fitting standard 1280 px displays with zero compositor clipping or coordinate scaling artifacts.
  2. **Modern `Gtk.ToggleButton` for Auto-Poll**:
     - Replaced `Gtk.CheckButton` with a proper `Gtk.ToggleButton` with `.toggle-btn` styling.
     - Added distinct active/pressed styling (`button.toggle-btn:checked`) with a luminous green/cyan gradient (`#a6e3a1` to `#94e2d5`), giving 100% matched rectangular hitbox and visual active indication.
  3. **Strict Vertical Alignment & Port Ellipsizing**:
     - Explicitly centered (`Gtk.Align.CENTER`) all buttons and controls in `_create_header_bar()` and `_create_sensors_tab()`.
     - Added Pango ellipsizing to `port_combo` to prevent simulation entries from stretching the header.
     - Added `:active` and `:disabled` CSS states to `button.primary-btn`.
  4. Mirrored across all 3 editions (`spectra`, `spectra-mm`, `spectra-win`) and verified with all 46 unit tests passing.

---

## 8. Performance Optimization, Security Hardening & v0.4.2 Release (Session 2026-10-26)
* **Performance Enhancements**:
  - In-memory profile resolution and model specification caching (`_PROFILE_LOOKUP_CACHE`, `_MODEL_SPEC_LOOKUP_CACHE`) in `profiles_db.py` reducing live auto-polling query resolution to O(1).
  - Optimized `query_ascii` frame reassembly in `serial_io.py` by removing redundant loop sleeping, relying on kernel `select.select()` yielding.
* **Security & Resource Management**:
  - Implemented `__enter__` and `__exit__` context managers on `JuraSerialConnection` and `JuraStatsSession` for deterministic serial port cleanup.
  - Injected defense-in-depth HTTP security headers (`nosniff`, `DENY`, `no-referrer`, `CSP`) in `gui_web.py`.
  - Added strict input validation for serial port parameters (`is_valid_port()`) in Web API.
  - Resolved GTK export dialog `import re` NameError and permitted `blob: data:` in Web CSP for reliable report saving.
  - Bumped version to `v0.4.2` (`spectra`), `v0.4.2_mm` (`spectra-mm`), and `v0.2.2` (`spectra-win`).


---

## 9. Next-Generation UI/UX Redesign & v0.5.0 Release (Session 2026-10-26)
* **Interactive Hydraulic & Sensor "Digital Twin"**:
  - Native Cairo vector rendering of the internal hydraulic and electrical circuit (`gui_widgets.py:DigitalTwinWidget`).
  - Real-time color-coded component state glowing based on live telemetry.
  - Interactive clickable component telemetry inspector card (Thermoblock 1/2, Flowmeter, Pump, Brew Unit, Reservoir, Tray, Beans, MCU).
* **Real-Time Oscilloscope & Strip Chart**:
  - Continuous 60-sample rolling time-series graph for Thermoblock 1 (°C), Thermoblock 2 (°C), and Flowmeter (ml/s) (`gui_widgets.py:OscilloscopeWidget`).
  - Real-time bus event stream log with Pause, Clear, and Export controls.
* **Executive Health Scorecard & AI Maintenance Advisor**:
  - Vector circular radial health gauge (`gui_widgets.py:RadialGaugeWidget`) calculating overall machine health ($0\text{--}100\%$).
  - Progress countdown bars for rated lifespan ($80{,}000$ cups), descaling cycle, and Claris water filter.
  - Heuristic diagnostic alert cards detecting calcification latency, microswitch contact chatter/bounce, and brew unit torque variations.
  - Technician field inspection verification checklist.
* **Specialty Beverage Analytics**:
  - Proportional bar charts with beverage preparation counts and percentage share (`gui_widgets.py:BeverageAnalyticsWidget`).
  - Category filtering (`All`, `Black Coffee`, `Milk Specialties`, `Hot Water / Steam`).
* **Customer Service PDF/HTML Inspection Certificate Generator**:
  - Branded customer inspection certificate generated via 1-click `🖨️ Service Receipt` button (`gui_widgets.py:generate_service_report_html`).
* **Version Standardization**:
  - Upgraded to `v0.5.1` (`spectra`), `v0.5.1_mm` (`spectra-mm`), and `v0.5.1_win` (`spectra-win`).

## 10. Optical Bean Detection Hardware Calibration & v0.5.1 Release (Session 2026-10-27)
* **Live Optical Calibration with Jura IMPRESSA XJ5 (`EF518M V02.20`)**:
  - Net delta $\Delta = (\text{ON\_ADC} - \text{OFF\_ADC})$ successfully eliminates ambient DC offsets (measured across $1,466$ to $1,694$ ambient counts).
  - **Covered / Interrupted / Beans Present**: $\Delta \le 89$ counts (live values: $86$–$89$ counts). Machine immediately updates to Ready.
  - **Uncovered / Open / Empty Hopper**: $\Delta \ge 91$ counts (live values: $91$–$96$ counts). Machine defers LCD update until brew/product selection, at which point it refuses to grind and prompts Fill Beans.
  - **Schmitt Trigger Hysteresis ($90$ counts)**: Latching previous state completely eliminates rapid 1-second boundary oscillations.
* **Release Artifacts**:
  - Upgraded to `v0.5.1` (`spectra`), `v0.5.1_mm` (`spectra-mm`), and `v0.5.1_win` (`spectra-win`).

## 11. Security Hardening & Performance Optimization Audit (Session 2026-10-27)
* **Stored XSS & Injection Prevention**:
  - Full HTML escaping via `html.escape()` for all machine models, serial numbers, beverage names, and maintenance labels in generated customer service inspection certificates (`generate_service_report_html`).
  - Web dashboard port validator (`is_valid_port`) hardened with CRLF injection checks (`\n`, `\r`) and path traversal protection.
* **GTK Thread Affinity & Crash Prevention**:
  - Background auto-poll worker now reads thread-safe `self.selected_port` cached on the main thread, eliminating direct widget queries (`port_combo.get_active_text()`) from secondary worker threads.
  - Wrapped dynamic beverage names and advisor checklist labels with `GLib.markup_escape_text()` to prevent Pango markup parser exceptions on special characters (`&`, `<`, `>`).
* **Memory & Rendering Performance Optimizations**:
  - Capped `event_stream_buffer` (500 lines) and `log_buffer` (1,000 lines) with rolling truncation to eliminate unbounded memory growth during long-running telemetry sessions.
  - `RadialGaugeWidget` now suppresses redundant `queue_draw()` calls when telemetry value is unchanged.
  - `DigitalTwinWidget` coordinate bounding boxes elevated to class constant `NODE_BOXES`, eliminating heap dictionary re-allocations on mouse motion events.
  - Precompiled Smart Connect regexes (`_RE_TR32`, `_RE_TG43`, `_RE_TG47`, `_RE_AN_ALERTS`) at module import in `jura_protocol.py`.
  - Added 4,096-byte boundary checks on incoming serial chunks (`query_ascii` and `_send_encrypted_cmd`) to protect against line noise buffer exhaustion.
  - Cross-platform certificate viewing: uses `os.startfile` on Windows, `open` on macOS, and `xdg-open` on Linux.
* **Validation**:
  - Created `test_security_and_optimizations.py` across all 3 repositories (67/67 unit tests passing).

## 12. Developer Memory Mapper & Differential Logic Scope (Session 2026-10-27)
* **Architecture & Concept**:
  - Purpose-built developer tool (`memory_mapper.py`) for reverse-engineering unknown appliance registers and observing memory deltas during physical switch / menu manipulations.
  - Full 512-word EEPROM memory space (`0x0000`..`0x01FF`, 1,024 bytes) interrogation via 32 fast block reads (`RT:`), with individual word fallback (`RE:`).
  - Also captures volatile state (`HZ:` heating/pump telemetry, `AS:` optical sensor ADCs, and front-panel gateways `TY:`, `TL:`, `TY$:`, `TL$:`, `CS$:`, `IC:`).
* **Traffic-Light Register Classification**:
  - 🟢 **Mapped**: Invariant platform registers (universal counters, calibrations, error logs) or model-specific mappings.
  - 🟠 **Theoretical**: Registers documented in legacy service notes or reverse engineering heuristics (volume settings, aroma strengths, filter thresholds).
  - 🔴 **Unknown**: Active non-zero values on the connected hardware requiring investigation.
  - ⚪ **Blank**: Unprogrammed or zero space (`0x0000`).
* **Live Differential Scope ("What Changed?" Mode)**:
  - Captures baseline snapshot (`capture_baseline`).
  - Real-time comparison identifies all modified registers, computing exact delta values ($\Delta = \text{current} - \text{baseline}$).
  - 16-bit binary inspector reveals exact bit-flip transitions (`b15` .. `b0`).
  - Noise masking suppresses natural NTC thermoblock temperature jitter ($\pm 1..2^\circ\text{C}$) and 1Hz heartbeat counter in volatile feeds.
* **Community Model Knowledge Persistence ("Filling the Blanks")**:
  - Identifies appliance via `TY:` / `TY$:` gateway interrogation to match `EF_CODE` (e.g. `EF518M`).
  - Automatically loads or initializes `docs/models/<EF>_<NAME>.json`.
  - Inline mapping interface (`map_register` in CLI and GUI) allows developers to define register name, description, category, and units.
  - Persists directly to JSON with atomic write and invalidates the profiles cache, updating the universal database in real time for community benefit.
* **Strict Physical Safety Invariant**:
  - Enforces read-only command policy (`SAFE_READ_PREFIXES`).
  - Prohibits any write command (`WE:`, `WT:`, `DA:`, `@tw:`), raising immediate `PermissionError` to guarantee physical appliance safety.
* **Dual Operation**:
  - **Terminal CLI**: Headless / SSH interactive REPL (`python3 memory_mapper.py --cli [--diff] [--watch]`).
  - **GTK Desktop GUI**: Modern dark window (`MemoryMapperWindow`) accessible from SPECTRA's header toolbar (`🔬 Memory Mapper`) or standalone (`python3 memory_mapper.py --gui`).
* **Mock EEPROM Simulation Support**:
  - Enhanced `serial_io.py`'s `is_demo` mode to host a complete 512-word simulated EEPROM with runtime register modification utility (`set_mock_eeprom_word`), enabling full offline developer differential testing.
* **Test Suite Expansion**:
  - Created `test_memory_mapper.py` covering classification, sweep reconstruction, baseline diffing, bit-flip detection, JSON persistence, and safety invariants.
  - Expanded unit test coverage to 82 unit tests across all 3 repositories (22 in `spectra`, 30 in `spectra-mm`, 30 in `spectra-win` — 100% passing).
