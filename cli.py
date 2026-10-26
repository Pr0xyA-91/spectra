#!/usr/bin/env python3
"""
SPECTRA - Universal Hardware Telemetry & Logic Board Diagnostics
Universal Appliance Telemetry & Diagnostics Engine (Jura Module)
"""

import sys
import os
import argparse
from typing import Optional

import serial_io
import profiles_db
import stats_collector as sc

__version__ = "0.4.1"


def print_banner():
    banner = r"""
  ███████╗██████╗ ███████╗ ██████╗████████╗██████╗  █████╗ 
  ██╔════╝██╔══██╗██╔════╝██╔════╝╚══██╔══╝██╔══██╗██╔══██╗
  ███████╗██████╔╝█████╗  ██║        ██║   ██████╔╝███████║
  ╚════██║██╔═══╝ ██╔══╝  ██║        ██║   ██╔══██╗██╔══██║
  ███████║██║     ███████╗╚██████╗   ██║   ██║  ██║██║  ██║
  ╚══════╝╚═╝     ╚══════╝ ╚═════╝   ╚═╝   ╚═╝  ╚═╝╚═╝  ╚═╝
   — Universal Hardware Telemetry & Logic Board Diagnostics (v0.4.1) —
    """
    print(banner)


def main():
    parser = argparse.ArgumentParser(
        description="SPECTRA - Universal Hardware Telemetry & Logic Board Diagnostics (v0.4.1)"
    )
    parser.add_argument("-V", "--version", action="version", version=f"SPECTRA {__version__} (Hardware Telemetry & Logic Board Diagnostics)")
    parser.add_argument("--cli", action="store_true", help="Run in command-line mode")
    parser.add_argument("-p", "--port", help="Serial port to connect to (e.g. /dev/ttyUSB0, /dev/ttyACM0, or demo)")
    parser.add_argument("-b", "--baud", type=int, default=9600, help="Baud rate (default: 9600)")
    parser.add_argument("--demo", action="store_true", help="Run with simulated demo machine (Jura S8)")
    parser.add_argument("--demo-model", choices=["S8", "E8", "Z10", "S8-SC"], default="S8", help="Model to simulate in demo mode")
    parser.add_argument("-s", "--sensors", "--live-sensors", action="store_true", help="Read and display live sensors, switches, and fault telemetry")
    parser.add_argument("--diff", metavar="BASELINE", help="Compare machine memory against baseline specification (e.g. EF518) or a previous JSON dump")
    parser.add_argument("-o", "--export", help="Output file path to save diagnostic report (.txt, .json, .csv)")
    parser.add_argument("-f", "--format", choices=["text", "json", "csv"], default="text", help="Report format (default: text)")
    parser.add_argument("--list-ports", action="store_true", help="List detected serial ports and exit")
    parser.add_argument("--list-models", action="store_true", help="List supported machine models and exit")
    parser.add_argument("-v", "--verbose", action="store_true", help="Show live raw serial protocol logging")

    args = parser.parse_args()

    if args.list_ports:
        ports = serial_io.list_serial_ports()
        print("Detected Serial Ports & Diagnostic Adapters:")
        for p in ports:
            print(f"  * {p}")
        sys.exit(0)

    if args.list_models:
        models = profiles_db.list_supported_models()
        print(f"Supported Machine Models ({len(models)} profiles):")
        for ef, label in models:
            print(f"  * {label:<35} [EF Code: {ef}]")
        sys.exit(0)

    print_banner()

    target_port = args.port
    if args.demo:
        target_port = f"DEMO / SIMULATION (Jura {args.demo_model})"

    if not target_port:
        available = [p for p in serial_io.list_serial_ports() if not p.startswith("DEMO")]
        if available:
            target_port = available[0]
            print(f"[*] Auto-detected serial port: {target_port}")
        else:
            print("[!] No physical serial adapter detected (/dev/ttyUSB* or /dev/ttyACM*).")
            print("[*] Falling back to interactive demo simulation mode.")
            target_port = f"DEMO / SIMULATION (Jura {args.demo_model})"

    print(f"[*] Connecting to: {target_port} at {args.baud} baud (8N1)...")

    # Fast Live Sensors Check Mode
    if args.sensors:
        print("[*] Interrogating live sensors and physical contacts...")
        sensors_data = sc.query_live_sensors(target_port, baudrate=args.baud)
        if "error" in sensors_data:
            print(f"[-] ERROR querying sensors: {sensors_data['error']}")
            sys.exit(1)

        print("\n" + "=" * 78)
        print(f"LIVE HARDWARE SENSORS & STATUS (Time: {sensors_data.get('timestamp')})")
        print(f"Port: {target_port} | Protocol: {sensors_data.get('protocol')}")
        print("=" * 78)

        print("\n[PHYSICAL MICROSWITCHES & LEVEL SENSORS]")
        for sw in sensors_data.get("switches", []):
            badge = f"[{sw.get('badge', 'OK')}]"
            print(f"  {sw.get('icon', '*')} {sw['name']:<32}: {sw['status']:<58} {badge:>10}")

        if sensors_data.get("alerts"):
            print("\n[ACTIVE SYSTEM WARNINGS & LOCKOUTS]")
            for a in sensors_data["alerts"]:
                lvl = a.get("level", "WARNING")
                msg = a.get("message") or f"{a.get('name')}: {a.get('details')}"
                print(f"  ⚠️ [{lvl}] {msg}")

        print("\n[DIAGNOSTIC COMPONENT HEALTH & SAFETY]")
        for s in sensors_data.get("sensors", []):
            badge = f"[{s.get('badge', 'OK')}]"
            print(f"  * {s['name']:<34}: {s['status']:<15} {badge:>8} -> {s['details']}")

        if sensors_data.get("error_counters"):
            print("\n[HISTORICAL SENSOR TRIP & FAULT FREQUENCY COUNTERS]")
            for c_name, c_cnt in sensors_data["error_counters"].items():
                print(f"  * {c_name:<36}: {c_cnt:>5} events")

        if sensors_data.get("telemetry"):
            print("\n[THERMAL HEATING & DUAL-THERMOBLOCK SENSORS]")
            telem = sensors_data["telemetry"]
            is_dual = telem.get("is_dual_heater", False)
            arch_str = "Dual-Heater Model (2 Thermoblocks)" if is_dual else "Single-Heater Model (1 Thermoblock)"
            print(f"  * Machine Architecture             : {arch_str}")

            c_str = telem.get("heater_coffee_str", "N/A")
            c_stat = telem.get("heater_coffee_status", "Nominal")
            raw_c = telem.get("heater_coffee_raw", telem.get("heater_ntc_raw", 0))
            print(f"  ☕ Coffee Thermoblock (TB1)        : {c_str:<12} [{c_stat}] (ADC: 0x{raw_c:04X})")

            s_str = telem.get("heater_steam_str", "N/A")
            s_stat = telem.get("heater_steam_status", "")
            raw_s = telem.get("heater_steam_raw", 0)
            if is_dual:
                print(f"  💨 Steam Thermoblock (TB2)         : {s_str:<12} [{s_stat}] (ADC: 0x{raw_s:04X})")
            else:
                print(f"  💨 Steam Thermoblock (TB2)         : Not Installed (Single Heater Model)")

            if "bu_encoder_str" in telem and telem["bu_encoder_str"] != "N/A":
                raw_pos = telem.get("bu_encoder_pos", 0)
                raw_ref = telem.get("bu_encoder_upper", 0)
                bu_st = telem.get("bu_position_state", "Home / Mill Position")
                bu_pct = telem.get("bu_stroke_pct", 0)
                print(f"  ⚙️ Brew Unit Encoder (Pos / Ref)   : {telem['bu_encoder_str']:<18} [{bu_st} | {bu_pct}%] (0x{raw_pos:04X} / 0x{raw_ref:04X})")
            if "bu_mill_target" in telem:
                print(f"  🎯 Brew Unit Mill Target (RE:0041) : {telem['bu_mill_target']} ticks (0x{telem['bu_mill_target']:04X})")
            if "bu_init_count" in telem:
                print(f"  🔄 Brew Unit Init Counter (RE:0056): {telem['bu_init_count']} cycles")

            print("\n[SYSTEM SETTINGS, SUBSYSTEMS & HYDRAULIC SENSORS]")
            if "loader_version" in telem:
                print(f"  * Main Board Bootloader (TL:)      : {telem['loader_version']}")
            if "display_firmware" in telem:
                print(f"  * Display / Sub-MCU Firmware (TY$:): {telem['display_firmware']}")
            if "water_hardness_dh" in telem:
                print(f"  * Configured Water Hardness        : {telem['water_hardness_dh']} °dH")
            if "filter_volume_liters" in telem:
                print(f"  * Water Volume Through Filter      : {telem['filter_volume_liters']} Liters")
            if "rotary_switch" in telem:
                print(f"  * Selection / Rotary Switch Position: {telem['rotary_switch']}")
            if "button_matrix" in telem:
                print(f"  * Front Panel Key Matrix / Aux Bits: 0x{telem['button_matrix']} / {telem.get('aux_inputs', '00')}")

        print("=" * 78 + "\n")

        if args.export:
            out_path = os.path.abspath(args.export)
            import json
            try:
                with open(out_path, "w", encoding="utf-8") as f:
                    json.dump(sensors_data, f, indent=2, ensure_ascii=False)
                print(f"[+] Sensor telemetry saved to: {out_path}")
            except Exception as e:
                print(f"[-] ERROR saving sensor telemetry to {out_path}: {e}")

        sys.exit(0)

    # Automated EEPROM Baseline Diff Mode
    if args.diff:
        print(f"[*] Auditing and diffing machine against baseline: {args.diff}...")
        conn = serial_io.JuraSerialConnection(target_port, baudrate=args.baud)
        live_dump = {}
        try:
            # Read gateways
            for gw in ["TY:", "TL:", "TY$:", "TL$:", "CS$:", "IC:", "HZ:", "AS:"]:
                live_dump[gw] = conn.query_ascii(gw, timeout=0.8)
            # Read EEPROM blocks
            live_eeprom = {}
            for addr in range(0x0000, 0x0200, 0x0010):
                r = conn.query_ascii(f"RT:{addr:04X}", timeout=1.0)
                if r and r.startswith("rt:"):
                    payload = r[3:].strip()
                    for w_idx in range(len(payload) // 4):
                        live_eeprom[f"{addr + w_idx:04X}"] = payload[w_idx*4 : (w_idx+1)*4]
            live_dump["eeprom"] = live_eeprom
        finally:
            conn.close()

        diff_report = sc.generate_eeprom_diff_report(live_dump, args.diff, label=target_port)
        print("\n" + diff_report)

        if args.export:
            out_path = os.path.abspath(args.export)
            try:
                with open(out_path, "w", encoding="utf-8") as f:
                    f.write(diff_report)
                print(f"[+] Diff report saved to: {out_path}")
            except Exception as e:
                print(f"[-] ERROR saving diff report to {out_path}: {e}")
        sys.exit(0)

    def log_handler(msg: str):
        if args.verbose:
            print(f"    {msg}")

    def prog_handler(pct: float, status: str):
        bar_len = 30
        filled = int(round(bar_len * pct))
        bar = "=" * filled + "-" * (bar_len - filled)
        sys.stdout.write(f"\r[*] Progress: [{bar}] {pct*100:3.0f}% - {status:<45}")
        sys.stdout.flush()

    with sc.JuraStatsSession(target_port, baudrate=args.baud, log_cb=log_handler) as session:
        print()
        success = session.run_interrogation(progress_cb=prog_handler)
        print("\n")

        if not success:
            print("[-] FAILED to read statistics from machine. Check connections, permissions, or port.")
            sys.exit(1)

        print("[+] Successfully interrogated machine!")
        text_report = session.export_text_report()
        print("\n" + text_report)

        if args.export:
            out_path = os.path.abspath(args.export)
            fmt = args.format
            if out_path.endswith(".json"):
                fmt = "json"
            elif out_path.endswith(".csv"):
                fmt = "csv"

            if fmt == "json":
                content = session.export_json()
            elif fmt == "csv":
                content = session.export_csv()
            else:
                content = text_report

            try:
                with open(out_path, "w", encoding="utf-8") as f:
                    f.write(content)
                print(f"\n[+] Diagnostic report saved to: {out_path} ({len(content)} bytes)")
            except Exception as e:
                print(f"\n[-] ERROR saving report to {out_path}: {e}")


if __name__ == "__main__":
    main()
