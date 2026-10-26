# Jura Model-Specific Hardware & Memory Specifications

This directory contains verified, model-specific hardware specifications, EEPROM layouts, and diagnostic command profiles for individual Jura coffee machine models.

---

## Model Index

| Model Family / Commercial Name | Jura Logic Board Code | Display MCU Code | Jura Article No. | System Architecture | Specification File |
| :--- | :---: | :---: | :---: | :--- | :--- |
| **IMPRESSA XJ5 Professional GII** | `EF518M V02.20` | `EF518D V02.04` | `13705` / `13583` | Single TB, Optical Hopper, External Plumbing | [`EF518_IMPRESSA_XJ5.md`](EF518_IMPRESSA_XJ5.md) |

---

## Architecture: Universal vs. Model-Specific

Jura coffee machine telemetry divides into two distinct layers:

1. **[Universal Memory & Telemetry Map (`../JURA_MEMORY_MAP.md`)](../JURA_MEMORY_MAP.md)**:
   * Covers platform invariants shared across ~90%+ of all Jura appliances:
     * Standard beverage counters (`0x0001`–`0x0006`)
     * Maintenance & service counters (`0x0007` Rinses, `0x0008` Cleanings, `0x0009` Descalings, `0x000A` Grinder time, `0x0015` Service)
     * Non-volatile safety fault latch bitmasks (`RE:0028` / `History_Bit`)
     * Lifetime subsystem error frequency counters (`RE:01B0`–`RE:01B6`, `RE:0103`)
     * Water hardness configuration (`RE:00C3` / `RE:0055`)
     * Serial counter & production date packed encoding (`RE:0031` & `RE:0032`)

2. **Model-Specific Specifications (`./<CODE>_<MODEL>.md`)**:
   * Covers hardware and firmware differences unique to a specific appliance family:
     * Optical infrared bean hopper sensors (`AS:` command photodiode ADCs)
     * Single-thermoblock vs. dual-thermoblock thermal sensor mapping
     * Variable Brew Unit mechanical stop & mill targets (`RE:0040`–`RE:0044`)
     * Sub-bus front panel display commands (`TY$:`, `TL$:`, `CS$:`, `TS$:`)
     * Commercial external plumbing accumulators (`Filter_Ext_*`)
     * Physical button-to-recipe configuration matrices

---

## How to Contribute a New Model Specification

To document and add a new Jura model to this repository, follow these steps:

### 1. Perform a Complete Telemetry & Memory Dump
Connect your machine via optical adapter and run the W.R.A.T. diagnostic dump:
```bash
# Dump complete JSON diagnostic state
python3 cli.py --port /dev/ttyUSB0 --export-json model_dump.json

# Interrogate voluntary telemetry and analog sensors
python3 -c '
import serial_io
conn = serial_io.JuraSerialConnection("/dev/ttyUSB0")
print("Main FW:   ", conn.query_ascii("TY:"))
print("Main BL:   ", conn.query_ascii("TL:"))
print("Display FW:", conn.query_ascii("TY$:"))
print("Display BL:", conn.query_ascii("TL$:"))
print("Checksum:  ", conn.query_ascii("CS$:"))
print("Hardware:  ", conn.query_ascii("IC:"))
print("Telemetry: ", conn.query_ascii("HZ:"))
print("Analog AS: ", conn.query_ascii("AS:"))
conn.close()
'
```

### 2. Copy the Model Specification Template
Use the template below to create `docs/models/<EF_CODE>_<MODEL_NAME>.md`:

```markdown
# Jura Model Specification: <Commercial Model Name>

## 1. Hardware & System Identification
* **Commercial Model Name**: <e.g. Jura E8 Piano White>
* **Main Board Logic Code**: <e.g. EF1092 V01.05 from TY:>
* **Main Bootloader**: <e.g. R8Cx Loader from TL:>
* **Display Unit / Sub-Bus**: <e.g. Direct MCU Drive or EFxxx from TY$:>
* **Jura Article Number**: <e.g. 15355 from profiles_data.json>
* **Hardware Mask / Code**: <from IC: query>
* **Heating Architecture**: <Single Thermoblock / Dual Thermoblock>
* **Fluid System**: <e.g. HP3 Milk Frother, Bypass Hot Water>
* **Hopper System**: <e.g. Mechanical Grinder Drop / Optical IR Sensor>

## 2. Model-Specific Hardware Features & Commands
* **Analog Sensors (AS:)**: <Supported / Not Supported, Thresholds>
* **Front Panel Sub-Bus ($ Commands)**: <Supported commands or N/A>
* **Brew Unit Stroke Limits**: <Target ticks from RE:0041, upper from RE:0040>

## 3. Product & Recipe Configuration Matrix
* <List direct selection buttons or rotary mappings>

## 4. Complete EEPROM Register Dump
* <Attach verified non-zero registers>
```

### 3. Submit a Pull Request
Submit your markdown file along with the anonymized memory dump.
