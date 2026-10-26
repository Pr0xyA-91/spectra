#!/usr/bin/env python3
"""
Jura Machine Hardware & Memory Specification Dumper (SPECTRA Contrib)
Part of SPECTRA — Universal Hardware Telemetry & Logic Board Diagnostics

Connects to a physical Jura coffee machine (or offline demo simulator),
interrogates ASCII gateways (TY:, TL:, TY$:, TL$:, CS$:, IC:, HZ:, AS:),
dumps the complete 512-word EEPROM memory space (0x0000 .. 0x01FF),
analyzes universal vs model-specific registers,
and auto-generates:
  - docs/models/<EF_CODE>_<MODEL_NAME>.json (Structured specification)
  - docs/models/<EF_CODE>_<MODEL_NAME>.md   (Documentation & Pull Request report)

Credits & Attribution:
  CM-P, Hajo Noerenberg, makefu, Jutta-Proto, AlexxIT, Otto Winter,
  Google Antigravity (Agy / DeepMind), and the open-source hardware community.
"""

import os
import sys
import re
import json
import time
import datetime
import argparse
from typing import Dict, Any, Optional, Tuple, List

# Ensure repository root is on sys.path
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

import serial_io
import profiles_db
import stats_collector

# Universal registers defined by platform invariants
UNIVERSAL_REGISTER_MAP = {
    0x0001: ("Espresso_Single", "Single Espresso cup count"),
    0x0002: ("Espresso_Double", "Double Espresso cup count"),
    0x0003: ("Coffee_Single", "Single Coffee cup count"),
    0x0004: ("Coffee_Double", "Double Coffee cup count"),
    0x0005: ("Cappuccino_Single", "Single Cappuccino cup count"),
    0x0006: ("Cappuccino_Double", "Double Cappuccino cup count"),
    0x0007: ("Rinses_Count", "Total rinse cycles executed"),
    0x0008: ("Cleaning_Count", "Total brew unit cleaning tablet cycles executed"),
    0x0009: ("Descaling_Count", "Total descaling cycles executed"),
    0x000A: ("Grinder_Seconds", "Total cumulative grinder motor run time in seconds"),
    0x0015: ("Service_Counter", "Preparations performed since last maintenance intervention"),
    0x0028: ("Fault_Latch_Bitmask", "Non-volatile hardware safety fault latch bitfield"),
    0x0029: ("Machine_Options", "Non-volatile machine feature and option flags"),
    0x0030: ("Machine_Article_Word", "Appliance hardware / article configuration number"),
    0x0031: ("Serial_Counter", "Production batch sequential manufacturing serial number"),
    0x0032: ("Production_Date", "Factory manufacturing date (Day: bits 0-4, Month: bits 5-8, Year: bits 9-15)"),
    0x0040: ("BU_Upper_Limit", "Brew Unit mechanical top travel limit encoder ticks"),
    0x0041: ("BU_Mill_Target", "Brew Unit ground coffee intake / grinder position ticks"),
    0x0042: ("BU_Prebrew_1", "Brew Unit pre-infusion position 1 ticks"),
    0x0043: ("BU_Compression", "Brew Unit maximum compaction / extraction position ticks"),
    0x0044: ("BU_Prebrew_2", "Brew Unit pre-infusion position 2 ticks"),
    0x0045: ("Drainage_Valve", "Drainage valve calibration offset ticks"),
    0x0055: ("Water_Hardness_Legacy", "Legacy water hardness setting"),
    0x00C3: ("Water_Hardness", "Configured water hardness (°dH: bits 8-15)"),
    0x00DA: ("SPDL_Country", "SPDL destination market ISO 3166 country code in ASCII"),
    0x00DB: ("SPDL_Date_Download", "Firmware flash download date bitfield"),
    0x00DC: ("SPDL_Date_Language", "Front-panel language string table flash date bitfield"),
    0x00E9: ("Retail_Counter_High", "Commercial retail cup counter high word"),
    0x00EA: ("Retail_Counter_Low", "Commercial retail cup counter low word"),
    0x0103: ("Encoder_Error_Count", "Lifetime rotary switch / encoder error count"),
    0x01B0: ("Error_Count_Heater", "Lifetime Thermoblock 1 over-temperature / timeout errors"),
    0x01B1: ("Error_Count_SteamHeater", "Lifetime Thermoblock 2 (Steam) errors"),
    0x01B2: ("Error_Count_BrewUnit", "Lifetime Brew Unit encoder / motor stall errors"),
    0x01B3: ("Error_Count_Flowmeter", "Lifetime flowmeter pulse missing / fluid blockage errors"),
    0x01B4: ("Error_Count_Solenoid", "Lifetime solenoid / ceramic valve switch errors"),
    0x01B5: ("Error_Count_Drainage", "Lifetime electronic drainage valve errors"),
    0x01B6: ("Error_Count_NTC", "Lifetime temperature sensor NTC short / open-circuit errors")
}

