# Jura WE8 / WE8 (EA) — Hardware Diagnostic & Memory Specification

**Appliance Type**: `15420 WE8 (EA)` / `WE8 Aroma G3 RFID Smart Connect`  
**Factory Article Numbers**: `15420` (Chrome EA), `15421` (Dark Inox EA), `15141` (Dark Inox), `15144` (Chrome)  
**Mainboard MCU Firmware**: `EF533M` / `EF535M` (Bootloader: `BL_RL78`)  
**Display Gateway Firmware**: `EF533D` / `EF535D`  
**EEPROM Architecture**: 512 words (1,024 bytes), 4-digit hex addressing (`RT:0000`..`RT:01F0`, `RE:xxxx`)  

---

## 1. Beverage Statistics Allocation

The Renesas RL78 platform allocates a consolidated beverage statistics bank at **`0x0180`** (with green tea at **`0x017F`**):

| EEPROM Address | Beverage Product | Jura Product Code | Notes |
|:---|:---|:---:|:---|
| `0x017F` | **Hot water for green tea** | `45` | Green tea portion counter |
| `0x0180` | **Espresso** | `2` | Single Espresso (also mirrored at `0x0000`) |
| `0x0181` | **Ristretto** | `1` | Single Ristretto (also mirrored at `0x0001`) |
| `0x0182` | **Coffee** | `3` | Single Coffee (also mirrored at `0x0002`) |
| `0x0183` | **Flat white** | `46` | Flat White (also mirrored at `0x0003`) |
| `0x0184` | **Cappuccino** | `4` | Single Cappuccino (also mirrored at `0x0004`) |
| `0x0185` | **Latte macchiato** | `7` | Latte Macchiato (also mirrored at `0x0005`) |
| `0x0186` | **Product with ground coffee** | `15` | Powder product (also mirrored at `0x0006`) |
| `0x0187` | **Portion of milk** | `10` | Portion of milk (also mirrored at `0x0013`) |
| `0x0188` | **Hot water** | `13` | Hot water (also mirrored at `0x0014`) |
| `0x0189` | **2 x Espresso** | `18` | Double Espresso (also mirrored at `0x00E0`) |
| `0x018A` | **2 x Ristretto** | `17` | Double Ristretto (also mirrored at `0x00E1`) |
| `0x018B` | **2 x Coffee** | `19` | Double Coffee (also mirrored at `0x00E2`) |
| `0x018C` | **2 x Special coffee** | `63` | Double Special Coffee (also mirrored at `0x00E3`) |
| `0x018D` | **Special coffee** | `47` | Single Special Coffee |
| `0x018E` | **Macchiato** | `6` | Espresso Macchiato |
| `0x018F` | **Espresso doppio** | `48` | Espresso Doppio |

---

## 2. Maintenance & Hygiene Counters

| EEPROM Address | Maintenance Metric | Description |
|:---|:---|:---|
| `0x0007` | **Coffee System Rinsing** | Total coffee system rinsing operations |
| `0x0008` | **Cleaning Operations** | Total cleaning cycles executed |
| `0x0009` | **Descaling Operations** | Total descaling cycles executed |
| `0x0020` | **Milk System Rinsing** | Total milk system rinsing operations |
| `0x0021` | **Milk System Cleaning** | Total milk system cleaning operations |
| `0x0022` | **Filter Change** | Total CLARIS Smart RFID filter changes |

---

## 3. Cockpit Wear / Life Remaining Percentages

| EEPROM Address | Cockpit Indicator | Bitfield / Byte | Description |
|:---|:---|:---:|:---|
| `0x0162` | **Descaling** | Low byte | Percentage life remaining (0% = immediate descaling required) |
| `0x0163` | **Cleaning** | Low byte | Percentage life remaining until cleaning prompted |
| `0x01E1` | **Filter Change** | Low byte | Percentage filter capacity remaining |

---

## 4. Hardware Identification & Batch Registers

| EEPROM Address | Register Name | Decoding Rule |
|:---|:---|:---|
| `0x0030` | **Appliance Number** | Decimal machine production sequence number |
| `0x0031` | **Serial Word** | Internal factory serial index |
| `0x0032` | **Production Date** | 16-bit bitfield: Day (b0..4), Month (b5..8), Year (1990 + b9..15) |
| `0x007E` / `0x007F` | **Article Number** | High byte `0x7E` and high byte `0x7F` (`0x3C` + `0x3C` = `15420`) |
| `0x00DA` | **Country Market** | 2 ASCII characters (e.g. `0x435A` = `CZ`) |
