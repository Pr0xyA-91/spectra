# Jura Coffee Machines — Universal Memory & Telemetry Map
**Master Specification for Open-Source Diagnostics & Reverse-Engineering**  
**Applicability**: Cross-platform reference covering Jura appliances from ~2002 to present (IMPRESSA, ENA, E-Line, S-Line, J-Line, Z-Line, GIGA, X-Line).

---

## 1. Architectural Overview & Scoping Convention

To facilitate collaboration across different Jura coffee machine models, all memory registers and telemetry signals are categorized into three distinct scope levels:

| Scope Marker | Meaning & Applicability | Examples |
| :--- | :--- | :--- |
| **`[UNIVERSAL]`** | **Platform Invariant**: Present and identically structured across ~90%+ of all Jura appliances. | Lifetime drink counters (`0x0001`–`0x0006`), Maintenance totals (`0x0007`–`0x000A`), Fault latch (`0x0028`), Error counters (`0x01B0`–`0x01B6`), Serial & Date (`0x0031`–`0x0032`), Water hardness (`0x00C3`). |
| **`[FAMILY-SHARED]`** | **Architecture Dependent**: Shared by machines having the same chassis, brew unit type, or heating system. | Encoder stroke targets (`0x0040`–`0x0044` on Gen II 5g–16g BU), Single vs Dual thermoblock mapping (`HZ[5]`), Display sub-bus (`$` commands). |
| **`[MODEL-SPECIFIC]`** | **Unique Hardware Variant**: Specific to a particular appliance family. Annotated with the exact model name and code. | Optical bean sensor (`AS:`), Commercial plumbing (`Filter_Ext_*`), front-panel recipe button matrices (`0x00B4`–`0x00BA`). |

---

## 2. Universal EEPROM Register Map (0x0000 – 0x01FF)

### A. Primary Beverage Counters

| Address | Scope | Parameter Name | Decoded Function & Notes |
| :---: | :---: | :--- | :--- |
| **`0x0001`** | **`[UNIVERSAL]`** | `Espresso_1_Cup` | Lifetime single espresso extractions. |
| **`0x0002`** | **`[UNIVERSAL]`** | `Coffee_1_Cup` | Lifetime single regular coffee extractions. |
| **`0x0004`** | **`[UNIVERSAL]`** | `Espresso_2_Cup` | Lifetime double espresso cycles (total cups $= \text{val} \times 2$). |
| **`0x0005`** | **`[UNIVERSAL]`** | `Coffee_2_Cup` | Lifetime double coffee cycles (total cups $= \text{val} \times 2$). |
| **`0x0006`** | **`[UNIVERSAL]`** | `Powder_Coffee` | Lifetime pre-ground coffee bypass cycles. |
| **`0x0013`** | **`[UNIVERSAL]`** | `Milk` | Lifetime milk / cappuccino preparations (`0` on pure black coffee models). |
| **`0x0014`** | **`[UNIVERSAL]`** | `Hotwater` | Lifetime hot water portions dispensed. |

---

### B. Maintenance, Cleaning & Grinder Counters

| Address | Scope | Parameter Name | Decoded Function & Notes |
| :---: | :---: | :--- | :--- |
| **`0x0007`** | **`[UNIVERSAL]`** | `Rinsing` | Lifetime completed coffee system rinse operations. |
| **`0x0008`** | **`[UNIVERSAL]`** | `Cleaning_Count` | Lifetime completed tablet cleaning cycles (*Reinigungszähler*). |
| **`0x0009`** | **`[UNIVERSAL]`** | `Decalcification` | Lifetime completed descaling programs (*Entkalkungszähler*). |
| **`0x000A`** | **`[UNIVERSAL]`** | `Milltime` | Cumulative grinder motor operating time in seconds. |
| **`0x0015`** | **`[UNIVERSAL]`** | `Service_Counter` | Preparations brewed since last authorized technician overhaul. |
| **`0x0045`** | **`[UNIVERSAL]`** | `Filter_Watervolume` | Cumulative water volume in deciliters delivered through internal CLARIS. |
| **`0x0056`** | **`[UNIVERSAL]`** | `Initialization` | Lifetime Brew Unit zero-switch initialization cycles (*Einschalt-Initialisierungen*). |

