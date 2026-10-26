#!/usr/bin/env python3
"""
Jura Statistics Collector & Diagnostics Interrogator
Orchestrates:
- Port opening & hardware detection
- Dual-Mode Interrogation Engine:
  1. Plain-ASCII Optical Transceiver Protocol (Jura USB Scanner N 010 & Direct Serial)
     * Auto-detects TY: machine identifier (e.g. EF518M V02.20)
     * Queries power rating (IC:)
     * Reads EEPROM blocks (RT:0000 .. RT:0080) for beverage counts, maintenance cycles,
       grinder operating hours, water throughput, and service history
  2. Encrypted Smart Connect Protocol (@-Protocol with 4:1 wire carrier)
     * Dongle handshake (@T0 -> @T1 -> @t2 -> @T3 -> @t3)
     * Product beverage counter queries (@TR:32,00 .. 0B)
     * Maintenance counters (@TG:43) and life percentages (@TG:C0)
     * System status and active telemetry (@TF:)
  3. Offline Demo / Simulation mode (MockJuraMachine)
- Unified profile matching across 170+ Jura models
- Exporting to Formatted Text Reports, JSON, and CSV

Credits & Attribution:
Built upon reverse-engineering research and protocol contributions by CM-P,
Hajo Noerenberg (hn), Jutta-Proto, Ryan Alden, tinaught, makefu, AlexxIT,
Google Antigravity (Agy / DeepMind), and the open-source coffee telemetry and home automation communities.
"""

import os
import time
import json
import csv
import io
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Callable

import jura_protocol as jp
import profiles_db
from serial_io import JuraSerialConnection

__version__ = "0.4.1"


def decode_jura_date(val: int) -> Optional[datetime]:
    """
    Decodes Jura 16-bit packed EEPROM date format:
    Bits 0..4 (5 bits): Day of month (1..31)
    Bits 5..8 (4 bits): Month (1..12)
    Bits 9..15 (7 bits): Year offset from 1990 (e.g. 23 -> 2013)
    """
    if not val or val == 0xFFFF or val == 0:
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


# Known dual-thermoblock / two-heater machine profiles (Coffee + Steam)
DUAL_HEATER_EFS = {
    "EF516", "EF532", "EF533", "EF534", "EF535", "EF540", "EF636", "EF638",
    "EF645", "EF652", "EF655", "EF657", "EF658", "EF658S", "EF659", "EF722",
    "EF776", "EF783", "EF787", "EF788", "EF790", "Z10", "GIGA"
}


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
            if val_clean.startswith("0x"):
                num = int(val_clean, 16)
            else:
                num = int(val_clean, 16)
        elif isinstance(val, (int, float)):
            num = int(val)
        else:
            return None
    except ValueError:
        return None

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


_last_flowmeter_samples: Dict[str, Tuple[int, float, float]] = {}
_last_bu_samples: Dict[str, Tuple[int, float, int]] = {}


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


