#!/usr/bin/env python3
"""SPECTRA Web Server persistent UI preferences and custom developer sensor mappings."""

import os
import sys
import json
import copy
import tempfile
import threading
from typing import Dict, Any, Optional

from spectra_web.state import PROJECT_DIR


def _resolve_ui_prefs_path() -> str:
    """Resolve UI prefs path via web_server facade when monkeypatched in tests."""
    facade = sys.modules.get("web_server")
    if facade is not None and hasattr(facade, "get_ui_prefs_path"):
        return facade.get_ui_prefs_path()
    return get_ui_prefs_path()


CUSTOM_SENSOR_MAPPINGS_FILE = os.path.join(PROJECT_DIR, "docs", "models", "custom_sensor_mappings.json")
_SENSOR_MAPPINGS_LOCK = threading.Lock()
_SENSOR_MAPPINGS_CACHE: Optional[Dict[str, Any]] = None
_SENSOR_MAPPINGS_MTIME: float = -1.0
_SENSOR_MAPPINGS_PATH: str = ""

# ============================================================================
# Developer Raw Sensor Catalog & Value Mapping Infrastructure [DEV ONLY]
# ============================================================================

DEFAULT_SENSOR_MAPPINGS: Dict[str, Dict[str, Any]] = {
    "HZ_0": {
        "frame": "HZ",
        "index": 0,
        "name": "Operating & Safety Bitfield",
        "category": "Status",
        "unit": "flags",
        "scale": 1.0,
        "desc": "12-nibble operational status: BU init, MV busy, Heater ready, MV init"
    },
    "HZ_1": {
        "frame": "HZ",
        "index": 1,
        "name": "BU Upper Limit Encoder Target",
        "category": "Brew Unit",
        "unit": "ticks",
        "scale": 1.0,
        "desc": "Mechanical top travel limit reference ticks (e.g. 0x0289 = 649)"
    },
    "HZ_2": {
        "frame": "HZ",
        "index": 2,
        "name": "BU Current Position Encoder",
        "category": "Brew Unit",
        "unit": "ticks",
        "scale": 1.0,
        "desc": "Real-time optical quadrature encoder ticks from home switch"
    },
    "HZ_3": {
        "frame": "HZ",
        "index": 3,
        "name": "Flowmeter Impulses",
        "category": "Hydraulics",
        "unit": "pulses",
        "scale": 1.0,
        "desc": "Turbine flow pulses in current cycle (~2.366 pulses / ml)"
    },
    "HZ_4": {
        "frame": "HZ",
        "index": 4,
        "name": "Coffee Thermoblock NTC",
        "category": "Thermal",
        "unit": "°C",
        "scale": 0.1,
        "desc": "Coffee Thermoblock temperature (0.1 °C resolution, e.g. 0x03CA = 970 = 97.0°C)"
    },
    "HZ_5": {
        "frame": "HZ",
        "index": 5,
        "name": "Steam Thermoblock NTC",
        "category": "Thermal",
        "unit": "°C",
        "scale": 0.1,
        "desc": "Steam Thermoblock temperature (0.1 °C resolution, if equipped)"
    },
    "HZ_6": {
        "frame": "HZ",
        "index": 6,
        "name": "Rotary Dial Knob",
        "category": "User Interface",
        "unit": "pos",
        "scale": 1.0,
        "desc": "Rotary switch knob selected position index"
    },
    "HZ_7": {
        "frame": "HZ",
        "index": 7,
        "name": "Auxiliary & Microswitch Cuts",
        "category": "Sensors",
        "unit": "bitfield",
        "scale": 1.0,
        "desc": "Chassis microswitches: Drip tray cut, water float cut, zero crossing"
    },
    "HZ_8": {
        "frame": "HZ",
        "index": 8,
        "name": "Front Panel Matrix / Puck Cake",
        "category": "Sensors",
        "unit": "ticks",
        "scale": 1.0,
        "desc": "Key matrix and ground coffee puck cake thickness measurement"
    },
    "HZ_9": {
        "frame": "HZ",
        "index": 9,
        "name": "Spout Dispenser Microswitches",
        "category": "Chassis",
        "unit": "bitfield",
        "scale": 1.0,
        "desc": "Height-adjustable coffee dispenser and drain switch states"
    },
    "AS_0": {
        "frame": "AS",
        "index": 0,
        "name": "Ambient IR Photodiode ADC",
        "category": "Optical Hopper",
        "unit": "counts",
        "scale": 1.0,
        "desc": "Ambient background IR photodiode ADC measurement"
    },
    "AS_1": {
        "frame": "AS",
        "index": 1,
        "name": "Reflected Beam IR Photodiode ADC",
        "category": "Optical Hopper",
        "unit": "counts",
        "scale": 1.0,
        "desc": "Reflected beam IR photodiode ADC measurement"
    },
    "AS_DELTA": {
        "frame": "AS",
        "index": 2,
        "name": "Optical Hopper Differential Delta",
        "category": "Optical Hopper",
        "unit": "counts",
        "scale": 1.0,
        "desc": "Delta between reflected and ambient IR (Threshold: 115 ± 5)"
    },
    "RE_0028": {
        "frame": "RE:0028",
        "index": 0,
        "name": "Hardware Fault Latch Register",
        "category": "Safety",
        "unit": "bitmask",
        "scale": 1.0,
        "desc": "16-bit non-volatile hardware safety lockout latch"
    },
    "CS_0": {
        "frame": "CS",
        "index": 0,
        "name": "Component Triac & Actuator State",
        "category": "Actuators",
        "unit": "bitmask",
        "scale": 1.0,
        "desc": "Triacs, pump, heating elements, and ceramic valve states"
    },
    "IC_0": {
        "frame": "IC",
        "index": 0,
        "name": "MCU Input Bus Line State",
        "category": "Hardware",
        "unit": "bitmask",
        "scale": 1.0,
        "desc": "Microcontroller digital input line status"
    }
}


