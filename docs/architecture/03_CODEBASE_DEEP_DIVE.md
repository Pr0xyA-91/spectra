# SPECTRA — Codebase Deep-Dive & Module Breakdown

---

## 1. Codebase Directory & File Inventory

SPECTRA is organized into modular Python components, data files, and diagnostic tools:

```
spectra/
├── cli.py                            # Command-line interface for headless automation
├── contrib/
│   ├── dump_machine_spec.py          # Machine specification & golden image dumper
│   └── restore_eeprom.py             # Non-destructive EEPROM restoration & checksum recalculator
├── docs/
│   ├── architecture/                 # Detailed architecture, hardware & protocol handbook
│   ├── JURA_MEMORY_MAP.md            # Universal 512-register EEPROM specification
│   └── models/                       # Golden model specification files (JSON & Markdown)
├── gui.py                            # Main GTK3 desktop diagnostics application
├── gui_widgets.py                    # Cairo vector Digital Twin & Oscilloscope widgets
├── jura_protocol.py                  # 4:1 wire carrier modulation & cryptographic framing
├── memory_mapper.py                  # Developer Memory Mapper, diff engine & register grid
├── profiles_data.json                # Database of 170+ machine profiles, alerts & products
├── profiles_db.py                    # Profiles database query engine & cache
├── serial_io.py                      # Physical serial port driver & simulation fallback
├── stats_collector.py                # Interrogation engine, telemetry extractor & sensor decoder
├── test_memory_mapper.py             # Unit tests for Memory Mapper engine
├── test_security_and_optimizations.py# Unit tests for security invariants & parser safety
└── test_thermal_and_dual_heaters.py  # Unit tests for thermal decoding, Z5 addressing & EAN
```

---

## 2. Detailed Module Explanations

### A. Low-Level Transport: [serial_io.py](../../serial_io.py)
* **Primary Responsibility**:
  Manages physical serial communication across Linux POSIX termios and PySerial on Windows. Provides automatic port discovery, safe connection timeouts, optical inter-frame delays, and offline simulation fallback.
* **Key Classes & Functions**:
  - `JuraSerialConnection`: Primary serial abstraction class.
    - `__init__(port_name, baudrate=9600, timeout=1.5)`: Opens the hardware serial device, configures `8N1` framing with zero parity and no flow control, or initializes the internal `MockJuraMachine` if `DEMO` is requested.
    - `query_ascii(cmd, timeout=1.5)`: Atomically transmits an ASCII command (appending `\r\n`), flushes the output buffer, reads back the response until `\r\n` is encountered, and strips terminal whitespaces. Includes inter-frame sleep guards for optical receiver recovery.
    - `read(size)`, `write(data)`: Low-level raw binary access for Smart Connect wire-encoded frames.
    - `list_jura_serial_ports()`: Probes system devicetree for known FTDI, CP210x, and USB-UART chipsets.
* **Why This Code Exists**:
  Hardware access must be cleanly isolated from telemetry parsing. By centralizing all serial operations in `serial_io.py`, SPECTRA can transparently switch between a real physical machine on `/dev/ttyUSB0` and a virtual mock machine during automated tests.

---

### B. Wire Protocols & Encryption: [jura_protocol.py](../../jura_protocol.py)
* **Primary Responsibility**:
  Implements the proprietary Smart Connect 4:1 wire carrier modulation and session key decryption algorithms used by modern Jura BLE dongles and modern logic boards.
* **Key Classes & Functions**:
  - `encode_wire(data: bytes) -> bytes`: Expands 1 byte into 4 wire-carrier bytes.
  - `decode_wire(wire_data: bytes) -> Tuple[bytes, bytes]`: Reassembles 4 wire bytes back into 1 data byte, validating framing bits and reporting residual unparsed bytes.
  - `decode_encrypted_frame(raw_bytes: bytes, key: int = 0x20) -> str`: Decodes and unscrambles encrypted responses from Smart Connect frames by applying inverse XOR masks and bit rotations.
  - `encode_encrypted_frame(cmd: str, key: int = 0x20) -> bytes`: Encapsulates plain text commands into encrypted Smart Connect frames ready for wire transmission.
  - `MockJuraMachine`: Realistic firmware simulator that mimics a Jura logic board. Accurately simulates Top-Tronic ASCII queries (`TY:`, `IC:`, `RT:`, `RE:`, `HZ:`, `AS:`) and Smart Connect handshakes (`@T0` $\to$ `@T3`).
* **Why This Code Exists**:
  Smart Connect machines refuse plain ASCII commands. `jura_protocol.py` encapsulates all proprietary bitwise transformations, allowing higher-level modules to simply send clean requests and receive clean strings.

---

