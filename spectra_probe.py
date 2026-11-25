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
import shutil
import subprocess
import datetime
import argparse
from typing import Dict, Any, Optional, Tuple, List

try:
    from version import BUILD_NUMBER
except ImportError:
    BUILD_NUMBER = "20261112.1820"

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

try:
    import spectra_py as _rust_core
    HAS_RUST_CORE = True
except ImportError:
    _rust_core = None
    HAS_RUST_CORE = False


SAFE_READ_COMMANDS = ("TY:", "TL:", "TY$:", "TL$:", "IC:", "CS$:", "HZ:", "AS:", "RT:", "RE:")


def _coerce_int(val_str: Any) -> Any:
    """Coerce string value to int if numeric (handling spaces, thousands commas/dots)."""
    if not isinstance(val_str, str):
        return val_str
    s = val_str.strip().strip('"\'')
    try:
        return int(s)
    except ValueError:
        pass
    # Remove whitespace / non-breaking space
    cleaned = re.sub(r'[\s\u00a0\u202f]', '', s)
    # Check standard thousands separators: 1,234 or 1.234
    if re.fullmatch(r'\d{1,3}(,\d{3})+', cleaned):
        try:
            return int(cleaned.replace(',', ''))
        except ValueError:
            pass
    if re.fullmatch(r'\d{1,3}(\.\d{3})+', cleaned):
        try:
            return int(cleaned.replace('.', ''))
        except ValueError:
            pass
    try:
        return int(cleaned)
    except ValueError:
        pass
    return val_str


def parse_joe_csv_lines(lines: List[str]) -> Dict[str, Any]:
    """Parse lines of an official J.O.E. app CSV export or freeform diagnostic `.txt` file."""
    result = {
        "model_name": "",
        "article_number": "",
        "serial_number": "",
        "market_region": "",
        "cockpit": {},
        "maintenance": {},
        "products": {},
        "total_products": None,
        "raw_lines": []
    }

    maint_tokens = (
        "clean", "decalc", "descal", "filter", "rinse", "rinsing",
        "milk", "capp", "brew", "reinig", "entkalk", "spül", "čist", "odváp"
    )
    beverage_tokens = (
        "espresso", "coffee", "kaffee", "káva", "ristretto", "cappuccino",
        "latte", "macchiato", "flat white", "americano", "cortado",
        "lungo", "portion", "hot water", "water", "foam", "powder",
        "ground", "aroma", "jug", "pot", "tea"
    )

    current_section = None
    for raw_line in lines:
        line = raw_line.strip()
        result["raw_lines"].append(line)
        if not line:
            continue

        # Header metadata (colon- or semicolon-delimited)
        meta_m = re.match(r"^([A-Za-z0-9\s./_-]{2,32}?)\s*[:;=]\s*(.+)$", line)
        if meta_m:
            mkey = meta_m.group(1).strip().lower()
            mval = meta_m.group(2).strip().strip('"\'')
            if mkey in ("model name", "machine model", "appliance", "appliance type", "model"):
                if mval:
                    result["model_name"] = mval
                continue
            if mkey in ("article number", "model number", "art. no", "art no", "item no", "type number", "artikelnummer"):
                if mval:
                    result["article_number"] = mval
                continue
            if mkey in ("serial number", "serial no", "serial", "s/n", "seriennummer"):
                if mval:
                    result["serial_number"] = mval
                continue
            if mkey in ("market", "region", "market region", "country", "country code"):
                if mval:
                    result["market_region"] = mval
                continue

        # Section markers
        low_line = line.lower().strip(":[]- ")
        if low_line == "cockpit":
            current_section = "cockpit"
            continue
        elif low_line in ("maintenance counter", "maintenance counters", "maintenance"):
            current_section = "maintenance"
            continue
        elif low_line in ("product counter", "product counters", "products", "beverage counters"):
            current_section = "products"
            continue

        # Key-value lines (comma, semicolon, tab, colon, or equals delimited)
        parts: List[str] = []
        if ';' in line:
            parts = [p.strip() for p in line.split(';') if p.strip()]
        elif ',' in line:
            try:
                import csv
                reader = csv.reader([line])
                parts = [p.strip() for p in next(reader) if p.strip()]
            except Exception:
                parts = [p.strip() for p in re.split(r'[,;]', line) if p.strip()]
        else:
            txt_m = re.match(r"^(?=.*[A-Za-z\u00C0-\u024F])([^:=;|]{2,48}?)\s*(?:[:=]|\t+|\s{2,})\s*(\d[\d,\.\s]{0,12}%?)\s*$", line)
            if txt_m:
                parts = [txt_m.group(1).strip(" :-•|"), txt_m.group(2).strip()]

        if len(parts) >= 2:
            key = parts[0]
            if len(parts) > 2 and all(p.isdigit() for p in parts[1:]):
                val_str = "".join(parts[1:])
            else:
                val_str = parts[1]

            if current_section == "cockpit":
                result["cockpit"][key] = val_str
            elif current_section == "maintenance":
                result["maintenance"][key] = _coerce_int(val_str)
            elif current_section == "products":
                if key.lower().startswith(("total number of products", "total products", "total preps")):
                    result["total_products"] = _coerce_int(val_str)
                else:
                    result["products"][key] = _coerce_int(val_str)
            else:
                # Freeform `.txt` line outside section headers: skip dates/temps/units
                low_key = key.lower()
                low_val = val_str.lower()
                if any(tok in low_key for tok in ("date", "timestamp", "time", "firmware", "ef", "baud", "voltage", "temp", "year")):
                    continue
                if "%" in low_val:
                    pct_m = re.search(r"(\d{1,3})\s*%", val_str)
                    if pct_m and 0 <= int(pct_m.group(1)) <= 100:
                        result["cockpit"][key] = f"{int(pct_m.group(1))}%"
                    continue
                if re.search(r"(°c|°f|ml/s|hz|rpm|v\b)", low_val):
                    continue
                coerced = _coerce_int(val_str)
                if isinstance(coerced, int) and coerced >= 0:
                    if low_key.startswith(("total number of products", "total products", "total preps")):
                        result["total_products"] = coerced
                    elif any(t in low_key for t in maint_tokens):
                        result["maintenance"][key] = coerced
                    elif any(t in low_key for t in beverage_tokens) or re.match(r"^[A-Za-z0-9]", key):
                        result["products"][key] = coerced

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

    if getattr(conn, "_is_smart_connect", False):
        for cmd, _ in commands:
            gateways[cmd] = "[NO_REPLY]"
        return gateways

    for idx, (cmd, desc) in enumerate(commands):
        ans = conn.query_ascii(cmd, timeout=1.2)
        gateways[cmd] = ans if ans else "[NO_REPLY]"
        if idx == 0 and not ans and (getattr(conn, "wire_mode", None) is None or getattr(conn, "_is_smart_connect", False)):
            for rem_cmd, _ in commands[1:]:
                gateways[rem_cmd] = "[NO_REPLY]"
            break

    return gateways


