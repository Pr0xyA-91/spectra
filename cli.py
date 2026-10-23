#!/usr/bin/env python3
"""
Jura Modern Diagnostics - Command Line Interface
"""

import sys
import os
import argparse
from typing import Optional

import serial_io
import profiles_db
import stats_collector as sc

__version__ = "0.3.1"


def print_banner():
    banner = r"""
     ____.                     _____            .___                   ________  .__                
    |    |__ _________ _____  /     \   ____  __| _/___________  ____  \______ \ |__|____     ____  
    |    |  |  \_  __ \\__  \/  \ /  \ /  _ \/ __ |/ __ \_  __ \/    \  |    |  \|  \__  \   / ___\ 
/\__|    |  |  /|  | \/ / __ \    Y    (  <_> ) /_/ \  ___/|  | \/   |  \ |    `   \  |/ __ \_/ /_/  >
\________|____/ |__|   (____  /____|__  /\____/\____ |\___  >__|  |___|  /_______  /__/____  /\___  / 
                            \/        \/            \/    \/           \/        \/        \//_____/  
        Universal Diagnostic & Statistics Reader for Jura Coffee Machines (v0.3.1)
    """
    print(banner)


def main():
    parser = argparse.ArgumentParser(
        description="Jura Modern Diagnostics & Statistics Telemetry Tool (v0.3.1)"
    )
    parser.add_argument("-V", "--version", action="version", version=f"Jura Modern Diag {__version__}")
    parser.add_argument("--cli", action="store_true", help="Run in command-line mode")
    parser.add_argument("-p", "--port", help="Serial port to connect to (e.g. /dev/ttyUSB0, /dev/ttyACM0, or demo)")
    parser.add_argument("-b", "--baud", type=int, default=9600, help="Baud rate (default: 9600)")
    parser.add_argument("--demo", action="store_true", help="Run with simulated demo machine (Jura S8)")
    parser.add_argument("--demo-model", choices=["S8", "E8", "Z10"], default="S8", help="Model to simulate in demo mode")
    parser.add_argument("-s", "--sensors", "--live-sensors", action="store_true", help="Read and display live sensors, switches, and fault telemetry")
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
            print(f"  {sw.get('icon', '*')} {sw['name']:<32}: {sw['status']:<30} {badge:>10}")

        print("\n[DIAGNOSTIC COMPONENT HEALTH & SAFETY]")
        for s in sensors_data.get("sensors", []):
            badge = f"[{s.get('badge', 'OK')}]"
            print(f"  * {s['name']:<34}: {s['status']:<15} {badge:>8} -> {s['details']}")

        if sensors_data.get("error_counters"):
            print("\n[HISTORICAL SENSOR TRIP & FAULT FREQUENCY COUNTERS]")
            for c_name, c_cnt in sensors_data["error_counters"].items():
                print(f"  * {c_name:<36}: {c_cnt:>5} events")

        if sensors_data.get("telemetry"):
            print("\n[HARDWARE TELEMETRY & SYSTEM SETTINGS]")
            telem = sensors_data["telemetry"]
            if "heater_ntc_raw" in telem:
                print(f"  * Thermoblock NTC Sensor Raw ADC   : {telem['heater_ntc_raw']}")
            if "water_hardness_dh" in telem:
                print(f"  * Configured Water Hardness        : {telem['water_hardness_dh']} °dH")
            if "filter_volume_liters" in telem:
                print(f"  * Water Volume Through Filter      : {telem['filter_volume_liters']} Liters")
            if "rotary_switch" in telem:
                print(f"  * Selection / Rotary Switch Position: {telem['rotary_switch']}")

        print("=" * 78 + "\n")

        if args.export:
            out_path = os.path.abspath(args.export)
            import json
            with open(out_path, "w", encoding="utf-8") as f:
                json.dump(sensors_data, f, indent=2, ensure_ascii=False)
            print(f"[+] Sensor telemetry saved to: {out_path}")

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

    session = sc.JuraStatsSession(target_port, baudrate=args.baud, log_cb=log_handler)
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

        with open(out_path, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"\n[+] Diagnostic report saved to: {out_path} ({len(content)} bytes)")


if __name__ == "__main__":
    main()
