# Jura ENA 7 (`EF634`) — Memory Map & Architecture Specification

## 1. Technical Overview

| Parameter | Specification | Notes |
| :--- | :--- | :--- |
| **Model Family** | **ENA 7** | Premium compact Jura automatic line |
| **Logic Board Firmware** | **`EF634`** | `ty:EF634 V01.31` |
| **Bootloader** | `tl:LOADER V5.0` | Direct optical plain-ASCII protocol |
| **Known Articles** | `13500`, `13760`, `13501`, `13524` | `13500` (Ristretto Black), `13760` (Blossom White) |
| **EEPROM Geometry** | 512 words (32 blocks $\times$ 16 words) | 4-digit hex addressing (`RT:0000`..`RT:01F0`) |
| **Heating Architecture** | Single Thermoblock (TB1) | Coffee heater only, manual steam valve |
| **Upper Memory Block** | `0x0100`–`0x01FF` | **SPDL Language Text Table** (e.g. Czech) |

---

## 2. Beverage Dispensing Memory Layout

Unlike classic Jura Impressa machines (which map `0x0001`–`0x0006`), ENA 7 employs an interleaved 1-cup / 2-cup sequence beginning at register `0x0000`:

| Register | Field Name | Unit | Type | Description |
| :---: | :--- | :---: | :---: | :--- |
| **`0x0000`** | `Espresso_Single` | cups | Single | Lifetime 1 Cup Espresso brews |
| **`0x0001`** | `Espresso_Double` | cycles | Double | Lifetime 2 Cups Espressi (cups $= \text{val} \times 2$) |
| **`0x0002`** | `Coffee_Single` | cups | Single | Lifetime 1 Cup Coffee brews |
| **`0x0003`** | `Coffee_Double` | cycles | Double | Lifetime 2 Cups Coffees (cups $= \text{val} \times 2$) |
| **`0x0004`** | `Aroma_Boost_Single` | cups | Single | Lifetime 1 Cup Aroma-Boost extractions |
| **`0x0005`** | `Steam_Water_Valve` | cycles | Aux | Manual steam/water valve openings (not in coffee prep total) |
| **`0x0006`** | `Ground_Coffee` | cups | Single | Lifetime pre-ground coffee bypass brews |

* **Total Coffee Preparations Formula**:
  $$\text{Total Preps} = \text{Espresso}_1 + \text{Espresso}_2 + \text{Coffee}_1 + \text{Coffee}_2 + \text{AromaBoost}_1 + \text{Ground}$$
* **Total Cups Formula**:
  $$\text{Total Cups} = \text{Single Preps} + (\text{Double Preps} \times 2)$$

---

## 3. Maintenance, Hygiene & Operational Registers

| Register | Name | Decoded Formula / Value | Description |
| :---: | :--- | :--- | :--- |
| **`0x0007`** | `Rinses` | Raw count | Lifetime coffee system rinse operations |
| **`0x0008`** | `Cleanings` | Raw count | Lifetime tablet cleaning cycles |
| **`0x0009`** | `Descalings` | Raw count | Lifetime completed descaling cycles |
| **`0x000A`** | `Grinder_Seconds` | Raw seconds | Cumulative grinder motor operating time |
| **`0x0010`** | `Water_Volume_Total` | Value in dl ($\div 10 = \text{Liters}$) | Cumulative water throughput incl. rinses |
| **`0x0012`** | `Descaling_Agent` | Value in dl ($\div 10 = \text{Liters}$) | Cumulative descaling fluid consumed |
| **`0x0015`** | `Service_Counter` | Raw count | Preparations brewed since last technician service |
| **`0x001B`** | `Milk_Minutes` | Minutes | Cumulative milk / milk froth duration |
| **`0x001C`** | `Hotwater_Minutes` | Minutes | Cumulative hot water dispensing duration |
| **`0x0030`** | `Appliance_Number` | Raw ID (e.g. `1004`) | Factory machine serial counter (Maschinennummer) |
| **`0x0031`** | `Serial_Word` | Raw ID (e.g. `1`) | Factory batch word |
| **`0x0032`** | `Production_Date` | Packed Jura date bitfield | Manufacturing date |
| **`0x0036`** | `Water_Through_Filter` | Value in dl | Cumulative water through current CLARIS cartridge |
| **`0x003D`** | `Water_Hardness` | Value in $^\circ\text{dH}$ | Configured water hardness (also in `0x00C3 >> 8`) |
| **`0x003E`** | `Auto_Off_Timeout` | Value in minutes | Automatic shut-off countdown ($300\text{ min} = 5.0\text{ h}$) |
| **`0x0052`** | `Total_Filter_Changes`| Raw count | **Total CLARIS filter cartridge replacements** |
| **`0x0056`** | `BU_Initializations` | Raw count | Lifetime brew unit power-on initializations |
| **`0x00D6`** | `Machine_Switch_On` | Raw count | Lifetime appliance power switch-on count |
| **`0x007E..7F`**| `Article_High..Low` | $(0x7E \ll 8) \mid 0x7F$ | Hardware article number (e.g. `0x34BC = 13500`) |

---

## 4. Hardware Safety & Service History Block

- **Safety Fault Register (`0x0028`)**:
  - `0x0019` ($25$) = Bits 0, 3, 4:
    - **Bit 0**: Error 0 (Check encoder / cable)
    - **Bit 3**: Error 7/8 (BU Initialization / position not possible)
    - **Bit 4**: Error 7/8 (BU Initialization not possible)
- **Service History Records (`0x0065`–`0x006F`)**:
  - `0x0065`: Service Date bitfield (`0x362F` $\to$ `15.1.2017`)
  - `0x0066`: Service Animation ID (`1540`)
  - `0x0067`: Invoicing Code (`110` = Repair)
  - `0x0068`: Service Stamp Index (`1`)
  - `0x006A` (low byte): Job Code (`254` = Appliance checked)