# Known model-specific registers (e.g. external plumbing, recipe configurations)
MODEL_SPECIFIC_REGISTER_MAP = {
    0x0000: ("Filter_Ext_Watervolume", "Cumulative volume drawn through external filtration (dl)"),
    0x0003: ("Filter_Ext_Watervolumeafter", "Volume drawn after external filter threshold exceeded (dl)"),
    0x0070: ("Filter_Ext_Rinsing", "Rinse water volume through external filter (dl)"),
    0x0071: ("Filter_Ext_Limit_Rinsing", "External filter maximum rinse limit threshold (dl)"),
    0x0076: ("Filter_Ext_Watervolume2", "Secondary external filter volume counter (dl)"),
    0x008B: ("Filter_Ext_Limit_Water", "Warning threshold for external filter cartridge replacement (dl)"),
    0x00B4: ("Espresso_1_2_Settings", "Front-Panel Buttons 1 & 2 aroma strength & pre-brew configuration"),
    0x00B5: ("Coffee_1_2_Settings", "Front-Panel Buttons 3 & 4 aroma strength & pre-brew configuration"),
    0x00B9: ("Espresso_1_2_Volume", "Dispensed water volume for Single & Double Espresso (dl)"),
    0x00BA: ("Coffee_1_2_Volume", "Dispensed water volume for Single & Double Coffee (dl)"),
    0x00BB: ("Hotwater_Volume", "Hot water portion volume (dl)"),
    0x00A9: ("Hotwater_Settings", "Hot water dispense temperature and bypass valve setting")
}


def print_banner():
    banner = """
===============================================================================
       SPECTRA — Machine Hardware & Memory Specification Dumper
        Automated Extraction for Community Hardware Specifications
===============================================================================
"""
    print(banner)


def query_gateways(conn: serial_io.JuraSerialConnection) -> Dict[str, str]:
    """Query all standard and voluntary ASCII hardware identification gateways."""
    print("[*] Interrogating hardware identification gateways...")
    gateways = {}

    queries = [
        ("TY:", "Main Board Firmware"),
        ("TL:", "Main Board Bootloader"),
        ("TY$:", "Sub-Bus Display MCU Firmware"),
        ("TL$:", "Sub-Bus Display Bootloader"),
        ("CS$:", "Sub-Bus Display Checksum"),
        ("IC:", "Hardware Architecture Mask"),
        ("HZ:", "Heating & Pump Telemetry"),
        ("AS:", "Analog Sensor ADC / Optical Hopper")
    ]

    for cmd, desc in queries:
        try:
            ans = conn.query_ascii(cmd, timeout=1.8)
            gateways[cmd] = ans.strip() if ans else "N/A"
            status = f"'{gateways[cmd]}'" if gateways[cmd] != "N/A" else "Not Supported / Timeout"
            print(f"    - {cmd:<5} ({desc:<30}): {status}")
        except Exception as e:
            gateways[cmd] = "ERROR"
            print(f"    - {cmd:<5} ({desc:<30}): Error ({e})")

    return gateways