---

### C. Preventive Maintenance Countdown Registers

| Address | Scope | Parameter Name | Decoded Function & Notes |
| :---: | :---: | :--- | :--- |
| **`0x000B`** | **`[UNIVERSAL]`** | `Steam_Since_Decalc` | Steam dispensing operations performed since last descaling. |
| **`0x000C`** | **`[UNIVERSAL]`** | `Hotwater_Since_Decalc` | Hot water cycles dispensed since last descaling. |
| **`0x000D`** | **`[UNIVERSAL]`** | `Coffee_Since_Decalc` | Coffee cups brewed since last descaling. |
| **`0x000F`** | **`[UNIVERSAL]`** | `Coffee_Before_CleaningAlert` | Coffees remaining before machine displays tablet cleaning prompt. |
| **`0x0016`** | **`[UNIVERSAL]`** | `Coffee_Since_CleaningAlert` | Overdue coffees brewed past the cleaning prompt threshold. |
| **`0x0017`** | **`[UNIVERSAL]`** | `Coffee_After_Decalc` | Overdue coffees brewed past the descaling prompt threshold. |
| **`0x0018`** | **`[UNIVERSAL]`** | `Steam_After_Decalc` | Overdue steam operations performed past descaling prompt. |
| **`0x0019`** | **`[UNIVERSAL]`** | `Hotwater_After_Decalc` | Overdue hot water operations performed past descaling prompt. |

> [!NOTE]
> **Jura Descaling Threshold Formula**:
> The appliance calculates the cumulative calcium carbonate load:
> $$\text{Load} = (\text{Coffees} \times 5) + (\text{Hotwater} \times \text{Factor}_{\text{water}}) + (\text{Steam} \times \text{Factor}_{\text{steam}} \times 4)$$
> When $\text{Load} \ge \frac{\text{HardnessLevel} \times 100 \times 2}{3}$, the machine prompts for descaling.

---

### D. Appliance Identification & Manufacturing Records

| Address | Scope | Parameter Name | Decoded Function & Formula |
| :---: | :---: | :--- | :--- |
| **`0x0030`** | **`[UNIVERSAL]`** | `Machine_Number` | Machine model article code or production variant. |
| **`0x0031`** | **`[UNIVERSAL]`** | `Serial_Number` | Factory electronic serial counter. |
| **`0x0032`** | **`[UNIVERSAL]`** | `Production_Date` | **Packed 16-Bit Date**: Day $= \text{val} \& 0x1F$, Month $= (\text{val} >> 5) \& 0x0F$, Year $= 2000 + ((\text{val} >> 9) \& 0x7F)$. |
| **`0x0075`** | **`[UNIVERSAL]`** | `CRC_Adr` | Non-volatile EEPROM memory block checksum (validated via `AN:0B`). |
| **`0x00C3`** | **`[UNIVERSAL]`** | `Water_Hardness` | Configured water hardness in **°dH** (stored in high byte: `(val >> 8) & 0xFF`). |
| **`0x00DA`** | **`[UNIVERSAL]`** | `Country_Code` | 2-character ASCII country identifier (`"CZ"`, `"DE"`, `"CH"`, `"IT"`). |
| **`0x00DB`** | **`[UNIVERSAL]`** | `Spdl_Download_Date` | Date timestamp when SPDL language pack was uploaded to MCU. |
| **`0x00E9`** | **`[UNIVERSAL]`** | `Retail_High` | High 16-bit word of cumulative retail counter ($\text{cups} = \text{High} \times 65536 + \text{Low}$). |
| **`0x00EA`** | **`[UNIVERSAL]`** | `Retail_Low` | Low 16-bit word of cumulative retail counter. |

---

### E. Safety Fault Register (`RE:0028` / `History_Bit`)

Address **`0x0028`** is the non-volatile safety latch storing historical error trips:

| Bit Mask | Scope | Error Definition | Description |
| :---: | :---: | :--- | :--- |
| **`0x0001`** | **`[UNIVERSAL]`** | `HB_Channel` | Encoder channel missing or cable disconnected. |
| **`0x0002`** | **`[UNIVERSAL]`** | `HB_NTC_short` | Coffee Thermoblock NTC sensor short circuit ($< 0.5\text{ k}\Omega$). |
| **`0x0004`** | **`[UNIVERSAL]`** | `HB_NTC_broken` | Coffee Thermoblock NTC open circuit / broken wire ($> 1\text{ M}\Omega$). |
| **`0x0008`** | **`[UNIVERSAL]`** | `HB_BU_Pos` | Brew Unit mechanical transit timeout (stuck gear or motor stall). |
| **`0x0010`** | **`[UNIVERSAL]`** | `HB_BU_Ini` | Brew Unit lower home microswitch initialization failed. |
| **`0x0020`** | **`[UNIVERSAL]`** | `HB_Decalc` | Descaling program aborted prematurely. |
| **`0x0040`** | **`[FAMILY-SHARED]`** | `HB_Relay_Main` / `HB_NTC2_short` | **Single TB**: Main power relay fault. **Dual TB**: Steam NTC short. |
| **`0x0080`** | **`[FAMILY-SHARED]`** | `HB_Overheat` / `HB_NTC2_broken` | **Single TB**: Thermal overheat cutoff. **Dual TB**: Steam NTC open. |
| **`0x0100`** | **`[UNIVERSAL]`** | `HB_FMTO_intake` | Flowmeter water intake timeout (system airbound or calcified). |
| **`0x0200`** | **`[UNIVERSAL]`** | `HB_FMTO_rinse` | Flowmeter rinse cycle timeout. |
| **`0x0400`** | **`[UNIVERSAL]`** | `HB_Heater` | Thermoblock heating element failure (temperature failed to rise). |
| **`0x0800`** | **`[UNIVERSAL]`** | `HB_KUtimeout` | Ceramic valve motor positioning timeout. |
| **`0x1000`** | **`[UNIVERSAL]`** | `HB_MV_Pos` | Multiway valve position verification error. |
| **`0x2000`** | **`[UNIVERSAL]`** | `HB_MV_Ini` | Multiway valve zero-switch initialization failed. |

---

### F. Lifetime Subsystem Error Frequency Counters

Registers **`0x01B0`–`0x01B6`** and **`0x0103`** store the cumulative event counts for each fault:

| Address | Scope | Low Byte Counter | High Byte Counter |
| :---: | :---: | :--- | :--- |
| **`0x0103`** | **`[UNIVERSAL]`** | `HBcounter_KU`: Ceramic valve controller timeouts (16-bit word). | Full 16-bit word. |
| **`0x01B0`** | **`[UNIVERSAL]`** | `HBcounter_Channel`: Encoder pulses. | `HBcounter_NTC_short`: TB1 Short circuits. |
| **`0x01B1`** | **`[UNIVERSAL]`** | `HBcounter_NTC_broken`: TB1 Open wires. | `HBcounter_BU_Pos`: BU mechanical travel timeouts. |
| **`0x01B2`** | **`[UNIVERSAL]`** | `HBcounter_BU_Ini`: BU zero initialization faults. | `HBcounter_Decalc`: Aborted descaling programs. |
| **`0x01B3`** | **`[FAMILY-SHARED]`** | `HBcounter_Relay_Main` (Single TB) / `TB2_Short` (Dual TB). | `HBcounter_Overheat` (Single TB) / `TB2_Open` (Dual TB). |
| **`0x01B4`** | **`[UNIVERSAL]`** | `HBcounter_FMTO_intake`: Intake timeouts. | `HBcounter_FMTO_rinse`: Rinse timeouts. |
| **`0x01B5`** | **`[UNIVERSAL]`** | `HBcounter_Heater`: Thermoblock element trips. | `HBcounter_KUtimeout`: Ceramic valve timeouts. |
| **`0x01B6`** | **`[UNIVERSAL]`** | `HBcounter_MV_Ini`: Multiway valve init faults. | `HBcounter_MV_Pos`: Multiway valve position faults. |

