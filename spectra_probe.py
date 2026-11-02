#!/usr/bin/env python3
"""
SPECTRA Field Capture & Remote Archetype Diagnostic Probe (spectra_probe.py)
Part of SPECTRA — Universal Hardware Telemetry & Logic Board Diagnostics

Purpose:
  Enables remote field colleagues and technicians to capture complete hardware
  telemetry, logic board gateways, and EEPROM memory from any connected Jura machine.
  If an official JURA Operating Experience (J.O.E.) app CSV export is available,
  the tool automatically correlates ground-truth beverage and maintenance counts
  against the raw EEPROM registers to uncover new or unknown memory layouts.

Outputs:
  - spectra_capture_<MODEL>_<TIMESTAMP>.json  (Full machine dump bundle for engineers)
  - spectra_capture_<MODEL>_<TIMESTAMP>.txt   (Human-readable diagnostic report)

Safety:
  Strictly read-only! Only issues verified diagnostic commands (TY:, TL:, TY$:,
  TL$:, IC:, CS$:, HZ:, AS:, RT:, RE:). Never writes to machine EEPROM.
"""

import os
import sys
import re
import csv
import json
import time
import datetime
import argparse
from typing import Dict, Any, Optional, Tuple, List

try:
    from version import BUILD_NUMBER
except ImportError:
    BUILD_NUMBER = "20261102.1435"

# Ensure repository root is on sys.path
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

try:
    import serial_io
    import profiles_db
    from stats_collector import decode_jura_date
except ImportError:
    serial_io = None
    profiles_db = None
    decode_jura_date = None


SAFE_READ_COMMANDS = ("TY:", "TL:", "TY$:", "TL$:", "IC:", "CS$:", "HZ:", "AS:", "RT:", "RE:")


def parse_joe_csv_lines(lines: List[str]) -> Dict[str, Any]:
    """Parse lines of an official J.O.E. app CSV export."""
    result = {
        "model_name": "",
        "article_number": "",
        "cockpit": {},
        "maintenance": {},
        "products": {},
        "total_products": None,
        "raw_lines": []
    }

    current_section = None
    for raw_line in lines:
        line = raw_line.strip()
        result["raw_lines"].append(line)
        if not line:
            continue

        # Header metadata
        if line.lower().startswith("model name:"):
            result["model_name"] = line.split(":", 1)[1].strip()
            continue
        if line.lower().startswith("article number:"):
            result["article_number"] = line.split(":", 1)[1].strip()
            continue

        # Section markers
        if line.lower() == "cockpit":
            current_section = "cockpit"
            continue
        elif line.lower() == "maintenance counter":
            current_section = "maintenance"
            continue
        elif line.lower() == "product counter":
            current_section = "products"
            continue

        # Key-value lines (comma or semicolon delimited)
        parts = [p.strip() for p in re.split(r'[,;]', line) if p.strip()]
        if len(parts) >= 2:
            key, val_str = parts[0], parts[1]
            if current_section == "cockpit":
                result["cockpit"][key] = val_str
            elif current_section == "maintenance":
                try:
                    result["maintenance"][key] = int(val_str)
                except ValueError:
                    result["maintenance"][key] = val_str
            elif current_section == "products":
                if key.lower().startswith("total number of products"):
                    try:
                        result["total_products"] = int(val_str)
                    except ValueError:
                        result["total_products"] = val_str
                else:
                    try:
                        result["products"][key] = int(val_str)
                    except ValueError:
                        result["products"][key] = val_str

    return result


def parse_joe_csv_text(csv_text: str) -> Dict[str, Any]:
    """Parse J.O.E. CSV from raw string content."""
    if not csv_text:
        return {}
    return parse_joe_csv_lines(csv_text.splitlines())


def parse_joe_csv(filepath: str) -> Dict[str, Any]:
    """Parse an official J.O.E. app CSV export file from disk."""
    if not filepath or not os.path.isfile(filepath):
        return {}

    encodings = ["utf-8", "latin1", "cp1252", "iso-8859-1"]
    lines = []

    for enc in encodings:
        try:
            with open(filepath, "r", encoding=enc) as f:
                lines = f.readlines()
            break
        except (UnicodeDecodeError, IOError):
            continue

    return parse_joe_csv_lines(lines)