def _load_custom_sensor_mappings_locked() -> Dict[str, Any]:
    global _SENSOR_MAPPINGS_CACHE, _SENSOR_MAPPINGS_MTIME, _SENSOR_MAPPINGS_PATH
    path = CUSTOM_SENSOR_MAPPINGS_FILE
    if not os.path.exists(path):
        _SENSOR_MAPPINGS_CACHE = None
        _SENSOR_MAPPINGS_MTIME = -1.0
        _SENSOR_MAPPINGS_PATH = path
        return copy.deepcopy(DEFAULT_SENSOR_MAPPINGS)
    try:
        st = os.stat(path)
        if _SENSOR_MAPPINGS_CACHE is not None and _SENSOR_MAPPINGS_PATH == path and st.st_mtime == _SENSOR_MAPPINGS_MTIME:
            return copy.deepcopy(_SENSOR_MAPPINGS_CACHE)
        mappings = copy.deepcopy(DEFAULT_SENSOR_MAPPINGS)
        with open(path, "r", encoding="utf-8") as f:
            saved = json.load(f)
        if isinstance(saved, dict):
            mappings.update(saved)
        _SENSOR_MAPPINGS_CACHE = copy.deepcopy(mappings)
        _SENSOR_MAPPINGS_MTIME = st.st_mtime
        _SENSOR_MAPPINGS_PATH = path
        return mappings
    except Exception:
        return copy.deepcopy(DEFAULT_SENSOR_MAPPINGS)


def load_custom_sensor_mappings() -> Dict[str, Any]:
    with _SENSOR_MAPPINGS_LOCK:
        return _load_custom_sensor_mappings_locked()


def _atomic_write_json_0600(target_path: str, payload: Dict[str, Any]) -> None:
    parent = os.path.dirname(os.path.abspath(target_path)) or "."
    os.makedirs(parent, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w",
        dir=parent,
        prefix=".spectra_prefs_",
        suffix=".tmp",
        delete=False,
        encoding="utf-8",
    ) as tf:
        json.dump(payload, tf, indent=2)
        tmp_path = tf.name
    try:
        if os.name != "nt":
            try:
                os.chmod(tmp_path, 0o600)
            except OSError:
                pass
        os.replace(tmp_path, target_path)
    except Exception:
        try:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
        except OSError:
            pass
        raise