---

## 3. Model-Specific & Family-Shared Register Directory

When interrogating a specific appliance, consult the corresponding specification in [`docs/models/`](models/):

| Register Range | Scope | Associated Models | Functional Description & Model Links |
| :--- | :---: | :--- | :--- |
| **`AS:` Command** | **`[MODEL-SPECIFIC]`** | **IMPRESSA XJ5, XJ9, GIGA 5, GIGA X7/X8/X9** | **Optical Infrared Bean Hopper Sensor**: Ambient vs. pulsed IR photodiode ADCs (`Empty > 1710`, `Beans OK <= 1680`). See [`EF518_IMPRESSA_XJ5.md`](models/EF518_IMPRESSA_XJ5.md). Absent on domestic lines (E8, S8, ENA). |
| **`0x0000`, `0x0003`, `0x0070`, `0x0071`, `0x0076`, `0x008B`** | **`[MODEL-SPECIFIC]`** | **IMPRESSA XJ5, XJ9, Commercial X-Line** | **Commercial External Plumbing & Filtration (`Filter_Ext_*`)**: Throughput and rinse limits for high-capacity external filter cartridges. See [`EF518_IMPRESSA_XJ5.md`](models/EF518_IMPRESSA_XJ5.md). |
| **`0x0040`–`0x0044`** | **`[FAMILY-SHARED]`** | **Gen II / III Variable Brew Group (5g–16g)** (XJ5, J9, Z7, S9, E8, S8) | **Brew Unit Mechanical Stroke Targets**: Mill target ~`226–230` ticks, Upper reference ~`648–650` ticks, Compression ~`520` ticks. Compact ENA Micro models use shorter ~`180–420` tick ranges. |
| **`0x00B4`–`0x00BA`** | **`[MODEL-SPECIFIC]`** | **IMPRESSA XJ5 (EF518, Art. 13705 / 13583)** | **Direct 4-Button Front-Panel Recipe Matrix**: Espresso 1/2 and Coffee 1/2 aroma strengths and dispensed volumes. See [`EF518_IMPRESSA_XJ5.md`](models/EF518_IMPRESSA_XJ5.md). |
| **`0x0340`–`0x0396`** | **`[MODEL-SPECIFIC]`** | **GIGA 5, GIGA X7 / X8 / X9 (EF535 / EF540)** | **Extended Barista Recipe Matrix (`Copy01`–`Copy22`)**: Up to 32 programmable specialized recipes with independent milk foam duration, bypass ratios, and dual grinder blend balances. |
| **`TY$:`, `TL$:`, `CS$:`, `TS$:`** | **`[FAMILY-SHARED]`** | **Display Sub-Bus Appliances** (XJ, J9, Z7, GIGA) | **Display MCU Gateway (`$` Sub-Bus)**: Communicates with front-panel TFT sub-boards (`EF518D`, `EF536D`). Absent on direct-drive segment display appliances. |

---

## 4. Universal Volatile Telemetry (`HZ:` Frame)

All modern and classic Jura appliances answer the plain ASCII `HZ:` query:
* **Syntax**: `HZ:\r\n`
* **Format**: `hz:STATUS, BU_UP, BU_POS, FLOW, TB1, TB2, ROT, CUTS, PUCK, INT`

