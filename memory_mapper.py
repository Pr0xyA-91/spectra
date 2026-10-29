#!/usr/bin/env python3
"""
SPECTRA — Developer Memory Mapper & Differential Logic Scope Tool
Part of SPECTRA — Universal Hardware Telemetry & Logic Board Diagnostics

Enables reverse-engineering, memory mapping, and differential state analysis
for Jura coffee machine microcontrollers (EEPROM 0x0000..0x01FF + volatile HZ:/AS:).

Features:
- Traffic-Light Register Classification:
    🟢 Mapped (Confirmed Platform & Model Registers)
    🟠 Theoretical (Service Docs & Reverse Engineering Heuristics)
    🔴 Unknown (Active Non-Zero Registers Requiring Investigation)
    ⚪ Blank (0x0000 / Unwritten Space)
- Live Differential Logic Scope ("What Changed?" Mode):
    Real-time delta tracking against a captured baseline snapshot.
    Bit-level transition detection (16-bit binary flip analysis).
    Smart noise/jitter masking for thermoblock NTC drift & 1Hz heartbeat.
- Community Model Knowledge Persistence ("Filling the Blanks"):
    Identifies connected model by EF code and auto-loads `docs/models/<EF>_*.json`.
    Inline mapping tool persists newly discovered registers directly to JSON.
- Dual Operational Interfaces:
    1. Interactive Terminal CLI (Headless / SSH / scriptable)
    2. Modern Dark GTK GUI (Embedded in SPECTRA or standalone)
- Strict Read-Only Safety:
    Prohibits any write commands (WE:, WT:, DA:). Physical safety guaranteed.
"""

import os
import sys
import re
import json
import time
import copy
import datetime
import threading
import argparse
from typing import Dict, List, Tuple, Optional, Any, Set

# Ensure repository root is on sys.path
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

import serial_io
import profiles_db

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


# ============================================================================
# Memory Mapper Engine
# ============================================================================