def save_custom_sensor_mapping(field_key: str, data: Dict[str, Any]) -> bool:
    global _SENSOR_MAPPINGS_CACHE, _SENSOR_MAPPINGS_MTIME, _SENSOR_MAPPINGS_PATH
    with _SENSOR_MAPPINGS_LOCK:
        mappings = _load_custom_sensor_mappings_locked()
        if field_key not in mappings:
            mappings[field_key] = {}
        mappings[field_key].update(data)
        try:
            _atomic_write_json_0600(CUSTOM_SENSOR_MAPPINGS_FILE, mappings)
            _SENSOR_MAPPINGS_CACHE = copy.deepcopy(mappings)
            _SENSOR_MAPPINGS_PATH = CUSTOM_SENSOR_MAPPINGS_FILE
            try:
                _SENSOR_MAPPINGS_MTIME = os.stat(CUSTOM_SENSOR_MAPPINGS_FILE).st_mtime
            except OSError:
                _SENSOR_MAPPINGS_MTIME = -1.0
            return True
        except Exception:
            return False


_ui_prefs_lock = threading.Lock()


def get_ui_prefs_path() -> str:
    """Return host-persistent path for SPECTRA UI preferences (onboarding, language)."""
    if sys.platform.startswith("win"):
        base = os.environ.get("APPDATA") or os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
        return os.path.join(base, "SPECTRA", "ui_prefs.json")
    base = os.environ.get("XDG_CONFIG_HOME") or os.path.join(os.path.expanduser("~"), ".config")
    return os.path.join(base, "spectra", "ui_prefs.json")


def _load_ui_prefs_unlocked(path: str) -> Dict[str, Any]:
    """Internal helper — caller MUST hold `_ui_prefs_lock`."""
    prefs: Dict[str, Any] = {"onboarding_seen": False, "lang": "en"}
    if os.path.isfile(path):
        try:
            with open(path, "r", encoding="utf-8") as fh:
                raw = json.load(fh)
            if isinstance(raw, dict):
                if isinstance(raw.get("onboarding_seen"), bool):
                    prefs["onboarding_seen"] = raw["onboarding_seen"]
                raw_lang = str(raw.get("lang") or "").strip().lower()
                if raw_lang in ("en", "cs"):
                    prefs["lang"] = raw_lang
        except Exception:
            pass
    return prefs


def load_ui_prefs() -> Dict[str, Any]:
    """Load persistent UI preferences (`onboarding_seen`, `lang`) with safe defaults."""
    path = _resolve_ui_prefs_path()
    with _ui_prefs_lock:
        return _load_ui_prefs_unlocked(path)


def save_ui_prefs(updates: Dict[str, Any]) -> Dict[str, Any]:
    """Merge and atomically persist UI preferences (`onboarding_seen`, `lang`) to disk."""
    path = _resolve_ui_prefs_path()
    with _ui_prefs_lock:
        prefs = _load_ui_prefs_unlocked(path)
        if isinstance(updates, dict):
            if "onboarding_seen" in updates:
                prefs["onboarding_seen"] = bool(updates["onboarding_seen"])
            if "lang" in updates:
                raw_lang = str(updates["lang"] or "").strip().lower()
                if raw_lang in ("en", "cs"):
                    prefs["lang"] = raw_lang
        try:
            _atomic_write_json_0600(path, prefs)
        except Exception:
            pass
        return prefs


def reset_custom_sensor_mappings() -> bool:
    global _SENSOR_MAPPINGS_CACHE, _SENSOR_MAPPINGS_MTIME, _SENSOR_MAPPINGS_PATH
    with _SENSOR_MAPPINGS_LOCK:
        _SENSOR_MAPPINGS_CACHE = None
        _SENSOR_MAPPINGS_MTIME = -1.0
        _SENSOR_MAPPINGS_PATH = ""
        if os.path.exists(CUSTOM_SENSOR_MAPPINGS_FILE):
            try:
                os.remove(CUSTOM_SENSOR_MAPPINGS_FILE)
                return True
            except Exception:
                return False
        return True


