#!/usr/bin/env python3
"""
SPECTRA - Universal Hardware Telemetry & Logic Board Diagnostics
Universal Appliance Telemetry & Diagnostics Engine (Jura Module)
"""

import sys
import os
import argparse
import time
from typing import Optional

import serial_io
import profiles_db
import stats_collector as sc

try:
    from version import __version__, __build__
except ImportError:
    __build__ = "20261112.1820"
    __version__ = f"Build {__build__}"


def print_banner():
    banner = rf"""
  ███████╗██████╗ ███████╗ ██████╗████████╗██████╗  █████╗ 
  ██╔════╝██╔══██╗██╔════╝██╔════╝╚══██╔══╝██╔══██╗██╔══██╗
  ███████╗██████╔╝█████╗  ██║        ██║   ██████╔╝███████║
  ╚════██║██╔═══╝ ██╔══╝  ██║        ██║   ██╔══██╗██╔══██║
  ███████║██║     ███████╗╚██████╗   ██║   ██║  ██║██║  ██║
  ╚══════╝╚═╝     ╚══════╝ ╚═════╝   ╚═╝   ╚═╝  ╚═╝╚═╝  ╚═╝
   — Universal Hardware Telemetry & Logic Board Diagnostics (Build {__build__}) —
    """
    print(banner)


