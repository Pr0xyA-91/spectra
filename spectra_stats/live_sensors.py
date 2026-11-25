#!/usr/bin/env python3
"""SPECTRA real-time live sensor & telemetry interrogation across supported manufacturers."""

import time
from datetime import datetime
from typing import Dict, List, Any, Optional, Tuple

import jura_protocol as jp
import profiles_db
from serial_io import JuraSerialConnection

from spectra_stats.calibration import (
    DUAL_HEATER_EFS,
    TWO_DIGIT_ADDRESS_EFS,
    get_optical_bean_calibration,
)
from spectra_stats.decoders import (
    decode_jura_temperature,
    evaluate_brew_unit_position,
    evaluate_thermoblock_status,
)

_last_flowmeter_samples: Dict[str, Tuple[int, float, float]] = {}
_last_bu_samples: Dict[str, Tuple[int, float, int]] = {}

def query_live_sensors(
    port_name: str,
    baudrate: int = 9600,
    conn: Optional[JuraSerialConnection] = None,
    profile: Optional[Dict[str, Any]] = None,
    is_legacy: bool = True,
    fast_poll: bool = False,
    manufacturer: str = "auto",
    **kwargs
) -> Dict[str, Any]:
    """
    Query live physical microswitches, hardware sensor statuses,
    temperature ADC readings, and component fault registers from the connected appliance.
    Supports Jura (ASCII / Smart Connect) and multi-manufacturer protocols (Nivona, Kalerm, Jetinno).
    """
    mfr_clean = (manufacturer or "auto").strip().lower()
    demo_vendor = getattr(conn, "demo_vendor", "jura") if conn else "jura"

    if mfr_clean not in ("jura", "auto") or demo_vendor not in ("jura", "hardware"):
        try:
            from spectra_engine import SpectraSession
            sess = None
            if conn is not None:
                cached_sess = getattr(conn, "_cached_spectra_session", None)
                if (
                    cached_sess is not None
                    and getattr(cached_sess, "conn", None) is conn
                    and getattr(cached_sess, "manufacturer", None) == mfr_clean
                ):
                    sess = cached_sess
                else:
                    sess = SpectraSession(port_name=port_name, baudrate=baudrate, conn=conn, manufacturer=mfr_clean)
                    setattr(conn, "_cached_spectra_session", sess)
            else:
                sess = SpectraSession(port_name=port_name, baudrate=baudrate, conn=conn, manufacturer=mfr_clean)
            return sess.query_live_sensors(fast_poll=fast_poll)
        except Exception:
            if conn is not None:
                try:
                    setattr(conn, "_cached_spectra_session", None)
                except Exception:
                    pass
            pass
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

    has_commercial_bean_sensor = False
    try:
        # Check if ASCII mode responds to TY:
        # In fast_poll mode, avoid redundant TY: and RE:0028 serial queries if cached on connection
        if getattr(conn, "_is_smart_connect", False) or "SMART CONNECT" in port_name.upper():
            detected_ef = getattr(conn, "_cached_ef", "") or ""
            is_ascii = False
        else:
            cached_ef = getattr(conn, "_cached_ef", None)
            if cached_ef:
                detected_ef = cached_ef
                is_ascii = True
            else:
                ty_resp = conn.query_ascii("TY:")
                is_ascii = (ty_resp is not None and ty_resp.startswith("ty:"))
                if not is_ascii and conn.is_demo:
                    is_ascii = "SMART CONNECT" not in conn.port_name.upper()
                elif not is_ascii and ("tty" in port_name.lower() or "com" in port_name.lower()):
                    hz_check = conn.query_ascii("HZ:")
                    if hz_check and hz_check.startswith("hz:"):
                        is_ascii = True
                detected_ef = ""
                if ty_resp and ty_resp.startswith("ty:"):
                    toks = ty_resp[3:].strip().split()
                    if toks:
                        detected_ef = toks[0].upper()
                if is_ascii and detected_ef:
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
            hz_beans_charged = True
            heater_ready_flag = True
            button_matrix_hex = "0000"
            aux_inputs_bits = "00"
            cake_thickness_ticks = 0
            has_hz_status = False
            parts: List[str] = []

            if hz_resp and hz_resp.startswith("hz:"):
                payload = hz_resp[3:].strip()
                parts = payload.split(",")

                if len(parts) > 0 and len(parts[0]) >= 7:
                    has_hz_status = True
                    bu_init_ok = (parts[0][1] == "1")
                    mv_busy = (parts[0][2] == "1")
                    hz_beans_charged = (parts[0][3] == "1")
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

            if port_key not in _last_flowmeter_samples and len(_last_flowmeter_samples) >= 32:
                _last_flowmeter_samples.pop(next(iter(_last_flowmeter_samples)), None)
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

            # 2. Query Diagnostic Fault & Input Registers (RE:0028, RE:0029, IC:)
            val_r28 = 0
            total_fm_timeouts = 0
            fm_intake_timeouts = 0
            fm_rinse_timeouts = 0
            bu_mill_target = getattr(conn, "_cached_bu_mill_target", 0)
            bu_init_count = 0
            loader_version = ""
            display_firmware = ""

            has_commercial_bean_sensor = bool(
                getattr(conn, "_as_supported", False)
                or (detected_ef and any(x in str(detected_ef).upper() for x in ("EF518", "XJ", "GIGA")))
                or ("XJ" in str(port_name).upper() or "GIGA" in str(port_name).upper())
            )

            # Query non-volatile configuration register RE:0029 (filter flags)
            cached_r29 = getattr(conn, "_cached_val_r29", None)
            should_query_r29 = (conn is not None and (not fast_poll or cached_r29 is None))

            val_r29 = cached_r29 if cached_r29 is not None else 0
            if should_query_r29:
                r29 = conn.query_ascii("RE:0029")
                if r29 and r29.startswith("re:"):
                    try:
                        val_r29 = int(r29[3:], 16)
                        setattr(conn, "_cached_val_r29", val_r29)
                    except ValueError:
                        pass

            raw_cs = getattr(conn, "_cached_raw_cs", None)
            if not fast_poll:
                # Query CS: (Component Status) during full interrogation
                cs_resp = conn.query_ascii("CS:")
                if cs_resp and cs_resp.lower().startswith("cs:"):
                    raw_cs = cs_resp
                    setattr(conn, "_cached_raw_cs", raw_cs)
                if raw_cs:
                    results["raw_cs"] = raw_cs

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
                val_r28 = getattr(conn, "_cached_val_r28", 0)
                results["fault_register_hex"] = f"0x{val_r28:04X}"

            # Coffee Heater NTC Diagnostic Sensor Self-Test (AS: Check Sensor - P518Ani.exe VA 0x004E6E28, String #251)
            # Polled during manual refresh (not fast_poll), on first query of a session, or every ~2.0s in Live Data
            last_as_ts = getattr(conn, "_last_as_ts", 0.0)
            cached_beans = getattr(conn, "_cached_beans_ok", None)
            as_supported = getattr(conn, "_as_supported", None)
            should_query_as = (as_supported is not False) and ((not fast_poll) or (cached_beans is None) or (now_ts - last_as_ts >= 3.0))

            if should_query_as:
                as_resp = conn.query_ascii("AS:")
                if as_resp and as_resp.startswith("as:"):
                    results["raw_as"] = as_resp
                    as_parts = as_resp[3:].split(",")
                    if len(as_parts) >= 2 and len(as_parts[0]) >= 8 and len(as_parts[1]) >= 8:
                        try:
                            off_adc = int(as_parts[0][4:8], 16)
                            on_adc = int(as_parts[1][4:8], 16)
                            # P518Ani.exe Check Sensor valid window: 180 < off_adc < 17000
                            if 0 < off_adc < 17000 and 0 < on_adc < 18500:
                                setattr(conn, "_cached_bean_adcs", (off_adc, on_adc))
                                setattr(conn, "_last_as_ts", now_ts)
                                setattr(conn, "_as_supported", True)
                                setattr(conn, "_as_fail_count", 0)
                        except ValueError:
                            pass
                elif as_resp is None and not conn.is_demo:
                    # Require 3 consecutive initial failures before treating AS: as unsupported
                    fail_cnt = getattr(conn, "_as_fail_count", 0) + 1
                    setattr(conn, "_as_fail_count", fail_cnt)
                    if fail_cnt >= 3 and getattr(conn, "_as_supported", None) is None:
                        setattr(conn, "_as_supported", False)

            # Re-evaluate commercial bean sensor support after AS: query
            has_commercial_bean_sensor = bool(
                getattr(conn, "_as_supported", False)
                or (detected_ef and any(x in str(detected_ef).upper() for x in ("EF518", "XJ", "GIGA")))
                or ("XJ" in str(port_name).upper() or "GIGA" in str(port_name).upper())
            )

            # Evaluate bean hopper status:
            # On Jura appliances, puck compression measurement <= 14 ticks indicates an empty grinder run (Universal fallback).
            # Note: On EF518 (XJ5/XJ9), the optical bean barrier is wired directly to the EF518D Display PCB and monitored locally.
            puck_empty = (cake_thickness_ticks > 0 and cake_thickness_ticks <= 14)
            beans_ok = not puck_empty
            setattr(conn, "_cached_beans_ok", beans_ok)

            # Evaluate dynamic Brew Unit mechanical position & movement delta
            prev_bu = _last_bu_samples.get(port_key)
            bu_delta_ticks = 0
            if prev_bu is not None:
                prev_bu_pos, prev_bu_ts, prev_bu_target = prev_bu
                if not bu_mill_target and prev_bu_target:
                    bu_mill_target = prev_bu_target
                if (now_ts - prev_bu_ts) < 10.0 and prev_bu_pos > 0 and bu_encoder_pos_raw > 0:
                    bu_delta_ticks = bu_encoder_pos_raw - prev_bu_pos
            if port_key not in _last_bu_samples and len(_last_bu_samples) >= 32:
                _last_bu_samples.pop(next(iter(_last_bu_samples)), None)
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
                if val_r29 is not None:
                    filter_ext = bool(val_r29 & 0x0001)
                    filter_claris = bool(val_r29 & 0x0010)

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
                    "details": "Monitored Locally by Display MCU (EF518D)" if has_commercial_bean_sensor else ("Puck thickness nominal" if beans_ok else "Grinder dry run detected"),
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
            _opt_cal = get_optical_bean_calibration()
            opt_thresh = _opt_cal["threshold"]
            opt_hyst = _opt_cal["hysteresis"]
            opt_lower = opt_thresh - opt_hyst
            opt_upper = opt_thresh + opt_hyst
            delta = None
            cached_adcs = getattr(conn, "_cached_bean_adcs", None)
            shunt_ratio = None
            gain_pct = None
            ntc_self_test_ok = None
            if cached_adcs:
                off_adc, on_adc = cached_adcs
                delta = on_adc - off_adc
                shunt_ratio = round(on_adc / off_adc, 4) if off_adc > 0 else 1.0
                gain_pct = round((shunt_ratio - 1.0) * 100.0, 2)
                ntc_self_test_ok = (180 < off_adc < 17000) and (1.050 <= shunt_ratio <= 1.070)

                # Coffee Heater NTC Diagnostic Sensor Self-Test (P518Ani.exe Check Sensor VA 0x004E6E28, String #251)
                sensor_list.append({
                    "id": "heater_ntc_diagnostic_sensor",
                    "name": "Coffee Heater NTC Diagnostic Sensor",
                    "status": "CALIBRATION NOMINAL (+6.0% Shunt OK)" if ntc_self_test_ok else "CALIBRATION WARNING / OUT OF RANGE",
                    "ok": ntc_self_test_ok,
                    "badge": f"{shunt_ratio:.4f} (+{gain_pct}%)" if ntc_self_test_ok else "FAULT",
                    "details": f"NTC Calibration Self-Test (AS:): Shunt ON ADC {on_adc} / Ambient OFF ADC {off_adc} (Ratio: {shunt_ratio:.4f}, Gain: +{gain_pct}%) | Range: 180..17000 | Status: {'Circuit Nominal' if ntc_self_test_ok else 'False Values (P518 String #251)'}",
                    "icon": "🌡️",
                    "value": shunt_ratio,
                    "unit": "ratio"
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
            has_error_counters = not (detected_ef.startswith("EF634") or detected_ef in TWO_DIGIT_ADDRESS_EFS)
            if not fast_poll and has_error_counters:
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
                "heater_ntc_self_test_ok": ntc_self_test_ok if cached_adcs else None,
                "heater_ntc_shunt_ratio": shunt_ratio if cached_adcs else None,
                "heater_ntc_shunt_gain_pct": gain_pct if cached_adcs else None,
                "optical_threshold": opt_thresh,
                "optical_hysteresis": opt_hyst,
                "optical_lower": opt_lower,
                "optical_upper": opt_upper,
                "optical_delta": delta,
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

            has_any_hz = bool(hz_resp and hz_resp.startswith("hz:") and len(parts) > 0)
            if not has_any_hz:
                for sw in results["switches"]:
                    if sw.get("id") == "machine_ready":
                        sw["status"] = "No Live HZ: Reply"
                        sw["ok"] = False
                        sw["badge"] = "NO FRAME"
                        sw["icon"] = "⚠️"
                results["telemetry"]["machine_state_badge"] = "NO FRAME"
                results["telemetry"]["machine_state_status"] = "No Live HZ: Reply"

            results["capabilities"] = {
                "vendor": "Jura",
                "topology": "jura_dual" if is_dual_heater else "jura_single",
                "protocol": results["protocol"],
                "ef_code": detected_ef or (profile or {}).get("ef_code", ""),
                "has_live_frame": has_any_hz,
                "has_coffee_temp": temp_coffee is not None,
                "has_steam_temp": bool(is_dual_heater and temp_steam is not None),
                "has_flowmeter": has_any_hz,
                "has_bu_encoder": bool(has_any_hz and (bu_encoder_upper_raw > 0 or bu_encoder_pos_raw > 0)),
                "has_valve_state": has_hz_status,
                "has_as_shunt": bool(cached_adcs or getattr(conn, "_as_supported", False)),
                "has_bean_sensor": has_any_hz or has_commercial_bean_sensor,
                "has_grounds_sensor": has_any_hz,
                "has_door_sensor": False,
                "has_cup_sensor": False,
                "has_pressure_sensor": False,
                "has_filter_sensor": True,
            }
            results["raw_frames"] = {
                "primary_cmd": "HZ:",
                "primary_raw": hz_resp or "",
                "tokens": list(parts) if has_any_hz else [],
                "cs": results.get("raw_cs", "") or "",
                "ic": results.get("raw_ic", "") or "",
                "as": results.get("raw_as", "") or "",
            }
        else:
            # Smart Connect Protocol Mode
            results["protocol"] = "Encrypted Smart Connect (@-Protocol)"
            if hasattr(conn, "query_encrypted"):
                tf_resp = conn.query_encrypted("@TF:\r\n", key=0x42, timeout=1.0)
                if not tf_resp and not getattr(conn, "_is_smart_connect", False):
                    t0_r = conn.query_encrypted("@T0\r\n", key=0x20, timeout=1.0)
                    if t0_r:
                        conn.query_encrypted("@T1\r\n", key=0x21, timeout=0.8)
                        conn.query_encrypted("@t2:818000\r\n", key=0x22, timeout=0.8)
                        conn.query_encrypted("@t3\r\n", key=0x23, timeout=0.6)
                        setattr(conn, "_is_smart_connect", True)
                        tf_resp = conn.query_encrypted("@TF:\r\n", key=0x42, timeout=1.0)
                elif tf_resp:
                    setattr(conn, "_is_smart_connect", True)
            else:
                wire_tx = jp.encode_wire(jp.build_encrypted_frame("@TF:\r\n", 0x42))
                conn.write(wire_tx)
                raw_rx = conn.read(512, timeout_sec=1.0)
                tf_resp = None
                if raw_rx:
                    if raw_rx.startswith(wire_tx):
                        raw_rx = raw_rx[len(wire_tx):]
                    aligned_len = (len(raw_rx) // 4) * 4
                    if aligned_len >= 4:
                        decoded, _ = jp.decode_wire(raw_rx[:aligned_len])
                        amp = decoded.find(b"&")
                        end = decoded.find(b"\r\n", amp) if amp != -1 else -1
                        if amp != -1 and end != -1:
                            pt = jp.decode_encrypted_frame(decoded[amp:end + 2])
                            if pt and pt.strip() != "@TF:":
                                tf_resp = pt

            has_tf_frame = bool(tf_resp and str(tf_resp).strip())
            results["raw_status"] = tf_resp or "N/A"
            active_alerts = []
            tf_tokens: List[str] = []
            if has_tf_frame:
                raw_tf = jp.parse_tf(tf_resp)
                if raw_tf:
                    active_alerts = profiles_db.get_active_alerts(profile or profiles_db.DEFAULT_PROFILE, raw_tf)
                tf_clean = str(tf_resp).strip()
                tf_payload = tf_clean.split(":", 1)[1].strip() if ":" in tf_clean else tf_clean
                if "," in tf_payload:
                    tf_tokens = [tok.strip() for tok in tf_payload.split(",") if tok.strip()]
                elif tf_payload:
                    tf_tokens = [tf_payload[i:i + 4] for i in range(0, len(tf_payload), 4)]

            alert_names = [a["name"].lower() for a in active_alerts]
            tank_ok = not any("water" in a for a in alert_names)
            tray_ok = not any("tray" in a for a in alert_names)
            beans_ok = not any("bean" in a for a in alert_names)
            ready_ok = has_tf_frame and (any("ready" in a for a in alert_names) or (len(active_alerts) == 0))

            results["switches"] = [
                {
                    "id": "water_tank",
                    "name": "Water Tank Level Sensor",
                    "status": ("Water OK / Tank Present" if tank_ok else "Fill Water Tank / Tank Empty") if has_tf_frame else "No @TF: Reply",
                    "ok": tank_ok if has_tf_frame else False,
                    "badge": ("NORMAL" if tank_ok else "WARNING") if has_tf_frame else "NO FRAME",
                    "icon": "💧"
                },
                {
                    "id": "drip_tray",
                    "name": "Drip Tray / Drawer Contact",
                    "status": ("Tray Inserted" if tray_ok else "Insert / Empty Tray") if has_tf_frame else "No @TF: Reply",
                    "ok": tray_ok if has_tf_frame else False,
                    "badge": ("NORMAL" if tray_ok else "WARNING") if has_tf_frame else "NO FRAME",
                    "icon": "📥"
                },
                {
                    "id": "bean_hopper",
                    "name": "Bean Hopper / Charge Sensor",
                    "status": ("Beans OK / Hopper Charged" if beans_ok else "Fill Beans / Hopper Empty") if has_tf_frame else "No @TF: Reply",
                    "ok": beans_ok if has_tf_frame else False,
                    "badge": ("NORMAL" if beans_ok else "FILL BEANS") if has_tf_frame else "NO FRAME",
                    "details": "Monitored Locally by Display MCU (EF518D)" if has_commercial_bean_sensor else ("Smart Connect @TF: status bit" if has_tf_frame else "Awaiting @TF: reply"),
                    "icon": "🫘"
                },
                {
                    "id": "machine_ready",
                    "name": "Appliance Operating State",
                    "status": ("Ready to Brew / Nominal" if ready_ok else "Busy / Status Notification") if has_tf_frame else "No @TF: Reply",
                    "ok": ready_ok,
                    "badge": ("READY" if ready_ok else "BUSY") if has_tf_frame else "NO FRAME",
                    "icon": "☕"
                }
            ]
            results["sensors"] = [
                {
                    "id": "system_status",
                    "name": "Smart Connect Telemetry Bus",
                    "status": "Active (@TF: Alert Bitmask Only)" if has_tf_frame else "No @TF: Reply",
                    "ok": has_tf_frame,
                    "badge": "NOMINAL" if has_tf_frame else "NO FRAME",
                    "details": "Encrypted @TF: status bus active (numeric temperatures, flowmeter & brew unit ticks are not exposed by @TF:)" if has_tf_frame else "Machine did not respond to @TF: telemetry query"
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
                "beans_ok": beans_ok if has_tf_frame else None,
                "is_dual_heater": is_dual_sc,
                "heater_count": 2 if is_dual_sc else 1,
                "heater_coffee_str": "Nominal (@TF:)" if has_tf_frame else "No Frame",
                "heater_coffee_status": "Ready" if has_tf_frame else "No Frame",
                "heater_steam_str": ("Nominal (@TF:)" if has_tf_frame else "No Frame") if is_dual_sc else "Not Installed (Single Heater Model)",
                "heater_steam_status": ("Ready" if has_tf_frame else "No Frame") if is_dual_sc else "Not Installed",
                "machine_state_badge": ("READY" if ready_ok else "BUSY") if has_tf_frame else "NO FRAME",
                "machine_state_status": ("Ready to Brew / Nominal" if ready_ok else "Busy / Status Notification") if has_tf_frame else "No @TF: Reply",
                "flow_pulses": 0,
                "flow_rate_ml_s": 0.0,
                "flow_volume_ml": 0.0,
            }
            results["capabilities"] = {
                "vendor": "Jura",
                "topology": "jura_smart_connect",
                "protocol": results["protocol"],
                "ef_code": detected_ef or profile_ef or "",
                "has_live_frame": has_tf_frame,
                "has_coffee_temp": False,
                "has_steam_temp": False,
                "has_flowmeter": False,
                "has_bu_encoder": False,
                "has_valve_state": False,
                "has_as_shunt": False,
                "has_bean_sensor": has_tf_frame,
                "has_grounds_sensor": False,
                "has_door_sensor": False,
                "has_cup_sensor": False,
                "has_pressure_sensor": False,
                "has_filter_sensor": False,
            }
            results["raw_frames"] = {
                "primary_cmd": "@TF:",
                "primary_raw": tf_resp or "",
                "tokens": tf_tokens,
                "cs": "",
                "ic": "",
                "as": "",
            }

    except Exception as e:
        results["error"] = str(e)
    finally:
        if close_when_done and conn:
            conn.close()

    return results