def query_gateways(conn) -> Dict[str, str]:
    """Interrogate all standard Jura diagnostic ASCII gateways."""
    gateways = {}
    commands = [
        ("TY:", "Main Logic Board Firmware EF Code"),
        ("TL:", "Main Microcontroller Bootloader Identification"),
        ("TY$:", "Display Sub-Bus Controller EF Code"),
        ("TL$:", "Display Sub-Bus Bootloader Identification"),
        ("CS$:", "Display Sub-Bus Firmware Checksum"),
        ("IC:", "Logic Board Hardware Architecture Code"),
        ("HZ:", "Heating System & Thermoblock Temperature ADC"),
        ("AS:", "Optical Bean Hopper Sensor ADC")
    ]

    for cmd, desc in commands:
        ans = conn.query_ascii(cmd, timeout=1.2)
        gateways[cmd] = ans if ans else "[NO_REPLY]"

    return gateways


def sweep_eeprom(conn, max_words: int = 512, on_progress=None) -> Dict[int, int]:
    """Safely sweep EEPROM memory using RT: block reads with RE: word fallbacks."""
    eeprom: Dict[int, int] = {}
    num_blocks = (max_words + 15) // 16

    for blk_idx in range(num_blocks):
        blk = blk_idx * 16
        pct = int((blk_idx / num_blocks) * 100)

        if on_progress:
            on_progress(pct, blk)

        cmd = f"RT:{blk:04X}"
        ans = conn.query_ascii(cmd, timeout=1.5)

        block_ok = False
        if ans and ans.lower().startswith("rt:"):
            raw_hex = ans[3:].strip()
            if len(raw_hex) >= 64:
                for idx in range(16):
                    w = int(raw_hex[idx * 4: idx * 4 + 4], 16)
                    eeprom[blk + idx] = w
                block_ok = True

        if not block_ok:
            # Fallback to word-by-word reads for this block
            for offset in range(16):
                addr = blk + offset
                w_ans = conn.query_ascii(f"RE:{addr:04X}", timeout=1.0)
                if w_ans and w_ans.lower().startswith("re:"):
                    try:
                        eeprom[addr] = int(w_ans[3:].strip()[:4], 16)
                    except ValueError:
                        eeprom[addr] = 0x0000
                else:
                    eeprom[addr] = 0x0000

    if on_progress:
        on_progress(100, max_words)

    return eeprom


def decode_machine_identity(eeprom: Dict[int, int], gateways: Dict[str, str]) -> Dict[str, Any]:
    """Decode factory hardware identity, article numbers, and production dates."""
    ident = {
        "article_number": "N/A",
        "appliance_number": 0,
        "serial_number": "N/A",
        "production_date": "N/A",
        "platform_family": "Unknown",
        "address_width": 2 if len(eeprom) <= 256 else 4,
        "max_words": len(eeprom)
    }

    # Detect platform family
    ty = gateways.get("TY:", "")
    tl = gateways.get("TL:", "")
    if "RL78" in tl.upper() or "EF533" in ty.upper() or "EF535" in ty.upper() or "EF536" in ty.upper():
        ident["platform_family"] = "Renesas RL78 (Modern TFT / Gen 2)"
    elif "R8C" in tl.upper() or "EF509" in ty.upper() or "EF518" in ty.upper():
        ident["platform_family"] = "Renesas R8C (Classic Domestic / Commercial)"
    elif "Z5" in ty.upper() or "EF642" in ty.upper():
        ident["platform_family"] = "Motorola 68HC (Legacy Top-Tronic)"

    # Factory Article Number from 0x007E / 0x007F (RL78 standard)
    if 0x007E in eeprom and 0x007F in eeprom:
        w_7e = eeprom[0x007E]
        w_7f = eeprom[0x007F]
        art_calc = ((w_7e >> 8) << 8) | (w_7f >> 8)
        if 10000 <= art_calc <= 99999:
            ident["article_number"] = str(art_calc)

    # Fallback article from 0x0030
    if ident["article_number"] == "N/A":
        art_30 = eeprom.get(0x0030, 0)
        if 10000 <= art_30 <= 99999:
            ident["article_number"] = str(art_30)

    ident["appliance_number"] = eeprom.get(0x0030, 0)

    # Production Date at 0x0032
    prod_word = eeprom.get(0x0032, 0)
    if prod_word > 0:
        day = prod_word & 0x1F
        month = (prod_word >> 5) & 0x0F
        year = 1990 + ((prod_word >> 9) & 0x7F)
        if 1 <= day <= 31 and 1 <= month <= 12 and 1990 <= year <= 2040:
            ident["production_date"] = f"{day}.{month}.{year}"
            if ident["appliance_number"] > 0:
                ident["serial_number"] = f"{year}{month:02d}{day:02d}{ident['appliance_number']:06d}"

    return ident


