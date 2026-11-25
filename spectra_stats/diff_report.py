#!/usr/bin/env python3
"""SPECTRA EEPROM differential report generator."""

import os
import json
from typing import Dict, Any

import profiles_db

from spectra_stats.decoders import decode_jura_date

def generate_eeprom_diff_report(
    live_dump: Dict[str, Any],
    baseline_source: Any,
    label: str = "Machine"
) -> str:
    """
    Generate an ASCII diff report comparing live machine EEPROM/telemetry
    against a baseline dump (file path or dictionary) or a model specification.
    """
    baseline_data = {}
    baseline_spec = None
    baseline_name = "Baseline"

    if isinstance(baseline_source, str):
        # File path or Model Name (e.g. EF518)
        if os.path.exists(baseline_source):
            baseline_name = os.path.basename(baseline_source)
            try:
                with open(baseline_source, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
                if "eeprom" in loaded or "hardware" in loaded:
                    baseline_data = loaded
            except Exception as e:
                return f"[-] Failed to load baseline JSON from {baseline_source}: {e}"
        else:
            # Check if model spec exists
            spec = profiles_db.get_model_spec(baseline_source)
            if spec:
                baseline_data = spec
                baseline_spec = spec
                baseline_name = f"Model Spec: {spec.get('model_family', baseline_source)}"
            else:
                return f"[-] Baseline '{baseline_source}' not found (provide a valid JSON dump path or model code like EF518)."
    elif isinstance(baseline_source, dict):
        baseline_data = baseline_source
        baseline_name = baseline_data.get("model_family", "Baseline Dictionary")

    live_eeprom = live_dump.get("eeprom", {})
    base_eeprom = baseline_data.get("eeprom", {})

    lines = []
    lines.append("=" * 82)
    lines.append(f"SPECTRA EEPROM & TELEMETRY AUDIT DIFF — {label}")
    lines.append(f"Live Interrogation vs. Baseline: {baseline_name}")
    lines.append("=" * 82)

    # 1. Telemetry & Firmware Gateways
    lines.append("\n[1. SYSTEM IDENTIFIERS & GATEWAYS]")
    lines.append(f"{'Gateway':<10} | {'Baseline Value':<28} | {'Live Machine Value':<28} | {'Status'}")
    lines.append("-" * 82)

    gateways = [
        ("TY:", "Main Firmware"),
        ("TL:", "Main Bootloader"),
        ("TY$:", "Display Firmware"),
        ("TL$:", "Display Bootloader"),
        ("CS$:", "Display Checksum"),
        ("IC:", "Hardware Code"),
        ("AS:", "Optical Sensor"),
        ("HZ:", "Telemetry Frame")
    ]
    for gw, desc in gateways:
        b_val = baseline_data.get(gw, "N/A")
        l_val = live_dump.get(gw, "N/A")
        if b_val is None: b_val = "N/A"
        if l_val is None: l_val = "N/A"
        match = (b_val == l_val) if (b_val != "N/A" and l_val != "N/A") else None
        st = "[MATCH]" if match else ("[DIFFERENT]" if match is False else "[UNVERIFIED]")
        lines.append(f"{gw:<10} | {str(b_val):<28} | {str(l_val):<28} | {st}")

    # 2. Known Parameter Mapping & Comparison
    param_map = {
        "0001": ("Espresso 1 Cup", "cups", "counter"),
        "0002": ("Coffee 1 Cup", "cups", "counter"),
        "0004": ("Espresso 2 Cup", "cycles", "counter"),
        "0005": ("Coffee 2 Cup", "cycles", "counter"),
        "0006": ("Powder Coffee", "cups", "counter"),
        "0007": ("Rinsing Operations", "cycles", "counter"),
        "0008": ("Tablet Cleanings", "cycles", "counter"),
        "0009": ("Descaling Programs", "cycles", "counter"),
        "000A": ("Grinder Run Duration", "seconds", "counter"),
        "000D": ("Coffees Since Descale", "cups", "diag"),
        "000F": ("Coffees Before Cleaning", "cups", "diag"),
        "0013": ("Milk Preparations", "cycles", "counter"),
        "0014": ("Hot Water Portions", "portions", "counter"),
        "0015": ("Service Counter", "preparations", "counter"),
        "0028": ("Safety Fault Latch", "hex", "fault"),
        "0031": ("Electronic Serial Counter", "number", "id"),
        "0032": ("Production Date", "date", "id"),
        "0040": ("BU Upper Stop Limit", "ticks", "calibration"),
        "0041": ("BU Mill Target (Home)", "ticks", "calibration"),
        "0042": ("BU Pre-Brew Travel 1", "ticks", "calibration"),
        "0043": ("BU Compression Chamber", "ticks", "calibration"),
        "0044": ("BU Pre-Brew Travel 2", "ticks", "calibration"),
        "0055": ("Water Hardness Level", "level", "config"),
        "0056": ("BU Zero Init Cycles", "cycles", "counter"),
        "00C3": ("Configured Water Hardness", "°dH", "config"),
        "00DA": ("Country Code", "ascii", "id"),
        "01B0": ("Encoder & TB1 Short", "events", "fault_counter"),
        "01B1": ("TB1 Open & BU Pos Error", "events", "fault_counter"),
        "01B2": ("BU Init & Descalc Aborts", "events", "fault_counter"),
        "01B4": ("Flowmeter Timeouts", "events", "fault_counter"),
    }

    # Add custom registers from spec if present
    spec_custom = baseline_data.get("custom_registers", {})
    for reg, c_info in spec_custom.items():
        r_up = reg.upper()
        if r_up not in param_map:
            param_map[r_up] = (c_info.get("name", f"Custom {r_up}"), "raw", "custom")

    lines.append("\n[2. TELEMETRY COUNTERS, CALIBRATION & HARDWARE SETTINGS]")
    lines.append(f"{'Address':<7} | {'Parameter Description':<27} | {'Baseline':<14} | {'Live':<14} | {'Delta':<10} | {'Status'}")
    lines.append("-" * 92)

    for addr in sorted(param_map.keys()):
        p_name, unit, kind = param_map[addr]
        l_hex = live_eeprom.get(addr, "0000")
        l_val = int(l_hex, 16)

        # Baseline value resolution
        b_val = None
        b_str = "N/A"
        if base_eeprom and addr in base_eeprom:
            b_hex = base_eeprom[addr]
            b_val = int(b_hex, 16)
            b_str = f"{b_val}"
        elif "hardware" in baseline_data and "bu_calibration" in baseline_data["hardware"]:
            # Check calibration targets
            bu_c = baseline_data["hardware"]["bu_calibration"]
            for target_k, t_reg in bu_c.get("registers", {}).items():
                if t_reg.upper() == addr:
                    t_val = bu_c.get(f"{target_k}_ticks") or bu_c.get(f"{target_k}_target_ticks")
                    if t_val:
                        b_val = t_val
                        b_str = f"{b_val} (Spec)"

        l_str = f"{l_val}"
        if kind == "fault":
            l_str = f"0x{l_hex}"
            b_str = f"0x{b_val:04X}" if b_val is not None else "0x0000 (Spec)"
        elif kind == "id" and addr == "00DA":
            try:
                l_str = "".join(chr((l_val >> 8) & 0xFF) + chr(l_val & 0xFF)).strip()
                if b_val is not None:
                    b_str = "".join(chr((b_val >> 8) & 0xFF) + chr(b_val & 0xFF)).strip()
            except Exception:
                pass

        delta_str = "-"
        status = "[MATCH]"

        if b_val is not None:
            if kind in ("counter", "diag", "fault_counter"):
                diff = l_val - b_val
                if diff > 0:
                    delta_str = f"+{diff}"
                    status = "[INCREMENTED]" if kind == "counter" else "[CHANGED]"
                elif diff < 0:
                    delta_str = f"{diff}"
                    status = "[DECREASED]"
                else:
                    delta_str = "0"
                    status = "[MATCH]"
            elif kind == "calibration":
                diff = l_val - b_val
                if diff != 0:
                    delta_str = f"{diff:+d} ticks"
                    status = "[DRIFT]" if abs(diff) > 8 else "[NOMINAL]"
                else:
                    delta_str = "0"
                    status = "[MATCH]"
            elif kind == "fault":
                if l_val != b_val:
                    delta_str = f"^0x{l_val ^ b_val:04X}"
                    status = "[FAULT TRIP]" if l_val > b_val else "[CLEARED]"
                else:
                    delta_str = "0"
                    status = "[MATCH]"
            else:
                if l_val != b_val:
                    delta_str = "MODIFIED"
                    status = "[CHANGED]"
                else:
                    delta_str = "0"
                    status = "[MATCH]"
        else:
            status = "[RECORDED]"

        lines.append(f"0x{addr:<5} | {p_name:<27} | {b_str:<14} | {l_str:<14} | {delta_str:<10} | {status}")

    # 3. Memory Divergence Summary
    if base_eeprom:
        divergent = []
        for addr, l_hex in sorted(live_eeprom.items()):
            if addr not in param_map:
                b_hex = base_eeprom.get(addr, "0000")
                if l_hex != b_hex and (int(l_hex, 16) != 0 or int(b_hex, 16) != 0):
                    divergent.append((addr, b_hex, l_hex, int(b_hex, 16), int(l_hex, 16)))

        if divergent:
            lines.append(f"\n[3. OTHER DIVERGENT UNMAPPED REGISTERS ({len(divergent)} addresses)]")
            lines.append(f"{'Address':<7} | {'Baseline Hex (Dec)':<20} | {'Live Hex (Dec)':<20} | {'Delta'}")
            lines.append("-" * 72)
            for addr, bh, lh, bv, lv in divergent[:25]:
                d = lv - bv
                lines.append(f"0x{addr:<5} | 0x{bh} ({bv:5d})        | 0x{lh} ({lv:5d})        | {d:+d}")
            if len(divergent) > 25:
                lines.append(f"   ... and {len(divergent) - 25} more divergent registers.")

    lines.append("=" * 82)
    lines.append("END OF EEPROM DIFF REPORT")
    lines.append("=" * 82)
    return "\n".join(lines)