def main():
    parser = argparse.ArgumentParser(
        description=f"SPECTRA - Universal Hardware Telemetry & Logic Board Diagnostics (Build {__build__})"
    )
    parser.add_argument("-V", "--version", action="version", version=f"SPECTRA Build {__build__} (Hardware Telemetry & Logic Board Diagnostics)")
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
    parser.add_argument("--set-bean-threshold", type=int, metavar="COUNTS", help="Set optical bean sensor sensitivity threshold (counts)")
    parser.add_argument("--get-bean-threshold", action="store_true", help="Show optical bean sensor calibration parameters")
    parser.add_argument("--hmi-inspect", metavar="PATH", help="Inspect and audit Kalerm HMI firmware binary or update folder")
    parser.add_argument("--hmi-search", metavar="QUERY", help="Filter keys/strings in Kalerm HMI firmware binary")
    parser.add_argument("--hmi-lang", default="cs-CZ", help="Locale for --hmi-search (default: cs-CZ)")
    parser.add_argument("--hmi-export-report", metavar="PATH", help="Export Markdown/HTML/PDF HMI firmware audit bug report")
    parser.add_argument("--hmi-patch", nargs="?", const="", metavar="OUT_PATH", help="Create patched lab binary copy")
    parser.add_argument("--hmi-semantic", action="store_true", help="Run 3-tier offline semantic hybrid auditor and extract learned glossary")
    parser.add_argument("--hmi-ollama", action="store_true", help="Enable optional local Ollama reviewer (127.0.0.1:11434)")
    parser.add_argument("--hmi-ollama-model", metavar="MODEL", help="Target model for local Ollama reviewer (e.g. qwen2.5:0.5b)")
    parser.add_argument("--hmi-ai-check", action="store_true", help="Run host hardware self-check and adaptive AI model recommendation")
    parser.add_argument("--check-update", action="store_true", help="Check GitHub releases for a newer SPECTRA build and exit")
    parser.add_argument("--update", action="store_true", help="Check for updates and apply self-update in the foreground")

    args = parser.parse_args()

    if args.check_update or args.update:
        import updater

        info = updater.check_for_updates(force=True, timeout=8.0)
        if not info.get("ok"):
            print(f"[-] Update check failed: {info.get('error') or 'Unknown error'}")
            sys.exit(1)

        cur_b = info.get("current_build") or updater.get_local_build()
        lat_b = info.get("latest_build") or "unknown"
        rel_url = info.get("release_url") or ""
        mode = info.get("install_mode") or info.get("platform") or "auto"

        print(f"[*] Installed Build: Build {cur_b}")
        print(f"[*] Latest Build:    Build {lat_b} ({mode})")
        if rel_url:
            print(f"[*] Release URL:     {rel_url}")

        if not info.get("update_available"):
            print(f"[+] SPECTRA is already up to date (Build {cur_b}).")
            sys.exit(0)

        print(f"[!] Update available: Build {cur_b} -> Build {lat_b}")
        if args.check_update and not args.update:
            sys.exit(0)

        # Foreground self-update without execv loop if already up to date or failed
        restarted_guard = os.environ.pop("SPECTRA_RESTARTED_AFTER_UPDATE", "") == "1"
        if restarted_guard:
            print(f"[+] Update check skipped post-restart relaunch (Build {cur_b}).")
            sys.exit(0)

        def _cli_noop_restart() -> None:
            return None

        updater.register_linux_restart_handler(_cli_noop_restart)
        try:
            res = updater.start_self_update(check_info=info)
            if not res.get("ok"):
                print(f"[-] Failed to start self-update: {res.get('error')}")
                sys.exit(1)
            last_msg = ""
            while True:
                st = updater.get_update_progress()
                msg = str(st.get("message") or st.get("status") or "")
                pct = int(st.get("percent") or 0)
                if msg and msg != last_msg:
                    print(f"[*] [{pct:3d}%] {msg}")
                    last_msg = msg
                if st.get("status") == "restarting" or st.get("restart_required"):
                    print(f"[+] Successfully updated to Build {st.get('current_build') or lat_b}.")
                    sys.exit(0)
                if not st.get("in_progress"):
                    if st.get("status") == "error":
                        print(f"[-] Update failed: {st.get('error') or msg}")
                        sys.exit(1)
                    if st.get("status") == "cancelled":
                        print("[!] Update cancelled.")
                        sys.exit(1)
                    print(f"[+] {msg or 'Up to date.'}")
                    sys.exit(0)
                time.sleep(0.25)
        finally:
            updater.register_linux_restart_handler(None)

    # Kalerm HMI AI System & Hardware Self-Check CLI handler
    if args.hmi_ai_check:
        try:
            import hmi_inspector
            status = hmi_inspector.KalermHmiInspector.get_ai_system_status()
            hw = status["hardware"]
            cpu = hw["cpu"]
            mem = hw["memory"]
            gpu = hw["gpu"]
            disk = hw["disk"]
            ollama = status["ollama"]

            print("=" * 78)
            print("SPECTRA HOST HARDWARE SELF-CHECK & ADAPTIVE AI MODEL SELECTOR")
            print("=" * 78)
            print(f"[*] Hardware Tier:        [{hw['tier']}]")
            print(f"    Description:          {hw['tier_description']}")
            print(f"[*] CPU Model:            {cpu['model']} ({cpu['logical_cores']} logical cores)")
            print(f"    SIMD Capabilities:    {', '.join(cpu['simd_flags']) if cpu['simd_flags'] else 'Standard x86/ARM'} (AVX2: {'YES' if cpu['has_avx2'] else 'NO'})")
            print(f"[*] Host Memory:          {mem['ram_available_mb']:,} MB available / {mem['ram_total_mb']:,} MB total")
            print(f"[*] GPU Acceleration:     {'Discrete GPU' if gpu['has_discrete_gpu'] else 'Integrated / CPU Only'} ({gpu['name']})")
            if gpu['has_discrete_gpu']:
                print(f"    VRAM Capacity:        {gpu['vram_total_mb']:,} MB")
            print(f"[*] Disk Space Free:      {disk['disk_free_gb']} GB")
            print(f"[*] Auto-Unload from RAM: {'RECOMMENDED (Low Memory Host)' if hw['auto_unload_recommended'] else 'Optional (High Memory Host)'}")
            print(f"[*] Recommended Model:    {hw['recommended_model']} (Default: {hw['default_selected_model']})")

            print("\n" + "-" * 78)
            print("LOCAL OLLAMA DAEMON STATUS")
            print("-" * 78)
            print(f"[*] Daemon Endpoint:      {ollama['endpoint']} ({'ONLINE' if ollama['available'] else 'OFFLINE'})")
            print(f"[*] Binary Installed:     {'YES (' + status['binary_path'] + ')' if status['binary_installed'] else 'NO (not in PATH)'}")
            if ollama['available']:
                print(f"[*] Installed Models:     {', '.join(ollama['models']) if ollama['models'] else 'None'}")

            print("\n" + "-" * 78)
            print("OFFLINE AI MODEL CATALOG & MACHINE COMPATIBILITY")
            print("-" * 78)
            print(f"{'Model ID':<16} {'RAM Min':<10} {'Disk':<9} {'Compatibility':<16} {'Speed / Description'}")
            print("-" * 78)
            for m in hw["model_catalog"]:
                rec_mark = "⭐ " if m["is_recommended"] else "   "
                ins_mark = " [Installed]" if m["is_installed"] else ""
                print(f"{rec_mark}{m['id']:<14} {m['min_ram_mb']} MB    {m['disk_mb']} MB   {m['compatibility']:<16} {m['speed_cpu']}{ins_mark}")
            print("=" * 78)
            sys.exit(0)
        except Exception as e:
            print(f"[-] ERROR in AI Hardware Check: {e}")
            sys.exit(1)

    # Kalerm HMI Inspector & Firmware Auditor CLI handler
    if args.hmi_inspect or args.hmi_search or args.hmi_export_report or args.hmi_patch is not None or args.hmi_semantic:
        try:
            import hmi_inspector
            target = args.hmi_inspect or hmi_inspector.DEFAULT_KALERM_DIR
            inspector = hmi_inspector.KalermHmiInspector(target)

            sig = inspector.verify_signature()
            print(f"[*] Target Binary: {inspector.binary_path}")
            print(f"[*] Binary Size:   {inspector.file_size:,} bytes")
            print(f"[*] SHA-256:       {sig['sha256']}")
            print(f"[*] Signature:     {sig['status_label']}")
            if sig["warning"]:
                print(f"    Notice: {sig['warning']}")

            if args.hmi_search:
                print(f"\n[*] Searching for '{args.hmi_search}' in locale {args.hmi_lang}...")
                langs = inspector.extract_all_languages()
                lang_data = langs.get(args.hmi_lang) or inspector.extract_language(args.hmi_lang)
                if not lang_data:
                    print(f"[-] Locale {args.hmi_lang} not found. Available: {', '.join(langs.keys())}")
                    sys.exit(1)

                matches = 0
                q = args.hmi_search.lower()
                for k, p in lang_data["phrases"].items():
                    if q in k.lower() or q in p["val"].lower():
                        matches += 1
                        print(f"[{p['index']:3d}] Key: {k}")
                        print(f"      Value:     {repr(p['val'])}")
                        print(f"      Value VMA: 0x{p['val_vma']:08x} (file offset: 0x{p['val_file_off']:08x})")
                        print(f"      Slot file: 0x{p['slot_file_off']:08x}")
                        print("-" * 60)
                print(f"[*] Total matches found: {matches}")

            if (args.hmi_inspect and not args.hmi_search and args.hmi_patch is None and not args.hmi_export_report) or (not args.hmi_search and args.hmi_patch is None and not args.hmi_export_report):
                target_loc = args.hmi_lang or "cs-CZ"
                print("\n" + "=" * 78)
                print(f"SPECTRA AUTOMATED FIRMWARE & LOCALIZATION AUDIT FINDINGS [{target_loc}]")
                print("=" * 78)
                findings = inspector.run_audit(target_locale=target_loc)
                for f in findings:
                    badge = f"[{f['severity']}]"
                    st = f"[{f['status']}]"
                    print(f"\n{st:<12} {badge:<10} {f['id']}: {f['key']} ({f['locale']})")
                    print(f"  Category:     {f['category']}")
                    print(f"  Current Val:  {repr(f['current_val'])}")
                    print(f"  Target Fix:   {repr(f['expected_val'])}")
                    print(f"  VMA / Offset: 0x{f['vma']:08x} / 0x{f['file_offset']:08x}")
                    print(f"  Description:  {f['description']}")
                print("\n" + "=" * 78)

            if args.hmi_semantic:
                target_loc = args.hmi_lang or "cs-CZ"
                print("\n" + "=" * 78)
                print(f"SPECTRA 3-TIER OFFLINE SEMANTIC HYBRID AUDITOR [{target_loc}]")
                print("=" * 78)
                sem_res = inspector.run_semantic_audit(
                    target_locale=target_loc,
                    use_ollama=args.hmi_ollama,
                    ollama_model=args.hmi_ollama_model
                )
                print(f"[*] Engine:           {sem_res['tier2_engine']}")
                print(f"[*] Total Phrases:    {sem_res['summary']['total_phrases']}")
                print(f"[*] Glossary Terms:   {sem_res['summary']['glossary_terms_count']} learned domain terms")
                print(f"[*] Avg Alignment:    {sem_res['summary']['average_alignment'] * 100:.1f}%")
                print(f"[*] Flagged Anomaly:  {sem_res['summary']['flagged_count']}")
                print(f"[*] Local Ollama:     {'Available' if sem_res['tier3_ollama']['available'] else 'Offline / Inactive'}")

                print(f"\n--- TOP LEARNED DOMAIN TERMS (Tier 1 Self-Learning Glossary) ---")
                for g in sem_res["tier1_glossary"][:15]:
                    print(f"  {g['en_term']:15} -> {g['target_term']:12} ({g['target_word']:15}) [conf={g['confidence']*100:.0f}%, sup={g['support']}]")

                if sem_res["flagged_phrases"]:
                    print(f"\n--- FLAGGED SEMANTIC ANOMALIES & LOW ALIGNMENT OUTLIERS ---")
                    for fl in sem_res["flagged_phrases"][:10]:
                        print(f"  [{fl['alignment_score']:.2f}] Key: {fl['key']}")
                        print(f"        EN:     {repr(fl['en_val'])}")
                        print(f"        Target: {repr(fl['target_val'])}")
                        print(f"        Reason: {fl['reason']}")
                        if fl.get("suggested_val"):
                            print(f"        Fix:    {repr(fl['suggested_val'])}")

            if args.hmi_patch is not None:
                out_p = args.hmi_patch if args.hmi_patch else None
                print("\n[*] Applying safety and localization fixes to binary...")
                res = inspector.apply_patches(out_p)
                print(f"[+] Patched binary successfully created: {res['output_path']}")
                print(f"[+] Patched SHA-256: {res['sha256']}")
                print(f"[+] Applied {len(res['patches_applied'])} patch operations.")

            if args.hmi_export_report:
                print(f"\n[*] Exporting audit report to {args.hmi_export_report}...")
                saved = inspector.export_bug_report(args.hmi_export_report)
                print(f"[+] Report exported successfully to: {saved}")

            sys.exit(0)
        except Exception as e:
            print(f"[-] ERROR in HMI Inspector: {e}")
            sys.exit(1)

    if args.get_bean_threshold:
        c = sc.get_optical_bean_calibration()
        print("Optical Bean Sensor Calibration:")
        print(f"  Active Threshold:  {c['threshold']} counts")
        print(f"  Hysteresis Window: ±{c['hysteresis']} counts")
        print(f"  Decision Bounds:   Charged <= {c['lower_bound']} counts | Empty >= {c['upper_bound']} counts")
        sys.exit(0)

    if args.set_bean_threshold is not None:
        val = sc.set_optical_bean_threshold(args.set_bean_threshold)
        c = sc.get_optical_bean_calibration()
        print(f"Updated optical bean sensor threshold to {val} counts.")
        print(f"Active Decision Bounds: Charged <= {c['lower_bound']} counts | Empty >= {c['upper_bound']} counts")
        sys.exit(0)

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
