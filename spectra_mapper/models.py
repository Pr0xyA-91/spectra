#!/usr/bin/env python3
"""SPECTRA Memory Mapper data structures, register catalogs, and safety constants."""

import copy
from typing import Dict, List, Optional, Any

# Status constants
STATUS_MAPPED = "mapped"
STATUS_THEORETICAL = "theoretical"
STATUS_UNKNOWN = "unknown"
STATUS_BLANK = "blank"

# Allowed read-only ASCII and wire prefixes
SAFE_READ_PREFIXES = (
    "RT:", "RE:", "TY:", "TL:", "TY$:", "TL$:", "CS$:", "IC:",
    "HZ:", "AS:", "@TR:", "@TG:", "@TF:", "@T0", "@T1", "@t2:"
)
FORBIDDEN_WRITE_COMMANDS = ("WE:", "WT:", "DA:", "@tw:", "@TW:", "we:", "wt:", "da:")

# Jura Top-Tronic 8-bit EEPROM Models (2-digit hex addressing: RT:xx / RE:xx)
TWO_DIGIT_ADDRESS_EFS = {
    "EF509M", "EF511", "EF511M", "EF527M", "EF631D", "EF632D",
    "EF642D", "EF642M", "EF643D", "EF644D", "EPSILON", "IOTA",
    "UFO", "E90", "ALPHAM", "ALPHAD", "C1300", "E1300", "E100"
}

# ============================================================================
# Universal Register Catalog (Platform Invariants — 🟢 Mapped)
# ============================================================================
UNIVERSAL_REGISTERS: Dict[int, Dict[str, Any]] = {
    0x0001: {"name": "Espresso_Single", "desc": "Single Espresso cup count", "category": "counters", "unit": "cups"},
    0x0002: {"name": "Espresso_Double", "desc": "Double Espresso cup count", "category": "counters", "unit": "cups"},
    0x0003: {"name": "Coffee_Single", "desc": "Single Coffee cup count", "category": "counters", "unit": "cups"},
    0x0004: {"name": "Coffee_Double", "desc": "Double Coffee cup count", "category": "counters", "unit": "cups"},
    0x0005: {"name": "Cappuccino_Single", "desc": "Single Cappuccino cup count", "category": "counters", "unit": "cups"},
    0x0006: {"name": "Cappuccino_Double", "desc": "Double Cappuccino cup count", "category": "counters", "unit": "cups"},
    0x0007: {"name": "Rinses_Count", "desc": "Total rinse cycles executed", "category": "maintenance", "unit": "cycles"},
    0x0008: {"name": "Cleaning_Count", "desc": "Total brew unit cleaning tablet cycles", "category": "maintenance", "unit": "cycles"},
    0x0009: {"name": "Descaling_Count", "desc": "Total descaling cycles executed", "category": "maintenance", "unit": "cycles"},
    0x000A: {"name": "Grinder_Seconds", "desc": "Total cumulative grinder motor run time", "category": "counters", "unit": "seconds"},
    0x0015: {"name": "Service_Counter", "desc": "Preparations since last maintenance intervention", "category": "maintenance", "unit": "cups"},
    0x0028: {"name": "Fault_Latch_Bitmask", "desc": "Non-volatile hardware safety fault latch bitfield", "category": "faults", "unit": "bitmask"},
    0x0029: {"name": "Machine_Options", "desc": "Non-volatile machine feature and option flags", "category": "hardware", "unit": "bitmask"},
    0x0030: {"name": "Machine_Article_Word", "desc": "Appliance hardware / article configuration number", "category": "hardware", "unit": "code"},
    0x0031: {"name": "Serial_Counter", "desc": "Sequential manufacturing production serial number", "category": "hardware", "unit": "id"},
    0x0032: {"name": "Production_Date", "desc": "Factory manufacturing date (Day: 0-4, Month: 5-8, Year: 9-15)", "category": "hardware", "unit": "date"},
    0x0040: {"name": "BU_Upper_Limit", "desc": "Brew Unit mechanical top travel limit encoder ticks", "category": "calibration", "unit": "ticks"},
    0x0041: {"name": "BU_Mill_Target", "desc": "Brew Unit ground coffee intake / grinder position ticks", "category": "calibration", "unit": "ticks"},
    0x0042: {"name": "BU_Prebrew_1", "desc": "Brew Unit pre-infusion position 1 ticks", "category": "calibration", "unit": "ticks"},
    0x0043: {"name": "BU_Compression", "desc": "Brew Unit maximum compaction / extraction position ticks", "category": "calibration", "unit": "ticks"},
    0x0044: {"name": "BU_Prebrew_2", "desc": "Brew Unit pre-infusion position 2 ticks", "category": "calibration", "unit": "ticks"},
    0x0045: {"name": "Drainage_Valve", "desc": "Drainage valve calibration offset ticks", "category": "calibration", "unit": "ticks"},
    0x0055: {"name": "Water_Hardness_Legacy", "desc": "Legacy water hardness setting", "category": "settings", "unit": "°dH"},
    0x00C3: {"name": "Water_Hardness", "desc": "Configured water hardness (°dH: bits 8-15)", "category": "settings", "unit": "°dH"},
    0x00DA: {"name": "SPDL_Country", "desc": "SPDL destination market ISO 3166 country code in ASCII", "category": "spdl", "unit": "ascii"},
    0x00DB: {"name": "SPDL_Date_Download", "desc": "Firmware flash download date bitfield", "category": "spdl", "unit": "date"},
    0x00DC: {"name": "SPDL_Date_Language", "desc": "Front-panel language string table flash date bitfield", "category": "spdl", "unit": "date"},
    0x00E9: {"name": "Retail_Counter_High", "desc": "Commercial retail cup counter high word", "category": "counters", "unit": "cups"},
    0x00EA: {"name": "Retail_Counter_Low", "desc": "Commercial retail cup counter low word", "category": "counters", "unit": "cups"},
    0x0103: {"name": "Encoder_Error_Count", "desc": "Lifetime rotary switch / encoder error count", "category": "faults", "unit": "errors"},
    0x01B0: {"name": "Error_Count_Heater", "desc": "Lifetime Thermoblock 1 over-temperature / timeout errors", "category": "faults", "unit": "errors"},
    0x01B1: {"name": "Error_Count_SteamHeater", "desc": "Lifetime Thermoblock 2 (Steam) errors", "category": "faults", "unit": "errors"},
    0x01B2: {"name": "Error_Count_BrewUnit", "desc": "Lifetime Brew Unit encoder / motor stall errors", "category": "faults", "unit": "errors"},
    0x01B3: {"name": "Error_Count_Flowmeter", "desc": "Lifetime flowmeter pulse missing / fluid blockage errors", "category": "faults", "unit": "errors"},
    0x01B4: {"name": "Error_Count_Solenoid", "desc": "Lifetime solenoid / ceramic valve switch errors", "category": "faults", "unit": "errors"},
    0x01B5: {"name": "Error_Count_Drainage", "desc": "Lifetime electronic drainage valve errors", "category": "faults", "unit": "errors"},
    0x01B6: {"name": "Error_Count_NTC", "desc": "Lifetime temperature sensor NTC short / open-circuit errors", "category": "faults", "unit": "errors"}
}

