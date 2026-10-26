#!/usr/bin/env python3
"""
W.R.A.T. - WhiteRat Asynchronous Telemetry
Universal Appliance Telemetry & Diagnostics Engine
Supports Jura, Nivona, Lamanti-KL (Kalerm), and Lamanti-JN (Jetinno).
"""

import sys
import os
import argparse
import json
from typing import Optional

import serial_io
import profiles_db
import stats_collector as sc
from wrat_engine import WRATSession, format_text_summary, format_csv_summary
from drivers import list_drivers, DRIVER_DISPLAY_NAMES

__version__ = "0.1"


def print_banner():
    banner = r"""
 __      __   __________     _____  ___________
/  \    /  \  \______   \   /  _  \ \__    ___/
\   \/\/   /   |       _/  /  /_\  \  |    |   
 \        /    |    |   \ /    |    \ |    |   
  \__/\  /     |____|_  / \____|__  / |____|   
       \/             \/          \/           
      W.R.A.T. — WhiteRat Asynchronous Telemetry (v0.1)
   Universal Diagnostics Engine [Multi-Manufacturer Support]
   Supported: Jura | Nivona | Lamanti-KL | Lamanti-JN
    """
    print(banner)


def main():
    parser = argparse.ArgumentParser(
        description="W.R.A.T. - WhiteRat Asynchronous Telemetry (Universal Multi-Manufacturer Engine)"
    )
    parser.add_argument("-V", "--version", action="version", version=f"W.R.A.T. {__version__} (WhiteRat Asynchronous Telemetry)")
    parser.add_argument("--cli", action="store_true", help="Run in command-line mode")
    parser.add_argument("-m", "--manufacturer", choices=["auto", "jura", "nivona", "lamanti-kl", "lamanti-jn"], default="auto", help="Appliance manufacturer driver (default: auto)")
    parser.add_argument("-p", "--port", help="Serial port to connect to (e.g. /dev/ttyUSB0, /dev/ttyACM0, or demo)")
    parser.add_argument("-b", "--baud", type=int, default=9600, help="Baud rate (default: 9600)")
    parser.add_argument("--demo", action="store_true", help="Run with simulated demo machine")
    parser.add_argument("--demo-model", choices=["S8", "E8", "Z10", "NICR768", "X680C", "JL300"], default="S8", help="Model to simulate in demo mode")
    parser.add_argument("-s", "--sensors", "--live-sensors", action="store_true", help="Read and display live sensors, switches, and fault telemetry")
    parser.add_argument("-o", "--export", help="Output file path to save diagnostic report (.txt, .json, .csv)")
    parser.add_argument("-f", "--format", choices=["text", "json", "csv"], default="text", help="Report format (default: text)")
    parser.add_argument("--list-ports", action="store_true", help="List detected serial ports and exit")
    parser.add_argument("--list-models", action="store_true", help="List supported machine models and exit")
    parser.add_argument("--list-manufacturers", action="store_true", help="List supported appliance manufacturers and exit")
    parser.add_argument("-v", "--verbose", action="store_true", help="Show live raw serial protocol logging")

    args = parser.parse_args()

    if args.list_manufacturers:
        print("Supported Appliance Manufacturers in W.R.A.T.:")
        for key, name, cls in list_drivers():
            caps = cls.capabilities
            caps_str = f"Live Sensors: {'YES' if caps.has_live_sensors else 'NO'} | Thermal: {'YES' if caps.has_thermal_sensors else 'NO'}"
            print(f"  * {name:<52} [Key: {key:<10}] ({caps_str})")
        sys.exit(0)

    if args.list_ports:
        ports = serial_io.list_serial_ports()
        print("Detected Serial Ports & Diagnostic Adapters:")
        for p in ports:
            print(f"  * {p}")
        sys.exit(0)

    if args.list_models:
        models = profiles_db.list_supported_models()
        print(f"Supported Jura Machine Models ({len(models)} profiles):")
        for ef, label in models:
            print(f"  * {label:<35} [EF Code: {ef}]")
        sys.exit(0)

    print_banner()

    target_port = args.port
    if args.demo:
        target_port = f"DEMO / SIMULATION ({args.demo_model})"

    if not target_port:
        available = [p for p in serial_io.list_serial_ports() if not p.startswith("DEMO")]
        if available:
            target_port = available[0]
            print(f"[*] Auto-detected serial port: {target_port}")
        else:
            print("[!] No physical serial adapter detected (/dev/ttyUSB* or /dev/ttyACM*).")
            print("[*] Falling back to interactive demo simulation mode.")
            target_port = f"DEMO / SIMULATION ({args.demo_model})"

    print(f"[*] Manufacturer mode: {args.manufacturer.upper()} | Port: {target_port} at {args.baud} baud (8N1)...")

    # Initialize WRAT session
    session = WRATSession(
        port_name=target_port,
        baudrate=args.baud,
        manufacturer=args.manufacturer
    )

    # Fast Live Sensors Check Mode
    if args.sensors:
        print("[*] Interrogating live sensors and physical contacts...")
        try:
            sensors_data = session.query_live_sensors()
        except Exception as e:
            print(f"[-] ERROR querying sensors: {e}")
            sys.exit(1)
        finally:
            session.close()

        print("\n" + "=" * 78)
        print(f"LIVE HARDWARE SENSORS & STATUS")
        print(f"Port: {target_port} | Vendor: {session.driver.vendor if session.driver else args.manufacturer}")
        print("=" * 78)

        print(f"\n[MACHINE READINESS]: {sensors_data.get('readiness', 'Nominal')}")

        print("\n[PHYSICAL MICROSWITCHES & LEVEL SENSORS]")
        for sw in sensors_data.get("switches", []):
            badge = f"[{sw.get('badge', 'OK')}]"
            print(f"  {sw.get('icon', '*')} {sw['name']:<32}: {sw['status']:<54} {badge:>12}")

        if sensors_data.get("alerts"):
            print("\n[ACTIVE SYSTEM WARNINGS & LOCKOUTS]")
            for a in sensors_data["alerts"]:
                lvl = a.get("level", "WARNING")
                msg = a.get("description") or a.get("message") or f"{a.get('name')}: {a.get('details')}"
                print(f"  ⚠️ [{lvl}] {msg}")

        print("\n[DIAGNOSTIC COMPONENT HEALTH & SAFETY]")
        for s in sensors_data.get("sensors", []):
            badge = f"[{s.get('badge', 'OK')}]"
            details = s.get('details', '')
            print(f"  {s.get('icon', '*')} {s['name']:<32}: {s['status']:<15} {badge:>10} -> {details}")

        if sensors_data.get("error_counters"):
            print("\n[HISTORICAL SENSOR TRIP & FAULT FREQUENCY COUNTERS]")
            for c_name, c_cnt in sensors_data["error_counters"].items():
                print(f"  * {c_name:<36}: {c_cnt:>5} events")

        if sensors_data.get("telemetry"):
            print("\n[THERMAL HEATING & SUBSYSTEM TELEMETRY]")
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
                print(f"  ⚙️ Brew Unit Encoder (Pos / Ref)   : {telem['bu_encoder_str']:<18} (0x{raw_pos:04X} / 0x{raw_ref:04X})")
            if "bu_mill_target" in telem:
                print(f"  🎯 Brew Unit Mill Target (RE:0041) : {telem['bu_mill_target']} ticks (0x{telem['bu_mill_target']:04X})")
            if "bu_init_count" in telem:
                print(f"  🔄 Brew Unit Init Counter (RE:0056): {telem['bu_init_count']} cycles")
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
            with open(out_path, "w", encoding="utf-8") as f:
                json.dump(sensors_data, f, indent=2, ensure_ascii=False)
            print(f"[+] Sensor telemetry saved to: {out_path}")

        sys.exit(0)

    def prog_handler(pct: float, status: str):
        bar_len = 30
        filled = int(round(bar_len * pct))
        bar = "=" * filled + "-" * (bar_len - filled)
        sys.stdout.write(f"\r[*] Progress: [{bar}] {pct*100:3.0f}% - {status:<45}")
        sys.stdout.flush()

    print()
    try:
        success = session.run_interrogation(progress_cb=prog_handler)
    except Exception as e:
        print(f"\n[-] Interrogation failed: {e}")
        sys.exit(1)
    finally:
        session.close()

    print("\n\n[+] Successfully interrogated machine!")
    summary = session.get_structured_summary()

    print("=" * 78)
    print(f"DIAGNOSTIC REPORT: {summary.get('vendor')} - {summary.get('machine_model')}")
    print(f"Serial Number: {summary.get('serial_number')} | Protocol: {summary.get('protocol_mode')}")
    print(f"Total Dispensed: {summary.get('total_cups'):,} cups ({summary.get('total_preparations', 0):,} total preparations)")
    print("=" * 78)

    print("\n[BEVERAGE DISPENSING COUNTERS]")
    for b in summary.get("beverages", []):
        d_str = " (Double)" if b.get("is_double") else ""
        print(f"  * {b.get('name') + d_str:<36}: {b.get('count', 0):>8,}")

    print("\n[MAINTENANCE & HYGIENE]")
    for m in summary.get("maintenance", []):
        pct_str = f" ({m.get('percent')}%)" if m.get("percent") is not None else ""
        print(f"  * {m.get('name'):<36}: {m.get('count', 0):>8,}{pct_str}")

    if summary.get("telemetry"):
        print("\n[OPERATIONAL METRICS & HARDWARE SPECS]")
        for k, v in summary["telemetry"].items():
            if not isinstance(v, (dict, list)):
                print(f"  * {k.replace('_', ' ').title():<36}: {v}")

    print("=" * 78 + "\n")

    if args.export:
        out_path = os.path.abspath(args.export)
        fmt = args.format
        if out_path.endswith(".json"):
            fmt = "json"
        elif out_path.endswith(".csv"):
            fmt = "csv"

        if fmt == "json":
            content = json.dumps(summary, indent=2, ensure_ascii=False)
        elif fmt == "csv":
            content = format_csv_summary(summary)
        else:
            content = format_text_summary(summary)

        with open(out_path, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"[+] Diagnostic report saved to: {out_path} ({len(content)} bytes)")


if __name__ == "__main__":
    main()
