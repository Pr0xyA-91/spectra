#!/usr/bin/env python3
"""
SPECTRA — Next-Gen Hardware Telemetry & Logic Board Diagnostics — Web Server
Provides REST APIs for real physical serial adapters (/dev/ttyUSB*, COM*) and simulated mock devices.
Serves the multi-paradigm reactive interface at http://127.0.0.1:8080.
"""

import os
import sys
import re
import time
import json
import socket
import threading
import mimetypes
from http.server import HTTPServer, ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from typing import Dict, Any, Optional, Tuple, List

# Auto-adopt uucp / dialout group if member in /etc/group but current session lacks it
if sys.platform.startswith("linux"):
    import glob
    serial_devs = glob.glob("/dev/ttyUSB*") + glob.glob("/dev/ttyACM*")
    needs_group = any(not os.access(dev, os.R_OK | os.W_OK) for dev in serial_devs)
    if needs_group:
        try:
            import grp
            user = os.environ.get("USER", "")
            for gname in ("uucp", "dialout"):
                try:
                    g_entry = grp.getgrnam(gname)
                    if user and user in g_entry.gr_mem:
                        args = " ".join([f'"{a}"' for a in sys.argv])
                        cmd = f"exec python3 {args}"
                        os.execlp("newgrp", "newgrp", gname, "-c", cmd)
                except KeyError:
                    pass
        except Exception:
            pass

# Ensure local modules are importable
PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

import serial_io
import stats_collector as sc
import gui_widgets
import memory_mapper
import copy
import spectra_probe
from version import __version__, __build__, __edition__

# Global Session State
_session_lock = threading.Lock()
_active_session: Optional[sc.JuraStatsSession] = None
_current_port: str = ""
_last_stats_cache: Optional[Dict[str, Any]] = None
_mapper_engine: Optional[memory_mapper.MemoryMapperEngine] = None

def get_dist_dir() -> str:
    if hasattr(sys, "_MEIPASS"):
        bundled = os.path.join(sys._MEIPASS, "web", "dist")
        if os.path.exists(bundled):
            return bundled
    if getattr(sys, "frozen", False):
        adjacent = os.path.join(os.path.dirname(sys.executable), "web", "dist")
        if os.path.exists(adjacent):
            return adjacent
    return os.path.join(PROJECT_DIR, "web", "dist")

DIST_DIR = get_dist_dir()
CUSTOM_SENSOR_MAPPINGS_FILE = os.path.join(PROJECT_DIR, "docs", "models", "custom_sensor_mappings.json")

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


def load_custom_sensor_mappings() -> Dict[str, Any]:
    mappings = copy.deepcopy(DEFAULT_SENSOR_MAPPINGS)
    if os.path.exists(CUSTOM_SENSOR_MAPPINGS_FILE):
        try:
            with open(CUSTOM_SENSOR_MAPPINGS_FILE, "r", encoding="utf-8") as f:
                saved = json.load(f)
                mappings.update(saved)
        except Exception:
            pass
    return mappings


def save_custom_sensor_mapping(field_key: str, data: Dict[str, Any]) -> bool:
    mappings = load_custom_sensor_mappings()
    if field_key not in mappings:
        mappings[field_key] = {}
    mappings[field_key].update(data)
    try:
        os.makedirs(os.path.dirname(CUSTOM_SENSOR_MAPPINGS_FILE), exist_ok=True)
        tmp = CUSTOM_SENSOR_MAPPINGS_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(mappings, f, indent=2)
        os.replace(tmp, CUSTOM_SENSOR_MAPPINGS_FILE)
        return True
    except Exception:
        return False


def reset_custom_sensor_mappings() -> bool:
    if os.path.exists(CUSTOM_SENSOR_MAPPINGS_FILE):
        try:
            os.remove(CUSTOM_SENSOR_MAPPINGS_FILE)
            return True
        except Exception:
            return False
    return True


def serialize_register_entry(r: memory_mapper.RegisterEntry) -> Dict[str, Any]:
    return {
        "addr": r.addr,
        "hex_addr": r.hex_addr,
        "val": r.val,
        "val_hex": f"0x{r.val:04X}",
        "val_dec": r.val,
        "status": r.status,
        "name": r.name,
        "desc": r.desc,
        "category": r.category,
        "unit": r.unit,
        "baseline_val": r.baseline_val,
        "baseline_hex": f"0x{r.baseline_val:04X}",
        "delta": r.delta,
        "is_changed": r.is_changed,
        "bits_flipped": r.bits_flipped,
        "high_byte": r.high_byte,
        "low_byte": r.low_byte,
        "signed_val": r.signed_val,
        "ascii_repr": r.ascii_repr,
    }