# ============================================================================
# Theoretical Register Catalog (Heuristics & Service Docs — 🟠 Theoretical)
# ============================================================================
THEORETICAL_REGISTERS: Dict[int, Dict[str, Any]] = {
    0x0000: {"name": "Filter_Ext_Watervolume", "desc": "Cumulative volume drawn through external filtration", "category": "counters", "unit": "dl"},
    0x0003: {"name": "Filter_Ext_Watervolumeafter", "desc": "Volume drawn after external filter threshold exceeded", "category": "counters", "unit": "dl"},
    0x0014: {"name": "Standby_Timeout_Config", "desc": "Auto-power off / energy save standby timeout", "category": "settings", "unit": "min"},
    0x0020: {"name": "Grinder_Aroma_Ticks", "desc": "Aroma grinder dosing step timing / ticks", "category": "settings", "unit": "ticks"},
    0x002B: {"name": "Descaling_Volume_Threshold", "desc": "Descaling intervention water volume target threshold", "category": "settings", "unit": "dl"},
    0x0070: {"name": "Filter_Ext_Rinsing", "desc": "Rinse water volume through external filter", "category": "counters", "unit": "dl"},
    0x0071: {"name": "Filter_Ext_Limit_Rinsing", "desc": "External filter maximum rinse limit threshold", "category": "settings", "unit": "dl"},
    0x0076: {"name": "Filter_Ext_Watervolume2", "desc": "Secondary external filter volume counter", "category": "counters", "unit": "dl"},
    0x008B: {"name": "Filter_Ext_Limit_Water", "desc": "Warning threshold for external filter replacement", "category": "settings", "unit": "dl"},
    0x00A9: {"name": "Hotwater_Settings", "desc": "Hot water dispense temperature & bypass valve setting", "category": "recipe", "unit": "cfg"},
    0x00B4: {"name": "Espresso_1_2_Settings", "desc": "Buttons 1 & 2 aroma strength & pre-brew configuration", "category": "recipe", "unit": "cfg"},
    0x00B5: {"name": "Coffee_1_2_Settings", "desc": "Buttons 3 & 4 aroma strength & pre-brew configuration", "category": "recipe", "unit": "cfg"},
    0x00B6: {"name": "Cappuccino_Settings", "desc": "Cappuccino aroma strength, milk foam ratio & sequence", "category": "recipe", "unit": "cfg"},
    0x00B7: {"name": "Latte_Macchiato_Settings", "desc": "Latte Macchiato pause time & milk foam proportions", "category": "recipe", "unit": "cfg"},
    0x00B8: {"name": "Milk_Portion_Settings", "desc": "Milk portion dispense duration and temperature", "category": "recipe", "unit": "cfg"},
    0x00B9: {"name": "Espresso_1_2_Volume", "desc": "Dispensed water volume for Single & Double Espresso", "category": "recipe", "unit": "dl"},
    0x00BA: {"name": "Coffee_1_2_Volume", "desc": "Dispensed water volume for Single & Double Coffee", "category": "recipe", "unit": "dl"},
    0x00BB: {"name": "Hotwater_Volume", "desc": "Hot water portion volume", "category": "recipe", "unit": "dl"},
    0x00BC: {"name": "Cappuccino_Volume", "desc": "Cappuccino coffee & milk total volume", "category": "recipe", "unit": "dl"},
    0x00BD: {"name": "Latte_Volume", "desc": "Latte Macchiato coffee & milk total volume", "category": "recipe", "unit": "dl"},
    0x00C4: {"name": "Auto_Off_Timeout", "desc": "Automatic shut-off countdown timer setting", "category": "settings", "unit": "hours"},
    0x00D0: {"name": "Display_Contrast_Brightness", "desc": "Front-panel LCD/TFT display contrast and brightness", "category": "settings", "unit": "level"},
    0x00D1: {"name": "Language_ID", "desc": "Front-panel user interface language index", "category": "settings", "unit": "id"},
    0x00D2: {"name": "Time_Format_24h", "desc": "Clock format (12h vs 24h display flag)", "category": "settings", "unit": "bool"}
}


