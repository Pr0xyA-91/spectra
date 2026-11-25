#!/usr/bin/env python3
"""
SPECTRA — Machine EEPROM Restoration Utility
Restores non-volatile registers and counters from docs/models/<EF>_*.json
with individual word verification and automated CRC recalculation (AN:0B).
"""

import sys
import os
import re
import time
import json
import argparse
import datetime
from typing import Dict, List, Optional, Tuple

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import serial_io

_HEX4_RE = re.compile(r"^[0-9A-F]{4}$")
_MAX_EEPROM_ADDR = 0x01FF
_CRC_REGISTER_ADDR = "0075"


def _validate_target_words(raw_words: Dict[str, str]) -> Dict[str, str]:
    """Validate 4-hex-digit EEPROM addresses/values and exclude CRC register 0x0075."""
    validated: Dict[str, str] = {}
    for raw_addr, raw_val in raw_words.items():
        addr = str(raw_addr).strip().upper()
        val = str(raw_val).strip().upper()
        if not _HEX4_RE.match(addr):
            raise ValueError(f"Invalid EEPROM address in spec (expected 4 hex digits): {raw_addr!r}")
        if not _HEX4_RE.match(val):
            raise ValueError(f"Invalid EEPROM value for 0x{addr} (expected 4 hex digits): {raw_val!r}")
        addr_int = int(addr, 16)
        if addr_int > _MAX_EEPROM_ADDR:
            raise ValueError(f"EEPROM address 0x{addr} exceeds maximum safe word index 0x{_MAX_EEPROM_ADDR:04X}")
        if addr == _CRC_REGISTER_ADDR:
            # Never overwrite CRC register directly; rebuilt exclusively via AN:0B after 100% write verification.
            continue
        validated[addr] = val
    return validated


def _save_prewrite_backup(
    hw_ef: str,
    current_words: Dict[str, str],
    backup_dir: Optional[str] = None,
) -> str:
    """Persist a timestamped pre-write EEPROM backup with owner-only permissions (0o600 on POSIX)."""
    safe_ef = re.sub(r"[^A-Za-z0-9_.-]+", "_", hw_ef or "UNKNOWN")[:32]
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    target_dir = backup_dir or os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "backups",
    )
    os.makedirs(target_dir, exist_ok=True)
    if os.name != "nt":
        try:
            os.chmod(target_dir, 0o700)
        except OSError:
            pass
    backup_path = os.path.join(target_dir, f"eeprom_prewrite_backup_{safe_ef}_{ts}.json")
    payload = {
        "hw_ef": hw_ef,
        "timestamp": ts,
        "non_zero_eeprom": dict(sorted(current_words.items())),
    }
    if os.name != "nt":
        fd = os.open(backup_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)
    else:
        with open(backup_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)
    return backup_path