| Field | Parameter | Scope | Decoding & Calibration Constants |
| :---: | :--- | :---: | :--- |
| **`STATUS`** | 12-char binary string | **`[UNIVERSAL]`** | Bit 0: Busy (`0`/`1`), Bit 1: BU Init OK (`1`), Bit 2: Valve Busy (`0`), Bit 5: Heater Ready (`1`), Bit 6: Valve Init OK (`1`), Bit 7: Extraction Pump Active (`1`). |
| **`BU_UP`** | 4-char hex | **`[FAMILY-SHARED]`** | Upper mechanical reference limit of Brew Unit (~`648–650` ticks on 5g–16g BU). |
| **`BU_POS`** | 4-char hex | **`[FAMILY-SHARED]`** | Current live encoder position ticks. Dynamic mechanical stroke: Home ~`230` (0%), Tamping ~`380`, Compression ~`520`, Upper Eject ~`650` (100%). |
| **`FLOW`** | 4-char hex | **`[UNIVERSAL]`** | Cumulative cycle flowmeter pulses. Calibrated to **`2.366 pulses per ml`** (~`422 pulses / dl`) for DigiMesa turbine. |
| **`TB1`** | 4-char hex | **`[UNIVERSAL]`** | Coffee Thermoblock NTC temperature in **0.1 °C** resolution (e.g. `0x03C6` $= 966 = 96.6\text{ }^\circ\text{C}$). |
| **`TB2`** | 4-char hex | **`[FAMILY-SHARED]`** | **Single TB Models**: `0x0802` ($2050$ open pull-up). **Dual TB Models**: Active steam thermoblock temperature in 0.1 °C (e.g. `0x0546` $= 135.0\text{ }^\circ\text{C}$). |
| **`ROT`** | 1-char digit | **`[UNIVERSAL]`** | Rotary selector switch position (`1`–`6`). |
| **`CUTS`** | 6-char binary string | **`[UNIVERSAL]`** | **Live Microswitches**: Bit 0: Drip Tray Missing (`1` = Missing), Bit 1: Grounds Full (`1` = Full), Bit 2: Water Tank Float (`1` = Low/Empty), Bit 3: **1 Hz MCU Internal Clock Tick** (`0` $\leftrightarrow$ `1`). |
| **`PUCK`** | 4-char hex | **`[UNIVERSAL]`** | Key matrix idle state (`0000`) and **Live Puck Thickness / Cake Measurement** (`000E` = empty grind threshold, `001D` = strong espresso puck). |
| **`INT`** | 2-char hex | **`[UNIVERSAL]`** | Hardware interlock reflection bits (Bit 0: Tray cut, Bit 1: Water tank cut). |

---

## 5. Standard Diagnostic Command Reference

| Command | Expected Response | Scope | Description |
| :--- | :--- | :---: | :--- |
| `TY:` | `ty:<EF_CODE> <VERSION>` | **`[UNIVERSAL]`** | Main logic board model code and firmware revision. |
| `TL:` | `tl:<LOADER_VERSION>` | **`[UNIVERSAL]`** | Main microcontroller hardware bootloader version. |
| `HZ:` | `hz:<TELEMETRY_FRAME>` | **`[UNIVERSAL]`** | Primary volatile sensor, encoder, and thermal telemetry stream. |
| `AS:` | `as:VREF,OFF,0000,VREF,ON,0001` | **`[MODEL-SPECIFIC]`** | Optical bean hopper photodiode analog reading (Commercial lines). |
| `IC:` | `ic:<HEX4>` | **`[UNIVERSAL]`** | Article number and hardware revision configuration code. |
| `RT:xxxx` | `rt:<64_HEX_CHARS>` | **`[UNIVERSAL]`** | Read non-volatile EEPROM block (16 words / 32 bytes). |
| `RE:xxxx` | `re:<4_HEX_CHARS>` | **`[UNIVERSAL]`** | Read single non-volatile 16-bit EEPROM word. |
| `TY$:` | `ty$:<EF_CODE> <VERSION>` | **`[FAMILY-SHARED]`** | Display sub-MCU firmware version (TFT sub-bus models). |
| `TL$:` | `tl$:<LOADER_VERSION>` | **`[FAMILY-SHARED]`** | Display sub-MCU bootloader version. |
| `CS$:` | `cs:<HEX4>` | **`[FAMILY-SHARED]`** | Display sub-MCU ROM / Flash integrity checksum. |
| `AN:02` / `AN:20` | `ok:` | **`[UNIVERSAL]`** | Enter / reset diagnostic technician testmode. |