def dump_full_eeprom(conn: serial_io.JuraSerialConnection) -> Dict[int, int]:
    """
    Read all 512 EEPROM words (0x0000 .. 0x01FF) using block reads (RT:),
    falling back to individual word reads (RE:) where blocks fail.
    """
    print("\n[*] Dumping complete 512-word EEPROM memory space (0x0000 .. 0x01FF)...")
    eeprom: Dict[int, int] = {}
    total_blocks = 32

    for b_idx in range(total_blocks):
        blk = b_idx * 16
        pct = int(((b_idx + 1) / total_blocks) * 100)
        bar_len = 30
        filled = int(bar_len * (b_idx + 1) // total_blocks)
        bar = "=" * filled + "-" * (bar_len - filled)
        sys.stdout.write(f"\r    [{bar}] {pct:>3}% Reading Block 0x{blk:04X}...")
        sys.stdout.flush()

        cmd = f"RT:{blk:04X}"
        ans = conn.query_ascii(cmd, timeout=1.8)

        block_success = False
        if ans and ans.lower().startswith("rt:"):
            raw_hex = ans[3:].strip()
            if len(raw_hex) >= 64:
                words = [int(raw_hex[i * 4: i * 4 + 4], 16) for i in range(16)]
                for idx, w in enumerate(words):
                    eeprom[blk + idx] = w
                block_success = True

        if not block_success:
            # Fallback to individual word reads for this block
            for offset in range(16):
                addr = blk + offset
                w_ans = conn.query_ascii(f"RE:{addr:04X}", timeout=1.2)
                if w_ans and w_ans.lower().startswith("re:"):
                    try:
                        eeprom[addr] = int(w_ans[3:].strip()[:4], 16)
                    except ValueError:
                        eeprom[addr] = 0x0000
                else:
                    eeprom[addr] = 0x0000

    sys.stdout.write(f"\r    [{'=' * 30}] 100% Complete! Read {len(eeprom)} words.               \n")
    sys.stdout.flush()
    return eeprom


def analyze_hardware(gateways: Dict[str, str], eeprom: Dict[int, int], model_name_override: Optional[str] = None) -> Tuple[Dict[str, Any], str, str]:
    """Extract hardware features, deduce capabilities, and match with profiles_db."""
    print("\n[*] Analyzing hardware capabilities and memory map...")

    ty_str = gateways.get("TY:", "")
    ef_match = re.search(r'(EF\w+)', ty_str.upper())
    ef_code = ef_match.group(1) if ef_match else "UNKNOWN"

    ty_sub = gateways.get("TY$:", "")
    ef_sub_match = re.search(r'(EF\w+)', ty_sub.upper())
    display_ef = ef_sub_match.group(1) if ef_sub_match else ""

    profiles = profiles_db.load_profiles()
    profile = profiles.get(ef_code, {})

    model_family = model_name_override or profile.get("model_family", "")
    if not model_family:
        if ef_code != "UNKNOWN":
            model_family = f"Jura Appliance ({ef_code})"
        else:
            model_family = "Unknown Jura Model"

    series = profile.get("series", "Jura Domestic / Commercial")
    article_numbers = profile.get("articles", [])
    if not article_numbers:
        # Check machine number from 0x0030
        art_word = eeprom.get(0x0030, 0)
        if art_word > 0:
            article_numbers = [str(art_word)]

    # Detect optical hopper from AS:
    has_optical_hopper = False
    optical_hopper_cfg = None
    as_ans = gateways.get("AS:", "")
    if as_ans and as_ans.lower().startswith("as:"):
        adc_match = re.findall(r'([0-9A-Fa-f]{4})', as_ans[3:])
        if len(adc_match) >= 2:
            has_optical_hopper = True
            ambient_adc = int(adc_match[0], 16)
            reflected_adc = int(adc_match[1], 16)
            optical_hopper_cfg = {
                "command": "AS:",
                "empty_adc_threshold": 1710,
                "nominal_adc_threshold": ambient_adc if ambient_adc > 1000 else 1680,
                "nominal_delta_max": 85,
                "empty_delta_min": 95
            }

    # Detect sub-bus display
    has_sub_bus = bool(display_ef and display_ef != "N/A" and not display_ef.startswith("ERROR"))

    # Detect heating architecture from HZ:
    hz_ans = gateways.get("HZ:", "")
    thermoblocks = 1
    has_steam_heater = False
    if hz_ans and hz_ans.lower().startswith("hz:"):
        parts = hz_ans[3:].split(",")
        if len(parts) >= 6:
            # part 4: TB1, part 5: TB2
            try:
                tb2_raw = int(parts[5].strip(), 16)
                if tb2_raw > 0 and tb2_raw != 0x0802:  # 0x0802 is sentinel for not installed
                    thermoblocks = 2
                    has_steam_heater = True
            except (ValueError, IndexError):
                pass

    # Detect external plumbing
    ext_plumbing_keys = [0x0000, 0x0003, 0x0070, 0x0071, 0x0076, 0x008B]
    has_external_plumbing = any(eeprom.get(k, 0) > 0 for k in ext_plumbing_keys)
    if "XJ" in model_family or "GIGA" in model_family or "X8" in model_family or "X10" in model_family:
        has_external_plumbing = True

    # Brew unit calibration ticks
    bu_upper = eeprom.get(0x0040, 1292)
    bu_mill = eeprom.get(0x0041, 230)
    bu_pre1 = eeprom.get(0x0042, 266)
    bu_comp = eeprom.get(0x0043, 520)
    bu_pre2 = eeprom.get(0x0044, 546)

    hardware = {
        "thermoblocks": thermoblocks,
        "has_steam_heater": has_steam_heater,
        "has_optical_hopper": has_optical_hopper,
        "has_sub_bus": has_sub_bus,
        "has_external_plumbing": has_external_plumbing,
        "has_milk_system": bool(profile.get("features", {}).get("milk_system", False)),
        "flowmeter_pulses_per_ml": 2.366,
        "bu_calibration": {
            "upper_limit_ticks": bu_upper,
            "mill_target_ticks": bu_mill,
            "prebrew_1_ticks": bu_pre1,
            "compression_ticks": bu_comp,
            "prebrew_2_ticks": bu_pre2,
            "registers": {
                "upper_limit": "0040",
                "mill_target": "0041",
                "prebrew_1": "0042",
                "compression": "0043",
                "prebrew_2": "0044"
            }
        }
    }
    if optical_hopper_cfg:
        hardware["optical_hopper"] = optical_hopper_cfg

    # Classify custom / model-specific non-zero registers
    custom_registers = {}
    for addr, val in sorted(eeprom.items()):
        if val == 0:
            continue
        if addr in MODEL_SPECIFIC_REGISTER_MAP:
            name, desc = MODEL_SPECIFIC_REGISTER_MAP[addr]
            custom_registers[f"{addr:04X}"] = {
                "name": name,
                "description": desc,
                "current_hex": f"0x{val:04X}",
                "current_dec": val
            }
        elif addr not in UNIVERSAL_REGISTER_MAP:
            custom_registers[f"{addr:04X}"] = {
                "name": f"Unmapped_0x{addr:04X}",
                "description": f"Model-specific register (Value: 0x{val:04X} / {val})",
                "current_hex": f"0x{val:04X}",
                "current_dec": val
            }

    # Standard recipe buttons
    recipe_buttons = []
    if 0x00B9 in eeprom and 0x00B4 in eeprom:
        recipe_buttons = [
            {"button": 1, "product": "1 Espresso", "volume_reg": "00B9", "volume_byte": "low", "settings_reg": "00B4", "settings_byte": "low"},
            {"button": 2, "product": "2 Espressi", "volume_reg": "00B9", "volume_byte": "high", "settings_reg": "00B4", "settings_byte": "high"},
            {"button": 3, "product": "1 Coffee", "volume_reg": "00BA", "volume_byte": "low", "settings_reg": "00B5", "settings_byte": "low"},
            {"button": 4, "product": "2 Coffees", "volume_reg": "00BA", "volume_byte": "high", "settings_reg": "00B5", "settings_byte": "high"}
        ]

    spec = {
        "model_family": model_family,
        "ef_code": ef_code,
        "display_ef": display_ef,
        "series": series,
        "article_numbers": [str(a) for a in article_numbers],
        "hardware": hardware,
        "custom_registers": custom_registers,
        "recipe_buttons": recipe_buttons,
        "gateways": gateways
    }

    clean_name = re.sub(r'[^A-Za-z0-9_]+', '_', model_family).strip('_')
    return spec, ef_code, clean_name


def write_specification_files(spec: Dict[str, Any], eeprom: Dict[int, int], out_dir: str, ef_code: str, clean_name: str) -> Tuple[str, str]:
    """Generate both the machine-readable JSON and human-readable Markdown specifications."""
    os.makedirs(out_dir, exist_ok=True)

    base_filename = f"{ef_code}_{clean_name}"
    json_path = os.path.join(out_dir, f"{base_filename}.json")
    md_path = os.path.join(out_dir, f"{base_filename}.md")

    # 1. Write Structured JSON
    spec_export = dict(spec)
    # Include non-zero words map for easy cross-model diffing
    spec_export["non_zero_eeprom"] = {f"{k:04X}": f"{v:04X}" for k, v in sorted(eeprom.items()) if v != 0}

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(spec_export, f, indent=2)

    # 2. Write Formatted Markdown Report
    hw = spec["hardware"]
    gw = spec["gateways"]
    bu = hw.get("bu_calibration", {})

    lines = []
    lines.append(f"# Jura Model Specification: {spec['model_family']}")
    lines.append("")
    lines.append(f"> Auto-generated by SPECTRA Machine Specification Dumper on {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append("")
    lines.append("## 1. System & Architecture Overview")
    lines.append("")
    lines.append("| Specification Attribute | Hardware Value / Configuration | Notes |")
    lines.append("| :--- | :--- | :--- |")
    lines.append(f"| **Commercial Model Family** | `{spec['model_family']}` | Commercial branding |")
    lines.append(f"| **Main Board Logic Code** | `{spec['ef_code']}` (`{gw.get('TY:', 'N/A')}`) | Logic board microcontroller |")
    lines.append(f"| **Main Board Bootloader** | `{gw.get('TL:', 'N/A')}` | Factory bootloader |")
    lines.append(f"| **Display Unit / Sub-Bus** | `{spec['display_ef'] or 'Direct / None'}` (`{gw.get('TY$:', 'N/A')}`) | Front panel MCU |")
    lines.append(f"| **Display Bootloader** | `{gw.get('TL$:', 'N/A')}` | Sub-bus bootloader |")
    lines.append(f"| **Display Checksum** | `{gw.get('CS$:', 'N/A')}` | Microcontroller checksum |")
    lines.append(f"| **Hardware Mask (IC:)** | `{gw.get('IC:', 'N/A')}` | Motherboard architecture code |")
    lines.append(f"| **Jura Article Numbers** | `{', '.join(spec['article_numbers']) or 'N/A'}` | Factory production SKU(s) |")
    lines.append(f"| **Thermoblock Heating** | `{hw['thermoblocks']} Thermoblock(s)` (Steam: `{'Yes' if hw['has_steam_heater'] else 'No'}`) | Thermal system |")
    lines.append(f"| **Optical Hopper Sensor** | `{'Installed (AS: Supported)' if hw['has_optical_hopper'] else 'Not Installed / Standard'}` | Infrared bean level monitor |")
    lines.append(f"| **External Plumbing** | `{'Supported (Filter_Ext Counters Active)' if hw['has_external_plumbing'] else 'Standard Tank'}` | Commercial plumbing support |")
    lines.append("")

    lines.append("## 2. Brew Unit Calibration & Travel Parameters")
    lines.append("")
    lines.append("| Position / Threshold | Register | Target Encoder Ticks | Function |")
    lines.append("| :--- | :---: | :---: | :--- |")
    lines.append(f"| **Upper Mechanical Limit** | `RE:0040` | `{bu.get('upper_limit_ticks', 'N/A')}` | Top mechanical end-stop |")
    lines.append(f"| **Mill / Intake Target** | `RE:0041` | `{bu.get('mill_target_ticks', 'N/A')}` | Position for ground coffee drop |")
    lines.append(f"| **Prebrew Travel 1** | `RE:0042` | `{bu.get('prebrew_1_ticks', 'N/A')}` | Pre-infusion chamber compression |")
    lines.append(f"| **Full Compression** | `RE:0043` | `{bu.get('compression_ticks', 'N/A')}` | Extraction maximum resistance |")
    lines.append(f"| **Prebrew Travel 2** | `RE:0044` | `{bu.get('prebrew_2_ticks', 'N/A')}` | Second pre-infusion position |")
    lines.append("")

    lines.append("## 3. Product Recipes & Direct Selection Matrix")
    lines.append("")
    if spec["recipe_buttons"]:
        lines.append("| Front Panel Button | Product Name | Volume Register | Settings Register |")
        lines.append("| :---: | :--- | :---: | :---: |")
        for btn in spec["recipe_buttons"]:
            lines.append(f"| Button {btn['button']} | **{btn['product']}** | `RE:{btn['volume_reg']}` ({btn['volume_byte']}) | `RE:{btn['settings_reg']}` ({btn['settings_byte']}) |")
    else:
        lines.append("*Rotary selection or multi-page display menu matrix.*")
    lines.append("")

    lines.append("## 4. Model-Specific & Unmapped EEPROM Registers")
    lines.append("")
    lines.append("| Register | Current Hex | Current Dec | Description / Functional Assignment |")
    lines.append("| :---: | :---: | :---: | :--- |")
    for reg_hex, rdata in sorted(spec["custom_registers"].items()):
        lines.append(f"| `RE:{reg_hex}` | `{rdata.get('current_hex', '0x0000')}` | `{rdata.get('current_dec', 0)}` | {rdata.get('description', rdata.get('name', ''))} |")
    lines.append("")

    lines.append("## 5. Non-Zero EEPROM Diagnostic Memory Dump")
    lines.append("")
    lines.append("| Address | Raw Hex | Decimal | Classification | Description |")
    lines.append("| :---: | :---: | :---: | :--- | :--- |")
    for addr, val in sorted(eeprom.items()):
        if val == 0:
            continue
        hex_addr = f"{addr:04X}"
        if addr in UNIVERSAL_REGISTER_MAP:
            cls = "**Universal**"
            name, desc = UNIVERSAL_REGISTER_MAP[addr]
        elif addr in MODEL_SPECIFIC_REGISTER_MAP:
            cls = "*Model-Specific*"
            name, desc = MODEL_SPECIFIC_REGISTER_MAP[addr]
        else:
            cls = "Unmapped"
            desc = "Subsystem or Model Register"
        lines.append(f"| `0x{hex_addr}` | `0x{val:04X}` | `{val}` | {cls} | {desc} |")
    lines.append("")

    lines.append("---")
    lines.append("### Contribution & Maintenance Note")
    lines.append("To contribute additions or corrections for this model specification:")
    lines.append("1. Fork and create a topic branch: `git checkout -b model/<EF_CODE>`")
    lines.append(f"2. Add your verified registers or recipe settings in `docs/models/{base_filename}.json`")
    lines.append("3. Submit a Pull Request to `https://github.com/Pr0xyA-91/spectra.git`")
    lines.append("")

    with open(md_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    return json_path, md_path


def print_contribution_guide(json_path: str, md_path: str, ef_code: str, model_name: str):
    """Print terminal summary and pull request submission instructions."""
    box = f"""
===============================================================================
[✓] SUCCESS: Model Specification Generated!
===============================================================================
Model Family : {model_name}
EF Code      : {ef_code}

Generated Files:
  - JSON Spec : {json_path}
  - Markdown  : {md_path}

How to Submit to SPECTRA upstream:
  1. Review the generated documentation file:
     cat {md_path}

  2. Create a git branch and commit the new model:
     git checkout -b model/{ef_code.lower()}
     git add {json_path} {md_path}
     git commit -m "feat(models): add hardware & memory spec for {model_name}"

  3. Push to your fork and submit a Pull Request on GitHub:
     git push origin model/{ef_code.lower()}
===============================================================================
"""
    print(box)


def main():
    parser = argparse.ArgumentParser(
        description="Dump Jura machine telemetry, analyze EEPROM, and auto-generate model specifications."
    )
    parser.add_argument("--port", "-p", help="Serial port to connect (e.g. /dev/ttyUSB0 or COM3)")
    parser.add_argument("--baud", "-b", type=int, default=9600, help="Baud rate (default: 9600)")
    parser.add_argument("--out-dir", "-o", default=os.path.join(REPO_ROOT, "docs", "models"), help="Destination directory for model specifications")
    parser.add_argument("--name", "-n", help="Override commercial model name (e.g. 'IMPRESSA XJ5 Professional GII')")
    parser.add_argument("--demo", "--sim", action="store_true", help="Run in offline simulation mode using virtual MockJuraMachine")
    parser.add_argument("--diff", help="Optional baseline JSON dump or model code to diff against")
    parser.add_argument("--yes", "-y", action="store_true", help="Non-interactive mode (auto-accept defaults)")

    args = parser.parse_args()
    print_banner()

    port = args.port
    if args.demo:
        port = "DEMO / SIMULATION (Jura S8)"
    elif not port:
        # Detect available ports
        detected = serial_io.list_serial_ports()
        if not detected:
            print("[-] No serial ports found. Use --demo to run offline simulation.")
            sys.exit(1)

        if len(detected) == 1 or args.yes:
            port = detected[0]
            print(f"[*] Auto-selected port: {port}")
        else:
            print("[?] Available serial ports:")
            for idx, p in enumerate(detected):
                print(f"    [{idx + 1}] {p}")
            if sys.stdin.isatty():
                try:
                    choice = input(f"\nSelect port [1-{len(detected)}] (default 1): ").strip()
                    sel_idx = int(choice) - 1 if choice else 0
                    port = detected[sel_idx]
                except (ValueError, IndexError):
                    port = detected[0]
            else:
                port = detected[0]
            print(f"[*] Selected port: {port}")

    print(f"[*] Connecting to {port} at {args.baud} baud (8N1)...")
    try:
        conn = serial_io.JuraSerialConnection(port, baudrate=args.baud, timeout=1.8)
    except Exception as e:
        print(f"[-] Failed to open serial port {port}: {e}")
        sys.exit(1)

    try:
        # 1. Query Gateways
        gateways = query_gateways(conn)

        # 2. Dump Full EEPROM
        eeprom = dump_full_eeprom(conn)

        # 3. Analyze Hardware & Map Registers
        spec, ef_code, clean_name = analyze_hardware(gateways, eeprom, model_name_override=args.name)

        # 4. Generate Files
        json_path, md_path = write_specification_files(spec, eeprom, args.out_dir, ef_code, clean_name)

        # 5. Optional Baseline Diff
        if args.diff:
            print("\n[*] Comparing against baseline...")
            diff_rep = stats_collector.generate_eeprom_diff_report(
                live_dump={"gateways": gateways, "eeprom": eeprom, "hardware": spec["hardware"]},
                baseline_source=args.diff,
                label=spec["model_family"]
            )
            print(diff_rep)

        # 6. Contributor Instructions
        print_contribution_guide(json_path, md_path, ef_code, spec["model_family"])

    finally:
        conn.close()


if __name__ == "__main__":
    main()