def _smart_connect_probe_sweep(conn, on_progress=None) -> Dict[int, int]:
    """Perform Smart Connect @T0..@t3 handshake and sweep @TR:32,00..1F via conn.query_encrypted."""
    import jura_protocol as jp
    eeprom: Dict[int, int] = {}
    if not hasattr(conn, "query_encrypted"):
        return eeprom

    if not getattr(conn, "_is_smart_connect", False):
        t0 = conn.query_encrypted("@T0\r\n", key=0x20, timeout=1.0)
        if not t0:
            return eeprom
        setattr(conn, "_is_smart_connect", True)
        conn.query_encrypted("@T1\r\n", key=0x21, timeout=0.8)
        t3 = conn.query_encrypted("@t2:818000\r\n", key=0x22, timeout=1.0)
        if t3 and "@T3:" in t3:
            conn.query_encrypted("@t3\r\n", key=0x23, timeout=0.6)

    any_bank = False
    consecutive_empty = 0
    for page in range(32):
        if not getattr(conn, "is_open", True):
            raise IOError("Serial port disconnected during Smart Connect EEPROM sweep.")
        if on_progress:
            on_progress(int((page / 32) * 100), page * 16)
        resp = conn.query_encrypted(f"@TR:32,{page:02X}\r\n", key=(0x30 + page) & 0xFF, timeout=0.8)
        if resp:
            parsed = jp.parse_tr32(resp)
            if parsed:
                any_bank = True
                consecutive_empty = 0
                _, words = parsed
                base = page * 4
                for idx, w in enumerate(words):
                    eeprom[base + idx] = w
                continue
        consecutive_empty += 1
        if page >= 12 and consecutive_empty >= 2:
            break
        if page == 1 and not any_bank and consecutive_empty >= 2:
            break

    if on_progress and any_bank:
        on_progress(100, len(eeprom))
    return eeprom