def correlate_with_joe(eeprom: Dict[int, int], joe_data: Dict[str, Any]) -> Dict[str, Any]:
    """Cross-reference ground truth from J.O.E. export against EEPROM addresses."""
    correlations = {
        "products": [],
        "maintenance": [],
        "cockpit": [],
        "summary": {
            "total_products_checked": 0,
            "matched_products": 0,
            "total_maint_checked": 0,
            "matched_maint": 0
        }
    }

    if not joe_data:
        return correlations

    def score_address_for_category(addr: int, category: str) -> int:
        if category == "product":
            if 0x0180 <= addr <= 0x018F or addr == 0x017F:
                return 100
            if 0x0330 <= addr <= 0x033F:
                return 95
            if 0x0001 <= addr <= 0x0006:
                return 90
            if 0x00E0 <= addr <= 0x00E6:
                return 80
        elif category == "maintenance":
            if 0x0007 <= addr <= 0x0009:
                return 100
            if 0x0020 <= addr <= 0x0022:
                return 95
            if addr == 0x000E or addr == 0x0014:
                return 90
        elif category == "cockpit":
            if 0x0160 <= addr <= 0x016F or 0x01E0 <= addr <= 0x01EF:
                return 100
        return 10

    # 1. Product beverage correlation
    prods = joe_data.get("products", {})
    for bev_name, count in prods.items():
        correlations["summary"]["total_products_checked"] += 1
        matches = []
        if count > 0:
            raw_matches = [addr for addr, val in eeprom.items() if val == count]
            raw_matches.sort(key=lambda a: score_address_for_category(a, "product"), reverse=True)
            matches = [f"0x{a:04X}" for a in raw_matches]

        matched = len(matches) > 0
        if matched:
            correlations["summary"]["matched_products"] += 1

        note = "Count is 0" if count == 0 else ""
        correlations["products"].append({
            "name": bev_name,
            "joe_count": count,
            "matched": matched,
            "candidate_addresses": matches,
            "suggested_address": matches[0] if matches else None,
            "note": note
        })

    # 2. Maintenance counter correlation
    maint = joe_data.get("maintenance", {})
    for m_name, count in maint.items():
        if not isinstance(count, int):
            continue
        correlations["summary"]["total_maint_checked"] += 1
        matches = []
        if count > 0:
            raw_matches = [addr for addr, val in eeprom.items() if val == count]
            raw_matches.sort(key=lambda a: score_address_for_category(a, "maintenance"), reverse=True)
            matches = [f"0x{a:04X}" for a in raw_matches]

        matched = len(matches) > 0
        if matched:
            correlations["summary"]["matched_maint"] += 1

        note = "Count is 0" if count == 0 else ""
        correlations["maintenance"].append({
            "name": m_name,
            "joe_count": count,
            "matched": matched,
            "candidate_addresses": matches,
            "suggested_address": matches[0] if matches else None,
            "note": note
        })

    # 3. Cockpit life percentages correlation
    cockpit = joe_data.get("cockpit", {})
    for c_name, val_str in cockpit.items():
        m_pct = re.search(r'(\d+)\s*%', val_str)
        if m_pct:
            pct_val = int(m_pct.group(1))
            matches = []
            if pct_val > 0:
                raw_matches = []
                for addr, val in eeprom.items():
                    # Prioritize high bytes or dual-byte encoding (e.g. 0x1E1E)
                    if (val & 0xFF) == pct_val or ((val >> 8) & 0xFF) == pct_val:
                        raw_matches.append(addr)
                raw_matches.sort(key=lambda a: score_address_for_category(a, "cockpit"), reverse=True)
                matches = [f"0x{a:04X}" for a in raw_matches]

            note = "0% (cannot isolate from zero registers)" if pct_val == 0 else ""
            correlations["cockpit"].append({
                "label": c_name,
                "joe_value": val_str,
                "percent_int": pct_val,
                "matched": len(matches) > 0,
                "candidate_addresses": matches,
                "suggested_address": matches[0] if matches else None,
                "note": note
            })

    return correlations