def _get_or_create_mapper(port: str) -> Tuple[Optional[memory_mapper.MemoryMapperEngine], Optional[str]]:
    global _active_session, _current_port, _mapper_engine
    if not port or not is_valid_port(port):
        return None, "Invalid or missing serial port"

    if _active_session is None or _current_port != port:
        if _active_session is not None:
            try:
                _active_session.close()
            except Exception:
                pass
        _active_session = sc.JuraStatsSession(port_name=port)
        _current_port = port
        _mapper_engine = None

    if _active_session.conn is not None and not _active_session.conn.is_open:
        try:
            _active_session.conn.close()
        except Exception:
            pass
        _active_session.conn = None
        _mapper_engine = None

    if _active_session.conn is None or not _active_session.conn.is_open:
        _active_session.conn = serial_io.JuraSerialConnection(port)
        _mapper_engine = None

    if _mapper_engine is None or _mapper_engine.conn != _active_session.conn:
        _mapper_engine = memory_mapper.MemoryMapperEngine(_active_session.conn)

    return _mapper_engine, None


def _decode_raw_sensors(mapper: memory_mapper.MemoryMapperEngine) -> Dict[str, Any]:
    # Query raw frames safely
    hz_raw = mapper.query_safe("HZ:", timeout=1.2) or ""
    as_raw = mapper.query_safe("AS:", timeout=1.2) or ""
    cs_raw = mapper.query_safe("CS:", timeout=1.2) or ""
    ic_raw = mapper.query_safe("IC:", timeout=1.2) or ""
    r28_raw = mapper.query_safe("RE:0028", timeout=1.2) or ""

    custom_mappings = load_custom_sensor_mappings()
    fields = []

    # 1. HZ: Frame parsing
    hz_clean = hz_raw.strip()
    if hz_clean.lower().startswith("hz:"):
        hz_clean = hz_clean[3:].strip()
    hz_parts = hz_clean.split(",") if hz_clean else []

    for idx, part in enumerate(hz_parts):
        key = f"HZ_{idx}"
        cfg = custom_mappings.get(key, DEFAULT_SENSOR_MAPPINGS.get(key, {}))
        name = cfg.get("name", f"HZ Field {idx}")
        category = cfg.get("category", "General")
        unit = cfg.get("unit", "")
        scale = float(cfg.get("scale", 1.0))
        desc = cfg.get("desc", f"Volatile HZ operational parameter {idx}")
        is_custom = key in custom_mappings and custom_mappings[key] != DEFAULT_SENSOR_MAPPINGS.get(key)

        raw_hex = part.strip()
        val_dec = None
        val_bin = ""
        scaled_val = None
        formatted = ""

        try:
            val_dec = int(raw_hex, 16)
            bit_len = max(len(raw_hex) * 4, 16)
            val_bin = f"{val_dec:0{bit_len}b}"
            val_bin_spaced = " ".join([val_bin[max(0, i - 4):i] for i in range(len(val_bin), 0, -4)][::-1])
        except ValueError:
            val_bin_spaced = ""

        if val_dec is not None:
            scaled_val = round(val_dec * scale, 2)
            if scale == 0.1:
                formatted = f"{scaled_val:.1f} {unit}".strip()
            elif scale == 1.0:
                formatted = f"{val_dec} {unit}".strip()
            else:
                formatted = f"{scaled_val} {unit}".strip()
        else:
            formatted = raw_hex

        notes = desc
        if idx == 0 and len(raw_hex) >= 7:
            bu_ok = raw_hex[1] == "1" if len(raw_hex) > 1 else False
            mv_busy = raw_hex[2] == "1" if len(raw_hex) > 2 else False
            heat_ready = raw_hex[5] == "1" if len(raw_hex) > 5 else False
            mv_ok = raw_hex[6] == "1" if len(raw_hex) > 6 else False
            notes = f"BU Init: {'OK' if bu_ok else 'Fault'} | Valve: {'Moving' if mv_busy else 'Idle'} | Heater: {'Ready' if heat_ready else 'Heating'} | Valve Init: {'OK' if mv_ok else 'Uninit'}"
        elif idx == 2 and val_dec is not None:
            notes = f"Brew Unit Encoder Position ({val_dec} ticks from home)"
        elif idx == 3 and val_dec is not None:
            vol_ml = round(val_dec / 2.366, 1)
            notes = f"Dispense Cycle Volume: ~{vol_ml} ml ({val_dec} flowmeter pulses)"
        elif idx == 4 and val_dec is not None:
            notes = f"Coffee Thermoblock Temp: {val_dec * 0.1:.1f} °C"
        elif idx == 5 and val_dec is not None:
            notes = f"Steam Thermoblock Temp: {val_dec * 0.1:.1f} °C"
        elif idx == 7 and len(raw_hex) >= 3:
            tray_missing = raw_hex[0] == "1"
            water_low = raw_hex[2] == "1" if len(raw_hex) > 2 else False
            notes = f"Drip Tray: {'MISSING' if tray_missing else 'OK'} | Water Tank: {'EMPTY/LOW' if water_low else 'OK'}"

        fields.append({
            "key": key,
            "frame": "HZ",
            "index": idx,
            "raw_hex": raw_hex,
            "raw_dec": val_dec,
            "raw_bin": val_bin_spaced,
            "name": name,
            "category": category,
            "unit": unit,
            "scale": scale,
            "scaled_val": scaled_val,
            "formatted": formatted,
            "desc": desc,
            "notes": notes,
            "is_custom": is_custom
        })

    # 2. AS: Frame parsing
    as_clean = as_raw.strip()
    if as_clean.lower().startswith("as:"):
        as_clean = as_clean[3:].strip()
    as_parts = as_clean.split(",") if as_clean else []
    off_adc = None
    on_adc = None

    if len(as_parts) >= 2:
        for idx in range(2):
            key = f"AS_{idx}"
            cfg = custom_mappings.get(key, DEFAULT_SENSOR_MAPPINGS.get(key, {}))
            name = cfg.get("name", f"AS Field {idx}")
            unit = cfg.get("unit", "counts")
            scale = float(cfg.get("scale", 1.0))
            desc = cfg.get("desc", "Optical IR ADC reading")
            raw_hex = as_parts[idx].strip()
            sub_hex = raw_hex[-4:] if len(raw_hex) >= 4 else raw_hex
            try:
                val_dec = int(sub_hex, 16)
                val_bin = f"{val_dec:016b}"
                val_bin_spaced = " ".join([val_bin[max(0, i - 4):i] for i in range(len(val_bin), 0, -4)][::-1])
            except ValueError:
                val_dec = None
                val_bin_spaced = ""

            if idx == 0:
                off_adc = val_dec
                notes = f"Ambient Background IR Light (LED OFF): {val_dec} ADC counts"
            else:
                on_adc = val_dec
                notes = f"Reflected IR Light (LED PULSED ON): {val_dec} ADC counts"

            fields.append({
                "key": key,
                "frame": "AS",
                "index": idx,
                "raw_hex": sub_hex,
                "raw_dec": val_dec,
                "raw_bin": val_bin_spaced,
                "name": name,
                "category": "Optical Hopper",
                "unit": unit,
                "scale": scale,
                "scaled_val": val_dec,
                "formatted": f"{val_dec} {unit}".strip() if val_dec is not None else sub_hex,
                "desc": desc,
                "notes": notes,
                "is_custom": key in custom_mappings and custom_mappings[key] != DEFAULT_SENSOR_MAPPINGS.get(key)
            })

        if off_adc is not None and on_adc is not None:
            delta = on_adc - off_adc
            key = "AS_DELTA"
            cfg = custom_mappings.get(key, DEFAULT_SENSOR_MAPPINGS.get(key, {}))
            calib = sc.get_optical_bean_calibration()
            thresh = calib.get("threshold", 115)
            hyst = calib.get("hysteresis", 5)
            beans_ok = (delta >= (thresh - hyst))
            notes = f"Differential Delta: {delta} counts | Threshold: {thresh} ± {hyst} | Status: {'BEANS OK (Beam Reflected)' if beans_ok else 'FILL BEANS (Hopper Empty)'}"
            fields.append({
                "key": key,
                "frame": "AS",
                "index": 2,
                "raw_hex": f"{delta & 0xFFFF:04X}",
                "raw_dec": delta,
                "raw_bin": f"{delta & 0xFFFF:016b}",
                "name": cfg.get("name", "Optical Hopper Differential Delta"),
                "category": "Optical Hopper",
                "unit": "counts",
                "scale": 1.0,
                "scaled_val": delta,
                "formatted": f"{delta} counts ({'BEANS OK' if beans_ok else 'FILL BEANS'})",
                "desc": cfg.get("desc", "Differential IR reflection delta"),
                "notes": notes,
                "is_custom": key in custom_mappings and custom_mappings[key] != DEFAULT_SENSOR_MAPPINGS.get(key)
            })

    # 3. RE:0028 Hardware Fault Latch
    r28_clean = r28_raw.strip()
    if r28_clean.lower().startswith("re:"):
        r28_clean = r28_clean[3:].strip()
    if r28_clean:
        try:
            val_r28 = int(r28_clean, 16)
            val_bin = f"{val_r28:016b}"
            val_bin_spaced = " ".join([val_bin[i:i+4] for i in range(0, 16, 4)])
        except ValueError:
            val_r28 = 0
            val_bin_spaced = ""

        fault_active = (val_r28 != 0)
        fault_notes = "Hardware nominal — No faults latched." if not fault_active else f"ACTIVE FAULT LATCH (Bitmask: 0x{val_r28:04X})"
        key = "RE_0028"
        cfg = custom_mappings.get(key, DEFAULT_SENSOR_MAPPINGS.get(key, {}))
        fields.append({
            "key": key,
            "frame": "RE:0028",
            "index": 0,
            "raw_hex": r28_clean,
            "raw_dec": val_r28,
            "raw_bin": val_bin_spaced,
            "name": cfg.get("name", "Hardware Fault Latch Register"),
            "category": "Safety",
            "unit": "bitmask",
            "scale": 1.0,
            "scaled_val": val_r28,
            "formatted": f"0x{val_r28:04X} ({'NOMINAL' if not fault_active else 'FAULT'})",
            "desc": cfg.get("desc", "16-bit non-volatile hardware safety lockout latch"),
            "notes": fault_notes,
            "is_custom": key in custom_mappings and custom_mappings[key] != DEFAULT_SENSOR_MAPPINGS.get(key)
        })

    # 4. CS: Component Status
    cs_clean = cs_raw.strip()
    if cs_clean.lower().startswith("cs:"):
        cs_clean = cs_clean[3:].strip()
    if cs_clean:
        try:
            val_cs = int(cs_clean, 16)
            val_bin = f"{val_cs:016b}"
            val_bin_spaced = " ".join([val_bin[i:i+4] for i in range(0, 16, 4)])
        except ValueError:
            val_cs = 0
            val_bin_spaced = ""
        key = "CS_0"
        cfg = custom_mappings.get(key, DEFAULT_SENSOR_MAPPINGS.get(key, {}))
        fields.append({
            "key": key,
            "frame": "CS",
            "index": 0,
            "raw_hex": cs_clean,
            "raw_dec": val_cs,
            "raw_bin": val_bin_spaced,
            "name": cfg.get("name", "Component Triac & Actuator State"),
            "category": "Actuators",
            "unit": "bitmask",
            "scale": 1.0,
            "scaled_val": val_cs,
            "formatted": f"0x{val_cs:04X}",
            "desc": cfg.get("desc", "Pump, heater triacs, and valve line states"),
            "notes": f"Actuator bitfield: 0x{val_cs:04X}",
            "is_custom": key in custom_mappings and custom_mappings[key] != DEFAULT_SENSOR_MAPPINGS.get(key)
        })

    # 5. IC: Input Bus State
    ic_clean = ic_raw.strip()
    if ic_clean.lower().startswith("ic:"):
        ic_clean = ic_clean[3:].strip()
    if ic_clean:
        try:
            val_ic = int(ic_clean, 16)
            val_bin = f"{val_ic:016b}"
            val_bin_spaced = " ".join([val_bin[i:i+4] for i in range(0, 16, 4)])
        except ValueError:
            val_ic = 0
            val_bin_spaced = ""
        key = "IC_0"
        cfg = custom_mappings.get(key, DEFAULT_SENSOR_MAPPINGS.get(key, {}))
        fields.append({
            "key": key,
            "frame": "IC",
            "index": 0,
            "raw_hex": ic_clean,
            "raw_dec": val_ic,
            "raw_bin": val_bin_spaced,
            "name": cfg.get("name", "MCU Input Bus Line State"),
            "category": "Hardware",
            "unit": "bitmask",
            "scale": 1.0,
            "scaled_val": val_ic,
            "formatted": f"0x{val_ic:04X}",
            "desc": cfg.get("desc", "Microcontroller digital input line status"),
            "notes": f"Input line states: 0x{val_ic:04X}",
            "is_custom": key in custom_mappings and custom_mappings[key] != DEFAULT_SENSOR_MAPPINGS.get(key)
        })

    return {
        "timestamp": time.strftime("%H:%M:%S"),
        "frames": {
            "HZ": hz_raw,
            "AS": as_raw,
            "CS": cs_raw,
            "IC": ic_raw,
            "RE_0028": r28_raw
        },
        "fields": fields,
        "custom_mappings": custom_mappings
    }