class MemoryMapperEngine:
    """
    Core engine managing EEPROM sweeps, baseline differentials,
    register classification, and model specification persistence.
    """

    def __init__(self, conn: serial_io.JuraSerialConnection, models_dir: Optional[str] = None):
        self.conn = conn
        self.models_dir = models_dir or os.path.join(SCRIPT_DIR, "docs", "models")
        os.makedirs(self.models_dir, exist_ok=True)

        self.gateways: Dict[str, str] = {}
        self.ef_code: str = "UNKNOWN"
        self.model_family: str = "Jura Appliance"
        self.is_two_digit: bool = False
        self.address_width: int = 4
        self.max_words: int = 512
        self.model_spec: Dict[str, Any] = {}
        self.spec_file_path: Optional[str] = None

        self.current_eeprom: Dict[int, int] = {i: 0 for i in range(512)}
        self.baseline_snapshot: Optional[MemorySnapshot] = None
        self.classified_registers: List[RegisterEntry] = []

        # Interrogate machine identity on start
        self.refresh_identity()

    def _assert_safe_command(self, cmd: str):
        """Enforce strict read-only safety invariant."""
        c = cmd.strip()
        for forbidden in FORBIDDEN_WRITE_COMMANDS:
            if c.startswith(forbidden):
                raise PermissionError(f"SAFETY VIOLATION: Write command '{cmd}' is strictly forbidden in Memory Mapper.")

    def query_safe(self, cmd: str, timeout: float = 1.5) -> Optional[str]:
        """Execute query verifying read-only safety invariant."""
        self._assert_safe_command(cmd)
        return self.conn.query_ascii(cmd, timeout=timeout)

    def refresh_identity(self):
        """Interrogate identification gateways and load/create model specification."""
        gateways_to_probe = ["TY:", "TL:", "TY$:", "TL$:", "CS$:", "IC:", "HZ:", "AS:"]
        for g in gateways_to_probe:
            try:
                ans = self.query_safe(g, timeout=1.2)
                if ans:
                    self.gateways[g] = ans.strip()
            except Exception:
                pass

        ty = self.gateways.get("TY:", "")
        m = re.search(r'(EF\w+)', ty.upper())
        if m:
            self.ef_code = m.group(1)
        elif self.conn.is_demo and "XJ5" in self.conn.port_name.upper():
            self.ef_code = "EF518M"
        else:
            self.ef_code = "UNKNOWN"

        profile = profiles_db.find_profile(self.ef_code)
        self.is_two_digit = (
            profile.get("address_width") == 2
            or any(self.ef_code.upper().startswith(p) for p in TWO_DIGIT_ADDRESS_EFS)
        )
        self.address_width = 2 if self.is_two_digit else 4
        self.max_words = profile.get("max_words", 256 if self.is_two_digit else 512)
        self.current_eeprom = {i: 0 for i in range(self.max_words)}

        self._load_or_init_model_spec()

    def _load_or_init_model_spec(self):
        """Find or initialize model specification file in docs/models/."""
        # 1. Search for matching EF file
        found_spec = None
        found_path = None

        if os.path.exists(self.models_dir):
            for fname in os.listdir(self.models_dir):
                if fname.upper().startswith(self.ef_code.upper()) and fname.endswith(".json"):
                    fpath = os.path.join(self.models_dir, fname)
                    try:
                        with open(fpath, "r", encoding="utf-8") as f:
                            data = json.load(f)
                        found_spec = data
                        found_path = fpath
                        break
                    except Exception:
                        pass

        if found_spec:
            self.model_spec = found_spec
            self.spec_file_path = found_path
            self.model_family = found_spec.get("model_family", self.model_family)
        else:
            # Try profiles database
            profile = profiles_db.find_profile(self.ef_code)
            self.model_family = profile.get("model_family", f"Jura Appliance ({self.ef_code})")
            clean_name = re.sub(r'[^A-Za-z0-9_]+', '_', self.model_family).strip('_')
            fname = f"{self.ef_code}_{clean_name}.json"
            self.spec_file_path = os.path.join(self.models_dir, fname)

            self.model_spec = {
                "model_family": self.model_family,
                "ef_code": self.ef_code,
                "display_ef": self.gateways.get("TY$:", "").replace("ty$:", ""),
                "series": profile.get("series", "Jura Appliance"),
                "address_width": self.address_width,
                "max_words": self.max_words,
                "article_numbers": [str(a) for a in profile.get("articles", [])],
                "hardware": {
                    "thermoblocks": 1,
                    "has_steam_heater": False,
                    "has_optical_hopper": bool("AS:" in self.gateways and "as:" in self.gateways["AS:"].lower()),
                    "has_sub_bus": bool("TY$:" in self.gateways),
                    "has_external_plumbing": False,
                    "flowmeter_pulses_per_ml": 2.366
                },
                "custom_registers": {}
            }

    def sweep_eeprom(self, progress_callback=None) -> Dict[int, int]:
        """
        Perform complete EEPROM sweep (16 blocks for 2-digit models, 32/64 blocks for 4-digit models),
        falling back to individual word reads (RE:) where blocks fail.
        """
        total_blocks = max(1, self.max_words // 16)
        for b_idx in range(total_blocks):
            blk = b_idx * 16
            blk_str = f"{blk:02X}" if self.address_width == 2 else f"{blk:04X}"
            if progress_callback:
                progress_callback(b_idx + 1, total_blocks, f"Reading Block 0x{blk_str}...")

            cmd = f"RT:{blk_str}"
            ans = self.query_safe(cmd, timeout=1.5)

            block_success = False
            if ans and ans.lower().startswith("rt:"):
                raw_hex = ans[3:].strip()
                if len(raw_hex) >= 64:
                    for i in range(16):
                        w_hex = raw_hex[i * 4: i * 4 + 4]
                        try:
                            self.current_eeprom[blk + i] = int(w_hex, 16)
                        except ValueError:
                            self.current_eeprom[blk + i] = 0x0000
                    block_success = True

            if not block_success:
                # Fallback to single word queries
                for i in range(16):
                    addr = blk + i
                    addr_str = f"{addr:02X}" if self.address_width == 2 else f"{addr:04X}"
                    w_ans = self.query_safe(f"RE:{addr_str}", timeout=1.0)
                    if w_ans and w_ans.lower().startswith("re:"):
                        try:
                            self.current_eeprom[addr] = int(w_ans[3:].strip()[:4], 16)
                        except ValueError:
                            self.current_eeprom[addr] = 0x0000
                    else:
                        self.current_eeprom[addr] = 0x0000

        self.classify_all()
        return dict(self.current_eeprom)

        self.classify_all()
        return dict(self.current_eeprom)

    def capture_baseline(self) -> MemorySnapshot:
        """Capture current EEPROM and volatile telemetry as baseline reference."""
        hz = self.query_safe("HZ:", timeout=1.0)
        as_ans = self.query_safe("AS:", timeout=1.0)
        self.baseline_snapshot = MemorySnapshot(
            timestamp=time.time(),
            eeprom=dict(self.current_eeprom),
            gateways=dict(self.gateways),
            hz_raw=hz,
            as_raw=as_ans
        )
        self.classify_all()
        return self.baseline_snapshot

    def classify_all(self) -> List[RegisterEntry]:
        """Classify all registers according to model spec, universal, theoretical, and unknown tables."""
        custom_regs = self.model_spec.get("custom_registers", {})
        baseline = self.baseline_snapshot.eeprom if self.baseline_snapshot else self.current_eeprom

        entries: List[RegisterEntry] = []
        max_words = getattr(self, "max_words", 512)
        addr_w = getattr(self, "address_width", 4)
        for addr in range(max_words):
            val = self.current_eeprom.get(addr, 0)
            base_val = baseline.get(addr, val)
            hex_addr = f"{addr:02X}" if addr_w == 2 else f"{addr:04X}"
            hex_addr_alt = f"{addr:04X}" if addr_w == 2 else f"{addr:02X}"

            # 1. Check Model Specification custom_registers
            reg_def = custom_regs.get(hex_addr) or custom_regs.get(hex_addr_alt)
            if reg_def:
                c = reg_def
                name = c.get("name", f"Reg_0x{hex_addr}")
                # If name starts with Unmapped_0x, treat as unknown
                if name.startswith("Unmapped_0x"):
                    status = STATUS_UNKNOWN if val != 0 else STATUS_BLANK
                    category = "unmapped" if val != 0 else "blank"
                else:
                    status = c.get("status", STATUS_MAPPED)
                    category = c.get("category", "settings")

                entry = RegisterEntry(
                    addr=addr,
                    val=val,
                    status=status,
                    name=name,
                    desc=c.get("description", ""),
                    category=category,
                    unit=c.get("unit", ""),
                    baseline_val=base_val
                )
            # 2. Universal platform register
            elif addr in UNIVERSAL_REGISTERS:
                u = UNIVERSAL_REGISTERS[addr]
                entry = RegisterEntry(
                    addr=addr,
                    val=val,
                    status=STATUS_MAPPED,
                    name=u["name"],
                    desc=u["desc"],
                    category=u["category"],
                    unit=u["unit"],
                    baseline_val=base_val
                )
            # 3. Theoretical register
            elif addr in THEORETICAL_REGISTERS:
                t = THEORETICAL_REGISTERS[addr]
                entry = RegisterEntry(
                    addr=addr,
                    val=val,
                    status=STATUS_THEORETICAL,
                    name=t["name"],
                    desc=t["desc"],
                    category=t["category"],
                    unit=t["unit"],
                    baseline_val=base_val
                )
            # 4. Unknown active or blank zero
            else:
                if val != 0:
                    entry = RegisterEntry(
                        addr=addr,
                        val=val,
                        status=STATUS_UNKNOWN,
                        name=f"Unmapped_0x{hex_addr}",
                        desc=f"Model-specific active register (0x{val:04X} / {val})",
                        category="unmapped",
                        unit="",
                        baseline_val=base_val
                    )
                else:
                    entry = RegisterEntry(
                        addr=addr,
                        val=0,
                        status=STATUS_BLANK,
                        name=f"Blank_0x{hex_addr}",
                        desc="Unwritten or zero register (0x0000)",
                        category="blank",
                        unit="",
                        baseline_val=base_val
                    )

            entries.append(entry)

        self.classified_registers = entries
        return entries

    def compute_diff(self, mask_noise: bool = True) -> Dict[str, Any]:
        """
        Compare current snapshot with baseline.
        If mask_noise is enabled, suppresses known jitter offsets (e.g., volatile clock noise).
        """
        if not self.baseline_snapshot:
            self.capture_baseline()

        self.classify_all()
        changed: List[RegisterEntry] = []
        total_bit_flips = 0

        for r in self.classified_registers:
            if r.is_changed:
                changed.append(r)
                total_bit_flips += len(r.bits_flipped)

        return {
            "changed_registers": changed,
            "total_changed_words": len(changed),
            "total_bit_flips": total_bit_flips,
            "timestamp": time.time()
        }

    def get_summary_stats(self) -> Dict[str, Any]:
        """Calculate mapping coverage metrics."""
        if not self.classified_registers:
            self.classify_all()

        mapped = sum(1 for r in self.classified_registers if r.status == STATUS_MAPPED)
        theoretical = sum(1 for r in self.classified_registers if r.status == STATUS_THEORETICAL)
        unknown = sum(1 for r in self.classified_registers if r.status == STATUS_UNKNOWN)
        blank = sum(1 for r in self.classified_registers if r.status == STATUS_BLANK)
        nonzero = mapped + theoretical + unknown
        coverage_pct = (mapped / nonzero * 100.0) if nonzero > 0 else 100.0

        changed = sum(1 for r in self.classified_registers if r.is_changed)

        return {
            "total_words": getattr(self, "max_words", 512),
            "mapped": mapped,
            "theoretical": theoretical,
            "unknown": unknown,
            "blank": blank,
            "nonzero": nonzero,
            "changed": changed,
            "coverage_pct": round(coverage_pct, 1)
        }

    def map_register(
        self,
        addr: int,
        name: str,
        desc: str,
        category: str = "settings",
        unit: str = "",
        status: str = STATUS_MAPPED
    ) -> Tuple[bool, str]:
        """
        Map a register and persist immediately into docs/models/<EF>_*.json.
        Returns (success, message).
        """
        hex_addr = f"{addr:02X}" if getattr(self, "address_width", 4) == 2 else f"{addr:04X}"
        name = name.strip()
        desc = desc.strip()
        category = category.strip() or "settings"
        unit = unit.strip()

        if not name:
            return False, "Register name cannot be empty."

        if "custom_registers" not in self.model_spec:
            self.model_spec["custom_registers"] = {}

        self.model_spec["custom_registers"][hex_addr] = {
            "name": name,
            "description": desc,
            "category": category,
            "unit": unit,
            "status": status,
            "current_hex": f"0x{self.current_eeprom.get(addr, 0):04X}",
            "current_dec": self.current_eeprom.get(addr, 0),
            "last_updated": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%SZ")
        }

        # Atomically write to file
        target_path = self.spec_file_path or os.path.join(self.models_dir, f"{self.ef_code}_Model.json")
        tmp_path = target_path + ".tmp"
        try:
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(self.model_spec, f, indent=2)
            os.replace(tmp_path, target_path)
            self.spec_file_path = target_path

            # Invalidate profiles database cache so SPECTRA main app refreshes
            profiles_db._MODEL_SPECS_CACHE = None
            profiles_db._MODEL_SPEC_LOOKUP_CACHE.clear()

            # Refresh local classifications
            self.classify_all()
            return True, f"Saved 0x{hex_addr} ({name}) to {os.path.basename(target_path)}"
        except Exception as e:
            if os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except Exception:
                    pass
            return False, f"Failed to save specification: {e}"


# ============================================================================
# Terminal ANSI Color & Formatting Utilities
# ============================================================================

class ANSI:
    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    UNDERLINE = "\033[4m"

    GREEN = "\033[92m"
    ORANGE = "\033[38;5;214m"
    RED = "\033[91m"
    GRAY = "\033[90m"
    CYAN = "\033[96m"
    YELLOW = "\033[93m"
    WHITE = "\033[97m"

    BG_DARK = "\033[48;5;235m"
    BG_GREEN = "\033[48;5;22m"
    BG_ORANGE = "\033[48;5;130m"
    BG_RED = "\033[48;5;52m"

    @classmethod
    def badge(cls, status: str) -> str:
        if status == STATUS_MAPPED:
            return f"{cls.GREEN}● MAPPED     {cls.RESET}"
        elif status == STATUS_THEORETICAL:
            return f"{cls.ORANGE}▲ THEORETICAL{cls.RESET}"
        elif status == STATUS_UNKNOWN:
            return f"{cls.RED}■ UNKNOWN    {cls.RESET}"
        else:
            return f"{cls.GRAY}○ BLANK      {cls.RESET}"


def print_banner():
    banner = f"""{ANSI.BOLD}{ANSI.CYAN}
================================================================================
       SPECTRA — Developer Memory Mapper & Differential Logic Scope
               Universal Firmware Reverse Engineering Toolkit
================================================================================{ANSI.RESET}"""
    print(banner)


# ============================================================================
# Terminal Interactive CLI
# ============================================================================

def run_cli(engine: MemoryMapperEngine, initial_sweep: bool = True):
    """Interactive command-line logic scope and memory mapping REPL."""
    print_banner()
    print(f"[*] Connected Appliance: {ANSI.BOLD}{engine.model_family} ({engine.ef_code}){ANSI.RESET}")
    print(f"[*] Specification File:  {ANSI.DIM}{engine.spec_file_path or 'Draft'}{ANSI.RESET}")

    if initial_sweep:
        print("[*] Performing initial 512-word EEPROM sweep...")
        engine.sweep_eeprom(lambda cur, tot, msg: sys.stdout.write(f"\r    [{'=' * cur}{' ' * (tot - cur)}] {cur}/{tot} {msg}"))
        print("\n[*] Initial sweep complete! Baseline captured.")
        engine.capture_baseline()

    stats = engine.get_summary_stats()
    print(f"[*] Coverage: {ANSI.GREEN}🟢 {stats['mapped']} Mapped{ANSI.RESET} | "
          f"{ANSI.ORANGE}🟠 {stats['theoretical']} Theoretical{ANSI.RESET} | "
          f"{ANSI.RED}🔴 {stats['unknown']} Unknown{ANSI.RESET} | "
          f"{ANSI.GRAY}⚪ {stats['blank']} Blank{ANSI.RESET} ({stats['coverage_pct']}%)")
    print(f"[*] Type {ANSI.CYAN}'help'{ANSI.RESET} or {ANSI.CYAN}'?'{ANSI.RESET} for commands.\n")

    prompt = f"{ANSI.BOLD}spectra-mapper> {ANSI.RESET}"
    while True:
        try:
            line = input(prompt).strip()
        except (EOFError, KeyboardInterrupt):
            print("\nExiting Memory Mapper.")
            break

        if not line:
            continue

        parts = line.split()
        cmd = parts[0].lower()
        args = parts[1:]

        if cmd in ("exit", "quit", "q"):
            print("Exiting Memory Mapper.")
            break

        elif cmd in ("help", "?"):
            print(f"""
{ANSI.BOLD}Available Commands:{ANSI.RESET}
  {ANSI.CYAN}read / sweep{ANSI.RESET}              Perform full 512-word sweep from machine
  {ANSI.CYAN}baseline{ANSI.RESET}                  Capture current snapshot as baseline
  {ANSI.CYAN}diff / delta{ANSI.RESET}              Show registers changed since baseline
  {ANSI.CYAN}watch [sec]{ANSI.RESET}               Continuous differential watch loop (default: 1.5s)
  {ANSI.CYAN}list [filter]{ANSI.RESET}             Display registers: all, mapped, theoretical, unknown, blank, diff
  {ANSI.CYAN}inspect <addr>{ANSI.RESET}            Inspect word in hex, dec, ASCII, and 16-bit binary
  {ANSI.CYAN}map <addr> <name> <desc>{ANSI.RESET} Map register and persist to docs/models/<EF>_*.json
  {ANSI.CYAN}stats{ANSI.RESET}                     Display coverage metrics and health scorecards
  {ANSI.CYAN}sim <addr> <hex_val>{ANSI.RESET}      Simulate EEPROM register change (Demo mode only)
  {ANSI.CYAN}help / ?{ANSI.RESET}                  Display this reference
  {ANSI.CYAN}quit / exit{ANSI.RESET}               Exit the tool
""")

        elif cmd in ("read", "sweep"):
            print("[*] Sweeping 512 EEPROM registers...")
            engine.sweep_eeprom(lambda cur, tot, msg: sys.stdout.write(f"\r    [{'=' * cur}{' ' * (tot - cur)}] {cur}/{tot} {msg}"))
            print("\n[+] Sweep complete.")
            diff_res = engine.compute_diff()
            if diff_res["total_changed_words"] > 0:
                print(f"[*] {ANSI.YELLOW}⚡ {diff_res['total_changed_words']} word(s) modified since baseline! Run 'diff' to inspect.{ANSI.RESET}")
            else:
                print("[*] No changes detected relative to baseline.")

        elif cmd == "baseline":
            engine.capture_baseline()
            print(f"[+] Baseline captured successfully ({len(engine.current_eeprom)} words recorded).")

        elif cmd in ("diff", "delta"):
            diff_res = engine.compute_diff()
            changed = diff_res["changed_registers"]
            if not changed:
                print(f"{ANSI.GREEN}✓ No changes detected since baseline.{ANSI.RESET}")
            else:
                print(f"\n{ANSI.BOLD}{ANSI.YELLOW}⚡ {len(changed)} Register(s) Changed ({diff_res['total_bit_flips']} bits flipped):{ANSI.RESET}")
                print(f"{ANSI.BOLD}ADDR   HEX     BASE    DELTA   STATUS        NAME                     BITS FLIPPED{ANSI.RESET}")
                print("-" * 80)
                for r in changed:
                    delta_str = f"{r.delta:+d}"
                    bits_str = ", ".join(f"b{b}" for b in r.bits_flipped)
                    print(f"0x{r.hex_addr} 0x{r.val:04X}  0x{r.baseline_val:04X}  {delta_str:<6} "
                          f"{ANSI.badge(r.status)} {r.name:<24} {bits_str}")
                print()

        elif cmd == "watch":
            interval = 1.5
            if args:
                try:
                    interval = float(args[0])
                except ValueError:
                    pass
            print(f"[*] Entering live differential scope watch mode ({interval}s interval)... Press Ctrl+C to stop.")
            try:
                sweep_count = 0
                while True:
                    time.sleep(interval)
                    sweep_count += 1
                    engine.sweep_eeprom()
                    diff_res = engine.compute_diff()
                    changed = diff_res["changed_registers"]
                    timestamp = datetime.datetime.now().strftime("%H:%M:%S")
                    if changed:
                        print(f"\n[{timestamp}] {ANSI.YELLOW}⚡ CHANGE DETECTED (Sweep #{sweep_count}):{ANSI.RESET}")
                        for r in changed:
                            bits_str = ", ".join(f"b{b}" for b in r.bits_flipped)
                            print(f"    - 0x{r.hex_addr} ({r.name}): 0x{r.baseline_val:04X} -> {ANSI.BOLD}0x{r.val:04X}{ANSI.RESET} "
                                  f"({r.delta:+d}) [Flipped: {bits_str}]")
                    else:
                        sys.stdout.write(f"\r[{timestamp}] Sweep #{sweep_count} OK (No changes)   ")
                        sys.stdout.flush()
            except KeyboardInterrupt:
                print("\n[*] Live watch stopped.")

        elif cmd in ("list", "show"):
            flt = args[0].lower() if args else "all"
            entries = engine.classified_registers or engine.classify_all()

            if flt == "mapped":
                filtered = [r for r in entries if r.status == STATUS_MAPPED]
            elif flt in ("theoretical", "theor"):
                filtered = [r for r in entries if r.status == STATUS_THEORETICAL]
            elif flt in ("unknown", "unmapped"):
                filtered = [r for r in entries if r.status == STATUS_UNKNOWN]
            elif flt == "blank":
                filtered = [r for r in entries if r.status == STATUS_BLANK]
            elif flt in ("diff", "changed"):
                filtered = [r for r in entries if r.is_changed]
            elif flt in ("nonzero", "active"):
                filtered = [r for r in entries if r.val != 0]
            else:
                filtered = entries

            print(f"\n{ANSI.BOLD}ADDR   HEX    DEC    STATUS        NAME                     DESCRIPTION{ANSI.RESET}")
            print("-" * 88)
            for r in filtered:
                print(f"0x{r.hex_addr} {r.val:04X}  {r.val:5d}  {ANSI.badge(r.status)} {r.name:<24} {r.desc[:34]}")
            print(f"Total shown: {len(filtered)} registers.\n")

        elif cmd == "inspect":
            if not args:
                print("Usage: inspect <hex_address> (e.g., inspect 0040)")
                continue
            try:
                addr = int(args[0], 16)
            except ValueError:
                print(f"Invalid hexadecimal address: '{args[0]}'")
                continue

            if not (0 <= addr < engine.max_words):
                print(f"Address out of range (0x0000..0x{engine.max_words - 1:04X}): 0x{addr:04X}")
                continue

            entries = {r.addr: r for r in (engine.classified_registers or engine.classify_all())}
            r = entries.get(addr)
            if not r:
                val = engine.current_eeprom.get(addr, 0)
                r = RegisterEntry(addr, val, STATUS_UNKNOWN, f"Unmapped_0x{addr:04X}", "")

            # Binary representation breakdown
            bin_str = f"{r.val:016b}"
            grouped_bin = f"{bin_str[0:4]} {bin_str[4:8]} {bin_str[8:12]} {bin_str[12:16]}"

            print(f"\n{ANSI.BOLD}=== Register 0x{r.hex_addr} Inspection ==={ANSI.RESET}")
            print(f"  Name:        {ANSI.BOLD}{r.name}{ANSI.RESET}")
            print(f"  Status:      {ANSI.badge(r.status)}")
            print(f"  Description: {r.desc}")
            print(f"  Category:    {r.category} (Unit: {r.unit or 'N/A'})")
            print(f"  Value Hex:   0x{r.val:04X}")
            print(f"  Value Dec:   {r.val} (Signed: {r.signed_val})")
            print(f"  High Byte:   0x{r.high_byte:02X} ({r.high_byte}) | Low Byte: 0x{r.low_byte:02X} ({r.low_byte})")
            print(f"  ASCII:       '{r.ascii_repr}'")
            print(f"  Binary (16): {ANSI.CYAN}{grouped_bin}{ANSI.RESET} (b15 .. b0)")

            # Visual Bitfield breakdown
            bits_header = "  Bits:        "
            bits_row =    "               "
            for b in range(15, -1, -1):
                bit_val = (r.val >> b) & 1
                flipped = b in r.bits_flipped
                col = ANSI.YELLOW if flipped else (ANSI.GREEN if bit_val else ANSI.GRAY)
                bits_row += f"{col}{bit_val}{ANSI.RESET} "
                bits_header += f"{b:2d} "
            print(bits_header)
            print(bits_row)

            if r.is_changed:
                print(f"  {ANSI.YELLOW}⚡ Changed from baseline (0x{r.baseline_val:04X}): Delta {r.delta:+d}{ANSI.RESET}")
            print()

        elif cmd == "map":
            if len(args) < 3:
                print("Usage: map <addr_hex> <name> <description> [category] [unit]")
                continue
            try:
                addr = int(args[0], 16)
            except ValueError:
                print(f"Invalid address: '{args[0]}'")
                continue

            name = args[1]
            desc = args[2]
            cat = args[3] if len(args) > 3 else "settings"
            unit = args[4] if len(args) > 4 else ""

            ok, msg = engine.map_register(addr, name, desc, category=cat, unit=unit)
            if ok:
                print(f"{ANSI.GREEN}✓ {msg}{ANSI.RESET}")
            else:
                print(f"{ANSI.RED}✗ Error: {msg}{ANSI.RESET}")

        elif cmd == "stats":
            stats = engine.get_summary_stats()
            print(f"\n{ANSI.BOLD}Specification Coverage Metrics:{ANSI.RESET}")
            print(f"  Model Family:     {engine.model_family} ({engine.ef_code})")
            print(f"  Total EEPROM:     {stats['total_words']} words (1,024 bytes)")
            print(f"  Active Non-Zero:  {stats['nonzero']} words")
            print(f"  🟢 Mapped:        {stats['mapped']} words")
            print(f"  🟠 Theoretical:   {stats['theoretical']} words")
            print(f"  🔴 Unknown:       {stats['unknown']} words")
            print(f"  ⚪ Blank (0x0000):{stats['blank']} words")
            print(f"  Coverage:         {ANSI.BOLD}{ANSI.GREEN}{stats['coverage_pct']}%{ANSI.RESET} of active registers documented\n")

        elif cmd == "sim":
            if not engine.conn.is_demo:
                print("The 'sim' command is only available when connected to a DEMO / SIMULATION port.")
                continue
            if len(args) < 2:
                print("Usage: sim <addr_hex> <val_hex> (e.g. sim 0014 0004)")
                continue
            try:
                addr = int(args[0], 16)
                val = int(args[1], 16)
            except ValueError:
                print("Invalid hex address or value.")
                continue

            engine.conn.set_mock_eeprom_word(addr, val)
            print(f"[+] Simulated EEPROM update: 0x{addr:04X} := 0x{val:04X}. Run 'read' or 'diff' to see change.")

        else:
            print(f"Unknown command: '{cmd}'. Type 'help' for available commands.")


# ============================================================================
# GTK Graphical Interface (MemoryMapperWindow)
# ============================================================================

try:
    import gi
    gi.require_version("Gtk", "3.0")
    from gi.repository import Gtk, Gdk, GLib, Pango
    HAS_GTK = True
except Exception:
    HAS_GTK = False


if HAS_GTK:
    class MemoryMapperWindow(Gtk.Window):
        """
        GTK3 Developer Memory Mapper & Differential Scope Window.
        Provides visual register grid, 16-bit binary inspector, live delta pulse,
        and quick-mapping dialog for filling community blanks.
        """

        def __init__(self, parent_app=None, initial_port: Optional[str] = ""):
            super().__init__(title="SPECTRA — Developer Memory Mapper & Differential Logic Scope")
            self.parent_app = parent_app
            self.initial_port = initial_port

            self.set_default_size(1080, 720)
            self.set_size_request(800, 520)
            self.set_position(Gtk.WindowPosition.CENTER)

            if parent_app and hasattr(parent_app, "get_icon"):
                icon = parent_app.get_icon()
                if icon:
                    self.set_icon(icon)

            self.conn: Optional[serial_io.JuraSerialConnection] = None
            self.engine: Optional[MemoryMapperEngine] = None
            self.engine_lock = threading.Lock()
            self.is_sweeping: bool = False
            self.is_capturing_baseline: bool = False
            self.is_watching: bool = False
            self.watch_thread: Optional[threading.Thread] = None
            self.mask_noise: bool = True
            self.current_filter: str = "all"
            self.search_query: str = ""
            self.current_selected_addr: Optional[int] = None
            self.row_iters: Dict[int, Gtk.TreeIter] = {}
            self.prev_row_values: Dict[int, tuple] = {}

            self._apply_css()
            self._create_ui()
            self.connect("destroy", self._on_destroy)

            # Connect port asynchronously
            if initial_port is not None:
                if initial_port:
                    self._connect_to_port(initial_port)
                else:
                    self._connect_to_port("DEMO / SIMULATION (Jura Impressa XJ5)")

        def _on_destroy(self, *args):
            """Cleanly terminate background threads when window is closed."""
            self.is_watching = False

        def _apply_css(self):
            css_provider = Gtk.CssProvider()
            css = b"""
            window {
                background-color: #1e1e2e;
                color: #cdd6f4;
                font-family: sans-serif;
            }
            .header-box {
                background-color: #181825;
                border-bottom: 1px solid #313244;
                padding: 10px 14px;
            }
            .pill-badge {
                border-radius: 6px;
                padding: 4px 10px;
                font-size: 11px;
                font-weight: bold;
                transition: all 200ms ease-in-out;
            }
            .pill-badge:hover {
                box-shadow: 0 2px 6px rgba(0, 0, 0, 0.35);
            }
            .badge-mapped {
                background-color: #1b382b;
                color: #a6e3a1;
                border: 1px solid #a6e3a1;
            }
            .badge-theor {
                background-color: #3e2b17;
                color: #fab387;
                border: 1px solid #fab387;
            }
            .badge-unknown {
                background-color: #3b1c24;
                color: #f38ba8;
                border: 1px solid #f38ba8;
            }
            .badge-blank {
                background-color: #181825;
                color: #6c7086;
                border: 1px solid #45475a;
            }
            .badge-changed {
                background-color: #1a324b;
                color: #89dceb;
                border: 1px solid #89dceb;
            }

            button {
                border-radius: 6px;
                min-height: 28px;
                transition: all 200ms ease-in-out;
            }

            button.primary-btn {
                background-image: linear-gradient(to bottom, #89b4fa, #74c7ec);
                color: #11111b;
                font-weight: bold;
                border-radius: 6px;
                padding: 6px 16px;
                border: 1px solid #74c7ec;
                min-height: 28px;
                transition: all 200ms ease-in-out;
            }
            button.primary-btn:hover {
                background-image: linear-gradient(to bottom, #b4befe, #89b4fa);
                border-color: #b4befe;
                box-shadow: 0 2px 10px rgba(137, 180, 250, 0.4);
            }
            button.primary-btn:active {
                background-image: linear-gradient(to bottom, #74c7ec, #89b4fa);
                box-shadow: inset 0 2px 4px rgba(0, 0, 0, 0.4);
            }
            button.primary-btn:disabled {
                background-image: none;
                background-color: #313244;
                color: #585b70;
                border: 1px solid #45475a;
                box-shadow: none;
            }

            button.secondary-btn {
                background-color: #24273a;
                background-image: none;
                color: #cdd6f4;
                border-radius: 6px;
                padding: 6px 14px;
                border: 1px solid #45475a;
                min-height: 28px;
                font-weight: 500;
                transition: all 200ms ease-in-out;
            }
            button.secondary-btn:hover {
                background-color: #313244;
                border-color: #89b4fa;
                color: #89b4fa;
                box-shadow: 0 2px 8px rgba(0, 0, 0, 0.3);
            }
            button.secondary-btn:active {
                background-color: #181825;
                box-shadow: inset 0 2px 4px rgba(0, 0, 0, 0.4);
            }
            button.secondary-btn:disabled {
                background-color: #1e1e2e;
                color: #585b70;
                border-color: #313244;
                box-shadow: none;
            }

            button.toggle-btn {
                background-color: #24273a;
                background-image: none;
                color: #cdd6f4;
                border-radius: 6px;
                padding: 6px 14px;
                border: 1px solid #45475a;
                min-height: 28px;
                font-weight: 500;
                transition: all 200ms ease-in-out;
            }
            button.toggle-btn:hover {
                background-color: #313244;
                border-color: #585b70;
                box-shadow: 0 2px 8px rgba(0, 0, 0, 0.25);
            }
            button.toggle-btn:checked {
                background-color: #a6e3a1;
                background-image: linear-gradient(to bottom, #a6e3a1, #94e2d5);
                color: #11111b;
                font-weight: bold;
                border: 1px solid #a6e3a1;
                box-shadow: 0 0 12px rgba(166, 227, 161, 0.45);
            }
            button.toggle-btn:checked:hover {
                background-image: linear-gradient(to bottom, #b4befe, #89b4fa);
                border-color: #b4befe;
                color: #11111b;
            }

            button.action-btn {
                background-image: linear-gradient(to bottom, #fab387, #f9e2af);
                color: #11111b;
                font-weight: bold;
                border-radius: 6px;
                padding: 6px 14px;
                border: 1px solid #fab387;
                min-height: 28px;
                transition: all 200ms ease-in-out;
            }
            button.action-btn:hover {
                background-image: linear-gradient(to bottom, #f9e2af, #fab387);
                border-color: #f9e2af;
                box-shadow: 0 2px 10px rgba(250, 179, 135, 0.4);
            }
            button.action-btn:active {
                background-image: linear-gradient(to bottom, #fab387, #e0a37e);
                box-shadow: inset 0 2px 4px rgba(0, 0, 0, 0.4);
            }
            button.action-btn:disabled {
                background-image: none;
                background-color: #313244;
                color: #585b70;
                border-color: #45475a;
                box-shadow: none;
            }

            .filter-pill {
                background-color: #24273a;
                background-image: none;
                color: #a6adc8;
                border: 1px solid #363a4f;
                border-radius: 14px;
                padding: 4px 12px;
                font-size: 11px;
                font-weight: 500;
                min-height: 26px;
                transition: all 180ms ease-in-out;
            }
            .filter-pill:hover {
                background-color: #313244;
                color: #cdd6f4;
                border-color: #585b70;
            }
            .filter-pill:checked {
                background-color: #89b4fa;
                background-image: linear-gradient(to bottom, #89b4fa, #74c7ec);
                color: #11111b;
                font-weight: bold;
                border-color: #89b4fa;
                box-shadow: 0 0 10px rgba(137, 180, 250, 0.4);
            }

            entry {
                background-color: #181825;
                color: #cdd6f4;
                border: 1px solid #45475a;
                border-radius: 6px;
                padding: 4px 8px;
                transition: all 200ms ease-in-out;
            }
            entry:focus {
                border-color: #89b4fa;
                box-shadow: 0 0 6px rgba(137, 180, 250, 0.35);
            }

            treeview {
                background-color: #181825;
                color: #cdd6f4;
                border: 1px solid #313244;
            }
            treeview:selected {
                background-color: #45475a;
                color: #cdd6f4;
            }

            .bit-btn {
                font-family: monospace;
                font-size: 12px;
                font-weight: bold;
                min-width: 28px;
                padding: 4px 6px;
                border-radius: 4px;
                border: 1px solid #45475a;
                background-color: #181825;
                color: #6c7086;
                transition: all 150ms ease-in-out;
            }
            .bit-btn:hover {
                border-color: #89b4fa;
                color: #cdd6f4;
                background-color: #24273a;
            }
            .bit-on {
                background-color: #1b382b;
                color: #a6e3a1;
                border-color: #a6e3a1;
                box-shadow: 0 0 8px rgba(166, 227, 161, 0.35);
            }
            .bit-flipped {
                background-color: #3e2b17;
                color: #f9e2af;
                border-color: #f9e2af;
                box-shadow: 0 0 10px rgba(249, 226, 175, 0.5);
            }

            textview text {
                background-color: #11111b;
                color: #a6e3a1;
                font-family: monospace;
                font-size: 11px;
            }
            """
            css_provider.load_from_data(css)
            screen = Gdk.Screen.get_default()
            if screen:
                Gtk.StyleContext.add_provider_for_screen(screen, css_provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

        def _create_ui(self):
            main_vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
            self.add(main_vbox)

            # 1. Header Toolbar
            header_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
            header_box.get_style_context().add_class("header-box")
            main_vbox.pack_start(header_box, False, False, 0)

            title_vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
            lbl_title = Gtk.Label()
            lbl_title.set_markup("<b><span size='large' color='#89b4fa'>🔬 SPECTRA Memory Mapper</span> <span color='#fab387' size='small'>Dev Logic Scope</span></b>")
            lbl_title.set_xalign(0.0)
            title_vbox.pack_start(lbl_title, False, False, 0)

            self.lbl_subtitle = Gtk.Label(label="Connecting to target machine...")
            self.lbl_subtitle.set_xalign(0.0)
            title_vbox.pack_start(self.lbl_subtitle, False, False, 0)
            header_box.pack_start(title_vbox, False, False, 0)

            # Spacer
            spacer = Gtk.Box()
            spacer.set_hexpand(True)
            header_box.pack_start(spacer, True, True, 0)

            # Stats Pills
            self.pill_mapped = Gtk.Label(label="🟢 0 Mapped")
            self.pill_mapped.get_style_context().add_class("pill-badge")
            self.pill_mapped.get_style_context().add_class("badge-mapped")
            header_box.pack_start(self.pill_mapped, False, False, 0)

            self.pill_theor = Gtk.Label(label="🟠 0 Theor.")
            self.pill_theor.get_style_context().add_class("pill-badge")
            self.pill_theor.get_style_context().add_class("badge-theor")
            header_box.pack_start(self.pill_theor, False, False, 0)

            self.pill_unknown = Gtk.Label(label="🔴 0 Unknown")
            self.pill_unknown.get_style_context().add_class("pill-badge")
            self.pill_unknown.get_style_context().add_class("badge-unknown")
            header_box.pack_start(self.pill_unknown, False, False, 0)

            self.pill_blank = Gtk.Label(label="⚪ 0 Blank")
            self.pill_blank.get_style_context().add_class("pill-badge")
            self.pill_blank.get_style_context().add_class("badge-blank")
            header_box.pack_start(self.pill_blank, False, False, 0)

            self.pill_changed = Gtk.Label(label="⚡ 0 Delta")
            self.pill_changed.get_style_context().add_class("pill-badge")
            self.pill_changed.get_style_context().add_class("badge-changed")
            header_box.pack_start(self.pill_changed, False, False, 0)

            # Control Action Buttons
            self.btn_sweep = Gtk.Button(label="⚡ Full Sweep")
            self.btn_sweep.get_style_context().add_class("primary-btn")
            self.btn_sweep.connect("clicked", lambda w: self._on_sweep_clicked())
            header_box.pack_start(self.btn_sweep, False, False, 0)

            self.btn_baseline = Gtk.Button(label="📸 Baseline")
            self.btn_baseline.get_style_context().add_class("secondary-btn")
            self.btn_baseline.set_tooltip_text("Capture current EEPROM values as baseline reference")
            self.btn_baseline.connect("clicked", lambda w: self._on_baseline_clicked())
            header_box.pack_start(self.btn_baseline, False, False, 0)

            self.btn_watch = Gtk.ToggleButton(label="⏱️ Live Diff")
            self.btn_watch.get_style_context().add_class("toggle-btn")
            self.btn_watch.set_tooltip_text("Continuously poll and display real-time memory modifications")
            self.btn_watch.connect("toggled", self._on_watch_toggled)
            header_box.pack_start(self.btn_watch, False, False, 0)

            # 2. Filter & Search Strip
            filter_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
            filter_box.set_border_width(8)
            main_vbox.pack_start(filter_box, False, False, 0)

            lbl_search = Gtk.Label(label="🔍 Filter:")
            filter_box.pack_start(lbl_search, False, False, 0)

            self.search_entry = Gtk.SearchEntry()
            self.search_entry.set_placeholder_text("Address (e.g. 0040) or Name...")
            self.search_entry.connect("search-changed", self._on_search_changed)
            filter_box.pack_start(self.search_entry, True, True, 0)

            # Filter Radio/Pills
            self.filter_buttons = {}
            max_w = self.engine.max_words if self.engine else 512
            for tag, lbl in [("all", f"All ({max_w})"), ("mapped", "🟢 Mapped"), ("theor", "🟠 Theor."),
                             ("unknown", "🔴 Unknown"), ("changed", "⚡ Changed")]:
                btn = Gtk.RadioButton.new_with_label_from_widget(
                    self.filter_buttons.get("all"), lbl
                )
                btn.set_mode(False)
                btn.get_style_context().add_class("filter-pill")
                btn.connect("toggled", self._on_filter_toggled, tag)
                filter_box.pack_start(btn, False, False, 0)
                self.filter_buttons[tag] = btn

            # Map Register Action
            self.btn_map_action = Gtk.Button(label="✏️ Map Register...")
            self.btn_map_action.get_style_context().add_class("action-btn")
            self.btn_map_action.set_tooltip_text("Open mapping editor to name and persist selected register")
            self.btn_map_action.connect("clicked", lambda w: self._on_map_dialog_clicked())
            filter_box.pack_start(self.btn_map_action, False, False, 4)

            # 3. Main TreeView Split Paned
            paned = Gtk.Paned(orientation=Gtk.Orientation.VERTICAL)
            paned.set_position(420)
            main_vbox.pack_start(paned, True, True, 0)

            # TreeView & ListStore
            # Store columns: 0: StatusText, 1: AddrHex, 2: ValHex, 3: ValDec, 4: DeltaHex, 5: Name, 6: Desc, 7: Cat, 8: AddrInt, 9: PangoMarkup
            self.store = Gtk.ListStore(str, str, str, str, str, str, str, str, int, str)
            self.tree_filter = self.store.filter_new()
            self.tree_filter.set_visible_func(self._filter_row_visible)

            self.tree = Gtk.TreeView(model=self.tree_filter)
            self.tree.get_selection().connect("changed", self._on_tree_selection_changed)
            self.tree.connect("row-activated", lambda t, p, c: self._on_map_dialog_clicked())

            cols = [
                ("Status", 0, 110),
                ("Address", 1, 80),
                ("Hex", 2, 70),
                ("Dec", 3, 70),
                ("Baseline / Delta", 4, 120),
                ("Register Name", 5, 200),
                ("Description", 6, 260),
                ("Category", 7, 100),
            ]

            for title, col_idx, width in cols:
                renderer = Gtk.CellRendererText()
                if col_idx in (1, 2, 3, 4):
                    renderer.set_property("family", "monospace")
                col = Gtk.TreeViewColumn(title, renderer, markup=9 if col_idx == 0 else col_idx)
                col.set_resizable(True)
                col.set_min_width(width)
                self.tree.append_column(col)

            scrolled_tree = Gtk.ScrolledWindow()
            scrolled_tree.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
            scrolled_tree.add(self.tree)
            paned.pack1(scrolled_tree, True, False)

            # 4. Bottom Detail & Bitfield Inspector
            bottom_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
            bottom_box.set_border_width(10)
            paned.pack2(bottom_box, False, False)

            # Left Inspector Pane (16-bit binary)
            inspector_frame = Gtk.Frame(label="16-Bit Register Bitfield & Data Breakdown")
            inspector_frame.set_hexpand(True)
            bottom_box.pack_start(inspector_frame, True, True, 0)

            insp_vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
            insp_vbox.set_border_width(8)
            inspector_frame.add(insp_vbox)

            # Bit Indicator Buttons (b15 .. b0)
            bit_grid = Gtk.Grid()
            bit_grid.set_column_spacing(4)
            bit_grid.set_row_spacing(2)
            insp_vbox.pack_start(bit_grid, False, False, 0)

            self.bit_labels = []
            for b in range(15, -1, -1):
                col_pos = 15 - b
                lbl_b = Gtk.Label(label=f"b{b}")
                lbl_b.get_style_context().add_class("card-label")
                bit_grid.attach(lbl_b, col_pos, 0, 1, 1)

                btn_bit = Gtk.Label(label="0")
                btn_bit.get_style_context().add_class("bit-btn")
                btn_bit.set_size_request(28, 24)
                bit_grid.attach(btn_bit, col_pos, 1, 1, 1)
                self.bit_labels.append(btn_bit)

            # Values row
            self.lbl_insp_breakdown = Gtk.Label()
            self.lbl_insp_breakdown.set_markup("Select any register to inspect bitfield and values.")
            self.lbl_insp_breakdown.set_xalign(0.0)
            insp_vbox.pack_start(self.lbl_insp_breakdown, False, False, 0)

            # Right Pane: Differential Event Stream
            log_frame = Gtk.Frame(label="Live Differential Event Scope")
            log_frame.set_size_request(380, -1)
            bottom_box.pack_start(log_frame, False, False, 0)

            scrolled_log = Gtk.ScrolledWindow()
            self.log_buffer = Gtk.TextBuffer()
            self.log_view = Gtk.TextView(buffer=self.log_buffer)
            self.log_view.set_editable(False)
            self.log_view.set_cursor_visible(False)
            scrolled_log.add(self.log_view)
            log_frame.add(scrolled_log)

            self._log_event("Memory Mapper initialized. Ready for sweeps.")

        def _log_event(self, msg: str):
            t = datetime.datetime.now().strftime("%H:%M:%S")
            line = f"[{t}] {msg}\n"
            GLib.idle_add(self._append_log_text, line)

        def _append_log_text(self, text: str):
            self.log_buffer.insert(self.log_buffer.get_end_iter(), text)
            # Bound buffer to last 200 lines
            if self.log_buffer.get_line_count() > 200:
                start = self.log_buffer.get_start_iter()
                end = self.log_buffer.get_iter_at_line(50)
                self.log_buffer.delete(start, end)
            adj = self.log_view.get_vadjustment()
            if adj:
                adj.set_value(adj.get_upper() - adj.get_page_size())

        def _connect_to_port(self, port_name: str):
            self.lbl_subtitle.set_markup(f"<i>Connecting to {port_name}...</i>")
            self.btn_sweep.set_sensitive(False)
            self.btn_baseline.set_sensitive(False)
            self.btn_watch.set_sensitive(False)
            self.btn_map_action.set_sensitive(False)

            def worker():
                try:
                    with self.engine_lock:
                        self.conn = serial_io.JuraSerialConnection(port_name)
                        self.engine = MemoryMapperEngine(self.conn)
                    GLib.idle_add(self._on_connect_success, port_name)
                except Exception as e:
                    GLib.idle_add(self._on_connect_failed, port_name, str(e))

            threading.Thread(target=worker, daemon=True).start()

        def _on_connect_success(self, port_name: str):
            if not self.engine:
                return
            model_str = f"{self.engine.model_family} ({self.engine.ef_code})"
            spec_str = os.path.basename(self.engine.spec_file_path or 'Draft')
            self.lbl_subtitle.set_markup(f"<b>Target:</b> {model_str} | <b>Port:</b> {port_name} | <b>Spec:</b> {spec_str}")
            self._log_event(f"Connected to {model_str} on {port_name}")

            self.btn_sweep.set_sensitive(True)
            self.btn_baseline.set_sensitive(True)
            self.btn_watch.set_sensitive(True)
            self.btn_map_action.set_sensitive(True)

            all_btn = self.filter_buttons.get("all")
            if all_btn:
                all_btn.set_label(f"All ({self.engine.max_words})")

            # Trigger initial background sweep
            self._on_sweep_clicked()

        def _on_connect_failed(self, port_name: str, err: str):
            self.lbl_subtitle.set_markup(f"<span color='#f38ba8'>Connection error: {err}</span>")
            self._log_event(f"Error opening port {port_name}: {err}")
            self.btn_sweep.set_sensitive(True)

        def _on_sweep_clicked(self):
            if self.is_sweeping or not self.engine:
                return
            self.is_sweeping = True
            self.btn_sweep.set_sensitive(False)
            self.btn_sweep.set_label("⏳ Sweeping...")
            self.btn_baseline.set_sensitive(False)

            def worker():
                diff_res = None
                try:
                    with self.engine_lock:
                        self.engine.sweep_eeprom()
                        if not self.engine.baseline_snapshot:
                            self.engine.capture_baseline()
                        diff_res = self.engine.compute_diff(self.mask_noise)
                except Exception as e:
                    self._log_event(f"Sweep error: {e}")
                finally:
                    GLib.idle_add(self._on_sweep_done, diff_res)

            threading.Thread(target=worker, daemon=True).start()

        def _on_sweep_done(self, diff_res):
            self.btn_sweep.set_label("⚡ Full Sweep")
            self.btn_sweep.set_sensitive(True)
            self.btn_baseline.set_sensitive(True)
            self.is_sweeping = False
            if diff_res is not None:
                self._update_tree_model(diff_res)

        def _on_baseline_clicked(self):
            if not self.engine or self.is_sweeping or self.is_capturing_baseline:
                return
            self.is_capturing_baseline = True
            self.btn_baseline.set_sensitive(False)
            self.btn_baseline.set_label("⏳ Capturing...")

            def worker():
                diff = None
                try:
                    with self.engine_lock:
                        self.engine.capture_baseline()
                        diff = self.engine.compute_diff(self.mask_noise)
                except Exception as e:
                    self._log_event(f"Baseline error: {e}")
                finally:
                    GLib.idle_add(self._on_baseline_done, diff)

            threading.Thread(target=worker, daemon=True).start()

        def _on_baseline_done(self, diff):
            self.btn_baseline.set_label("📸 Baseline")
            self.btn_baseline.set_sensitive(True)
            self.is_capturing_baseline = False
            self._log_event("Captured new baseline reference.")
            if diff is not None:
                self._update_tree_model(diff)

        def _on_watch_toggled(self, btn):
            self.is_watching = btn.get_active()
            if self.is_watching:
                self.btn_watch.set_label("🔴 Live Diff [ON]")
                self._log_event("Live Differential Scope watch started.")
                self.watch_thread = threading.Thread(target=self._watch_loop, daemon=True)
                self.watch_thread.start()
            else:
                self.btn_watch.set_label("⏱️ Live Diff")
                self._log_event("Live Differential Scope watch stopped.")

        def _watch_loop(self):
            while self.is_watching and self.engine:
                time.sleep(0.8)
                if not self.is_watching:
                    break
                # Non-blocking lock to avoid contention with manual sweeps
                acquired = self.engine_lock.acquire(blocking=False)
                if not acquired:
                    continue
                try:
                    self.engine.sweep_eeprom()
                    diff = self.engine.compute_diff(self.mask_noise)
                    changed = diff.get("changed_registers", [])
                    if changed:
                        for r in changed:
                            bits = ", ".join(f"b{b}" for b in r.bits_flipped)
                            self._log_event(f"⚡ 0x{r.hex_addr} ({r.name}): 0x{r.baseline_val:04X} -> 0x{r.val:04X} ({r.delta:+d}) [{bits}]")
                    GLib.idle_add(self._update_tree_model, diff)
                except Exception as e:
                    self._log_event(f"Watch error: {e}")
                    break
                finally:
                    self.engine_lock.release()

        def _get_badge_markup(self, status: str) -> str:
            if status == STATUS_MAPPED:
                return "<span color='#a6e3a1'>● Mapped</span>"
            elif status == STATUS_THEORETICAL:
                return "<span color='#fab387'>▲ Theor.</span>"
            elif status == STATUS_UNKNOWN:
                return "<span color='#f38ba8'>■ Unknown</span>"
            else:
                return "<span color='#6c7086'>○ Blank</span>"

        def _update_tree_model(self, diff_res):
            if not self.engine:
                return

            registers = self.engine.classified_registers
            if not registers:
                return

            # Fast in-place updates: only populate from scratch if row count changed or uninitialized
            if len(self.row_iters) != len(registers):
                self.store.clear()
                self.row_iters.clear()
                self.prev_row_values.clear()

                for r in registers:
                    badge_markup = self._get_badge_markup(r.status)
                    delta_str = f"0x{r.baseline_val:04X} ({r.delta:+d})" if r.is_changed else f"0x{r.baseline_val:04X} (+0)"
                    row_data = [
                        r.status,
                        f"0x{r.hex_addr}",
                        f"0x{r.val:04X}",
                        f"{r.val}",
                        delta_str,
                        r.name,
                        r.desc,
                        r.category,
                        r.addr,
                        badge_markup
                    ]
                    tree_iter = self.store.append(row_data)
                    self.row_iters[r.addr] = tree_iter
                    self.prev_row_values[r.addr] = (r.val, r.baseline_val, r.status, r.name, r.desc, r.is_changed)
                self.tree_filter.refilter()
            else:
                # IN-PLACE MUTATION: only update rows that actually changed!
                had_filter_impact = False
                for r in registers:
                    prev = self.prev_row_values.get(r.addr)
                    curr = (r.val, r.baseline_val, r.status, r.name, r.desc, r.is_changed)
                    if prev != curr:
                        tree_iter = self.row_iters.get(r.addr)
                        if tree_iter:
                            badge_markup = self._get_badge_markup(r.status)
                            delta_str = f"0x{r.baseline_val:04X} ({r.delta:+d})" if r.is_changed else f"0x{r.baseline_val:04X} (+0)"
                            self.store[tree_iter] = [
                                r.status,
                                f"0x{r.hex_addr}",
                                f"0x{r.val:04X}",
                                f"{r.val}",
                                delta_str,
                                r.name,
                                r.desc,
                                r.category,
                                r.addr,
                                badge_markup
                            ]
                            self.prev_row_values[r.addr] = curr
                            if (prev and prev[5] != curr[5]) or self.current_filter in ("changed", "unknown", "theor", "mapped"):
                                had_filter_impact = True

                if had_filter_impact:
                    self.tree_filter.refilter()
                    self._restore_selection()

            # Update scorecards
            stats = self.engine.get_summary_stats()
            self.pill_mapped.set_text(f"🟢 {stats['mapped']} Mapped")
            self.pill_theor.set_text(f"🟠 {stats['theoretical']} Theor.")
            self.pill_unknown.set_text(f"🔴 {stats['unknown']} Unknown")
            self.pill_blank.set_text(f"⚪ {stats['blank']} Blank")
            self.pill_changed.set_text(f"⚡ {stats['changed']} Delta")

            # Live update 16-bit inspector if currently inspected register changed
            if self.current_selected_addr is not None:
                self._update_inspector_for_addr(self.current_selected_addr)

        def _restore_selection(self):
            if self.current_selected_addr is None:
                return
            def find_row(model, path, iter, user_data):
                if model.get_value(iter, 8) == self.current_selected_addr:
                    user_data.append(path)
                    return True
                return False
            found = []
            self.tree_filter.foreach(find_row, found)
            if found:
                self.tree.get_selection().select_path(found[0])

        def _filter_row_visible(self, model, iter, data):
            if not self.engine:
                return True

            status = model.get_value(iter, 0) or ""
            addr_hex = (model.get_value(iter, 1) or "").lower()
            name = (model.get_value(iter, 5) or "").lower()
            desc = (model.get_value(iter, 6) or "").lower()
            delta_str = model.get_value(iter, 4) or ""

            # Search text query
            q = self.search_query.lower()
            if q:
                if q not in addr_hex and q not in name and q not in desc:
                    return False

            # Button filter
            if self.current_filter == "mapped":
                return status == STATUS_MAPPED
            elif self.current_filter == "theor":
                return status == STATUS_THEORETICAL
            elif self.current_filter == "unknown":
                return status == STATUS_UNKNOWN
            elif self.current_filter == "changed":
                return not delta_str.endswith("(+0)")
            return True

        def _on_filter_toggled(self, btn, tag):
            if btn.get_active():
                self.current_filter = tag
                self.tree_filter.refilter()
                self._restore_selection()

        def _on_search_changed(self, entry):
            self.search_query = entry.get_text().strip()
            self.tree_filter.refilter()
            self._restore_selection()

        def _on_tree_selection_changed(self, selection):
            model, tree_iter = selection.get_selected()
            if not tree_iter:
                return
            addr = model.get_value(tree_iter, 8)
            self.current_selected_addr = addr
            self._update_inspector_for_addr(addr)

        def _update_inspector_for_addr(self, addr: int):
            if not self.engine:
                return

            # Find matching RegisterEntry
            r_match = next((r for r in self.engine.classified_registers if r.addr == addr), None)
            if not r_match:
                return

            val = r_match.val
            base_val = r_match.baseline_val
            flipped_bits = r_match.bits_flipped
            name = r_match.name
            desc = r_match.desc

            # Update bit indicator buttons (b15 down to b0)
            for b in range(16):
                idx = 15 - b
                btn = self.bit_labels[idx]
                bit_val = (val >> b) & 1
                btn.set_text(str(bit_val))

                ctx = btn.get_style_context()
                ctx.remove_class("bit-on")
                ctx.remove_class("bit-flipped")

                if b in flipped_bits:
                    ctx.add_class("bit-flipped")
                elif bit_val:
                    ctx.add_class("bit-on")

            hb = (val >> 8) & 0xFF
            lb = val & 0xFF
            signed_val = val if val < 32768 else val - 65536
            c1 = chr(hb) if 32 <= hb <= 126 else "."
            c2 = chr(lb) if 32 <= lb <= 126 else "."

            delta_info = ""
            if r_match.is_changed:
                delta_info = f" | <span color='#89dceb'><b>Delta: {r_match.delta:+d} (Baseline: 0x{base_val:04X})</b></span>"

            markup = (
                f"<b>0x{addr:04X} ({name}):</b> Hex <code>0x{val:04X}</code> | Dec: <code>{val}</code> (Signed: {signed_val}) | "
                f"High Byte: <code>0x{hb:02X}</code> ({hb}) | Low Byte: <code>0x{lb:02X}</code> ({lb}) | ASCII: '<code>{c1}{c2}</code>'{delta_info}\n"
                f"<span color='#a6adc8'>{desc}</span>"
            )
            self.lbl_insp_breakdown.set_markup(markup)

        def _on_map_dialog_clicked(self):
            selection = self.tree.get_selection()
            model, tree_iter = selection.get_selected()

            # Resilient selection: if None, restore from active address or first row
            if not tree_iter and self.current_selected_addr is not None:
                def find_row(model, path, iter, user_data):
                    if model.get_value(iter, 8) == self.current_selected_addr:
                        user_data.append(iter)
                        return True
                    return False
                found = []
                self.tree_filter.foreach(find_row, found)
                if found:
                    tree_iter = found[0]
                    self.tree.get_selection().select_iter(tree_iter)
                    model = self.tree_filter

            if not tree_iter:
                first_iter = self.tree_filter.get_iter_first()
                if first_iter:
                    tree_iter = first_iter
                    self.tree.get_selection().select_iter(tree_iter)
                    model = self.tree_filter
                else:
                    self._log_event("⚠️ Please select a register in the table before clicking Map Register.")
                    return

            addr = model.get_value(tree_iter, 8)
            val_hex = model.get_value(tree_iter, 2)
            name = model.get_value(tree_iter, 5)
            desc = model.get_value(tree_iter, 6)
            cat = model.get_value(tree_iter, 7)

            dialog = Gtk.Dialog(
                title=f"Map Register 0x{addr:04X} — Persist Model Specification",
                transient_for=self,
                flags=Gtk.DialogFlags.MODAL | Gtk.DialogFlags.DESTROY_WITH_PARENT
            )
            dialog.add_buttons(
                Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL,
                "💾 Save & Persist", Gtk.ResponseType.OK
            )
            dialog.set_default_size(440, 280)

            btn_ok = dialog.get_widget_for_response(Gtk.ResponseType.OK)
            if btn_ok:
                btn_ok.get_style_context().add_class("primary-btn")
            btn_cancel = dialog.get_widget_for_response(Gtk.ResponseType.CANCEL)
            if btn_cancel:
                btn_cancel.get_style_context().add_class("secondary-btn")

            content = dialog.get_content_area()
            content.set_spacing(10)
            content.set_border_width(12)

            grid = Gtk.Grid()
            grid.set_column_spacing(10)
            grid.set_row_spacing(8)
            content.pack_start(grid, True, True, 0)

            grid.attach(Gtk.Label(label="Register Address:"), 0, 0, 1, 1)
            lbl_addr = Gtk.Label(label=f"0x{addr:04X} ({val_hex})")
            lbl_addr.set_xalign(0.0)
            grid.attach(lbl_addr, 1, 0, 1, 1)

            grid.attach(Gtk.Label(label="Identifier Name:"), 0, 1, 1, 1)
            entry_name = Gtk.Entry()
            # If name is generic unmapped, leave empty for easy typing
            default_name = "" if name.startswith("Unmapped_0x") or name.startswith("Blank_0x") else name
            entry_name.set_text(default_name)
            entry_name.set_placeholder_text("e.g. Water_Hardness_dH")
            grid.attach(entry_name, 1, 1, 1, 1)

            grid.attach(Gtk.Label(label="Description:"), 0, 2, 1, 1)
            entry_desc = Gtk.Entry()
            entry_desc.set_text(desc if not desc.startswith("Model-specific") else "")
            entry_desc.set_placeholder_text("e.g. Water hardness level configured by user")
            grid.attach(entry_desc, 1, 2, 1, 1)

            grid.attach(Gtk.Label(label="Category:"), 0, 3, 1, 1)
            combo_cat = Gtk.ComboBoxText()
            for c in ["settings", "counters", "calibration", "hardware", "maintenance", "recipe", "faults", "spdl", "custom"]:
                combo_cat.append_text(c)
            combo_cat.set_active(0)
            grid.attach(combo_cat, 1, 3, 1, 1)

            grid.attach(Gtk.Label(label="Unit:"), 0, 4, 1, 1)
            entry_unit = Gtk.Entry()
            entry_unit.set_placeholder_text("e.g. °dH, dl, ticks, sec")
            grid.attach(entry_unit, 1, 4, 1, 1)

            grid.attach(Gtk.Label(label="Status:"), 0, 5, 1, 1)
            combo_status = Gtk.ComboBoxText()
            combo_status.append_text("🟢 Mapped (Confirmed)")
            combo_status.append_text("🟠 Theoretical (Unconfirmed)")
            combo_status.set_active(0)
            grid.attach(combo_status, 1, 5, 1, 1)

            dialog.show_all()
            resp = dialog.run()

            if resp == Gtk.ResponseType.OK:
                new_name = entry_name.get_text().strip()
                new_desc = entry_desc.get_text().strip()
                new_cat = combo_cat.get_active_text() or "settings"
                new_unit = entry_unit.get_text().strip()
                status_choice = STATUS_MAPPED if combo_status.get_active() == 0 else STATUS_THEORETICAL

                if new_name:
                    ok, msg = self.engine.map_register(
                        addr=addr,
                        name=new_name,
                        desc=new_desc,
                        category=new_cat,
                        unit=new_unit,
                        status=status_choice
                    )
                    if ok:
                        self._log_event(f"Mapped 0x{addr:04X} -> {new_name}")
                        self._update_tree_model(self.engine.compute_diff(self.mask_noise))
                    else:
                        self._log_event(f"Error mapping register: {msg}")

            dialog.destroy()


# ============================================================================
# Main Entry Point
# ============================================================================

def main():
    parser = argparse.ArgumentParser(description="SPECTRA Developer Memory Mapper & Differential Scope Tool")
    parser.add_argument("--port", type=str, default="", help="Serial port or simulation profile (e.g. /dev/ttyUSB0)")
    parser.add_argument("--cli", action="store_true", help="Launch interactive terminal CLI mode")
    parser.add_argument("--gui", action="store_true", help="Launch graphical GTK3 interface")
    parser.add_argument("--diff", action="store_true", help="Capture baseline and watch for differential changes")
    parser.add_argument("--watch", type=float, nargs="?", const=1.5, help="Continuous watch loop with interval in seconds")
    parser.add_argument("--demo", action="store_true", help="Force DEMO / SIMULATION mode")

    args = parser.parse_args()

    port = args.port
    if args.demo and not port:
        port = "DEMO / SIMULATION (Jura Impressa XJ5)"

    # If no port specified, scan or pick demo
    if not port:
        available_ports = serial_io.scan_serial_ports()
        if available_ports:
            port = available_ports[0]
        else:
            port = "DEMO / SIMULATION (Jura Impressa XJ5)"

    # Determine mode: default to GUI if GTK is available and CLI not explicitly requested
    launch_gui = args.gui or (HAS_GTK and not (args.cli or args.diff or args.watch is not None))

    if launch_gui and HAS_GTK:
        app = MemoryMapperWindow(initial_port=port)
        app.connect("destroy", Gtk.main_quit)
        app.show_all()
        Gtk.main()
    else:
        conn = serial_io.JuraSerialConnection(port)
        engine = MemoryMapperEngine(conn)
        if args.watch is not None:
            engine.sweep_eeprom()
            engine.capture_baseline()
            # Directly run watch
            run_cli(engine, initial_sweep=False)
        else:
            run_cli(engine, initial_sweep=True)


if __name__ == "__main__":
    main()