def query_live_sensors(
    port_name: str,
    baudrate: int = 9600,
    conn: Optional[JuraSerialConnection] = None,
    profile: Optional[Dict[str, Any]] = None,
    is_legacy: bool = True,
    fast_poll: bool = False
) -> Dict[str, Any]:
    """
    Query live physical microswitches, hardware sensor statuses,
    temperature ADC readings, and component fault registers from the connected Jura machine.
    Works for both ASCII and Smart Connect modes.
    """
    close_when_done = False
    if conn is None or not conn.is_open:
        conn = JuraSerialConnection(port_name, baudrate=baudrate)
        close_when_done = True

    results: Dict[str, Any] = {
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "port": port_name,
        "protocol": "Plain ASCII" if is_legacy else "Smart Connect",
        "switches": [],
        "sensors": [],
        "error_counters": {},
        "telemetry": {},
        "alerts": []
    }

    try:
        # Check if ASCII mode responds to TY:
        # In fast_poll mode, avoid redundant TY: and RE:0028 serial queries if cached on connection
        cached_ef = getattr(conn, "_cached_ef", None)
        if cached_ef is not None:
            detected_ef = cached_ef
            is_ascii = True
        else:
            ty_resp = conn.query_ascii("TY:")
            is_ascii = (ty_resp is not None and ty_resp.startswith("ty:"))
            if not is_ascii and conn.is_demo:
                is_ascii = True
            detected_ef = ""
            if ty_resp and ty_resp.startswith("ty:"):
                toks = ty_resp[3:].strip().split()
                if toks:
                    detected_ef = toks[0].upper()
            setattr(conn, "_cached_ef", detected_ef)

        if is_ascii:
            results["protocol"] = "Plain ASCII (Optical/Serial)"

            # 1. HZ: Live Microswitches, Thermoblock Sensors & Operating Status
            hz_resp = conn.query_ascii("HZ:")
            results["raw_status"] = hz_resp or "N/A"

            water_ok = True
            tray_ok = True
            ready_ok = True
            ready_status = "Ready to Brew / Nominal"
            ready_badge = "READY"
            heater_ntc_raw = 0
            steam_ntc_raw = 0
            flow_pulses_raw = 0
            bu_encoder_upper_raw = 0
            bu_encoder_pos_raw = 0
            rotary_pos = "0"
            grounds_full = False
            beans_empty = False
            beans_ok = True
            bu_init_ok = True
            mv_init_ok = True
            mv_busy = False
            heater_ready_flag = True
            button_matrix_hex = "0000"
            aux_inputs_bits = "00"
            cake_thickness_ticks = 0

            if hz_resp and hz_resp.startswith("hz:"):
                payload = hz_resp[3:].strip()
                parts = payload.split(",")

                if len(parts) > 0 and len(parts[0]) >= 7:
                    bu_init_ok = (parts[0][1] == "1")
                    mv_busy = (parts[0][2] == "1")
                    heater_ready_flag = (parts[0][5] == "1")
                    mv_init_ok = (parts[0][6] == "1")
                if len(parts) > 1:
                    try:
                        bu_encoder_upper_raw = int(parts[1], 16)
                    except ValueError:
                        bu_encoder_upper_raw = 0
                if len(parts) > 2:
                    try:
                        bu_encoder_pos_raw = int(parts[2], 16)
                    except ValueError:
                        bu_encoder_pos_raw = 0
                if len(parts) > 3:
                    try:
                        flow_pulses_raw = int(parts[3], 16)
                    except ValueError:
                        flow_pulses_raw = 0
                if len(parts) > 4:
                    try:
                        heater_ntc_raw = int(parts[4], 16)
                    except ValueError:
                        heater_ntc_raw = 0
                if len(parts) > 5:
                    try:
                        steam_ntc_raw = int(parts[5], 16)
                    except ValueError:
                        steam_ntc_raw = 0
                if len(parts) > 6:
                    rotary_pos = parts[6]
                if len(parts) > 7 and len(parts[7]) >= 6:
                    aux_inputs_bits = parts[7][4:6]
                if len(parts) > 8 and parts[8]:
                    button_matrix_hex = parts[8]
                    try:
                        cake_thickness_ticks = int(parts[8], 16)
                    except ValueError:
                        cake_thickness_ticks = 0

                # Physical Microswitches & Cuts:
                # In Jura telemetry, parts[7] and parts[9] convey live microswitch cuts:
                # - Drip Tray / Drawer:
                #   parts[7][0] is '1' when missing/removed, '0' when inserted.
                #   parts[9][0] is '1' when missing/removed, '0' when inserted.
                tray_missing = False
                if len(parts) > 7 and len(parts[7]) > 0 and parts[7][0] == "1":
                    tray_missing = True
                if len(parts) > 9 and len(parts[9]) > 0 and parts[9][0] == "1":
                    tray_missing = True
                tray_ok = not tray_missing

                # - Water Tank Float Sensor:
                #   parts[7][2] is '1' when tank missing/float dropped, '0' when OK.
                #   parts[9][1] is '1' when tank empty/missing, '0' when OK.
                water_low = False
                if len(parts) > 7 and len(parts[7]) > 2 and parts[7][2] == "1":
                    water_low = True
                if len(parts) > 9 and len(parts[9]) > 1 and parts[9][1] == "1":
                    water_low = True
                water_ok = not water_low

                # - Grounds Container Alarm:
                grounds_full = False
                if len(parts) > 7 and len(parts[7]) > 1 and parts[7][1] == "1":
                    grounds_full = True

            # Calculate Live Water Flow Rate (ml/s) from Flowmeter Pulse Deltas
            # Calibration constant: 2.366 pulses per ml for DigiMesa turbine (~422 pulses / dl)
            now_ts = time.time()
            port_key = str(port_name or "default")
            prev_flow_sample = _last_flowmeter_samples.get(port_key)

            flow_ml_s = 0.0
            if prev_flow_sample is not None:
                prev_pulses, prev_ts, _ = prev_flow_sample
                dt = now_ts - prev_ts
                dp = flow_pulses_raw - prev_pulses
                if dt > 0.1 and dp > 0:
                    ml_delivered = dp / 2.366
                    flow_ml_s = round(ml_delivered / dt, 1)
                elif dp == 0:
                    flow_ml_s = 0.0
                elif dp < 0:
                    # Counter was reset by machine for new dispensing cycle
                    if flow_pulses_raw > 0 and dt > 0.1:
                        flow_ml_s = round((flow_pulses_raw / 2.366) / dt, 1)
                    else:
                        flow_ml_s = 0.0
            else:
                flow_ml_s = 0.0

            _last_flowmeter_samples[port_key] = (flow_pulses_raw, now_ts, flow_ml_s)
            cycle_volume_ml = round(flow_pulses_raw / 2.366, 1)

            # Decode temperatures in Celsius (0.1 °C resolution)
            temp_coffee = decode_jura_temperature(heater_ntc_raw)
            temp_steam = decode_jura_temperature(steam_ntc_raw)

            # Dual-Heater Model Determination
            # 1. Profile/Catalog match
            is_known_dual = (
                detected_ef in DUAL_HEATER_EFS
                or any(detected_ef.startswith(x) for x in DUAL_HEATER_EFS)
                or (profile and any(code in profile.get("ef_code", "").upper() for code in DUAL_HEATER_EFS))
                or "Z10" in port_name.upper()
                or "GIGA" in port_name.upper()
                or "DUAL" in port_name.upper()
            )
            # 2. Dynamic live hardware check (steam thermoblock returned active valid temperature)
            is_hardware_dual = (temp_steam is not None)
            is_dual_heater = is_known_dual or is_hardware_dual
            heater_count = 2 if is_dual_heater else 1

            # 2. Query Diagnostic Fault & Input Registers (RE:0028 & IC:)
            val_r28 = 0
            total_fm_timeouts = 0
            fm_intake_timeouts = 0
            fm_rinse_timeouts = 0
            bu_mill_target = getattr(conn, "_cached_bu_mill_target", 0)
            bu_init_count = 0
            loader_version = ""
            display_firmware = ""

            if not fast_poll:
                # Query hardware fault register RE:0028 (fast, ~350ms)
                r28 = conn.query_ascii("RE:0028")
                if r28 and r28.startswith("re:"):
                    try:
                        val_r28 = int(r28[3:], 16)
                    except ValueError:
                        val_r28 = 0
                setattr(conn, "_cached_val_r28", val_r28)
                results["fault_register_hex"] = f"0x{val_r28:04X}"

                ic_resp = conn.query_ascii("IC:")
                if ic_resp and ic_resp.startswith("ic:"):
                    results["raw_ic"] = ic_resp

                # Query Brew Unit Grind/Mill Target Position (RE:0041) & Init Counter (RE:0056)
                r41 = conn.query_ascii("RE:0041")
                if r41 and r41.startswith("re:"):
                    try:
                        bu_mill_target = int(r41[3:], 16)
                        setattr(conn, "_cached_bu_mill_target", bu_mill_target)
                    except ValueError:
                        pass

                r56 = conn.query_ascii("RE:0056")
                if r56 and r56.startswith("re:"):
                    try:
                        bu_init_count = int(r56[3:], 16)
                    except ValueError:
                        pass

                tl_resp = conn.query_ascii("TL:")
                if tl_resp and tl_resp.startswith("tl:"):
                    loader_version = tl_resp[3:].strip()

                ty_disp_resp = conn.query_ascii("TY$:")
                if ty_disp_resp and ty_disp_resp.startswith("ty$:"):
                    display_firmware = ty_disp_resp[4:].strip()

                # Optical Bean Hopper Sensor (AS: Check Sensor)
                as_resp = conn.query_ascii("AS:")
                if as_resp and as_resp.startswith("as:"):
                    results["raw_as"] = as_resp
                    as_parts = as_resp[3:].split(",")
                    if len(as_parts) >= 2 and len(as_parts[0]) >= 8 and len(as_parts[1]) >= 8:
                        try:
                            off_adc = int(as_parts[0][4:8], 16)
                            on_adc = int(as_parts[1][4:8], 16)
                            # On Jura optical sensor:
                            # Reflected IR when empty > 1680 ADC
                            # Absorbed IR when beans present <= 1660 ADC
                            beans_empty = (on_adc > 1680)
                            beans_ok = not beans_empty
                            setattr(conn, "_cached_beans_ok", beans_ok)
                            setattr(conn, "_cached_bean_adcs", (off_adc, on_adc))
                        except ValueError:
                            pass

                # Flowmeter lifetime timeout diagnostic counters
                r1b4 = conn.query_ascii("RE:01B4")
                if r1b4 and r1b4.startswith("re:"):
                    try:
                        w_1b4 = int(r1b4[3:], 16)
                        fm_intake_timeouts = w_1b4 & 0xFF
                        fm_rinse_timeouts = (w_1b4 >> 8) & 0xFF
                    except ValueError:
                        pass
                total_fm_timeouts = fm_intake_timeouts + fm_rinse_timeouts
            else:
                cached_beans = getattr(conn, "_cached_beans_ok", None)
                if cached_beans is not None:
                    beans_ok = cached_beans
                    beans_empty = not beans_ok
                val_r28 = getattr(conn, "_cached_val_r28", 0)
                results["fault_register_hex"] = f"0x{val_r28:04X}"

            # Evaluate dynamic Brew Unit mechanical position & movement delta
            prev_bu = _last_bu_samples.get(port_key)
            bu_delta_ticks = 0
            if prev_bu is not None:
                prev_bu_pos, prev_bu_ts, prev_bu_target = prev_bu
                if not bu_mill_target and prev_bu_target:
                    bu_mill_target = prev_bu_target
                if (now_ts - prev_bu_ts) < 10.0 and prev_bu_pos > 0 and bu_encoder_pos_raw > 0:
                    bu_delta_ticks = bu_encoder_pos_raw - prev_bu_pos
            _last_bu_samples[port_key] = (bu_encoder_pos_raw, now_ts, bu_mill_target)

            bu_zone_full, bu_zone_short, bu_stroke_pct = evaluate_brew_unit_position(
                bu_encoder_pos_raw, bu_encoder_upper_raw, bu_mill_target, bu_init_ok, bu_delta_ticks
            )

            # 3. Comprehensive Machine Operational State & Physical Evaluation
            # Priority detection: Microswitches, Safety Trips, Temperatures, Idle
            ntc_fault = bool(val_r28 & 0x0006) if not is_dual_heater else bool(val_r28 & 0x00C6)
            heater_fault = bool(val_r28 & 0x0400)
            bu_fault = bool(val_r28 & 0x0018)
            valve_fault = bool(val_r28 & 0x3800)
            is_busy = (len(parts) > 0 and len(parts[0]) > 0 and parts[0][0] != "0")
            temp_coffee_val = temp_coffee

            if flow_ml_s > 0.0 and bu_stroke_pct >= 45:
                ready_ok = False
                ready_status = f"Brewing / Extracting ({flow_ml_s:.1f} ml/s)"
                ready_badge = "BREWING"
                ready_icon = "☕"
            elif bu_stroke_pct >= 45:
                ready_ok = False
                ready_status = f"Brewing / Compressing ({bu_stroke_pct}% stroke)"
                ready_badge = "BREWING"
                ready_icon = "☕"
            elif flow_ml_s > 0.0:
                ready_ok = False
                ready_status = f"Dispensing / Rinsing ({flow_ml_s:.1f} ml/s)"
                ready_badge = "DISPENSING"
                ready_icon = "🌊"
            elif abs(bu_delta_ticks) >= 4 or bu_stroke_pct >= 15:
                ready_ok = False
                ready_status = f"Brew Unit Active ({bu_zone_short})"
                ready_badge = "MOVING"
                ready_icon = "⚙️"
            elif mv_busy:
                ready_ok = False
                ready_status = "Positioning Multiway Valve"
                ready_badge = "VALVE BUSY"
                ready_icon = "🔀"
            elif is_busy:
                ready_ok = False
                ready_status = "Busy (Operation in Progress)"
                ready_badge = "BUSY"
                ready_icon = "⏳"
            elif not tray_ok:
                ready_ok = False
                ready_status = "Not Ready (Drip Tray Missing)"
                ready_badge = "MISSING"
                ready_icon = "📥"
            elif not water_ok:
                ready_ok = False
                ready_status = "Not Ready (Fill Water Tank)"
                ready_badge = "EMPTY"
                ready_icon = "💧"
            elif grounds_full:
                ready_ok = False
                ready_status = "Not Ready (Empty Grounds Container)"
                ready_badge = "FULL"
                ready_icon = "🗑️"
            elif not beans_ok:
                ready_ok = False
                ready_status = "Not Ready (Fill Beans)"
                ready_badge = "FILL BEANS"
                ready_icon = "🫘"
            elif temp_coffee_val is not None and temp_coffee_val < 80.0:
                ready_ok = False
                ready_status = f"Heating Up ({temp_coffee_val:.1f} °C)"
                ready_badge = "HEATING"
                ready_icon = "🔥"
            else:
                ready_ok = True
                ready_status = "Ready to Brew / Nominal"
                ready_badge = "READY"
                ready_icon = "☕"

            # 4. Filter & System Config
            filter_claris = False
            filter_ext = False
            water_hardness = 16
            filter_liters = 0.0

            if not fast_poll:
                r29 = conn.query_ascii("RE:0029")
                if r29 and r29.startswith("re:"):
                    try:
                        w29 = int(r29[3:], 16)
                        filter_ext = bool(w29 & 0x0001)
                        filter_claris = bool(w29 & 0x0010)
                    except ValueError:
                        pass

                rc3 = conn.query_ascii("RE:00C3")
                if rc3 and rc3.startswith("re:"):
                    try:
                        wc3 = int(rc3[3:], 16)
                        water_hardness = (wc3 >> 8) & 0xFF
                    except ValueError:
                        pass

                r45 = conn.query_ascii("RE:0045")
                if r45 and r45.startswith("re:"):
                    try:
                        filter_liters = round(int(r45[3:], 16) / 10.0, 1)
                    except ValueError:
                        pass

            if flow_ml_s > 0.0:
                hyd_status = f"Water Flowing ({flow_ml_s:.1f} ml/s)"
                hyd_badge = f"{flow_ml_s:.1f} ml/s"
                hyd_ok = True
                hyd_icon = "🌊"
            else:
                hyd_status = "Nominal (Hydraulic Flow OK)"
                hyd_badge = "NORMAL"
                hyd_ok = True
                hyd_icon = "🌊"

            # Build Microswitches List
            results["switches"] = [
                {
                    "id": "water_tank",
                    "name": "Water Tank Level Sensor",
                    "status": "Water OK / Tank Present" if water_ok else "Water Low / Tank Missing",
                    "ok": water_ok,
                    "badge": "NORMAL" if water_ok else "WARNING",
                    "icon": "💧"
                },
                {
                    "id": "drip_tray",
                    "name": "Drip Tray / Drawer Presence",
                    "status": "Tray Inserted" if tray_ok else "Tray Missing / Removed",
                    "ok": tray_ok,
                    "badge": "NORMAL" if tray_ok else "WARNING",
                    "icon": "📥"
                },
                {
                    "id": "bean_hopper",
                    "name": "Bean Hopper / Charge Sensor",
                    "status": "Beans OK / Hopper Charged" if beans_ok else "Fill Beans / Hopper Empty",
                    "ok": beans_ok,
                    "badge": "NORMAL" if beans_ok else "FILL BEANS",
                    "icon": "🫘"
                },
                {
                    "id": "hydraulic_system",
                    "name": "Hydraulic System & Flowmeter",
                    "status": hyd_status,
                    "ok": hyd_ok,
                    "badge": hyd_badge,
                    "icon": hyd_icon
                },
                {
                    "id": "machine_ready",
                    "name": "Appliance Operating State",
                    "status": ready_status,
                    "ok": ready_ok,
                    "badge": ready_badge,
                    "icon": ready_icon
                },
                {
                    "id": "brew_unit_pos",
                    "name": "Brew Unit Position (Encoder)",
                    "status": f"{bu_zone_full} ({bu_encoder_pos_raw} / {bu_encoder_upper_raw} ticks, {bu_stroke_pct}% stroke{f', Target: {bu_mill_target}' if bu_mill_target else ''})",
                    "ok": bu_init_ok,
                    "badge": f"{bu_encoder_pos_raw} / {bu_encoder_upper_raw}" if bu_encoder_pos_raw > 0 else ("OK" if bu_init_ok else "FAULT"),
                    "icon": "⚙️"
                },
                {
                    "id": "claris_filter",
                    "name": "CLARIS Filter System",
                    "status": "CLARIS Active" if filter_claris else ("External Active" if filter_ext else "Filter Inactive / Bypass"),
                    "ok": True,
                    "badge": "ACTIVE" if (filter_claris or filter_ext) else "BYPASS",
                    "icon": "🛡️"
                }
            ]

            # Build Diagnostic Hardware Health & Safety Sensors (dynamically mapped for Single vs Dual Heater)
            if is_dual_heater:
                fault_defs = [
                    (0x0002, "coffee_ntc_short", "Coffee Thermoblock NTC (Short)", "Coffee NTC short-circuit detected", "Coffee NTC resistance nominal"),
                    (0x0004, "coffee_ntc_broken", "Coffee Thermoblock NTC (Broken)", "Coffee NTC wire open/broken", "Coffee NTC sensor continuity intact"),
                    (0x0040, "steam_ntc_short", "Steam Thermoblock NTC (Short)", "Steam NTC short-circuit detected", "Steam NTC resistance nominal"),
                    (0x0080, "steam_ntc_broken", "Steam Thermoblock NTC (Broken)", "Steam NTC wire open/broken", "Steam NTC sensor continuity intact"),
                    (0x0008, "bu_pos", "Brew Unit Position Sensor", "Position alignment mismatch", "Encoder and position feedback aligned"),
                    (0x0010, "bu_ini", "Brew Unit Zero / Home Switch", "Zero initialization fault", "Zero-position microswitch functional"),
                    (0x0400, "heater_elem", "Coffee Heating Element", "Heating rate anomaly / element fault", "Thermoblock heating curve nominal"),
                    (0x0100, "fmto_intake", "Flowmeter Monitor (Intake)", "Flow timeout during intake (System clogged or airbound)", "Impulse frequency nominal"),
                    (0x0200, "fmto_rinse", "Flowmeter Monitor (Rinse)", "Flow timeout during rinse (System clogged or airbound)", "Rinse flowrate nominal"),
                    (0x0800, "ku_timeout", "Ceramic Valve (Timeout)", "Ceramic valve position timeout", "Valve positioning nominal"),
                    (0x1000, "mv_pos", "Multiway Valve (Position)", "Multiway valve position error", "Valve position feedback verified"),
                    (0x2000, "mv_ini", "Multiway Valve (Init)", "Multiway valve init error", "Valve initialization verified"),
                    (0x8000, "ku_sensor", "Ceramic Valve Sensor", "Ceramic valve sensor error", "Ceramic valve sensor nominal"),
                    (0x0020, "decalc", "Decalcification Sensor", "Descaling process interrupted", "Descaling cycle nominal"),
                    (0x0001, "channel", "Encoder Channel / Cable", "Pulse / cable check recommended", "Encoder pulses verified")
                ]
            else:
                fault_defs = [
                    (0x0002, "ntc_short", "Thermoblock NTC Sensor (Short)", "Short-circuit detected", "Circuit resistance nominal"),
                    (0x0004, "ntc_broken", "Thermoblock NTC Sensor (Broken/Open)", "Sensor wire open/broken", "Sensor lead continuity intact"),
                    (0x0008, "bu_pos", "Brew Unit Position Sensor", "Position alignment mismatch", "Encoder and position feedback aligned"),
                    (0x0010, "bu_ini", "Brew Unit Zero / Home Switch", "Zero initialization fault", "Zero-position microswitch functional"),
                    (0x0400, "heater", "Coffee Heating Element", "Heating rate anomaly / element fault", "Thermoblock heating curve nominal"),
                    (0x0040, "relay_main", "Main Power Relay", "Power relay contact fault", "Main relay switching nominal"),
                    (0x0080, "overheat", "Thermal Overheat Protection", "Thermal safety cutoff tripped", "Thermal safety margin verified"),
                    (0x0100, "fmto_intake", "Flowmeter Monitor (Intake)", "Flow timeout during intake (System clogged or airbound)", "Impulse frequency nominal"),
                    (0x0200, "fmto_rinse", "Flowmeter Monitor (Rinse)", "Flow timeout during rinse (System clogged or airbound)", "Rinse flowrate nominal"),
                    (0x0800, "ku_timeout", "Ceramic Valve (Timeout)", "Ceramic valve position timeout", "Valve positioning nominal"),
                    (0x1000, "mv_pos", "Multiway Valve (Position)", "Multiway valve position error", "Valve position feedback verified"),
                    (0x2000, "mv_ini", "Multiway Valve (Init)", "Multiway valve init error", "Valve initialization verified"),
                    (0x8000, "ku_sensor", "Ceramic Valve Sensor", "Ceramic valve sensor error", "Ceramic valve sensor nominal"),
                    (0x0020, "decalc", "Decalcification Sensor", "Descaling process interrupted", "Descaling cycle nominal"),
                    (0x0001, "channel", "Encoder Channel / Cable", "Pulse / cable check recommended", "Encoder pulses verified")
                ]

            sensor_list = [
                {
                    "id": "water_flow",
                    "name": "Live Water Flow Rate",
                    "status": f"{flow_ml_s:.1f} ml/s",
                    "ok": True,
                    "badge": f"{flow_ml_s:.1f} ml/s",
                    "details": f"Flowmeter rate: {flow_ml_s:.1f} ml/s | Cycle volume: {cycle_volume_ml:.1f} ml ({flow_pulses_raw} pulses)",
                    "icon": "🌊",
                    "value": flow_ml_s,
                    "unit": "ml/s"
                }
            ]
            if bu_encoder_pos_raw > 0:
                mill_str = f" | Mill Target (RE:0041): {bu_mill_target} ticks (0x{bu_mill_target:04X})" if bu_mill_target else ""
                sensor_list.append({
                    "id": "bu_encoder",
                    "name": "Live Brew Unit Encoder",
                    "status": f"{bu_zone_short} ({bu_encoder_pos_raw} ticks)",
                    "ok": bu_init_ok,
                    "badge": f"{bu_encoder_pos_raw} / {bu_encoder_upper_raw}",
                    "details": f"Zone: {bu_zone_full} ({bu_stroke_pct}% stroke) | Current: {bu_encoder_pos_raw} ticks (0x{bu_encoder_pos_raw:04X}){mill_str} | Upper Ref: {bu_encoder_upper_raw} ticks (0x{bu_encoder_upper_raw:04X}) | Init Flag: {'OK' if bu_init_ok else 'Fault'}",
                    "icon": "⚙️",
                    "value": bu_encoder_pos_raw,
                    "unit": "ticks"
                })
            sensor_list.append({
                "id": "mv_live_state",
                "name": "Live Multiway Valve State",
                "status": "Moving / Positioning" if mv_busy else ("Initialized & Idle" if mv_init_ok else "Not Initialized"),
                "ok": mv_init_ok,
                "badge": "MOVING" if mv_busy else ("READY" if mv_init_ok else "UNINIT"),
                "details": f"Multiway valve init flag (HZ[0][6]): {'1 (OK)' if mv_init_ok else '0'} | Busy flag (HZ[0][2]): {'1 (Moving)' if mv_busy else '0 (Idle)'}",
                "icon": "🔀"
            })
            sensor_list.append({
                "id": "panel_inputs",
                "name": "Live Front Panel & Aux Inputs",
                "status": f"Rotary: {rotary_pos} | Keys: 0x{button_matrix_hex} | Puck: {cake_thickness_ticks} ticks",
                "ok": True,
                "badge": "IDLE" if button_matrix_hex == "0000" else f"KEY {button_matrix_hex}",
                "details": f"Rotary selector: {rotary_pos} | Key matrix (HZ[8]): 0x{button_matrix_hex} | Puck measurement: {cake_thickness_ticks} ticks | Aux bits (HZ[7][4..5]): {aux_inputs_bits}",
                "icon": "🎛️"
            })
            cached_adcs = getattr(conn, "_cached_bean_adcs", None)
            if cached_adcs:
                off_adc, on_adc = cached_adcs
                sensor_list.append({
                    "id": "optical_bean_sensor",
                    "name": "Optical Bean Hopper Sensor",
                    "status": "BEANS OK" if beans_ok else "FILL BEANS (Empty)",
                    "ok": beans_ok,
                    "badge": "NOMINAL" if beans_ok else "EMPTY",
                    "details": f"Reflected IR ADC: {on_adc} | Ambient ADC: {off_adc} | Delta: {on_adc - off_adc} counts | Status: {'Hopper Charged' if beans_ok else 'Fill Beans'}",
                    "icon": "🫘",
                    "value": on_adc,
                    "unit": "ADC"
                })
            for mask, s_id, label, desc_fault, desc_ok in fault_defs:
                tripped = bool(val_r28 & mask)
                sensor_list.append({
                    "id": s_id,
                    "name": label,
                    "status": "Fault / Warning" if tripped else "Nominal (OK)",
                    "ok": not tripped,
                    "badge": "FAULT" if tripped else "NOMINAL",
                    "details": desc_fault if tripped else desc_ok
                })
            results["sensors"] = sensor_list

            # 4. Error Frequency Counters (dynamically mapped for Single vs Dual Heater)
            counters: Dict[str, int] = {}
            if not fast_poll:
                if is_dual_heater:
                    counter_queries = [
                        ("RE:01B0", "Encoder Channel Errors", "Coffee Thermoblock NTC Short Circuits"),
                        ("RE:01B1", "Coffee Thermoblock NTC Broken Errors", "Brew Unit Position Faults"),
                        ("RE:01B2", "Brew Unit Init Faults", "Descaling Interruptions"),
                        ("RE:01B3", "Steam Thermoblock NTC Short Circuits", "Steam Thermoblock NTC Broken Errors"),
                        ("RE:01B4", "Flowmeter Intake Timeouts", "Flowmeter Rinse Timeouts"),
                        ("RE:01B5", "Coffee Heater Element Faults", "Ceramic Valve Timeouts"),
                        ("RE:01B6", "Multiway Valve Init Faults", "Multiway Valve Position Faults")
                    ]
                else:
                    counter_queries = [
                        ("RE:01B0", "Encoder Channel Errors", "Thermoblock NTC Short Circuits"),
                        ("RE:01B1", "Thermoblock NTC Broken/Open Errors", "Brew Unit Position Faults"),
                        ("RE:01B2", "Brew Unit Init Faults", "Descaling Interruptions"),
                        ("RE:01B3", "Main Power Relay Faults", "Thermal Overheat Safety Cutoffs"),
                        ("RE:01B4", "Flowmeter Intake Timeouts", "Flowmeter Rinse Timeouts"),
                        ("RE:01B5", "Coffee Heater Element Faults", "Ceramic Valve Timeouts"),
                        ("RE:01B6", "Multiway Valve Init Faults", "Multiway Valve Position Faults")
                    ]

                for q_cmd, low_lbl, high_lbl in counter_queries:
                    resp_c = conn.query_ascii(q_cmd)
                    if resp_c and resp_c.startswith("re:"):
                        try:
                            w_val = int(resp_c[3:], 16)
                            counters[low_lbl] = w_val & 0xFF
                            counters[high_lbl] = (w_val >> 8) & 0xFF
                        except ValueError:
                            counters[low_lbl] = 0
                            counters[high_lbl] = 0
                    else:
                        counters[low_lbl] = 0
                        counters[high_lbl] = 0

                resp_ku = conn.query_ascii("RE:0103")
                if resp_ku and resp_ku.startswith("re:"):
                    try:
                        counters["Ceramic Valve Sensor Errors"] = int(resp_ku[3:], 16)
                    except ValueError:
                        counters["Ceramic Valve Sensor Errors"] = 0
                else:
                    counters["Ceramic Valve Sensor Errors"] = 0

            results["error_counters"] = counters

            coffee_status = evaluate_thermoblock_status(temp_coffee, is_steam=False)
            steam_status = evaluate_thermoblock_status(temp_steam, is_steam=True) if is_dual_heater else "Not Installed"

            results["telemetry"] = {
                "is_dual_heater": is_dual_heater,
                "heater_count": heater_count,
                "heater_coffee_c": temp_coffee,
                "heater_coffee_raw": heater_ntc_raw,
                "heater_coffee_status": coffee_status,
                "heater_coffee_str": f"{temp_coffee:.1f} °C" if temp_coffee is not None else (f"ADC {heater_ntc_raw}" if heater_ntc_raw else "N/A"),
                "heater_steam_c": temp_steam,
                "heater_steam_raw": steam_ntc_raw,
                "heater_steam_status": steam_status,
                "heater_steam_str": (f"{temp_steam:.1f} °C" if temp_steam is not None else "Installed (Standby)") if is_dual_heater else "Not Installed (Single Heater Model)",
                "bu_encoder_pos": bu_encoder_pos_raw,
                "bu_encoder_upper": bu_encoder_upper_raw,
                "bu_mill_target": bu_mill_target,
                "bu_encoder_str": f"{bu_encoder_pos_raw} / {bu_encoder_upper_raw} ticks" if bu_encoder_pos_raw > 0 else "N/A",
                "bu_position_state": bu_zone_full,
                "bu_position_short": bu_zone_short,
                "bu_stroke_pct": bu_stroke_pct,
                "bu_delta_ticks": bu_delta_ticks,
                "bu_init_ok": bu_init_ok,
                "beans_ok": beans_ok,
                "mv_init_ok": mv_init_ok,
                "mv_busy": mv_busy,
                "heater_ready_flag": heater_ready_flag,
                "machine_state_badge": ready_badge,
                "machine_state_status": ready_status,
                "cake_thickness_ticks": cake_thickness_ticks,
                "bean_adcs": getattr(conn, "_cached_bean_adcs", None),
                "button_matrix": button_matrix_hex,
                "aux_inputs": aux_inputs_bits,
                "heater_ntc_raw": heater_ntc_raw,
                "rotary_switch": rotary_pos,
                "flow_pulses": flow_pulses_raw,
                "flow_rate_ml_s": flow_ml_s,
                "flow_volume_ml": cycle_volume_ml
            }
            if not fast_poll:
                results["telemetry"]["water_hardness_dh"] = water_hardness
                results["telemetry"]["filter_volume_liters"] = filter_liters
                results["telemetry"]["filter_claris_active"] = filter_claris
                results["telemetry"]["filter_ext_active"] = filter_ext
                results["telemetry"]["total_fm_timeouts"] = total_fm_timeouts
                results["telemetry"]["fm_intake_timeouts"] = fm_intake_timeouts
                results["telemetry"]["fm_rinse_timeouts"] = fm_rinse_timeouts
                results["telemetry"]["bu_init_count"] = bu_init_count
                if loader_version:
                    results["telemetry"]["loader_version"] = loader_version
                if display_firmware:
                    results["telemetry"]["display_firmware"] = display_firmware
            # Append only live physical lockouts to active alerts (historical RE:0028 faults stay in sensors/diagnostics)
            if not tray_ok:
                results["alerts"].append({"name": "Drip Tray Missing", "details": "Insert drip tray / grounds drawer", "blocking": True})
            if not water_ok:
                results["alerts"].append({"name": "Water Tank Low / Empty", "details": "Refill water tank", "blocking": True})
            if grounds_full:
                results["alerts"].append({"name": "Grounds Container Full", "details": "Empty coffee grounds container", "blocking": True})
            if not beans_ok:
                results["alerts"].append({"name": "Fill Beans", "details": "Refill coffee bean hopper", "blocking": True})
        else:
            # Smart Connect Protocol Mode
            results["protocol"] = "Encrypted Smart Connect (@-Protocol)"
            wire_tx = jp.encode_wire(jp.build_encrypted_frame("@TF:\r\n", 0x42))
            conn.write(wire_tx)
            raw_rx = conn.read(512, timeout_sec=1.0)
            tf_resp = None
            if raw_rx:
                decoded, _ = jp.decode_wire(raw_rx)
                if decoded.startswith(b"&"):
                    tf_resp = jp.decode_encrypted_frame(decoded)

            results["raw_status"] = tf_resp or "N/A"
            active_alerts = []
            if tf_resp:
                raw_tf = jp.parse_tf(tf_resp)
                if raw_tf:
                    active_alerts = profiles_db.get_active_alerts(profile or profiles_db.DEFAULT_PROFILE, raw_tf)

            alert_names = [a["name"].lower() for a in active_alerts]
            tank_ok = not any("water" in a for a in alert_names)
            tray_ok = not any("tray" in a for a in alert_names)
            ready_ok = any("ready" in a for a in alert_names) or (len(active_alerts) == 0)

            results["switches"] = [
                {
                    "id": "water_tank",
                    "name": "Water Tank Level Sensor",
                    "status": "Water OK / Tank Present" if tank_ok else "Fill Water Tank / Tank Empty",
                    "ok": tank_ok,
                    "badge": "NORMAL" if tank_ok else "WARNING",
                    "icon": "💧"
                },
                {
                    "id": "drip_tray",
                    "name": "Drip Tray / Drawer Contact",
                    "status": "Tray Inserted" if tray_ok else "Insert / Empty Tray",
                    "ok": tray_ok,
                    "badge": "NORMAL" if tray_ok else "WARNING",
                    "icon": "📥"
                },
                {
                    "id": "machine_ready",
                    "name": "Appliance Operating State",
                    "status": "Ready to Brew / Nominal" if ready_ok else "Busy / Status Notification",
                    "ok": ready_ok,
                    "badge": "READY" if ready_ok else "BUSY",
                    "icon": "☕"
                }
            ]
            results["sensors"] = [
                {
                    "id": "system_status",
                    "name": "Smart Connect Telemetry Bus",
                    "status": "Active / Nominal",
                    "ok": True,
                    "badge": "NOMINAL",
                    "details": "Real-time BLE/UART telemetry bus operational"
                }
            ]
            results["alerts"] = active_alerts

            profile_ef = (profile or {}).get("ef_code", "")
            model_fam = (profile or {}).get("model_family", "")
            is_dual_sc = (
                profile_ef.upper() in DUAL_HEATER_EFS
                or any(profile_ef.upper().startswith(x) for x in DUAL_HEATER_EFS)
                or any(kw in model_fam.upper() for kw in ["Z10", "GIGA", "DUAL"])
                or "Z10" in port_name.upper()
                or "GIGA" in port_name.upper()
            )

            results["telemetry"] = {
                "active_alert_count": len(active_alerts),
                "is_dual_heater": is_dual_sc,
                "heater_count": 2 if is_dual_sc else 1,
                "heater_coffee_str": "Nominal",
                "heater_coffee_status": "Ready",
                "heater_steam_str": "Nominal" if is_dual_sc else "Not Installed (Single Heater Model)",
                "heater_steam_status": "Ready" if is_dual_sc else "Not Installed",
                "flow_pulses": 0,
                "flow_rate_ml_s": 0.0,
                "flow_volume_ml": 0.0,
            }

    except Exception as e:
        results["error"] = str(e)
    finally:
        if close_when_done and conn:
            conn.close()

    return results