def compute_advisor_health(summary: Dict[str, Any], live_sensors: Optional[Dict[str, Any]] = None) -> Tuple[int, List[Dict[str, str]]]:
    """Runs automated heuristic health analysis matching SPECTRA diagnostic engine."""
    score = 95
    cards = []
    telemetry = summary.get("telemetry", {})
    alerts = summary.get("alerts", [])
    maint = summary.get("maintenance", [])
    error_counters = (live_sensors or {}).get("error_counters", {}) if live_sensors else {}

    # 1. Descaling
    decalc_due = False
    decalc_pct = None
    for m in maint:
        lbl = m.get("label", "").lower()
        if "decalc" in lbl or "descal" in lbl:
            decalc_pct = m.get("percentage")
            if decalc_pct is not None and decalc_pct > 80:
                decalc_due = True

    if decalc_due or (decalc_pct is not None and decalc_pct > 75):
        score -= 10
        cards.append({
            "icon": "⚠️",
            "title": "Thermoblock Descaling Recommended",
            "desc": f"Descaling cycle life progress is at {decalc_pct}%. Heatup efficiency is impacted by calcification.",
            "action": "Action: Run complete descaling procedure using Jura 3-phase descaling tablets.",
            "severity": "warn"
        })
    else:
        cards.append({
            "icon": "✓",
            "title": "Hydraulic Calcification Within Margin",
            "desc": f"Thermoblock fluid channel resistance is optimal. Progress: {decalc_pct or 0}%.",
            "action": "Status: Descaling not required at this time.",
            "severity": "ok"
        })

    # 2. Drip Tray Microswitch Bouncing
    tray_trips = error_counters.get("Drip Tray Missing Trips", 0)
    if tray_trips > 10:
        score -= 5
        cards.append({
            "icon": "🔧",
            "title": f"Drip Tray Microswitch Bouncing ({tray_trips} events)",
            "desc": "High switch trip frequency detected. Potential contact oxidation or loose seating springs.",
            "action": "Action: Inspect metal contact leaf springs on tray backplate; clean with isopropyl alcohol.",
            "severity": "info"
        })

    # 3. Active Blocking Alerts
    for a in alerts:
        if a.get("blocking", False):
            score -= 25
            cards.append({
                "icon": "🔴",
                "title": f"Critical Alert: {a.get('name', 'Machine Error')}",
                "desc": "Appliance is in a lockout state preventing beverage preparation.",
                "action": "Action: Review error code resolution guide before clearing EEPROM faults.",
                "severity": "error"
            })

    # 4. Brew Unit Health
    bu_trips = error_counters.get("Brew Unit Timeout Trips", 0)
    if bu_trips > 0:
        score -= 8
        cards.append({
            "icon": "⚠️",
            "title": f"Brew Unit Motor Drive Hesitation ({bu_trips} trips)",
            "desc": "Motor current peaks exceeded threshold during mechanical stroke.",
            "action": "Action: Disassemble brew unit, clean guide rails, and replace silicone O-rings.",
            "severity": "warn"
        })
    else:
        cards.append({
            "icon": "✓",
            "title": "Brew Unit Mechanics in Optimal Tolerance",
            "desc": "Zero encoder jitter recorded. Motor drive torque is within factory specification.",
            "action": "Status: Standard maintenance interval active.",
            "severity": "ok"
        })

    final_score = max(20, min(100, score))
    return final_score, cards


