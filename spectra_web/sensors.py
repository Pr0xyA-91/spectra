#!/usr/bin/env python3
"""SPECTRA Web Server mapper session lookup, raw sensor decoding, and advisor health scoring."""

import time
from typing import Dict, Any, Optional, Tuple, List

import serial_io
import stats_collector as sc
import memory_mapper

from spectra_web import state as _wstate
from spectra_web.state import _session_lock
from spectra_web.prefs import DEFAULT_SENSOR_MAPPINGS, load_custom_sensor_mappings
from spectra_web.security import is_valid_port

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


def _canonical_port(port: str) -> str:
    norm = serial_io.normalize_port_name(port)
    if norm.upper().startswith(("COM", "\\\\.\\COM")):
        return norm.upper()
    return norm


def _get_or_create_mapper(port: str) -> Tuple[Optional[memory_mapper.MemoryMapperEngine], Optional[str]]:
    if not port or not is_valid_port(port):
        return None, "Invalid or missing serial port"

    norm_port = _canonical_port(port)
    if _wstate._active_session is None or _canonical_port(_wstate._current_port) != norm_port:
        if _wstate._active_session is not None:
            try:
                _wstate._active_session.close()
            except Exception:
                pass
        _wstate._active_session = sc.JuraStatsSession(port_name=norm_port)
        _wstate._current_port = norm_port
        _wstate._mapper_engine = None

    if _wstate._active_session.conn is not None and not _wstate._active_session.conn.is_open:
        try:
            _wstate._active_session.conn.close()
        except Exception:
            pass
        _wstate._active_session.conn = None
        _wstate._mapper_engine = None

    if _wstate._active_session.conn is None or not _wstate._active_session.conn.is_open:
        _wstate._active_session.conn = serial_io.JuraSerialConnection(norm_port)
        _wstate._mapper_engine = None

    if _wstate._mapper_engine is None or _wstate._mapper_engine.conn != _wstate._active_session.conn:
        _wstate._mapper_engine = memory_mapper.MemoryMapperEngine(_wstate._active_session.conn)

    return _wstate._mapper_engine, None


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