def generate_mock_python_code(gateways: Dict[str, str], eeprom: Dict[int, int], model_name: str) -> str:
    """Generate drop-in Python mock machine initialization code for serial_io.py & tests."""
    clean_name = re.sub(r'[^A-Za-z0-9_]', '_', model_name.upper()).strip('_')
    ef_code = gateways.get("TY:", "EFUNKNOWN").replace("ty:", "").replace("TY:", "").strip()

    lines = [
        f"        # Simulation Mock Seed for Jura {model_name} ({ef_code})",
        f"        if '{clean_name.split('_')[0]}' in self.port_name.upper():",
        f"            self._mock_eeprom = {{i: 0x0000 for i in range({len(eeprom)})}}"
    ]

    # Pick non-zero informative registers
    priority_addrs = [
        0x0007, 0x0008, 0x0009, 0x000A, 0x0010, 0x0015, 0x0020, 0x0021, 0x0022,
        0x0030, 0x0031, 0x0032, 0x007E, 0x007F, 0x0162, 0x0163, 0x01E1, 0x017F
    ]
    # Add any beverage block registers (0x0180..0x018F or 0x0330..0x033F)
    for a in range(0x0180, 0x0190):
        if a in eeprom and eeprom[a] > 0:
            priority_addrs.append(a)
    for a in range(0x0330, 0x0340):
        if a in eeprom and eeprom[a] > 0:
            priority_addrs.append(a)

    for addr in sorted(set(priority_addrs)):
        if addr in eeprom and eeprom[addr] > 0:
            val = eeprom[addr]
            lines.append(f"            self._mock_eeprom[0x{addr:04X}] = 0x{val:04X}  # {val}")

    lines.append("            return\n")
    return "\n".join(lines)


def capture_machine_bundle(
    conn,
    joe_data: Optional[Dict[str, Any]] = None,
    max_words: int = 0,
    on_progress=None
) -> Dict[str, Any]:
    """
    Safely interrogate gateways, sweep EEPROM, decode identity,
    correlate ground truth, and return self-contained capture bundle dictionary.
    """
    gateways = query_gateways(conn)

    # Determine geometry
    if max_words <= 0:
        tl = gateways.get("TL:", "").upper()
        ty = gateways.get("TY:", "").upper()
        port_name = getattr(conn, "raw_port_label", getattr(conn, "port_name", ""))
        if "EF529" in ty or "D4" in port_name.upper():
            max_words = 1024
        elif "RL78" in tl or "EF533" in ty or "EF535" in ty or "EF536" in ty:
            probe_200 = conn.query_ascii("RT:0200", timeout=1.0)
            if probe_200 and probe_200.lower().startswith("rt:") and not probe_200[3:].startswith("0000" * 16):
                max_words = 1024
            else:
                max_words = 512
        else:
            max_words = 512

    eeprom = sweep_eeprom(conn, max_words=max_words, on_progress=on_progress)
    identity = decode_machine_identity(eeprom, gateways)
    model_name = (joe_data or {}).get("model_name") or identity.get("article_number") or "Jura_Appliance"
    identity["model_name"] = model_name

    correlations = correlate_with_joe(eeprom, joe_data or {}) if joe_data else {}
    mock_code = generate_mock_python_code(gateways, eeprom, model_name)

    return {
        "metadata": {
            "timestamp": datetime.datetime.now().isoformat(),
            "spectra_build": BUILD_NUMBER,
            "probe_version": "1.1.0",
            "port": getattr(conn, "raw_port_label", getattr(conn, "port_name", "UNKNOWN"))
        },
        "identity": identity,
        "gateways": gateways,
        "joe_ground_truth": joe_data or {},
        "correlations": correlations,
        "mock_python_snippet": mock_code,
        "eeprom_words": {f"0x{addr:04X}": val for addr, val in sorted(eeprom.items())}
    }