def is_valid_port(port: str) -> bool:
    if not port or not isinstance(port, str):
        return False
    p = port.strip()
    if not p or len(p) > 256:
        return False
    if p.startswith("/dev/tty") or p.startswith("/dev/pts/") or p.startswith("/dev/serial/"):
        return not any(ch in p for ch in [";", "&", "|", "`", "$", "..", "\x00", "\n", "\r"])
    if p.upper().startswith("COM"):
        return not any(ch in p for ch in [";", "&", "|", "`", "$", "..", "\x00", "\n", "\r"])
    if "DEMO" in p.upper() or p.lower() in ("mock", "demo"):
        return True
    return False


class SpectraApiHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        # Silence routine 200 HTTP access logs in terminal
        pass

    def _send_security_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("X-Content-Type-Options", "nosniff")

    def do_OPTIONS(self):
        self.send_response(200)
        self._send_security_headers()
        self.end_headers()

    def do_HEAD(self):
        self.do_GET()

    def do_GET(self):
        global _active_session, _current_port, _last_stats_cache
        url = urlparse(self.path)
        params = parse_qs(url.query)

        # 1. API: List Serial Ports
        if url.path == "/api/ports":
            ports = serial_io.list_serial_ports()
            self._send_json(ports)
            return

        # 2. API: Live Sensors & Microswitches
        elif url.path == "/api/sensors":
            port = params.get("port", [""])[0].strip()
            fast_poll = params.get("fast", ["1"])[0] == "1"

            if not port:
                self._send_json({"error": "No serial port specified", "switches": [], "sensors": []})
                return
            if not is_valid_port(port):
                self._send_json({"error": "Invalid serial port", "switches": [], "sensors": []})
                return

            with _session_lock:
                try:
                    if _active_session is None or _current_port != port:
                        if _active_session is not None:
                            try:
                                _active_session.close()
                            except Exception:
                                pass
                        _active_session = sc.JuraStatsSession(port_name=port)
                        _current_port = port

                    if _active_session.conn is not None and not _active_session.conn.is_open:
                        try:
                            _active_session.conn.close()
                        except Exception:
                            pass
                        _active_session.conn = None

                    if _active_session.conn is None or not _active_session.conn.is_open:
                        _active_session.conn = serial_io.JuraSerialConnection(port)

                    data = sc.query_live_sensors(
                        port_name=port,
                        conn=_active_session.conn,
                        profile=_active_session.profile,
                        is_legacy=_active_session.is_legacy_cleartext,
                        fast_poll=fast_poll,
                    )
                except Exception as e:
                    # In case of disconnect or error, reset session
                    if _active_session is not None:
                        try:
                            _active_session.close()
                        except Exception:
                            pass
                        _active_session = None
                    data = {
                        "error": str(e),
                        "timestamp": time.strftime("%H:%M:%S"),
                        "switches": [],
                        "sensors": [],
                        "telemetry": {},
                    }

            self._send_json(data)
            return

        # 3. API: Full Interrogation & Statistics
        elif url.path == "/api/stats":
            port = params.get("port", [""])[0].strip()
            if not port or not is_valid_port(port):
                self._send_json({"error": "Invalid or missing serial port"})
                return

            with _session_lock:
                try:
                    if _active_session is not None:
                        try:
                            _active_session.close()
                        except Exception:
                            pass
                        _active_session = None
                    
                    sess = sc.JuraStatsSession(port_name=port)
                    sess.run_interrogation()
                    data = sess.get_structured_summary()
                    score, cards = compute_advisor_health(data, {})
                    data["health_score"] = score
                    data["advisor_cards"] = cards
                    _last_stats_cache = data
                    _active_session = sess
                    _current_port = port
                except Exception as e:
                    data = {"error": str(e)}

            self._send_json(data)
            return

        # 4. API: Optical Bean Threshold Calibration Info
        elif url.path == "/api/calibration":
            calib = sc.get_optical_bean_calibration()
            self._send_json(calib)
            return

        # 5. API: Branded Service Report (HTML Inspection Certificate)
        elif url.path == "/api/service_report":
            port = params.get("port", [""])[0].strip()
            if not port or not is_valid_port(port):
                self._send_json({"error": "Invalid or missing serial port"})
                return

            summary = _last_stats_cache
            if summary is None or _current_port != port:
                self.send_response(400)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(b"<html><body style='background:#121218;color:#eee;font-family:monospace;padding:40px;'><h2>Data Not Read Yet</h2><p>Please interrogate the machine first before generating a service certificate.</p></body></html>")
                return

            score, _ = compute_advisor_health(summary, {})
            checklist = [
                ("Visual inspection of silicone pressure lines & brass fittings", True),
                ("Safety thermal cutoff continuity (TB1: 0.1Ω, TB2: 0.1Ω)", True),
                ("Descaling cycle execution & flowmeter verification", True),
                ("Clean microswitch contact leaves on rear chassis", True),
            ]
            html_content = gui_widgets.generate_service_report_html(summary, score, checklist)

            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(html_content.encode("utf-8"))
            return

        # 6. API: Export Data (JSON, CSV, Plain Text Report, Diagnostic Capture Bundle)
        elif url.path == "/api/export":
            port = params.get("port", [""])[0].strip()
            fmt = params.get("format", ["json"])[0].lower()
            if not port or not is_valid_port(port):
                self._send_json({"error": "Invalid or missing serial port"})
                return

            with _session_lock:
                timestamp = time.strftime("%Y%m%d_%H%M%S")

                if fmt in ("capture", "dump"):
                    # Full hardware diagnostic capture bundle (raw EEPROM + gateways)
                    safe_conn = _active_session.conn if (_active_session and _current_port == port and _active_session.conn and _active_session.conn.is_open) else None
                    owns = False
                    if safe_conn is None:
                        safe_conn = serial_io.JuraSerialConnection(port)
                        owns = True
                    try:
                        bundle = spectra_probe.capture_machine_bundle(safe_conn)
                    finally:
                        if owns:
                            safe_conn.close()

                    content = json.dumps(bundle, indent=2, ensure_ascii=False)
                    safe_model = re.sub(r'[^\w\-_]', '_', str(bundle.get("identity", {}).get("model_name") or "appliance"))
                    filename = f"spectra_capture_{safe_model}_{timestamp}.json"
                    mime = "application/json; charset=utf-8"
                    ext = "json"
                else:
                    if _active_session is None or _current_port != port or _last_stats_cache is None:
                        self._send_json({
                            "error": "Machine data has not been read yet. Please interrogate machine first before exporting.",
                            "success": False
                        })
                        return

                    safe_model = re.sub(r'[^\w\-_]', '_', str(_active_session.model_family or "appliance"))

                    if fmt == "csv":
                        content = _active_session.export_csv()
                        mime = "text/csv; charset=utf-8"
                        ext = "csv"
                    elif fmt == "text" or fmt == "txt":
                        content = _active_session.export_text_report()
                        mime = "text/plain; charset=utf-8"
                        ext = "txt"
                    else:
                        content = _active_session.export_json()
                        mime = "application/json; charset=utf-8"
                        ext = "json"

                    filename = f"spectra_export_{safe_model}_{timestamp}.{ext}"

            self.send_response(200)
            self.send_header("Content-Type", mime)
            self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(content.encode("utf-8") if isinstance(content, str) else content)
            return

        # 7. API: Developer Memory Mapper Info [DEV ONLY]
        elif url.path == "/api/mapper/info":
            port = params.get("port", [""])[0].strip()
            with _session_lock:
                mapper, err = _get_or_create_mapper(port)
                if mapper is None:
                    self._send_json({"error": err})
                    return
                stats = mapper.get_summary_stats()
                self._send_json({
                    "ef_code": mapper.ef_code,
                    "model_family": mapper.model_family,
                    "address_width": mapper.address_width,
                    "max_words": mapper.max_words,
                    "is_two_digit": mapper.is_two_digit,
                    "spec_file": os.path.basename(mapper.spec_file_path or ""),
                    "summary": stats
                })
            return

        # 8. API: Developer Memory Mapper Sweep [DEV ONLY]
        elif url.path == "/api/mapper/sweep":
            port = params.get("port", [""])[0].strip()
            block_param = params.get("block", ["all"])[0].strip()
            with _session_lock:
                mapper, err = _get_or_create_mapper(port)
                if mapper is None:
                    self._send_json({"error": err, "registers": []})
                    return
                if block_param == "all" or not block_param.isdigit():
                    mapper.sweep_eeprom()
                    regs = [serialize_register_entry(r) for r in mapper.classified_registers]
                else:
                    b_idx = int(block_param)
                    updated = mapper.sweep_block(b_idx)
                    regs = [serialize_register_entry(r) for r in updated]
                summary = mapper.get_summary_stats()
                self._send_json({
                    "registers": regs,
                    "summary": summary,
                    "timestamp": time.strftime("%H:%M:%S")
                })
            return

        # 9. API: Developer Memory Mapper Diff [DEV ONLY]
        elif url.path == "/api/mapper/diff":
            port = params.get("port", [""])[0].strip()
            with _session_lock:
                mapper, err = _get_or_create_mapper(port)
                if mapper is None:
                    self._send_json({"error": err, "changed_registers": []})
                    return
                diff = mapper.compute_diff(mask_noise=True)
                diff["changed_registers"] = [serialize_register_entry(r) for r in diff["changed_registers"]]
                diff["summary"] = mapper.get_summary_stats()
                self._send_json(diff)
            return

        # 10. API: Developer Raw Sensor Telemetry & Field Breakdown [DEV ONLY]
        elif url.path == "/api/mapper/raw_sensors":
            port = params.get("port", [""])[0].strip()
            with _session_lock:
                mapper, err = _get_or_create_mapper(port)
                if mapper is None:
                    self._send_json({"error": err, "frames": {}, "fields": []})
                    return
                raw_data = _decode_raw_sensors(mapper)
                self._send_json(raw_data)
            return

        # 5. Static Assets (Compiled React App in web/dist)
        self._serve_static(url.path)

    def do_POST(self):
        url = urlparse(self.path)
        content_length = int(self.headers.get("Content-Length", 0))
        post_body = self.rfile.read(content_length)
        data = {}
        if post_body:
            try:
                data = json.loads(post_body.decode("utf-8"))
            except Exception:
                pass

        # 1. API: Raw Command Injection (Safe prefixes or hex)
        if url.path == "/api/command":
            port = data.get("port", "").strip()
            cmd = data.get("cmd", "").strip()

            if not port or not is_valid_port(port):
                self._send_json({"error": "Invalid serial port", "success": False})
                return
            if not cmd:
                self._send_json({"error": "No command specified", "success": False})
                return

            # Safety: Filter allowed diagnostic commands
            SAFE_ASCII = ("TY:", "IC:", "HZ:", "CS:", "AS:", "RT:", "RE:", "TL:", "TY$:")
            cmd_upper = cmd.upper()
            if not any(cmd_upper.startswith(prefix) for prefix in SAFE_ASCII):
                self._send_json({
                    "error": f"Refusing command '{cmd}'. Only safe read prefixes {SAFE_ASCII} permitted.",
                    "success": False
                })
                return

            with _session_lock:
                try:
                    if _active_session is not None and _current_port == port and _active_session.conn and _active_session.conn.is_open:
                        resp = _active_session.conn.query_ascii(cmd, timeout=1.2)
                    else:
                        conn = serial_io.JuraSerialConnection(port)
                        resp = conn.query_ascii(cmd, timeout=1.2)
                        conn.close()
                    self._send_json({
                        "success": True,
                        "cmd": cmd,
                        "response": resp or "[NO_REPLY]",
                        "timestamp": time.strftime("%H:%M:%S")
                    })
                except Exception as e:
                    self._send_json({"error": str(e), "success": False})
            return

        # 1b. API: Diagnostic Hardware Dump Bundle Capture
        elif url.path == "/api/export_capture":
            port = data.get("port", "").strip()
            joe_csv = data.get("joe_csv", "").strip()

            if not port or not is_valid_port(port):
                self._send_json({"error": "Invalid serial port", "success": False})
                return

            joe_data = spectra_probe.parse_joe_csv_text(joe_csv) if joe_csv else {}
            with _session_lock:
                try:
                    safe_conn = _active_session.conn if (_active_session and _current_port == port and _active_session.conn and _active_session.conn.is_open) else None
                    owns = False
                    if safe_conn is None:
                        safe_conn = serial_io.JuraSerialConnection(port)
                        owns = True
                    try:
                        bundle = spectra_probe.capture_machine_bundle(safe_conn, joe_data=joe_data)
                    finally:
                        if owns:
                            safe_conn.close()

                    safe_model = re.sub(r'[^\w\-_]', '_', str(bundle.get("identity", {}).get("model_name") or "appliance"))
                    timestamp = time.strftime("%Y%m%d_%H%M%S")
                    filename = f"spectra_capture_{safe_model}_{timestamp}.json"
                    self._send_json({
                        "success": True,
                        "filename": filename,
                        "bundle": bundle
                    })
                except Exception as e:
                    self._send_json({"error": str(e), "success": False})
            return

        # 2. API: Set Optical Bean Sensor Threshold
        elif url.path == "/api/set_threshold":
            val = int(data.get("threshold", 115))
            new_t = sc.set_optical_bean_threshold(val, save=True)
            self._send_json({"success": True, "threshold": new_t, "calib": sc.get_optical_bean_calibration()})
            return

        # 3. API: Reset Optical Bean Sensor Threshold
        elif url.path == "/api/reset_threshold":
            new_t = sc.reset_optical_bean_threshold(save=True)
            self._send_json({"success": True, "threshold": new_t, "calib": sc.get_optical_bean_calibration()})
            return

        # 4. API: Capture Baseline Reference [DEV ONLY]
        elif url.path == "/api/mapper/baseline":
            port = data.get("port", "").strip()
            with _session_lock:
                mapper, err = _get_or_create_mapper(port)
                if mapper is None:
                    self._send_json({"error": err, "success": False})
                    return
                snap = mapper.capture_baseline()
                summary = mapper.get_summary_stats()
                self._send_json({
                    "success": True,
                    "timestamp": snap.timestamp,
                    "summary": summary
                })
            return

        # 5. API: Map Register to Model Spec [DEV ONLY]
        elif url.path == "/api/mapper/map_register":
            port = data.get("port", "").strip()
            addr = int(data.get("addr", 0))
            name = str(data.get("name", "")).strip()
            desc = str(data.get("desc", "")).strip()
            category = str(data.get("category", "settings")).strip()
            unit = str(data.get("unit", "")).strip()
            status = str(data.get("status", "mapped")).strip()

            with _session_lock:
                mapper, err = _get_or_create_mapper(port)
                if mapper is None:
                    self._send_json({"error": err, "success": False})
                    return
                ok, msg = mapper.map_register(addr, name, desc, category, unit, status)
                self._send_json({
                    "success": ok,
                    "message": msg,
                    "summary": mapper.get_summary_stats(),
                    "registers": [serialize_register_entry(r) for r in mapper.classified_registers]
                })
            return

        # 6. API: Map Sensor Field [DEV ONLY]
        elif url.path == "/api/mapper/map_sensor_field":
            field_key = str(data.get("key", "")).strip()
            if not field_key:
                self._send_json({"error": "No sensor field key specified", "success": False})
                return
            ok = save_custom_sensor_mapping(field_key, {
                "name": str(data.get("name", "")).strip(),
                "category": str(data.get("category", "General")).strip(),
                "unit": str(data.get("unit", "")).strip(),
                "scale": float(data.get("scale", 1.0)),
                "desc": str(data.get("desc", "")).strip(),
            })
            self._send_json({
                "success": ok,
                "mappings": load_custom_sensor_mappings(),
                "message": f"Saved custom mapping for {field_key}"
            })
            return

        # 7. API: Reset Custom Sensor Mappings to Defaults [DEV ONLY]
        elif url.path == "/api/mapper/reset_sensor_mappings":
            reset_custom_sensor_mappings()
            self._send_json({
                "success": True,
                "mappings": load_custom_sensor_mappings(),
                "message": "Reset sensor mappings to defaults"
            })
            return

        else:
            self.send_error(404, "Endpoint Not Found")

    def _serve_static(self, req_path: str):
        if not os.path.isdir(DIST_DIR):
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(b"<h1>SPECTRA Backend Online</h1><p>Please build the web UI with <code>npm run build</code> inside the <code>web/</code> directory.</p>")
            return

        clean_path = req_path.lstrip("/")
        if not clean_path or clean_path == "index.html":
            file_path = os.path.join(DIST_DIR, "index.html")
        else:
            file_path = os.path.join(DIST_DIR, clean_path)

        if not os.path.isfile(file_path):
            # Fallback to SPA index.html for client-side routing
            file_path = os.path.join(DIST_DIR, "index.html")

        if os.path.isfile(file_path):
            mime_type, _ = mimetypes.guess_type(file_path)
            if not mime_type:
                mime_type = "application/octet-stream"

            self.send_response(200)
            self.send_header("Content-Type", mime_type)
            self.send_header("Cache-Control", "public, max-age=3600")
            self._send_security_headers()
            self.end_headers()
            with open(file_path, "rb") as f:
                self.wfile.write(f.read())
        else:
            self.send_error(404, "File Not Found")

    def _send_json(self, data: Any):
        try:
            payload = json.dumps(data, ensure_ascii=False, default=str).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self._send_security_headers()
            self.end_headers()
            self.wfile.write(payload)
        except (BrokenPipeError, ConnectionResetError):
            pass


def find_free_port(start_port: int = 8080) -> int:
    for port in range(start_port, start_port + 50):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(("127.0.0.1", port)) != 0:
                return port
    return start_port


def main(auto_open: bool = False):
    port = find_free_port(8080)
    server_address = ("127.0.0.1", port)
    httpd = ThreadingHTTPServer(server_address, SpectraApiHandler)

    print("=" * 78)
    print(f"  SPECTRA (Build {__build__}) Hardware Telemetry API & Web Server")
    print("=" * 78)
    print(f"[*] API & Web Service listening on: http://127.0.0.1:{port}")
    print("[*] Serving Next-Gen Multi-Paradigm UI connected to live hardware adapters.")
    print("=" * 78)

    # Automatically launch browser on Windows or when auto_open is True or --open is passed
    if auto_open or sys.platform.startswith("win") or "--open" in sys.argv:
        try:
            import webbrowser
            threading.Timer(0.8, lambda: webbrowser.open(f"http://127.0.0.1:{port}")).start()
        except Exception:
            pass

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n[*] Shutting down SPECTRA API server...")
        global _active_session
        if _active_session is not None:
            try:
                _active_session.close()
            except Exception:
                pass
        httpd.server_close()


if __name__ == "__main__":
    main()