def sweep_eeprom(conn, max_words: int = 512, on_progress=None, address_width: int = 4) -> Dict[int, int]:
    """Safely sweep EEPROM memory using RT: block reads with RE: fast-fail and Smart Connect fallback."""
    if getattr(conn, "_is_smart_connect", False):
        sc_map = _smart_connect_probe_sweep(conn, on_progress=on_progress)
        if sc_map:
            return sc_map

    addr_w = 2 if int(address_width or 4) == 2 else 4
    if addr_w == 2 and max_words > 256:
        max_words = 256

    def _fmt_addr(a: int) -> str:
        return f"{a:02X}" if addr_w == 2 else f"{a:04X}"

    eeprom: Dict[int, int] = {}
    num_blocks = (max_words + 15) // 16
    consecutive_failed_blocks = 0
    any_block_ok = False

    for blk_idx in range(num_blocks):
        if not getattr(conn, "is_open", True):
            raise IOError("Serial port disconnected during EEPROM sweep.")
        blk = blk_idx * 16
        pct = int((blk_idx / num_blocks) * 100)

        if on_progress:
            on_progress(pct, blk)

        blk_hex = _fmt_addr(blk)
        cmd = f"RT:{blk_hex}"
        try:
            ans = conn.query_ascii(cmd, timeout=1.5)
        except (IOError, OSError) as exc:
            if not getattr(conn, "is_open", True):
                raise IOError(f"Serial port disconnected at block 0x{blk_hex}: {exc}") from exc
            ans = None

        block_ok = False
        if ans and ans.lower().startswith("rt:"):
            raw_hex = ans[3:].strip()
            if len(raw_hex) >= 64:
                try:
                    for idx in range(16):
                        w = int(raw_hex[idx * 4: idx * 4 + 4], 16)
                        eeprom[blk + idx] = w
                    block_ok = True
                except ValueError:
                    block_ok = False

        if block_ok:
            any_block_ok = True
            consecutive_failed_blocks = 0
        else:
            # Probe first word RE:{blk_hex} before falling back to remaining 15 words
            try:
                first_ans = conn.query_ascii(f"RE:{blk_hex}", timeout=1.0)
            except (IOError, OSError) as exc:
                if not getattr(conn, "is_open", True):
                    raise IOError(f"Serial port disconnected at word 0x{blk_hex}: {exc}") from exc
                first_ans = None

            if first_ans and first_ans.lower().startswith("re:"):
                try:
                    eeprom[blk] = int(first_ans[3:].strip()[:4], 16)
                except ValueError:
                    eeprom[blk] = 0x0000
                any_block_ok = True
                consecutive_failed_blocks = 0
                for offset in range(1, 16):
                    if not getattr(conn, "is_open", True):
                        raise IOError("Serial port disconnected during EEPROM sweep.")
                    addr = blk + offset
                    addr_hex = _fmt_addr(addr)
                    try:
                        w_ans = conn.query_ascii(f"RE:{addr_hex}", timeout=1.0)
                    except (IOError, OSError) as exc:
                        if not getattr(conn, "is_open", True):
                            raise IOError(f"Serial port disconnected at word 0x{addr_hex}: {exc}") from exc
                        w_ans = None
                    if w_ans and w_ans.lower().startswith("re:"):
                        try:
                            eeprom[addr] = int(w_ans[3:].strip()[:4], 16)
                        except ValueError:
                            eeprom[addr] = 0x0000
                    else:
                        eeprom[addr] = 0x0000
            else:
                for offset in range(16):
                    eeprom[blk + offset] = 0x0000
                consecutive_failed_blocks += 1
                if (not any_block_ok and consecutive_failed_blocks >= 2) or consecutive_failed_blocks >= 3:
                    break

    has_nonzero = any(v not in (0, 0xFFFF) for v in eeprom.values())
    if (not any_block_ok and consecutive_failed_blocks >= 2) or not has_nonzero:
        sc_map = _smart_connect_probe_sweep(conn, on_progress=on_progress)
        if sc_map:
            return sc_map

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
    elif "R8C" in tl.upper() or "EF509" in ty.upper() or "EF518" in ty.upper() or "EF634" in ty.upper():
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