### C. Profiles Database: [profiles_db.py](../../profiles_db.py) & [profiles_data.json](../../profiles_data.json)
* **Primary Responsibility**:
  Maintains the relational database of 170+ Jura machine profiles. Defines machine family names, series, article numbers, product codes (single vs. double espresso, ristretto, cappuccino, latte macchiato, flat white), maintenance labels, hardware alert masks, address width (2-digit vs 4-digit), and maximum EEPROM size.
* **Key Classes & Functions**:
  - `load_profiles()`: Loads and caches `profiles_data.json`.
  - `find_profile(raw_model_or_ef: str) -> dict`: Intelligent matching engine that takes a raw firmware string (e.g. `'EF642M V01.12'`) and extracts the model definition. Supports longest-prefix matching, suffix stripping (`V2`, `_C`), and fallback to `DEFAULT_PROFILE`.
  - `get_product_name(profile, code)`: Resolves an integer product code into a human-readable drink name.
* **Why This Code Exists**:
  Jura machines do not broadcast drink names over serial—they return raw numbers. For example, beverage code `4` represents "2 Espressi" on Top-Tronic models, but "Cappuccino" on Smart Connect models. `profiles_db.py` ensures counter numbers are mapped to the correct beverage descriptions.

---

### D. Interrogation & Telemetry Engine: [stats_collector.py](../../stats_collector.py)
* **Primary Responsibility**:
  The core analytical and interrogation engine of SPECTRA. Orchestrates connection establishment, dual-mode protocol probing, EEPROM block sweeps, direct register reads, GS1 serial and EAN generation, live sensor parsing, and export generation.
* **Key Classes & Functions**:
  - `JuraStatsSession`: Core interrogation session manager.
    - `run_interrogation(progress_cb)`: Executes the full interrogation sequence:
      1. Probes machine type via `TY:`.
      2. If ASCII is detected, checks address width (2-digit vs 4-digit) against `TWO_DIGIT_ADDRESS_EFS` and profile.
      3. Probes Display Sub-Bus MCU via `TY$:`.
      4. Sweeps EEPROM blocks (`RT:`). For 2-digit models (e.g. Z5), sweeps 16 blocks and includes block `0xE0` for double beverage counters.
      5. Directly queries identification registers (`RE:`): Machine Number (`0x30`), Serial Word (`0x31`), Production Date (`0x32`), Service Counter (`0x15`), Water volume (`0x10`), Descaling volume (`0x12`), Filter cycles (`0x22`), and baseline Retail references (`0xE9`/`0xEA`).
      6. If `TY:` fails, transitions to Mode B and negotiates the Smart Connect `@T0` handshake.
    - `query_live_sensors(port_name, conn, fast_poll)`: Interrogates real-time operational sensors (`HZ:` and `AS:`) without executing a full EEPROM dump.
    - `get_structured_summary() -> dict`: Produces a complete dictionary of lifetime cups, preparations, maintenance cycles, component statuses, and hardware alerts.
  - `decode_jura_date(val: int) -> datetime`: Decodes Jura's 16-bit date bitfield:
    $$\text{Year} = 1990 + (\text{val} \gg 9), \quad \text{Month} = (\text{val} \gg 5) \& 0x0F, \quad \text{Day} = \text{val} \& 0x1F$$
  - `decode_jura_temperature(raw_val) -> Optional[float]`: Decodes thermoblock NTC raw hexadecimal ADC into $0.1^\circ\text{C}$ resolution. Suppresses uninstalled sensor values ($\ge 1900$).
  - `calculate_gs1_check_digit(base_str: str) -> int`: Computes the GS1 / Luhn-style modulo-10 check digit for GTIN-14 barcode compliance.
  - Optical Bean Sensor Calibration:
    - `get_optical_bean_threshold()` / `set_optical_bean_threshold(val)`: Manages runtime and persisted IR through-beam calibration in `~/.config/spectra/calibration.json`.
* **Why This Code Exists**:
  It bridges the gap between raw hardware bytes and actionable diagnostic data, translating machine registers into human metrics: operating hours, dispensed liters, cleanings, and active alarms.

---

### E. Developer Memory Mapper & Scope: [memory_mapper.py](../../memory_mapper.py)
* **Primary Responsibility**:
  An interactive reverse-engineering and EEPROM differential inspection environment. Enables technicians to observe real-time bit flips during appliance operation, map unknown registers, and commit them to golden model specifications.
