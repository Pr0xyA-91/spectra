#!/usr/bin/env python3
"""SPECTRA Jura scalar, thermal, date, GS1, and brew-unit position decoders."""

from datetime import datetime
from typing import Any, Optional, Tuple

from spectra_stats.calibration import (
    DUAL_HEATER_EFS,
    _rust_core,
    is_rust_core_enabled,
)

def decode_jura_date(val: int) -> Optional[datetime]:
    """
    Decodes Jura 16-bit packed EEPROM date format:
    Bits 0..4 (5 bits): Day of month (1..31)
    Bits 5..8 (4 bits): Month (1..12)
    Bits 9..15 (7 bits): Year offset from 1990 (e.g. 23 -> 2013)
    """
    if is_rust_core_enabled() and _rust_core is not None and hasattr(_rust_core, "decode_jura_date_word"):
        try:
            if not isinstance(val, int) or val < 0 or val > 0xFFFF:
                return None
            ymd = _rust_core.decode_jura_date_word(val)
            return datetime(ymd[0], ymd[1], ymd[2]) if ymd is not None else None
        except Exception:
            pass
    if not val or val == 0xFFFF:
        return None
    day = val & 0x1F
    month = (val >> 5) & 0x0F
    year = 1990 + (val >> 9)
    try:
        return datetime(year, month, day)
    except ValueError:
        return None


def calculate_gs1_check_digit(digits: str) -> int:
    """Calculate GS1 standard mod-10 check digit."""
    total = 0
    for idx, char in enumerate(reversed(digits)):
        weight = 3 if idx % 2 == 0 else 1
        total += int(char) * weight
    return (10 - (total % 10)) % 10



def decode_jura_temperature(val: Any) -> Optional[float]:
    """
    Convert Jura NTC temperature reading into Celsius (°C) with 0.1°C precision.
    Jura microcontrollers report temperatures in tenths of a degree Celsius (0.1 °C):
    - Ambient / room temperature: 0x00E2 (226) -> 22.6 °C
    - Active brewing temperature: 0x03C4 (964) -> 96.4 °C
    - Active steam thermoblock:   0x0546 (1350) -> 135.0 °C
    Values >= 1900 (e.g. 0x0802 = 2050) denote inactive / disabled / not installed circuits.
    """
    if val is None:
        return None
    try:
        if isinstance(val, str):
            val_clean = val.strip().lower()
            num = int(val_clean, 16)
        elif isinstance(val, (int, float)):
            num = int(val)
        else:
            return None
    except ValueError:
        return None

    if is_rust_core_enabled() and _rust_core is not None and hasattr(_rust_core, "decode_jura_temperature_word"):
        try:
            return _rust_core.decode_jura_temperature_word(num)
        except Exception:
            pass

    if num <= 0 or num >= 1900:
        return None

    # Standard Jura 0.1 °C resolution (15.0 °C to 185.0 °C):
    if 150 <= num <= 1850:
        return round(num / 10.0, 1)

    # Fallback for direct integer Celsius (15 °C .. 150 °C)
    if 15 <= num < 150:
        return round(float(num), 1)

    return None


def evaluate_thermoblock_status(temp_c: Optional[float], is_steam: bool = False) -> str:
    """
    Evaluate plain-language operational status from decoded temperature in Celsius.
    - Coffee thermoblock: nominal brewing temperature is ~90°C - 98°C.
    - Steam thermoblock: nominal steaming temperature is ~125°C - 145°C.
    """
    if temp_c is None:
        return "Not Installed" if is_steam else "Disconnected / Sensor Fault"

    if is_steam:
        if 120.0 <= temp_c <= 155.0:
            return "Ready for Steam"
        elif temp_c > 155.0:
            return "Thermal Safety Warning (>155°C)"
        elif temp_c >= 50.0:
            return "Heating Up (Steam)"
        else:
            return "Cold / Standby"
    else:
        if 85.0 <= temp_c <= 105.0:
            return "Ready to Brew"
        elif temp_c > 105.0:
            return "Steam Purge / Hot"
        elif temp_c >= 45.0:
            return "Heating Up (Coffee)"
        else:
            return "Cold / Standby"


def evaluate_brew_unit_position(
    pos: int,
    upper_ref: int,
    mill_target: int = 0,
    init_ok: bool = True,
    delta_ticks: int = 0
) -> Tuple[str, str, int]:
    """
    Dynamically evaluate the mechanical zone, short card subtitle, and stroke
    percentage (0-100%) of the Brew Unit from live encoder ticks:
    - Lower / Mill (Home) Target: RE:0041 (~226-230 ticks) -> 0% stroke
    - Pre-Brew / Tamping Travel: RE:0042 (~250-450 ticks)
    - Brewing / Compression Chamber: RE:0043/RE:0044 (~460-610 ticks)
    - Upper Reference / Eject & Rinse: HZ[1] (~647-648 ticks) -> 100% stroke
    """
    if not init_ok:
        return "Init / Position Fault", "Position Fault", 0
    if pos <= 0:
        return "Standby / Unknown", "Standby", 0

    eff_target = mill_target if mill_target > 0 else 230
    eff_upper = upper_ref if upper_ref > eff_target else 648
    span = max(1, eff_upper - eff_target)
    stroke_pct = max(0, min(100, round(((pos - eff_target) / span) * 100)))

    if abs(pos - eff_target) <= 16:
        zone_full = "Home / Mill Position"
        zone_short = "Home / Mill"
        stroke_pct = 0
    elif pos < eff_target - 16:
        zone_full = "Lower Limit / Bottom"
        zone_short = "Lower Limit"
    elif pos >= eff_upper - 24:
        zone_full = "Upper / Eject & Rinse"
        zone_short = "Upper / Eject"
        if abs(pos - eff_upper) <= 12:
            stroke_pct = 100
    elif pos >= eff_target + int(0.55 * span):
        zone_full = "Brewing / Compression"
        zone_short = "Brewing / Compress"
    else:
        zone_full = "Tamping / Pre-Brew Travel"
        zone_short = "Tamping / Travel"

    if abs(delta_ticks) >= 4:
        arrow = "▲" if delta_ticks > 0 else "▼"
        zone_full = f"Moving {arrow} ({zone_full})"
        zone_short = f"Moving {arrow} {zone_short}"

    return zone_full, zone_short, stroke_pct

