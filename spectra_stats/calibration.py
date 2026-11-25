#!/usr/bin/env python3
"""SPECTRA Statistics Collector constants, product filters, and optical bean calibration."""

import os
import sys
import json
from datetime import datetime
from typing import Dict, Any, Optional, Tuple

try:
    import spectra_py as _rust_core
    HAS_RUST_CORE = True
except ImportError:
    _rust_core = None
    HAS_RUST_CORE = False

try:
    from version import __version__, __build__
except ImportError:
    __build__ = "20261112.1820"
    __version__ = f"Build {__build__}"


def is_rust_core_enabled() -> bool:
    """Resolve HAS_RUST_CORE dynamically so monkeypatches on stats_collector.HAS_RUST_CORE take effect."""
    facade = sys.modules.get("stats_collector")
    if facade is not None and hasattr(facade, "HAS_RUST_CORE"):
        return bool(getattr(facade, "HAS_RUST_CORE"))
    return HAS_RUST_CORE


_COFFEE_PRODUCT_KEYWORDS = (
    "coffee", "kaffee", "káva", "espresso", "espressi", "ristretto", "ristretti",
    "cappuccino", "latte", "macchiato", "flat white", "cortado", "americano",
    "lungo", "doppio", "barista", "melange", "au lait", "ground", "aroma", "special",
)
_NON_COFFEE_PRODUCT_KEYWORDS = (
    "water", "voda", "wasser", "tea", "čaj", "milk", "mléko", "mléčná",
    "milch", "foam", "pěna", "schaum", "steam", "pára", "dampf",
)
_NON_COFFEE_PRODUCT_CODES = frozenset((8, 10, 13, 45))


def is_non_coffee_product(name: str, code: Optional[int] = None) -> bool:
    """
    Return True for standalone non-coffee beverages (steam, milk/milk foam, hot water/tea)
    that count in total preparations only, never in total coffee cups.
    """
    low = str(name or "").strip().lower()
    if any(tok in low for tok in _COFFEE_PRODUCT_KEYWORDS):
        return False
    if code is not None and code in _NON_COFFEE_PRODUCT_CODES:
        return True
    return any(tok in low for tok in _NON_COFFEE_PRODUCT_KEYWORDS)


# ---------------------------------------------------------------------------
# Optical Bean Sensor Calibration Settings (Dev-configurable)
# ---------------------------------------------------------------------------
DEFAULT_OPTICAL_BEAN_THRESHOLD = 115
DEFAULT_OPTICAL_BEAN_HYSTERESIS = 5

# ---------------------------------------------------------------------------
# Hardware Article to Model Mapping
# ---------------------------------------------------------------------------
ARTICLE_MODEL_MAP: Dict[str, Tuple[str, str, str]] = {
    "15133": ("A1", "15133 A1 Piano Black", "A-Line"),
    "15171": ("A1", "15171 A1 Piano White", "A-Line"),
    "15125": ("A1", "15125 A1", "A-Line"),
    "15110": ("ENA Micro 101 Aroma+", "15110 ENA Micro 101 Aroma+", "ENA Micro"),
    "13594": ("ENA Micro 1", "13594 ENA Micro 1 Micro Black", "ENA Micro"),
    "13636": ("ENA Micro 1", "13636 ENA Micro 1 Micro Silver", "ENA Micro"),
    "13735": ("ENA Micro 1", "13735 ENA Micro 1", "ENA Micro"),
    "15221": ("D4", "15221 D4 Piano Black", "D-Line"),
    "13356": ("IMPRESSA Z5", "13356 IMPRESSA Z5 230V CH", "Z-Line"),
    "15420": ("WE8 (EA)", "15420 WE8 (EA)", "WE-Line"),
    "15421": ("WE8 (EA)", "15421 WE8 (EA)", "WE-Line"),
    "15141": ("WE8", "15141 WE8", "WE-Line"),
    "15144": ("WE8", "15144 WE8", "WE-Line"),
    "15109": ("E8", "15109 E8 Piano Black", "E-Line"),
    "15084": ("E8", "15084 E8 Chrome", "E-Line"),
    "13500": ("ENA 7", "13500 ENA 7 Ristretto Black EU 230V/50Hz", "ENA-Line"),
    "13760": ("ENA 7", "13760 ENA 7 Blossom White EU 230V/50Hz", "ENA-Line"),
    "13501": ("ENA 7", "13501 ENA 7", "ENA-Line"),
    "13524": ("ENA 7", "13524 ENA 7", "ENA-Line"),
}