* **Key Classes & Functions**:
  - `RegisterEntry`: Represents a single 16-bit EEPROM register, tracking its current value, baseline value, category, description, and flipped bits.
  - `MemorySnapshot`: Immutable snapshot of the entire EEPROM (256 or 512 words) alongside volatile telemetry (`HZ:`, `AS:`).
  - `MemoryMapperEngine`: Core logic engine.
    - `sweep_eeprom(progress_callback)`: Executes a complete memory sweep (16 blocks for 2-digit models, 32 blocks for 4-digit models).
    - `capture_baseline()`: Captures a reference snapshot before an operation (e.g., grinding or brewing).
    - `compute_diff(mask_noise)`: Compares the current memory state against the baseline, calculating active deltas and isolating flipped bits.
    - `classify_all()`: Classifies registers into a 4-tier traffic-light system:
      - 🟢 **Mapped**: Register function is known and verified.
      - 🟠 **Theoretical**: Register function is hypothesized based on family similarity.
      - 🔴 **Unknown / Active**: Register has changed but lacks documentation.
      - ⚪ **Blank**: Register value is 0.
    - `map_register(addr, name, desc, category, unit)`: Immediately updates and persists a newly identified register into `docs/models/<EF>_*.json`.
    - `_assert_safe_command(cmd)`: Enforces the read-only safety invariant.
  - `MemoryMapperWindow`: GTK3 GUI window providing an interactive 16-bit register matrix, bit-level inspector, search filter, and mapping dialog.
* **Why This Code Exists**:
  New Jura models often contain undocumented registers. The Memory Mapper provides a safe, structured way to discover register addresses without risking write operations.

---

### F. Desktop GUI & Digital Twin: [gui.py](../../gui.py) & [gui_widgets.py](../../gui_widgets.py)
* **Primary Responsibility**:
  Provides a modern, high-framerate GTK3 desktop interface featuring a Cairo-drawn vector digital twin of the coffee machine's internal hydraulic circuit, a real-time thermal/flow oscilloscope strip chart, and detailed telemetry dashboards.
* **Key Components**:
  - `DigitalTwinWidget` ([gui_widgets.py](../../gui_widgets.py)):
    - Custom GTK widget rendering an interactive hydraulic schematic using vector Cairo primitives.
    - Renders the Water Tank, Turbine Flowmeter, Vibration Pump, Dual Thermoblocks, Ceramic Valve, Brew Unit, Bean Hopper, and Drip Tray.
    - Visually updates component colors based on live telemetry (e.g. flashing red when water is low or bean hopper is empty; pulsing blue when flowmeter registers water flow; heating gradient from cold blue to brewing red on thermoblocks).
  - `StripChartWidget` ([gui_widgets.py](../../gui_widgets.py)):
    - Real-time oscilloscope strip chart graphing Coffee Thermoblock temperature, Steam Thermoblock temperature, and water flow rate over a 60-second sliding window.
  - `JuraDiagApp` ([gui.py](../../gui.py)):
    - Main application window managing tabs: Overview, Statistics & Preparations, Maintenance & Hygiene, Live Digital Twin, and Developer Tools.
    - Handles asynchronous interrogation worker threads to keep the UI fluid at 60 FPS.
    - Includes the development branch optical bean sensor calibration slider.
* **Why This Code Exists**:
  Technicians need immediate visual feedback when diagnosing a machine. Rather than reading raw numbers, they can see the hydraulic flow, thermal behavior, and switch states represented visually.

---

### G. Command-Line Interface: [cli.py](../../cli.py)
* **Primary Responsibility**:
  Headless CLI interface for running diagnostic interrogations, generating text/JSON/CSV reports, and adjusting calibration parameters in automated test environments or remote terminals.
* **Supported Commands**:
  - `python3 cli.py -p /dev/ttyUSB0`: Executes full interrogation and outputs a formatted diagnostic report.
  - `python3 cli.py -p /dev/ttyUSB0 -s`: Quick-polls live sensors (`HZ:`, `AS:`) without a full EEPROM dump.
  - `python3 cli.py -p /dev/ttyUSB0 -f json -o report.json`: Exports structured diagnostic telemetry to JSON.
  - `python3 cli.py --get-bean-threshold` / `--set-bean-threshold <VAL>`: Inspects or adjusts the bean sensor threshold.
* **Why This Code Exists**:
  Allows automated diagnostic scripts, workshop benches, and remote technicians to run tests without launching a graphical desktop.

---

### H. Archival & Restoration Utilities: [contrib/](../../contrib/)
* **[dump_machine_spec.py](../../contrib/dump_machine_spec.py)**:
  Extracts an exhaustive golden machine specification from a connected physical appliance, saving register maps, raw hex dumps, and Markdown documentation into `docs/models/`.
* **[restore_eeprom.py](../../contrib/restore_eeprom.py)**:
  A non-destructive EEPROM restoration tool designed to recover corrupted logic boards:
  - Reads a verified golden specification (`docs/models/<EF>_*.json`).
  - Verifies machine type compatibility via `TY:`.
  - Performs word-by-word comparison against physical EEPROM.
  - Writes only mismatched registers using `WE:<ADDR>,<VAL>`.
  - Automatically recalculates and commits the internal logic board checksum via `AN:0B` (verified at register `0x0075`).
  - Includes `--dry-run` simulation mode to preview changes safely.