# ============================================================================
# Data Structures
# ============================================================================

class RegisterEntry:
    """Represents a single 16-bit register word in EEPROM."""
    def __init__(
        self,
        addr: int,
        val: int,
        status: str,
        name: str,
        desc: str,
        category: str = "custom",
        unit: str = "",
        baseline_val: Optional[int] = None
    ):
        self.addr: int = addr
        self.hex_addr: str = f"{addr:04X}"
        self.val: int = val & 0xFFFF
        self.status: str = status
        self.name: str = name
        self.desc: str = desc
        self.category: str = category
        self.unit: str = unit
        self.baseline_val: int = val if baseline_val is None else (baseline_val & 0xFFFF)
        self.delta: int = self.val - self.baseline_val
        self.bits_flipped: List[int] = self._compute_bit_flips()

    def _compute_bit_flips(self) -> List[int]:
        flips = []
        for bit_idx in range(16):
            if ((self.val >> bit_idx) & 1) != ((self.baseline_val >> bit_idx) & 1):
                flips.append(bit_idx)
        return flips

    @property
    def is_changed(self) -> bool:
        return self.delta != 0

    @property
    def high_byte(self) -> int:
        return (self.val >> 8) & 0xFF

    @property
    def low_byte(self) -> int:
        return self.val & 0xFF

    @property
    def signed_val(self) -> int:
        return self.val if self.val < 32768 else self.val - 65536

    @property
    def ascii_repr(self) -> str:
        hb, lb = self.high_byte, self.low_byte
        c1 = chr(hb) if 32 <= hb <= 126 else "."
        c2 = chr(lb) if 32 <= lb <= 126 else "."
        return f"{c1}{c2}"


class MemorySnapshot:
    """Complete snapshot of 512-word EEPROM plus volatile and gateway telemetry."""
    def __init__(
        self,
        timestamp: float,
        eeprom: Dict[int, int],
        gateways: Dict[str, str],
        hz_raw: Optional[str] = None,
        as_raw: Optional[str] = None
    ):
        self.timestamp = timestamp
        self.eeprom = copy.deepcopy(eeprom)
        self.gateways = copy.deepcopy(gateways)
        self.hz_raw = hz_raw
        self.as_raw = as_raw