def build_text_report(bundle: Dict[str, Any]) -> str:
    """Construct a clean diagnostic text report for human technician review."""
    meta = bundle["metadata"]
    ident = bundle["identity"]
    gateways = bundle["gateways"]
    corr = bundle.get("correlations", {})
    joe = bundle.get("joe_ground_truth", {})

    sep = "=" * 78
    sub_sep = "-" * 78

    out = [
        sep,
        "  SPECTRA ARCHETYPE PROBE & HARDWARE TELEMETRY CAPTURE REPORT",
        sep,
        f"  Capture Timestamp : {meta['timestamp']}",
        f"  SPECTRA Build     : {meta.get('spectra_build', BUILD_NUMBER)}",
        f"  Probe Version     : {meta['probe_version']}",
        f"  Target Port       : {meta['port']}",
        f"  Platform Family   : {ident['platform_family']}",
        f"  Identified Model  : {ident.get('model_name', 'Unknown')}",
        f"  Article Number    : {ident['article_number']}",
        f"  Serial Number     : {ident['serial_number']}",
        f"  Production Date   : {ident['production_date']}",
        f"  Memory Geometry   : {ident['max_words']} words ({ident['max_words'] // 16} blocks, {ident['address_width']}-digit hex)",
        sub_sep,
        "HARDWARE BUS GATEWAY RESPONSES:",
        sub_sep
    ]

    for cmd, resp in sorted(gateways.items()):
        out.append(f"  {cmd:<8} -> {resp}")

    if joe:
        out.extend([
            sub_sep,
            "J.O.E. GROUND TRUTH CORRELATION ANALYSIS:",
            sub_sep,
            f"  J.O.E. Model      : {joe.get('model_name', 'N/A')}",
            f"  J.O.E. Article    : {joe.get('article_number', 'N/A')}",
            f"  Total Products    : {joe.get('total_products', 'N/A')}",
            ""
        ])

        out.append("  Beverage Counter Registers Found in EEPROM:")
        for p in corr.get("products", []):
            if p["matched"]:
                cand_str = p['candidate_addresses'][0]
                if len(p['candidate_addresses']) > 1:
                    cand_str += f" (also in: {', '.join(p['candidate_addresses'][1:4])})"
                status = f"MATCH -> {cand_str}"
            else:
                status = p.get("note") or "NO MATCH FOUND"
            out.append(f"    - {p['name']:<28} Count: {p['joe_count']:<6} [{status}]")

        out.append("")
        out.append("  Maintenance Operations Counters Found in EEPROM:")
        for m in corr.get("maintenance", []):
            if m["matched"]:
                cand_str = m['candidate_addresses'][0]
                if len(m['candidate_addresses']) > 1:
                    cand_str += f" (also in: {', '.join(m['candidate_addresses'][1:4])})"
                status = f"MATCH -> {cand_str}"
            else:
                status = m.get("note") or "NO MATCH FOUND"
            out.append(f"    - {m['name']:<32} Count: {m['joe_count']:<6} [{status}]")

        out.append("")
        out.append("  Cockpit Life Percentage Registers Found in EEPROM:")
        for c in corr.get("cockpit", []):
            if c["matched"]:
                cand_str = c['candidate_addresses'][0]
                if len(c['candidate_addresses']) > 1:
                    cand_str += f" (also in: {', '.join(c['candidate_addresses'][1:4])})"
                status = f"MATCH -> {cand_str}"
            else:
                status = c.get("note") or "NO MATCH"
            out.append(f"    - {c['label']:<28} Value: {c['joe_value']:<10} [{status}]")

    out.extend([
        sub_sep,
        "NON-ZERO EEPROM REGISTER SNAPSHOT (Hex Dump Sample):",
        sub_sep
    ])

    eeprom = bundle["eeprom_words"]
    sample_addrs = sorted(int(k, 16) for k, v in eeprom.items() if v > 0)
    for addr in sample_addrs[:80]:
        val = eeprom[f"0x{addr:04X}"]
        out.append(f"  0x{addr:04X} : {val:>6}  (0x{val:04X})")
    if len(sample_addrs) > 80:
        out.append(f"  ... and {len(sample_addrs) - 80} more non-zero words in full JSON bundle.")

    out.append(sep)
    out.append("  Instructions: Send the accompanying .json capture file to the engineering team.")
    out.append(sep)
    return "\n".join(out)