# ---------------------------------------------------------------------------
# Jura Top-Tronic 8-bit EEPROM Models (2-digit hex addressing: RT:xx / RE:xx)
# ---------------------------------------------------------------------------
TWO_DIGIT_ADDRESS_EFS = {
    "EF509M", "EF511", "EF511M", "EF527M", "EF631D", "EF632D",
    "EF642D", "EF642M", "EF643D", "EF644D", "EPSILON", "IOTA",
    "UFO", "E90", "ALPHAM", "ALPHAD", "C1300", "E1300", "E100"
}

_optical_bean_threshold = DEFAULT_OPTICAL_BEAN_THRESHOLD
_optical_bean_hysteresis = DEFAULT_OPTICAL_BEAN_HYSTERESIS

CONFIG_DIR = os.path.expanduser("~/.config/spectra")
CALIBRATION_FILE = os.path.join(CONFIG_DIR, "calibration.json")


def get_optical_bean_threshold() -> int:
    """Return active optical bean sensor threshold in counts (default 115)."""
    return _optical_bean_threshold


def set_optical_bean_threshold(val: int, save: bool = True) -> int:
    """Set optical bean sensor threshold in counts (clamped 30..250)."""
    global _optical_bean_threshold
    _optical_bean_threshold = max(30, min(250, int(val)))
    if save:
        _save_calibration()
    return _optical_bean_threshold


def reset_optical_bean_threshold(save: bool = True) -> int:
    """Reset optical bean threshold to factory default (115 counts)."""
    return set_optical_bean_threshold(DEFAULT_OPTICAL_BEAN_THRESHOLD, save=save)


def get_optical_bean_calibration() -> Dict[str, Any]:
    """Return dictionary of active optical calibration parameters and bounds."""
    return {
        "threshold": _optical_bean_threshold,
        "hysteresis": _optical_bean_hysteresis,
        "lower_bound": _optical_bean_threshold - _optical_bean_hysteresis,
        "upper_bound": _optical_bean_threshold + _optical_bean_hysteresis
    }


def _load_calibration():
    global _optical_bean_threshold, _optical_bean_hysteresis
    if os.path.exists(CALIBRATION_FILE):
        try:
            with open(CALIBRATION_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if "optical_bean_threshold" in data:
                    loaded_thresh = max(30, min(250, int(data["optical_bean_threshold"])))
                    # Migrate legacy 99 default to new calibrated 115 default
                    if loaded_thresh == 99:
                        _optical_bean_threshold = DEFAULT_OPTICAL_BEAN_THRESHOLD
                    else:
                        _optical_bean_threshold = loaded_thresh
                if "optical_bean_hysteresis" in data:
                    loaded_hyst = max(0, min(20, int(data["optical_bean_hysteresis"])))
                    if loaded_hyst == 2:
                        _optical_bean_hysteresis = DEFAULT_OPTICAL_BEAN_HYSTERESIS
                    else:
                        _optical_bean_hysteresis = loaded_hyst
        except Exception:
            pass


def _save_calibration():
    try:
        os.makedirs(CONFIG_DIR, exist_ok=True)
        tmp_path = f"{CALIBRATION_FILE}.tmp.{os.getpid()}"
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump({
                "optical_bean_threshold": _optical_bean_threshold,
                "optical_bean_hysteresis": _optical_bean_hysteresis,
                "updated_at": datetime.now().isoformat()
            }, f, indent=2)
        os.replace(tmp_path, CALIBRATION_FILE)
    except Exception:
        pass


_load_calibration()


# Known dual-thermoblock / two-heater machine profiles (Coffee + Steam)
DUAL_HEATER_EFS = {
    "EF516", "EF532", "EF533", "EF534", "EF535", "EF540", "EF636", "EF638",
    "EF645", "EF652", "EF655", "EF657", "EF658", "EF658S", "EF659", "EF722",
    "EF776", "EF783", "EF787", "EF788", "EF790", "Z10", "GIGA"
}