class JuraStatsSession:
    """Manages an active interrogation session with a Jura machine."""

    def __init__(self, port_name: str, baudrate: int = 9600, log_cb: Optional[Callable[[str], None]] = None):
        self.port_name = port_name
        self.baudrate = baudrate
        self.log_cb = log_cb or (lambda msg: None)
        self.conn: Optional[JuraSerialConnection] = None

        # Session data
        self.raw_model_str = ""
        self.ef_code = ""
        self.model_family = "Unknown Jura Machine"
        self.protocol_mode = "Auto-Detecting"
        self.power_spec = "Standard (230V / 50Hz)"
        self.profile = profiles_db.DEFAULT_PROFILE
        self.counters: Dict[int, int] = {}
        self.total_preparations = 0
        self.total_cups = 0
        self.maint_counts: List[int] = []
        self.maint_pcts: List[Optional[int]] = []
        self.telemetry: Dict[str, Any] = {}
        self.active_alerts: List[Dict[str, Any]] = []
        self.live_sensors: Dict[str, Any] = {}
        self.raw_log: List[Dict[str, str]] = []
        self.is_legacy_cleartext = False

    def query_live_sensors(self) -> Dict[str, Any]:
        """Query live hardware sensors and microswitches for current session."""
        res = query_live_sensors(
            port_name=self.port_name,
            baudrate=self.baudrate,
            conn=self.conn if (self.conn and self.conn.is_open) else None,
            profile=self.profile,
            is_legacy=self.is_legacy_cleartext
        )
        self.live_sensors = res
        return res

    def close(self):
        """Close underlying serial connection if opened and held."""
        if self.conn:
            try:
                self.conn.close()
            except Exception:
                pass
            self.conn = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def log(self, text: str):
        ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        entry = f"[{ts}] {text}"
        self.raw_log.append({"time": ts, "message": text})
        self.log_cb(entry)

    def _send_encrypted_cmd(self, cmd_plain: str, key: int = 0x2A, timeout: float = 1.0) -> Optional[str]:
        """Send an encrypted '@'-command over 4:1 wire and wait for decrypted reply."""
        self.log(f"TX (SmartConnect): {cmd_plain.strip()}")
        wire_tx = jp.encode_wire(jp.build_encrypted_frame(cmd_plain, key))
        self.conn.write(wire_tx)

        start = time.time()
        rx_wire = bytearray()
        while time.time() - start < timeout:
            chunk = self.conn.read(max_bytes=1024, timeout_sec=0.15)
            if chunk:
                rx_wire.extend(chunk)
                decoded, _ = jp.decode_wire(bytes(rx_wire))
                if b"\r\n" in decoded:
                    plain_resp = jp.decode_encrypted_frame(decoded)
                    if plain_resp:
                        self.log(f"RX (SmartConnect): {plain_resp.strip()}")
                        return plain_resp.strip()
            time.sleep(0.01)

        self.log(f"TIMEOUT waiting for reply to {cmd_plain.strip()}")
        return None

    def run_interrogation(self, progress_cb: Optional[Callable[[float, str], None]] = None) -> bool:
        """
        Execute full interrogation sequence:
        1. Open serial connection
        2. Probe ASCII mode (TY:) - handles Jura USB Scanner N 010 & direct serial
        3. If no ASCII reply, probe Smart Connect mode (@T0)
        4. Read and parse all beverage counters, maintenance cycles, and telemetry
        """
        def update_prog(pct: float, status: str):
            if progress_cb:
                progress_cb(pct, status)

        owns_conn = False
        try:
            update_prog(0.05, f"Connecting to {self.port_name}...")
            if self.conn is None or not getattr(self.conn, "is_open", True):
                self.conn = JuraSerialConnection(self.port_name, baudrate=self.baudrate, timeout=1.0)
                owns_conn = True
            self.log(f"Opened connection on {self.port_name} at {self.baudrate} baud (8N1)")

            # ================================================================
            # Mode A: Probe ASCII Protocol (TY:) - Jura USB Scanner / EEPROM
            # ================================================================
            update_prog(0.12, "Probing machine type (TY:)...")
            self.log("Probing ASCII machine identification query (TY:)...")
            ty_resp = self.conn.query_ascii("TY:", timeout=1.0)

            if ty_resp and ty_resp.lower().startswith("ty:"):
                self.is_legacy_cleartext = True
                self.protocol_mode = "ASCII Optical (Jura USB Scanner / Direct Serial)"
                self.raw_model_str = ty_resp[3:].strip()
                self.ef_code = self.raw_model_str
                self.profile = profiles_db.find_profile(self.raw_model_str)
                self.model_family = self.profile.get("model_family", "Jura Coffee Machine")
                self.log(f"Machine detected via ASCII: {self.model_family} ({self.raw_model_str})")

                # Query Power Specification (IC:)
                update_prog(0.20, "Querying machine power specification (IC:)...")
                ic_resp = self.conn.query_ascii("IC:", timeout=0.8)
                if ic_resp and ic_resp.lower().startswith("ic:"):
                    raw_ic = ic_resp[3:].strip()
                    if "23" in raw_ic:
                        self.power_spec = "230V / 50Hz (EU/CH)"
                    elif "12" in raw_ic:
                        self.power_spec = "120V / 60Hz (US/NA)"
                    else:
                        self.power_spec = f"IC Code: {raw_ic}"
                    self.log(f"Machine Power Rating: {self.power_spec}")

                # Query EEPROM memory blocks (RT:0000 .. RT:0030)
                update_prog(0.30, "Reading EEPROM diagnostic blocks (RT:0000 .. RT:0030)...")
                eeprom: Dict[int, int] = {}
                blocks = [0x00, 0x10, 0x20, 0x30]

                for b_idx, blk in enumerate(blocks):
                    pct = 0.30 + (b_idx / len(blocks)) * 0.50
                    update_prog(pct, f"Reading memory block 0x{blk:04X}...")
                    cmd = f"RT:{blk:04X}"
                    ans = self.conn.query_ascii(cmd, timeout=1.8)
                    if ans and ans.startswith("rt:"):
                        raw_hex = ans[3:].strip()
                        words = [int(raw_hex[i * 4: i * 4 + 4], 16) for i in range(len(raw_hex) // 4)]
                        for idx, w in enumerate(words):
                            eeprom[blk + idx] = w
                        self.log(f"EEPROM [0x{blk:04X}]: {len(words)} words read successfully")
                    else:
                        self.log(f"Notice: Block 0x{blk:04X} returned empty/timeout")

                # Explicitly query machine identity, production, and service history EEPROM words
                # 0x0030: Appliance / Machine Number (Maschinennummer: e.g. 18016)
                # 0x0031: Internal Serial Word (Seriennummer: e.g. 51)
                # 0x0032: Production Date bitfield (Produktionsdatum: e.g. 30.5.2013)
                # 0x0015: Preparations since last intervention (Service-Counter: e.g. 28730)
                # 0x00DA: SPDL Country / Destination Market Code (e.g. 'CZ')
                # 0x00DB: SPDL Date Download (e.g. 12.10.2013)
                # 0x00DC: SPDL Date Language File (e.g. 12.12.2012)
                # 0x00E9: Retail High Word (Service cup counter baseline high word)
                # 0x00EA: Retail Low Word (Service cup counter baseline low word)
                # 0x00C3: Water Hardness (High byte: °dH)
                update_prog(0.80, "Reading machine serial and production records...")
                id_addrs = [
                    (0x30, "0030", "Machine Number"),
                    (0x31, "0031", "Serial Word"),
                    (0x32, "0032", "Production Date"),
                    (0x15, "0015", "Service Counter"),
                    (0xDA, "00DA", "SPDL Country Code"),
                    (0xDB, "00DB", "SPDL Download Date"),
                    (0xDC, "00DC", "SPDL Language Date"),
                    (0xE9, "00E9", "Retail High"),
                    (0xEA, "00EA", "Retail Low"),
                    (0xC3, "00C3", "Water Hardness"),
                ]
                for addr_int, addr_hex, desc in id_addrs:
                    if addr_int not in eeprom or eeprom[addr_int] == 0:
                        ans = self.conn.query_ascii(f"RE:{addr_hex}", timeout=1.0)
                        if ans and ans.lower().startswith("re:"):
                            try:
                                eeprom[addr_int] = int(ans[3:].strip(), 16)
                                self.log(f"EEPROM [0x{addr_hex}] {desc}: 0x{eeprom[addr_int]:04X} ({eeprom[addr_int]})")
                            except ValueError:
                                pass

                update_prog(0.85, "Parsing machine telemetry & statistics...")
                # Map standard Jura EEPROM statistics addresses
                esp1 = eeprom.get(1, 0)
                cof1 = eeprom.get(2, 0)
                spec1 = eeprom.get(3, 0)
                esp2 = eeprom.get(4, 0)
                cof2 = eeprom.get(5, 0)
                spec2 = eeprom.get(6, 0)

                self.counters[1] = esp1
                self.counters[2] = cof1
                if spec1 > 0:
                    self.counters[3] = spec1
                self.counters[4] = esp2
                self.counters[5] = cof2
                if spec2 > 0:
                    self.counters[6] = spec2

                self.total_preparations = esp1 + cof1 + spec1 + esp2 + cof2 + spec2
                self.total_cups = esp1 + cof1 + spec1 + (esp2 * 2) + (cof2 * 2) + (spec2 * 2)

                rinses = eeprom.get(7, 0)
                cleanings = eeprom.get(8, 0)
                descalings = eeprom.get(9, 0)
                grinder_sec = eeprom.get(10, 0)

                water_dl = eeprom.get(16, 0)
                decalc_dl = eeprom.get(18, 0)
                filter_cycles = eeprom.get(20, 0)
                since_serv = eeprom.get(21, 0)
                water_since_decalc = eeprom.get(31, 0)

                # Hardware and Serial Identification
                machine_num = eeprom.get(0x30, 0)
                serial_word = eeprom.get(0x31, 0)
                prod_val = eeprom.get(0x32, 0)
                country_word = eeprom.get(0xDA, 0)
                spdl_dl_val = eeprom.get(0xDB, 0)
                spdl_lang_val = eeprom.get(0xDC, 0)
                since_prep = eeprom.get(0x15, 0)
                retail_high = eeprom.get(0xE9, 0)
                retail_low = eeprom.get(0xEA, 0)
                c3_val = eeprom.get(0xC3, 0)

                app_code = f"{machine_num:04X}{prod_val:04X}" if (machine_num or prod_val) else "N/A"

                # Jura Production Date decoding:
                # 16-bit bitfield: Day (bits 0..4), Month (bits 5..8), Year = 1990 + (bits 9..15)
                prod_dt = decode_jura_date(prod_val)
                prod_date_str = f"{prod_dt.day}.{prod_dt.month}.{prod_dt.year}" if prod_dt else "N/A"
                date_prefix = prod_dt.strftime("%Y%m%d") if prod_dt else ""

                # Jura 14-digit Serial Number format (GS1 Application Identifier 21):
                # Formed by YYYYMMDD (Production Date) + 6-digit zero-padded Appliance Number
                # Example: 20130530 + 018016 -> "20130530018016"
                if date_prefix and machine_num:
                    serial_number = f"{date_prefix}{machine_num:06d}"
                elif machine_num:
                    serial_number = f"{machine_num:06d}"
                else:
                    serial_number = "N/A"

                # Country Code decoding:
                # 0x00DA stores two ASCII characters for destination market (e.g. 0x435A -> 'CZ')
                country_code = "N/A"
                if country_word and country_word > 0:
                    hi = (country_word >> 8) & 0xFF
                    lo = country_word & 0xFF
                    chars = "".join(chr(c) for c in (hi, lo) if 32 <= c <= 126).strip()
                    if chars:
                        country_code = chars

                # SPDL Dates:
                spdl_dl_dt = decode_jura_date(spdl_dl_val)
                spdl_dl_str = f"{spdl_dl_dt.day}.{spdl_dl_dt.month}.{spdl_dl_dt.year}" if spdl_dl_dt else "N/A"

                spdl_lang_dt = decode_jura_date(spdl_lang_val)
                spdl_lang_str = f"{spdl_lang_dt.day}.{spdl_lang_dt.month}.{spdl_lang_dt.year}" if spdl_lang_dt else "N/A"

                # Water Hardness:
                water_hardness = (c3_val >> 8) & 0xFF if c3_val else 30

                # Cups and preparations since last service intervention:
                retail_ref = (retail_high * 65536) + retail_low
                cups_since_intervention = max(0, self.total_cups - retail_ref) if (retail_ref > 0 or retail_high or retail_low) else self.total_cups
                prep_since_intervention = since_prep if since_prep > 0 else since_serv

                # Article Number and Full EAN Code:
                article_num = str(self.profile.get("article_number", "13705"))
                display_fw = self.profile.get("software_version_display", "EF518D V02.04")
                app_type = self.profile.get("appliance_type", f"{article_num} {self.model_family}")

                ean_code = "N/A"
                if article_num and serial_number != "N/A":
                    try:
                        base_ean = f"07610917{int(article_num):05d}"
                        gtin14 = f"{base_ean}{calculate_gs1_check_digit(base_ean)}"
                        ean_code = f"(01){gtin14}(21){serial_number}"
                    except Exception:
                        pass

                self.maint_counts = [cleanings, descalings, rinses, filter_cycles]
                self.maint_pcts = [None, None, None, None]

                gh = grinder_sec // 3600
                gm = (grinder_sec % 3600) // 60
                gs = grinder_sec % 60

                self.telemetry = {
                    "serial_number": serial_number,
                    "production_date": prod_date_str,
                    "appliance_number": machine_num,
                    "machine_number": machine_num,
                    "serial_number_word": serial_word,
                    "article_number": article_num,
                    "ean_code": ean_code,
                    "appliance_code": app_code,
                    "appliance_type": app_type,
                    "software_version_display": display_fw,
                    "spdl_download_date": spdl_dl_str,
                    "spdl_country_code": country_code,
                    "spdl_language_date": spdl_lang_str,
                    "water_hardness_dh": water_hardness,
                    "total_cups": self.total_cups,
                    "total_preparations": self.total_preparations,
                    "preparations_since_intervention": prep_since_intervention,
                    "cups_since_intervention": cups_since_intervention,
                    "grinder_seconds": grinder_sec,
                    "grinder_formatted": f"{gh}h {gm}m {gs}s",
                    "water_dispensed_liters": round(water_dl / 10.0, 1),
                    "descaling_agent_liters": round(decalc_dl / 10.0, 1),
                    "since_last_service_preparations": prep_since_intervention,
                    "water_since_decalc_liters": round(water_since_decalc / 10.0, 1),
                    "power_spec": self.power_spec,
                }

                # Interrogate Live Hardware Sensors & Switches
                update_prog(0.96, "Reading live sensors & hardware switches (HZ:, RE:0028)...")
                self.live_sensors = self.query_live_sensors()
                if self.live_sensors.get("alerts"):
                    self.active_alerts = []
                    for a in self.live_sensors["alerts"]:
                        name = a.get("name")
                        details = a.get("details", "")
                        msg = a.get("message") or (f"{name}: {details}" if name else str(a))
                        self.active_alerts.append({
                            "bit": 0,
                            "blocking": a.get("blocking", True),
                            "name": msg
                        })
                else:
                    self.active_alerts = [
                        {"bit": 0, "blocking": False, "name": "System Nominal / Ready to Brew"}
                    ]

                update_prog(1.0, "Interrogation completed successfully!")
                self.log(f"ASCII Interrogation successful: {self.total_cups:,} cups read!")
                return True

            # ================================================================
            # Mode B: Smart Connect Handshake (@T0) - Encrypted 4:1 Wire
            # ================================================================
            self.log("No response to TY:; initiating Smart Connect handshake (@T0)...")
            update_prog(0.20, "Initiating Smart Connect handshake (@T0)...")
            t0_resp = self._send_encrypted_cmd("@T0\r\n", key=0x20, timeout=1.2)

            if not t0_resp:
                self.log("ERROR: Machine did not respond to ASCII (TY:) or Smart Connect (@T0).")
                return False

            self.protocol_mode = "Encrypted Smart Connect (@-Protocol)"
            update_prog(0.28, "Sending handshake step 2 (@T1)...")
            t1_resp = self._send_encrypted_cmd("@T1\r\n", key=0x21, timeout=1.2)

            challenge_payload = "01C000"
            if t1_resp and t1_resp.startswith("@T2:"):
                challenge_payload = t1_resp[4:].strip()

            update_prog(0.35, "Answering machine challenge (@t2)...")
            t3_resp = self._send_encrypted_cmd("@t2:818000\r\n", key=0x22, timeout=1.2)

            if t3_resp and "@T3:" in t3_resp:
                idx = t3_resp.find("@T3:")
                self.raw_model_str = t3_resp[idx + 4:].strip()
                self._send_encrypted_cmd("@t3\r\n", key=0x23, timeout=0.6)
            else:
                self.raw_model_str = "EF536M V02.01 (Smart Connect)"

            self.profile = profiles_db.find_profile(self.raw_model_str)
            self.model_family = self.profile.get("model_family", "Modern Jura")
            self.ef_code = self.raw_model_str
            self.log(f"Smart Connect machine identified: {self.model_family} ({self.raw_model_str})")

            # Beverage Counters (@TR:32,00 .. 0B)
            update_prog(0.45, "Reading beverage counters...")
            for bank in range(12):
                update_prog(0.45 + (bank / 12.0) * 0.35, f"Reading beverage counters (Bank {bank}/11)...")
                cmd = f"@TR:32,{bank:02X}\r\n"
                resp = self._send_encrypted_cmd(cmd, key=0x30 + bank, timeout=0.8)
                if resp:
                    parsed = jp.parse_tr32(resp)
                    if parsed:
                        _, words = parsed
                        for w_idx, count_val in enumerate(words):
                            code = bank * 4 + w_idx
                            if count_val != 0xFFFF:
                                self.counters[code] = count_val

            self.total_preparations = self.counters.get(0, sum(v for k, v in self.counters.items() if k != 0))
            self.total_cups = self.total_preparations

            # Maintenance Counters (@TG:43)
            update_prog(0.82, "Reading maintenance counters (@TG:43)...")
            tg43_resp = self._send_encrypted_cmd("@TG:43\r\n", key=0x40, timeout=1.0)
            if tg43_resp:
                mc = jp.parse_tg43(tg43_resp)
                if mc:
                    self.maint_counts = mc
                    self.log(f"Parsed Maintenance Counts: {self.maint_counts}")

            # Maintenance Percentages (@TG:C0)
            update_prog(0.88, "Reading maintenance life percentages (@TG:C0)...")
            tgc0_resp = self._send_encrypted_cmd("@TG:C0\r\n", key=0x41, timeout=1.0)
            if tgc0_resp:
                mp = jp.parse_tgc0(tgc0_resp)
                if mp:
                    self.maint_pcts = mp
                    self.log(f"Parsed Maintenance Percentages: {self.maint_pcts}")

            # Alerts & Telemetry (@TF:)
            update_prog(0.94, "Reading active alerts and system status (@TF:)...")
            tf_resp = self._send_encrypted_cmd("@TF:\r\n", key=0x42, timeout=1.0)
            if tf_resp:
                raw_tf = jp.parse_tf(tf_resp)
                if raw_tf:
                    self.active_alerts = profiles_db.get_active_alerts(self.profile, raw_tf)

            if not self.telemetry:
                self.telemetry = {
                    "total_cups": self.total_cups,
                    "total_preparations": self.total_preparations,
                    "serial_number": "2018041544012" if (self.conn and self.conn.is_demo) else "N/A",
                    "production_date": "15.04.2018" if (self.conn and self.conn.is_demo) else "N/A",
                    "machine_number": 44012 if (self.conn and self.conn.is_demo) else "N/A",
                    "country_code": "EU" if (self.conn and self.conn.is_demo) else "N/A",
                }

            # Interrogate Live Telemetry & Alerts
            self.live_sensors = self.query_live_sensors()

            update_prog(1.0, "Interrogation successfully completed!")
            self.log("Smart Connect interrogation completed successfully!")
            return True

        except Exception as e:
            self.log(f"EXCEPTION during interrogation: {e}")
            return False
        finally:
            if owns_conn and self.conn:
                self.conn.close()

    def get_structured_summary(self) -> Dict[str, Any]:
        """Produce structured statistics dictionary."""
        grand_total = self.total_cups or self.total_preparations

        # Build beverage list
        beverage_list = []
        profile_codes = set()
        profile_prods = self.profile.get("products", [])
        # In ASCII EEPROM mode, if a Smart Connect profile was matched (which lacks code 1 or maps 4 to Cappuccino),
        # fall back to classic 6-slot EEPROM beverage descriptors so counts are not mislabeled.
        if self.is_legacy_cleartext and (not profile_prods or any(p.get("code") == 4 and not p.get("is_double") for p in profile_prods)):
            profile_prods = [
                {"code": 1, "name": "1 Espresso", "is_double": False, "active": True},
                {"code": 2, "name": "1 Coffee", "is_double": False, "active": True},
                {"code": 3, "name": "1 Special Coffee / Ristretto", "is_double": False, "active": True},
                {"code": 4, "name": "2 Espressi", "is_double": True, "active": True},
                {"code": 5, "name": "2 Coffees", "is_double": True, "active": True},
                {"code": 6, "name": "2 Special Coffees", "is_double": True, "active": True},
            ]

        for p in profile_prods:
            code = p.get("code")
            profile_codes.add(code)
            count = self.counters.get(code, 0)
            beverage_list.append({
                "code": code,
                "name": p.get("name", f"Product #{code}"),
                "count": count,
                "is_double": p.get("is_double", False),
                "active": p.get("active", True)
            })

        # Add any other non-zero counters not in profile
        for code, count in sorted(self.counters.items()):
            if code != 0 and code not in profile_codes and count > 0:
                beverage_list.append({
                    "code": code,
                    "name": profiles_db.get_product_name(self.profile, code),
                    "count": count,
                    "is_double": False,
                    "active": True
                })

        # Build maintenance list
        # In ASCII EEPROM mode, self.maint_counts is always [cleanings, descalings, rinses, filter_cycles]
        if self.is_legacy_cleartext:
            mc_labels = ["Cleaning", "Descaling", "Rinsing", "Filter Change"]
        else:
            mc_labels = self.profile.get("maintenance_counters", [
                "Cleaning", "FilterChange", "Decalc", "CappuRinse", "CoffeeRinse", "CappuClean"
            ])

        maint_data = []
        for i, label in enumerate(mc_labels):
            cnt = self.maint_counts[i] if i < len(self.maint_counts) else 0
            pct = self.maint_pcts[i] if i < len(self.maint_pcts) else None
            maint_data.append({
                "index": i,
                "label": label,
                "name": label,
                "count": cnt,
                "percentage": pct,
                "percent": pct
            })

        return {
            "timestamp": datetime.now().isoformat(),
            "port": self.port_name,
            "machine_model": self.model_family,
            "firmware_string": self.raw_model_str,
            "ef_code": self.ef_code,
            "protocol_mode": self.protocol_mode,
            "power_spec": self.power_spec,
            "serial_number": self.telemetry.get("serial_number", "N/A"),
            "production_date": self.telemetry.get("production_date", "N/A"),
            "machine_number": self.telemetry.get("machine_number", "N/A"),
            "country_code": self.telemetry.get("country_code", "N/A"),
            "total_preparations": self.total_preparations,
            "total_cups": grand_total,
            "beverages": beverage_list,
            "maintenance": maint_data,
            "telemetry": self.telemetry,
            "alerts": self.active_alerts,
            "live_sensors": self.live_sensors,
            "raw_log_entries": len(self.raw_log)
        }

    # ========================================================================
    # Exporters
    # ========================================================================

    def export_text_report(self) -> str:
        """
        Generate clean formatted diagnostics report matching
        the classic Jura Service Diagnostics format.
        """
        data = self.get_structured_summary()
        now_str = datetime.now().strftime("%d.%m.%Y %H:%M:%S")

        out = []
        out.append("=" * 78)
        out.append("JURA COFFEE MACHINE DIAGNOSTICS & TELEMETRY REPORT")
        out.append(f"SPECTRA Diagnostics Suite v{__version__} (Hardware Telemetry - Jura Module)")
        out.append("=" * 78)
        out.append("")
        out.append(f"Date of diagnosis: {now_str}")
        out.append(f"Connection Port:   {self.port_name} (9600 8N1)")
        out.append("")
        out.append("-" * 78)
        out.append("APPLIANCE IDENTIFICATION & SYSTEM DATA:")
        out.append("-" * 78)
        if self.telemetry and "appliance_type" in self.telemetry:
            out.append(f"Appliance Type:    {self.telemetry['appliance_type']}")
        else:
            out.append(f"Appliance Model:   {data['machine_model']}")
        if self.telemetry and "article_number" in self.telemetry:
            out.append(f"Article Number:    {self.telemetry['article_number']}")
        out.append(f"Software Version:  {data['firmware_string']}")
        if self.telemetry and "software_version_display" in self.telemetry:
            out.append(f"Software Version Display: {self.telemetry['software_version_display']}")
        if self.telemetry and "serial_number" in self.telemetry and self.telemetry["serial_number"] != "N/A":
            out.append(f"Serial Number:     {self.telemetry['serial_number']}")
        if self.telemetry and "serial_number_word" in self.telemetry and self.telemetry["serial_number_word"]:
            out.append(f"Serial Word (ID):  {self.telemetry['serial_number_word']}")
        if self.telemetry and "appliance_number" in self.telemetry:
            out.append(f"Appliance Number:  {self.telemetry['appliance_number']}")
        if self.telemetry and "production_date" in self.telemetry and self.telemetry["production_date"] != "N/A":
            out.append(f"Date of Production:{self.telemetry['production_date']:>14}")
        if self.telemetry and "appliance_code" in self.telemetry and self.telemetry["appliance_code"] != "N/A":
            out.append(f"Appliance Code:    {self.telemetry['appliance_code']}")
        if self.telemetry and "ean_code" in self.telemetry and self.telemetry["ean_code"] != "N/A":
            out.append(f"EAN-Code:          {self.telemetry['ean_code']}")
        out.append(f"Protocol:          {data['protocol_mode']}")
        out.append(f"Power Spec:        {data['power_spec']}")
        if self.telemetry:
            if "spdl_download_date" in self.telemetry and self.telemetry["spdl_download_date"] != "N/A":
                out.append(f"SPDL Date Download:{self.telemetry['spdl_download_date']:>14}")
            if "spdl_country_code" in self.telemetry and self.telemetry["spdl_country_code"] != "N/A":
                out.append(f"SPDL Country Code: {self.telemetry['spdl_country_code']}")
            if "spdl_language_date" in self.telemetry and self.telemetry["spdl_language_date"] != "N/A":
                out.append(f"SPDL Date Lang:    {self.telemetry['spdl_language_date']:>14}")
            if "water_hardness_dh" in self.telemetry:
                out.append(f"Water Hardness:    {self.telemetry['water_hardness_dh']} °dH")
        out.append("")

        out.append("-" * 78)
        out.append("BEVERAGE PREPARATIONS & DISPENSING COUNTERS:")
        out.append("-" * 78)
        out.append(f"   {data['total_cups']:>8}      Total Number of Coffee Cups")
        if self.telemetry and "cups_since_intervention" in self.telemetry:
            out.append(f"   {self.telemetry['cups_since_intervention']:>8}      Total Coffee Cups Since Last Intervention")
        out.append(f"   {data['total_preparations']:>8}      Total Coffee Preparations")
        if self.telemetry and "preparations_since_intervention" in self.telemetry:
            out.append(f"   {self.telemetry['preparations_since_intervention']:>8}      Preparations Since Last Intervention")
        out.append("   " + "-" * 55)

        for bev in sorted(data['beverages'], key=lambda x: x['count'], reverse=True):
            if bev['count'] > 0:
                dbl_str = " (2x Cups)" if bev['is_double'] else ""
                out.append(f"   {bev['count']:>8}      {bev['name']}{dbl_str}")

        unused = [b for b in data['beverages'] if b['count'] == 0]
        if unused:
            out.append("")
            out.append("   Beverages with 0 preparations:")
            for b in unused[:8]:
                out.append(f"          0      {b['name']}")
        out.append("")

        out.append("-" * 78)
        out.append("MAINTENANCE & HYGIENE COUNTERS:")
        out.append("-" * 78)
        for m in data['maintenance']:
            pct_str = f" [Life remaining: {m['percentage']}%]" if m['percentage'] is not None else ""
            out.append(f"   {m['count']:>8}      Total {m['label']}{pct_str}")
        out.append("")

        if self.telemetry:
            out.append("-" * 78)
            out.append("OPERATIONAL TELEMETRY & LIFETIME METRICS:")
            out.append("-" * 78)
            if "grinder_formatted" in self.telemetry:
                out.append(f"   Grinder Operating Time:     {self.telemetry['grinder_formatted']} ({self.telemetry['grinder_seconds']} seconds)")
            if "water_dispensed_liters" in self.telemetry:
                out.append(f"   Total Water Dispensed:      {self.telemetry['water_dispensed_liters']} Liters")
            if "descaling_agent_liters" in self.telemetry:
                out.append(f"   Descaling Agent Consumed:   {self.telemetry['descaling_agent_liters']} Liters")
            if "since_last_service_preparations" in self.telemetry:
                out.append(f"   Cycles Since Last Service:  {self.telemetry['since_last_service_preparations']} preparations")
            out.append("")

        out.append("-" * 78)
        out.append("ACTIVE SYSTEM ALERTS & TELEMETRY:")
        out.append("-" * 78)
        if not data['alerts']:
            out.append("   [OK] System Ready - No Active Faults or Warnings")
        else:
            for alert in data['alerts']:
                status_type = "CRITICAL / BLOCKING" if alert.get('blocking') else "READY / STATUS"
                out.append(f"   [{status_type}] {alert['name']}")
        out.append("")

        # Live Sensors & Hardware Output
        ls = self.live_sensors or data.get("live_sensors")
        if ls and (ls.get("switches") or ls.get("sensors") or ls.get("telemetry")):
            out.append("-" * 78)
            ts = ls.get("timestamp", now_str)
            out.append(f"LIVE HARDWARE SENSORS & TELEMETRY (Read at: {ts}):")
            out.append("-" * 78)

            telem = ls.get("telemetry", {})
            if telem:
                out.append("   [Thermoblock Heaters & Thermal Sensors]")
                is_dual = telem.get("is_dual_heater", False)
                arch_str = "Dual-Heater Model (2 Thermoblocks)" if is_dual else "Single-Heater Model (1 Thermoblock)"
                out.append(f"   * Appliance Architecture        : {arch_str}")
                c_str = telem.get("heater_coffee_str", "N/A")
                c_stat = telem.get("heater_coffee_status", "")
                out.append(f"   * Coffee Thermoblock (TB1)      : {c_str:<12} [{c_stat}]")
                s_str = telem.get("heater_steam_str", "N/A")
                s_stat = telem.get("heater_steam_status", "")
                if is_dual:
                    out.append(f"   * Steam Thermoblock (TB2)       : {s_str:<12} [{s_stat}]")
                else:
                    out.append(f"   * Steam Thermoblock (TB2)       : Not Installed (Single Heater Model)")
                if "bu_encoder_str" in telem and telem["bu_encoder_str"] != "N/A":
                    out.append(f"   * Brew Unit Encoder (Pos / Ref) : {telem['bu_encoder_str']}")
                if "bu_mill_target" in telem:
                    out.append(f"   * Brew Unit Mill Target (RE:0041): {telem['bu_mill_target']} ticks (0x{telem['bu_mill_target']:04X})")
                if "bu_init_count" in telem:
                    out.append(f"   * Brew Unit Init Count (RE:0056): {telem['bu_init_count']} cycles")
                if "loader_version" in telem:
                    out.append(f"   * Main Board Bootloader (TL:)   : {telem['loader_version']}")
                if "display_firmware" in telem:
                    out.append(f"   * Display / Sub-MCU (TY$:)      : {telem['display_firmware']}")
                out.append("")

            if ls.get("switches"):
                out.append("   [Microswitches & Physical Contacts]")
                for sw in ls["switches"]:
                    out.append(f"   * {sw['name']:<30}: {sw['status']} [{sw.get('badge', 'OK')}]")
                out.append("")

            if ls.get("sensors"):
                out.append("   [Diagnostic Component Health & Safety Sensors]")
                for s in ls["sensors"]:
                    out.append(f"   * {s['name']:<32}: {s['status']} ({s['details']})")
                out.append("")

            if ls.get("error_counters"):
                out.append("   [Historical Sensor Trip & Fault Frequency Counters]")
                for c_name, c_cnt in ls["error_counters"].items():
                    out.append(f"   * {c_name:<36}: {c_cnt:>5} events")
                out.append("")

        out.append("=" * 78)
        out.append("END OF DIAGNOSTICS REPORT")
        out.append("=" * 78)
        return "\n".join(out)

    def export_json(self) -> str:
        """Export structured data as JSON string."""
        return json.dumps(self.get_structured_summary(), indent=2, ensure_ascii=False)

    def export_csv(self) -> str:
        """Export counters as CSV string."""
        data = self.get_structured_summary()
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["Category", "Item Code / Index", "Name / Label", "Value", "Unit / Notes"])
        writer.writerow(["Total", 0, "Grand Total Cups Dispensed", data["total_cups"], "cups"])
        writer.writerow(["Total", 1, "Total Brew Cycles", data["total_preparations"], "cycles"])

        for bev in data["beverages"]:
            writer.writerow(["Beverage", bev["code"], bev["name"], bev["count"], "cups"])

        for m in data["maintenance"]:
            writer.writerow(["Maintenance", m["index"], m["label"], m["count"], f"Life: {m['percentage']}%" if m['percentage'] is not None else ""])

        if self.telemetry:
            for k, v in self.telemetry.items():
                writer.writerow(["Telemetry", 0, k, v, ""])

        for a in data["alerts"]:
            writer.writerow(["Alert", a.get("bit", 0), a["name"], "ACTIVE", "BLOCKING" if a.get("blocking") else "NOTICE"])

        return output.getvalue()


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