def main():
    parser = argparse.ArgumentParser(
        description="SPECTRA Field Capture & Remote Archetype Diagnostic Probe",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Interactive mode (prompts for port and optional J.O.E. CSV):
  python3 spectra_probe.py

  # Direct automated capture from customer machine:
  python3 spectra_probe.py --port /dev/ttyUSB0 --joe ~/Downloads/WE8.csv

  # Offline simulation capture test:
  python3 spectra_probe.py --demo WE8 --joe ~/Downloads/WE8.csv
"""
    )
    parser.add_argument("--port", "-p", help="Serial port (e.g. /dev/ttyUSB0 or COM3)")
    parser.add_argument("--joe", "-j", help="Path to official J.O.E. app CSV export file")
    parser.add_argument("--demo", "-d", help="Run in offline simulation mode (e.g. WE8, S8, D4, XJ5, Z6)")
    parser.add_argument("--words", "-w", type=int, default=0, help="Override EEPROM words (e.g. 512 or 1024; 0 = auto-detect)")
    parser.add_argument("--out", "-o", help="Custom output filename prefix")
    parser.add_argument("--non-interactive", action="store_true", help="Do not prompt for missing inputs")

    args = parser.parse_args()

    print("=" * 78)
    print("  SPECTRA Field Capture & Remote Archetype Diagnostic Probe")
    print("=" * 78)

    # 1. Determine Port
    port_name = args.port
    if args.demo:
        port_name = f"DEMO / SIMULATION (Jura {args.demo.upper()})"
    elif not port_name:
        available_ports = []
        if serial_io:
            available_ports = serial_io.list_diagnostic_ports()
        else:
            import glob
            available_ports = glob.glob("/dev/ttyUSB*") + glob.glob("/dev/ttyACM*")

        # Filter out pty/pts and dummy serials for cleaner selection
        real_ports = [p for p in available_ports if not p.startswith("/dev/pts") and not p.startswith("/dev/ttyS")]
        if not real_ports:
            real_ports = available_ports

        if not real_ports:
            print("[-] No diagnostic serial ports found! Please specify --port or connect adapter.")
            sys.exit(1)

        if len(real_ports) == 1 or args.non_interactive:
            port_name = real_ports[0]
            print(f"[*] Auto-selected serial port: {port_name}")
        else:
            print("[*] Available Diagnostic Ports:")
            for idx, p in enumerate(real_ports, 1):
                print(f"    [{idx}] {p}")
            try:
                choice = input(f"\nSelect port [1-{len(real_ports)}] (default 1): ").strip()
                sel_idx = int(choice) - 1 if choice else 0
                port_name = real_ports[sel_idx]
            except (ValueError, IndexError, KeyboardInterrupt):
                print("\n[-] Aborted by user.")
                sys.exit(1)

    # 2. Determine J.O.E. CSV file
    joe_path = args.joe
    if not joe_path and not args.non_interactive:
        # Search common directories for .csv files
        candidates = []
        for d in [os.getcwd(), os.path.expanduser("~/Downloads"), "/tmp"]:
            if os.path.isdir(d):
                for f in os.listdir(d):
                    if f.lower().endswith(".csv") and ("we8" in f.lower() or "d4" in f.lower() or "joe" in f.lower() or "jura" in f.lower()):
                        candidates.append(os.path.join(d, f))

        default_cand = candidates[0] if candidates else ""
        prompt = f"\nPath to J.O.E. CSV export (optional, press Enter to skip"
        if default_cand:
            prompt += f", default: {default_cand}): "
        else:
            prompt += "): "

        try:
            user_joe = input(prompt).strip()
            if user_joe:
                joe_path = user_joe
            elif default_cand:
                joe_path = default_cand
        except KeyboardInterrupt:
            print("\n[-] Aborted by user.")
            sys.exit(1)

    joe_data = parse_joe_csv(joe_path) if joe_path else {}
    if joe_data:
        print(f"[+] Successfully loaded J.O.E. export: {joe_data.get('model_name')} (Article: {joe_data.get('article_number')})")
        print(f"    Products: {len(joe_data.get('products', {}))}, Maintenance counters: {len(joe_data.get('maintenance', {}))}")

    # 3. Connect to machine
    print(f"\n[*] Connecting to target: {port_name} (9600 baud, 8N1)...")
    if not serial_io:
        print("[-] serial_io module required.")
        sys.exit(1)

    try:
        conn = serial_io.JuraSerialConnection(port_name, baudrate=9600, timeout=1.5)
    except Exception as e:
        print(f"[-] Failed to open serial port: {e}")
        sys.exit(1)

    try:
        bar_len = 30
        def on_prog(pct, blk):
            filled = int((pct / 100.0) * bar_len)
            bar = "=" * filled + " " * (bar_len - filled)
            sys.stdout.write(f"\r    [{bar}] {pct:>3}% (Block 0x{blk:04X})")
            sys.stdout.flush()

        print("[*] Interrogating hardware bus gateways & sweeping EEPROM memory...")
        bundle = capture_machine_bundle(
            conn,
            joe_data=joe_data,
            max_words=args.words,
            on_progress=on_prog
        )
        print()
        print(f"[+] Capture completed successfully: {len(bundle['eeprom_words'])} words captured.")

    finally:
        conn.close()

    identity = bundle["identity"]
    model_name = identity["model_name"]
    print(f"\n[+] Machine Identity Decoded:")
    print(f"    Platform Family : {identity['platform_family']}")
    print(f"    Model Name      : {model_name}")
    print(f"    Article Number  : {identity['article_number']}")
    print(f"    Serial Number   : {identity['serial_number']}")
    print(f"    Production Date : {identity['production_date']}")

    if joe_data and bundle.get("correlations"):
        summary = bundle["correlations"]["summary"]
        print("\n[*] Ground-Truth Correlation Analysis:")
        print(f"    Products Matched    : {summary['matched_products']} / {summary['total_products_checked']}")
        print(f"    Maintenance Matched : {summary['matched_maint']} / {summary['total_maint_checked']}")
    timestamp_str = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    clean_model = re.sub(r'[^A-Za-z0-9_]', '_', model_name).strip('_')
    prefix = args.out or f"spectra_capture_{clean_model}_{timestamp_str}"

    # 9. Save JSON bundle & human text report
    json_filename = f"{prefix}.json"
    txt_filename = f"{prefix}.txt"

    with open(json_filename, "w", encoding="utf-8") as f:
        json.dump(bundle, f, indent=2)

    report_text = build_text_report(bundle)
    with open(txt_filename, "w", encoding="utf-8") as f:
        f.write(report_text)

    print("\n" + "=" * 78)
    print(f"[+] CAPTURE COMPLETE! Files generated:")
    print(f"    JSON Bundle : {os.path.abspath(json_filename)}")
    print(f"    Text Report : {os.path.abspath(txt_filename)}")
    print("=" * 78)
    print("[*] Remote Colleague Instructions:")
    print(f"    Please email or upload '{os.path.basename(json_filename)}' to the development team.")
    print("    With this file, engineers can replicate and debug the exact machine offline.")
    print("=" * 78)


if __name__ == "__main__":
    main()