def restore_eeprom(
    port: str,
    json_path: str,
    dry_run: bool = True,
    inter_write_delay: float = 0.04,
    *,
    confirm_lab_write: bool = False,
    backup_dir: Optional[str] = None,
    non_interactive_confirm: bool = False,
) -> bool:
    print("=== SPECTRA EEPROM Restoration Tool ===")
    print(f"Target Port:      {port}")
    print(f"Model Spec:       {json_path}")
    print(f"Dry Run Mode:     {'YES (Read-only simulation)' if dry_run else 'NO (Live EEPROM Write)'}")

    if not dry_run and not confirm_lab_write:
        print("Error: Live EEPROM writes require confirm_lab_write=True (--apply --confirm-lab-write).")
        return False

    if not os.path.exists(json_path):
        print(f"Error: Model file '{json_path}' not found.")
        return False

    with open(json_path, "r", encoding="utf-8") as f:
        model_spec = json.load(f)

    raw_target_words = model_spec.get("non_zero_eeprom", {})
    if not isinstance(raw_target_words, dict) or not raw_target_words:
        print("Error: No 'non_zero_eeprom' mapping found in model specification.")
        return False

    try:
        target_words = _validate_target_words(raw_target_words)
    except ValueError as exc:
        print(f"Error: Invalid model specification: {exc}")
        return False

    print(f"Loaded {len(target_words)} validated target register words from specification (0x0075 CRC excluded).")

    print(f"\nConnecting to {port} at 9600 baud...")
    conn = serial_io.JuraSerialConnection(port, baudrate=9600, timeout=1.0)
    try:
        if not getattr(conn, "is_open", False) and hasattr(conn, "open"):
            conn.open()

        # Verify machine type
        ty_resp = conn.query_ascii("TY:", timeout=1.0)
        print(f"Machine identification query (TY:): {ty_resp}")
        if not ty_resp or not ty_resp.lower().startswith("ty:"):
            print("Error: Machine did not reply to TY: identification.")
            return False

        hw_ef = ty_resp[3:].strip().split()[0].upper()
        spec_ef = str(model_spec.get("ef_code", "")).upper()
        if hw_ef and spec_ef and not hw_ef.startswith(spec_ef[:5]):
            print(f"ERROR: Hardware EF code '{hw_ef}' does not match specification '{spec_ef}'!")
            if non_interactive_confirm:
                return False
            resp = input("Proceed anyway despite EF mismatch? Type 'IGNORE MISMATCH' to continue: ")
            if resp.strip() != "IGNORE MISMATCH":
                return False

        # Check differences and snapshot current state for pre-write backup
        print("\nComparing current machine EEPROM against target specification...")
        mismatched: Dict[str, Tuple[str, str]] = {}
        current_snapshot: Dict[str, str] = {}
        for idx, (addr_str, exp_val) in enumerate(sorted(target_words.items())):
            curr = conn.query_ascii(f"RE:{addr_str}", timeout=0.8)
            curr_val = curr[3:].strip().upper() if curr and curr.lower().startswith("re:") else "ERR"
            current_snapshot[addr_str] = curr_val
            if curr_val != exp_val:
                mismatched[addr_str] = (curr_val, exp_val)
            if (idx + 1) % 25 == 0 or (idx + 1) == len(target_words):
                print(f"  Verified {idx + 1}/{len(target_words)} registers...", flush=True)

        print(f"Registers requiring update: {len(mismatched)} / {len(target_words)}", flush=True)
        if not mismatched:
            print("All target registers match hardware EEPROM! Nothing to write.")
            return True

        for addr_str, (curr_v, exp_v) in sorted(mismatched.items())[:15]:
            print(f"  0x{addr_str}: Current=0x{curr_v} -> Target=0x{exp_v}")
        if len(mismatched) > 15:
            print(f"  ... and {len(mismatched) - 15} more registers.")

        if dry_run:
            print("\n[Dry Run] No writes performed.")
            return True

        # Mandatory pre-write backup before mutating word 0
        backup_path = _save_prewrite_backup(hw_ef, current_snapshot, backup_dir=backup_dir)
        print(f"\nSaved pre-write EEPROM backup: {backup_path}")

        # Mandatory explicit confirmation before physical EEPROM write
        if not non_interactive_confirm:
            expected_phrase = f"RESTORE {hw_ef}"
            prompt = f"Type '{expected_phrase}' to write {len(mismatched)} words to physical EEPROM: "
            typed = input(prompt).strip()
            if typed != expected_phrase:
                print("Aborted by technician before writing any EEPROM words.")
                return False

        print(f"\nWriting {len(mismatched)} words to physical EEPROM (WE:<ADDR>,<VAL>)...")
        success_count = 0
        failed: List[str] = []
        t0 = time.time()

        for idx, (addr_str, (_curr_v, exp_v)) in enumerate(sorted(mismatched.items())):
            cmd = f"WE:{addr_str},{exp_v}"
            ans = conn.query_unsafe_lab_command(
                cmd,
                confirm_token=serial_io.LAB_WRITE_CONFIRM_TOKEN,
                timeout=1.2,
            )
            time.sleep(inter_write_delay)

            # Verification read-back
            verify_ans = conn.query_ascii(f"RE:{addr_str}", timeout=0.8)
            read_back = verify_ans[3:].strip().upper() if verify_ans and verify_ans.lower().startswith("re:") else ""

            if read_back == exp_v:
                success_count += 1
                if (idx + 1) % 10 == 0 or (idx + 1) == len(mismatched):
                    print(f"[{idx+1:02d}/{len(mismatched)}] Restored 0x{addr_str} = 0x{exp_v} (Verified OK)")
            else:
                print(f"ERROR on 0x{addr_str}: write='{ans}', read_back='{read_back}' != '{exp_v}'")
                failed.append(addr_str)

        elapsed = time.time() - t0
        print(f"\nWrite completed in {elapsed:.1f}s: {success_count}/{len(mismatched)} verified OK, {len(failed)} failed.")

        if failed or success_count != len(mismatched):
            print("\n[CRITICAL INTERLOCK] Partial EEPROM write failure detected!")
            print("ABORTING AN:0B CRC recalculation to avoid sealing a corrupted EEPROM image.")
            print(f"Failed addresses: {', '.join('0x' + a for a in failed)}")
            print(f"Restore pre-write backup using: {backup_path}")
            return False

        # Rebuild CRC strictly after 100% read-back verification succeeded
        print("\nAll words verified OK. Rebuilding internal EEPROM checksum via AN:0B...")
        crc_ans = conn.query_unsafe_lab_command(
            "AN:0B",
            confirm_token=serial_io.LAB_WRITE_CONFIRM_TOKEN,
            timeout=1.5,
        )
        print(f"AN:0B response: {crc_ans}")
        new_crc = conn.query_ascii("RE:0075", timeout=1.0)
        print(f"Recalculated CRC register (RE:0075): {new_crc}")
        return True
    finally:
        try:
            conn.close()
        except Exception:
            pass


if __name__ == "__main__":
    default_spec = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "docs",
        "models",
        "EF518M_IMPRESSA_XJ5_Professional_GII.json",
    )
    parser = argparse.ArgumentParser(description="Restore Jura EEPROM registers from JSON spec (defaults to read-only dry-run)")
    parser.add_argument("--port", default="/dev/ttyUSB0", help="Serial port (/dev/ttyUSB0)")
    parser.add_argument("--spec", default=default_spec, help="Path to model JSON")
    parser.add_argument("--dry-run", action="store_true", help="Simulate without writing (default)")
    parser.add_argument("--apply", action="store_true", help="Perform live EEPROM writes (requires --confirm-lab-write)")
    parser.add_argument("--confirm-lab-write", action="store_true", help="Explicitly confirm live bench EEPROM write authorization")
    args = parser.parse_args()

    is_dry_run = True if args.dry_run or not args.apply else False
    success = restore_eeprom(
        args.port,
        args.spec,
        dry_run=is_dry_run,
        confirm_lab_write=bool(args.confirm_lab_write),
    )
    sys.exit(0 if success else 1)