def correlate_with_joe(
    eeprom: Dict[int, int],
    joe_data: Dict[str, Any],
    use_ollama: bool = False,
    ollama_model: Optional[str] = None,
) -> Dict[str, Any]:
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
            if 0x0000 <= addr <= 0x0006:
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

    def _rank_matches(value: int, category: str) -> List[str]:
        if value <= 0 or (category == "cockpit" and value > 0xFF):
            return []
        if HAS_RUST_CORE and _rust_core is not None and hasattr(_rust_core, "correlate_with_joe_ranked"):
            try:
                clean_eeprom = {int(k): int(v) for k, v in eeprom.items() if 0 <= int(k) <= 0xFFFF and 0 <= int(v) <= 0xFFFF}
                return list(_rust_core.correlate_with_joe_ranked(clean_eeprom, int(value), category))
            except Exception:
                pass
        if category == "cockpit":
            raw_matches = [
                addr for addr, val in eeprom.items()
                if (val & 0xFF) == value or ((val >> 8) & 0xFF) == value
            ]
        else:
            raw_matches = [addr for addr, val in eeprom.items() if val == value]
        raw_matches.sort(key=lambda a: score_address_for_category(a, category), reverse=True)
        return [f"0x{a:04X}" for a in raw_matches]

    # 1. Product beverage correlation
    prods = joe_data.get("products", {})
    for bev_name, count in prods.items():
        if not isinstance(count, int):
            continue
        correlations["summary"]["total_products_checked"] += 1
        matches = _rank_matches(count, "product")

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
        matches = _rank_matches(count, "maintenance")

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
            matches = _rank_matches(pct_val, "cockpit")

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

    if use_ollama:
        try:
            import spectra_ai
            if spectra_ai.is_ai_enabled():
                canon_products = [
                    "Espresso", "2x Espresso", "Coffee", "2x Coffee", "Cappuccino",
                    "Latte Macchiato", "Ristretto", "2x Ristretto", "Flat White",
                    "Espresso Macchiato", "Milk Foam", "Milk", "Hot Water",
                    "Pot of Coffee", "Americano", "Lungo", "Cortado",
                ]
                canon_maint = [
                    "Cleaning", "Descaling", "Filter Change", "Milk System Cleaning",
                    "Cappuccino Rinse", "Coffee Rinse", "Switch-off Rinse",
                ]
                unmatched_prod = [p["name"] for p in correlations["products"] if not p.get("matched")]
                unmatched_maint = [m["name"] for m in correlations["maintenance"] if not m.get("matched")]
                if unmatched_prod:
                    p_map = spectra_ai.match_joe_labels_with_ai(unmatched_prod, canon_products, model=ollama_model)
                    for p in correlations["products"]:
                        if p["name"] in p_map:
                            p["ai_canonical_match"] = p_map[p["name"]]
                if unmatched_maint:
                    m_map = spectra_ai.match_joe_labels_with_ai(unmatched_maint, canon_maint, model=ollama_model)
                    for m in correlations["maintenance"]:
                        if m["name"] in m_map:
                            m["ai_canonical_match"] = m_map[m["name"]]
        except Exception:
            pass

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
    on_progress=None,
    use_ollama: bool = False,
    ollama_model: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Safely interrogate gateways, sweep EEPROM, decode identity,
    correlate ground truth, and return self-contained capture bundle dictionary.
    """
    gateways = query_gateways(conn)

    # Determine geometry & address width
    tl = gateways.get("TL:", "").upper()
    ty = gateways.get("TY:", "").upper()
    ty_clean = ty.replace("TY:", "").strip()
    address_width = 4
    try:
        from spectra_stats.calibration import TWO_DIGIT_ADDRESS_EFS
        prof_hint = profiles_db.find_profile(ty_clean) if (profiles_db and ty_clean) else None
        if (isinstance(prof_hint, dict) and prof_hint.get("address_width") == 2) or any(
            ty_clean.startswith(p) for p in TWO_DIGIT_ADDRESS_EFS
        ):
            address_width = 2
    except Exception:
        pass

    if max_words <= 0:
        port_name = getattr(conn, "raw_port_label", getattr(conn, "port_name", ""))
        if address_width == 2:
            max_words = 256
        elif "EF529" in ty or "D4" in port_name.upper():
            max_words = 1024
        elif not getattr(conn, "_is_smart_connect", False) and ("RL78" in tl or "EF533" in ty or "EF535" in ty or "EF536" in ty):
            probe_200 = conn.query_ascii("RT:0200", timeout=1.0)
            if probe_200 and probe_200.lower().startswith("rt:") and not probe_200[3:].startswith("0000" * 16):
                max_words = 1024
            else:
                max_words = 512
        else:
            max_words = 512

    eeprom = sweep_eeprom(conn, max_words=max_words, on_progress=on_progress, address_width=address_width)
    identity = decode_machine_identity(eeprom, gateways)

    model_name = (joe_data or {}).get("model_name")
    if not model_name:
        try:
            import stats_collector
            art_num = str(identity.get("article_number", ""))
            if art_num in getattr(stats_collector, "ARTICLE_MODEL_MAP", {}):
                fam_info = stats_collector.ARTICLE_MODEL_MAP[art_num]
                model_name = fam_info[0] if isinstance(fam_info, (list, tuple)) else str(fam_info)
            elif profiles_db and ty_clean:
                prof = profiles_db.find_profile(ty_clean)
                if isinstance(prof, dict) and prof.get("model_family") and prof != profiles_db.DEFAULT_PROFILE:
                    model_name = str(prof["model_family"])
        except Exception:
            pass

    if not model_name:
        model_name = identity.get("article_number") or "Jura_Appliance"
    identity["model_name"] = model_name

    correlations = correlate_with_joe(eeprom, joe_data or {}, use_ollama=use_ollama, ollama_model=ollama_model) if joe_data else {}
    mock_code = generate_mock_python_code(gateways, eeprom, model_name)

    try:
        import offset_db_sync
        offset_db_ver = offset_db_sync.get_offset_db_version()
    except Exception:
        offset_db_ver = f"bundled-{BUILD_NUMBER}"

    return {
        "metadata": {
            "timestamp": datetime.datetime.now().isoformat(),
            "spectra_build": BUILD_NUMBER,
            "offset_db_version": offset_db_ver,
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
        f"  Offset DB Version : {meta.get('offset_db_version', f'bundled-{BUILD_NUMBER}')}",
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


COMMUNITY_REPO = "Pr0xyA-91/spectra-captures"


def upload_capture_to_community_repo(
    json_path: Optional[str] = None,
    repo: str = COMMUNITY_REPO,
    open_browser: bool = False,
    bundle_data: Optional[Dict[str, Any]] = None
) -> Tuple[bool, str, Optional[str]]:
    """
    Uploads a captured EEPROM JSON bundle to the public SPECTRA community repository.
    Never swallows errors silently (returns precise error messages).
    Never opens a browser directly unless open_browser=True.
    Limits issue body to 65,536 characters; creates an unlisted Gist if the bundle is larger.
    Retries issue creation without labels if target repository lacks the 'capture' label (422).

    Returns:
        (success: bool, status_message: str, url: Optional[str])
    """
    import urllib.request
    import urllib.error
    import urllib.parse
    import github_auth

    # 1. Resolve payload
    if bundle_data is not None:
        data = bundle_data
    elif json_path and os.path.isfile(json_path):
        try:
            with open(json_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            return False, f"Invalid JSON bundle: {e}", None
    elif json_path:
        return False, f"File not found: {json_path}", None
    else:
        return False, "No capture data or file path provided.", None

    ident = data.get("identity", {})
    offset_fix = data.get("ai_offset_fix") or data.get("override")
    fix_dict = offset_fix if isinstance(offset_fix, dict) else {}
    model_name = fix_dict.get("model_name") or ident.get("model_name") or "Unknown"
    article_number = str(fix_dict.get("article_number") or ident.get("article_number") or "unknown")
    serial_number = str(fix_dict.get("serial_number") or ident.get("serial_number") or "N/A")
    market_region = str(fix_dict.get("market_region") or ident.get("market_region") or "N/A")
    gateways = data.get("gateways", {})
    firmware = gateways.get("TY:", "").replace("ty:", "").strip()
    words_count = len(data.get("eeprom_words", {}))
    has_joe = bool(data.get("joe_ground_truth", {}).get("raw_lines"))
    metadata = data.get("metadata") or {}
    timestamp = data.get("timestamp") or metadata.get("timestamp") or time.strftime("%Y-%m-%d %H:%M:%S")
    build_val = data.get("build") or metadata.get("spectra_build") or BUILD_NUMBER

    has_offset_fix = isinstance(offset_fix, dict) and bool(
        offset_fix.get("products") or offset_fix.get("maintenance") or offset_fix.get("maintenance_pct")
    )

    safe_model = github_auth.sanitize_issue_text(str(model_name), max_chars=200)
    safe_article = github_auth.sanitize_issue_text(str(article_number), max_chars=80)
    safe_serial = github_auth.sanitize_issue_text(str(serial_number), max_chars=120)
    safe_market = github_auth.sanitize_issue_text(str(market_region), max_chars=80)
    safe_fw = github_auth.sanitize_issue_text(str(firmware), max_chars=120)

    title = (
        f"[Offset Fix + Capture] {safe_model} (Article {safe_article})"
        if has_offset_fix
        else f"[Capture] {safe_model} (Article {safe_article})"
    )
    header = (
        f"### Machine Details\n"
        f"- **Manufacturer**: {github_auth.sanitize_issue_text(str(ident.get('manufacturer', 'Jura')), max_chars=80)}\n"
        f"- **Model Name**: {safe_model}\n"
        f"- **Article Number**: {safe_article}\n"
        f"- **Serial Number**: {safe_serial}\n"
        f"- **Market / Region**: {safe_market}\n"
        f"- **Firmware**: {safe_fw}\n"
        f"- **Build**: {build_val}\n"
        f"- **Timestamp**: {timestamp}\n"
        f"- **EEPROM Words**: {words_count}\n"
        f"- **J.O.E. Ground Truth**: {'Yes' if has_joe else 'No'}\n"
        f"- **Verified Offset Fix Included**: {'Yes (Local AI + J.O.E.)' if has_offset_fix else 'No'}\n\n"
    )

    fix_section = ""
    if has_offset_fix:
        import machine_library
        merged_ident = dict(ident)
        merged_ident.setdefault("model_name", model_name)
        merged_ident.setdefault("article_number", article_number)
        if serial_number and serial_number != "N/A":
            merged_ident["serial_number"] = serial_number
        if market_region and market_region != "N/A":
            merged_ident["market_region"] = market_region
        harvest_patch = machine_library.build_offset_patch_payload(offset_fix, identity=merged_ident)
        if isinstance(harvest_patch, dict) and isinstance(harvest_patch.get("override"), dict) and harvest_patch["override"].get("notes"):
            harvest_patch["override"]["notes"] = github_auth.sanitize_issue_text(str(harvest_patch["override"]["notes"]), max_chars=2000)

        fix_lines = [
            "### Verified EEPROM Offset Fix (Local AI Calibration)",
            f"- **Model Used**: `{github_auth.sanitize_issue_text(str(offset_fix.get('model_used', 'local_ai')), max_chars=120)}`",
        ]
        if offset_fix.get("notes"):
            fix_lines.append(f"- **Notes**: {github_auth.sanitize_issue_text(str(offset_fix.get('notes')), max_chars=2000)}")
        fix_lines.extend([
            "",
            "| Category | Item | Address | J.O.E. Ref | EEPROM Raw | Exact |",
            "|---|---|---|---|---|---|",
        ])
        for p in offset_fix.get("products", []):
            fix_lines.append(
                f"| Product | {p.get('name')} | `{p.get('addr_hex')}` | {p.get('joe_count')} | {p.get('eeprom_val')} | {'Yes' if p.get('verified_exact') else 'No'} |"
            )
        for m in offset_fix.get("maintenance", []):
            fix_lines.append(
                f"| Maintenance | {m.get('name')} | `{m.get('addr_hex')}` | {m.get('joe_count')} | {m.get('eeprom_val')} | {'Yes' if m.get('verified_exact') else 'No'} |"
            )
        for c in offset_fix.get("maintenance_pct", []):
            fix_lines.append(
                f"| Cockpit % | {c.get('name')} ({c.get('byte')} byte) | `{c.get('addr_hex')}` | {c.get('joe_pct')}% | `{c.get('eeprom_word_hex')}` | Yes |"
            )
        fix_lines.extend([
            "",
            "### Automated Harvesting Payload (`spectra.offset_patch.v1`)",
            "```json",
            json.dumps(harvest_patch, indent=2, ensure_ascii=False),
            "```",
            "",
        ])
        fix_section = "\n".join(fix_lines) + "\n"

    # Fallback pre-filled submission URL (unauthenticated / manual fallback)
    compact_body = (
        header +
        fix_section +
        "### Capture JSON Data\n"
        "Please paste your capture JSON below:\n\n"
        "```json\n\n```\n"
    )
    params = urllib.parse.urlencode({
        "template": "capture_submission.md",
        "title": title,
        "body": compact_body
    })
    web_url = f"https://github.com/{repo}/issues/new?{params}"

    # 2. Resolve authentication token
    resolved = github_auth.resolve_token()
    token = resolved["token"] if resolved else None

    if not token:
        if open_browser:
            try:
                import webbrowser
                webbrowser.open(web_url)
            except Exception:
                pass
        return False, "Authentication missing: please sign in with GitHub or provide an access token.", web_url

    # 3. Format payload: direct issue body vs Gist fallback (65,536 char limit)
    sanitized_data = json.loads(json.dumps(data, ensure_ascii=False))
    if isinstance(sanitized_data, dict):
        # Ensure required spectra-captures catalog root keys are always present
        meta_obj = sanitized_data.get("metadata")
        if not isinstance(meta_obj, dict):
            meta_obj = {}
            sanitized_data["metadata"] = meta_obj
        meta_obj.setdefault("timestamp", timestamp)
        meta_obj.setdefault("spectra_build", str(build_val))
        meta_obj.setdefault("probe_version", f"Build {build_val}")
        if not isinstance(sanitized_data.get("identity"), dict):
            sanitized_data["identity"] = dict(ident)
        if not isinstance(sanitized_data.get("gateways"), dict):
            sanitized_data["gateways"] = {}
        if not isinstance(sanitized_data.get("eeprom_words"), dict):
            sanitized_data["eeprom_words"] = {}

        for k_fix in ("ai_offset_fix", "override"):
            if isinstance(sanitized_data.get(k_fix), dict) and sanitized_data[k_fix].get("notes"):
                sanitized_data[k_fix]["notes"] = github_auth.sanitize_issue_text(
                    str(sanitized_data[k_fix]["notes"]), max_chars=2000
                )
        if isinstance(sanitized_data.get("joe_ground_truth"), dict) and isinstance(sanitized_data["joe_ground_truth"].get("raw_lines"), list):
            sanitized_data["joe_ground_truth"]["raw_lines"] = [
                github_auth.sanitize_issue_text(str(ln), max_chars=500)
                for ln in sanitized_data["joe_ground_truth"]["raw_lines"]
            ]
    json_str = github_auth.sanitize_issue_text(json.dumps(sanitized_data, indent=2, ensure_ascii=False), max_chars=250000)
    direct_body = (
        header +
        fix_section +
        "### Capture JSON Data\n"
        "```json\n"
        f"{json_str}\n"
        "```\n"
    )

    if len(direct_body.encode("utf-8")) <= 65536:
        issue_body = direct_body
    else:
        # Create unlisted gist
        safe_model = re.sub(r'[^\w\-_]', '_', model_name)
        gist_filename = f"spectra_capture_{safe_model}_{time.strftime('%Y%m%d_%H%M%S')}.json"
        gist_payload = json.dumps({
            "description": f"SPECTRA Capture Bundle - {model_name} (Article {article_number})",
            "public": False,
            "files": {
                gist_filename: {
                    "content": json_str
                }
            }
        }).encode("utf-8")

        gist_req = urllib.request.Request(
            "https://api.github.com/gists",
            data=gist_payload,
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
                "Content-Type": "application/json",
                "User-Agent": "SPECTRA-Diagnostics"
            }
        )
        try:
            import tls_utils
            with urllib.request.urlopen(gist_req, timeout=25, context=tls_utils.get_ssl_context()) as g_resp:
                g_data = json.loads(g_resp.read().decode("utf-8"))
                gist_url = g_data.get("html_url")
        except urllib.error.HTTPError as he:
            err_info = github_auth._extract_github_http_error(he)
            return False, github_auth._format_github_http_error(err_info, prefix="GitHub Gist API error"), None
        except urllib.error.URLError as ue:
            return False, f"Network error creating capture gist: {ue.reason}", None
        except Exception as e:
            return False, f"Failed to upload capture gist: {e}", None

        issue_body = (
            header +
            fix_section +
            "### Capture JSON Data\n"
            f"> **Note**: The full capture payload ({len(json_str):,} characters) exceeds GitHub's 65,536 character issue limit.\n\n"
            f"**Full JSON Capture Bundle (Gist)**: [{gist_filename}]({gist_url})\n"
        )

    # 4. Create Issue in community repository
    api_url = f"https://api.github.com/repos/{repo}/issues"

    def _post_issue(include_label: bool = True):
        payload_dict = {
            "title": title,
            "body": issue_body,
        }
        if include_label:
            payload_dict["labels"] = ["capture"]
        req = urllib.request.Request(
            api_url,
            data=json.dumps(payload_dict).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
                "Content-Type": "application/json",
                "User-Agent": "SPECTRA-Diagnostics"
            }
        )
        import tls_utils
        return urllib.request.urlopen(req, timeout=20, context=tls_utils.get_ssl_context())

    try:
        with _post_issue(include_label=True) as resp:
            resp_data = json.loads(resp.read().decode("utf-8"))
            issue_url = resp_data.get("html_url")
            return True, f"Capture uploaded successfully: {issue_url}", issue_url
    except urllib.error.HTTPError as he:
        err_info = github_auth._extract_github_http_error(he)
        if err_info["is_label_error"]:
            # Retry without label (422 missing label or 403 non-collaborator label creation denied)
            try:
                with _post_issue(include_label=False) as resp2:
                    resp_data2 = json.loads(resp2.read().decode("utf-8"))
                    issue_url = resp_data2.get("html_url")
                    return True, f"Capture uploaded successfully: {issue_url}", issue_url
            except urllib.error.HTTPError as he2:
                err_info2 = github_auth._extract_github_http_error(he2)
                return False, github_auth._format_github_http_error(err_info2), None
            except Exception as e2:
                return False, f"GitHub API error on retry: {e2}", None
        return False, github_auth._format_github_http_error(err_info), None
    except urllib.error.URLError as ue:
        return False, f"Network error contacting GitHub API: {ue.reason}", None
    except Exception as e:
        return False, f"Failed to submit issue: {e}", None


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
    parser.add_argument("--upload", action="store_true", help="Automatically submit captured bundle to community telemetry database (Pr0xyA-91/spectra-captures)")
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
            available_ports = serial_io.list_serial_ports()
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
    print("[*] Community Telemetry Integration:")
    print(f"    Target Database: https://github.com/{COMMUNITY_REPO}")
    print("=" * 78)

    # 10. Community Telemetry Upload
    should_upload = args.upload
    if not should_upload and not args.non_interactive and sys.stdin.isatty():
        try:
            choice = input(f"\n[?] Upload '{os.path.basename(json_filename)}' to public telemetry database for analysis? [y/N]: ").strip().lower()
            if choice in ("y", "yes"):
                should_upload = True
        except (KeyboardInterrupt, EOFError):
            pass

    if should_upload:
        print(f"\n[*] Submitting capture to SPECTRA community repository ({COMMUNITY_REPO})...")
        success, msg, issue_url = upload_capture_to_community_repo(json_filename)
        if success:
            print(f"[+] {msg}")
            if issue_url:
                print(f"    Tracking Issue: {issue_url}")
        else:
            print(f"[-] Upload failed: {msg}")
            if issue_url and not args.non_interactive and sys.stdin.isatty():
                try:
                    open_br = input("\n[?] Open pre-filled submission form in browser? [y/N]: ").strip().lower()
                    if open_br in ("y", "yes"):
                        import webbrowser
                        webbrowser.open(issue_url)
                    else:
                        print(f"    You can manually submit by creating an issue at: {issue_url}")
                except (KeyboardInterrupt, EOFError):
                    print(f"    You can manually submit by creating an issue at: {issue_url}")
            elif issue_url:
                print(f"    You can manually submit by creating an issue at: {issue_url}")


if __name__ == "__main__":
    main()
