#!/usr/bin/env python3
"""
SPECTRA — Machine EEPROM Restoration Utility
Restores non-volatile registers and counters from docs/models/<EF>_*.json
with individual word verification and automated CRC recalculation (AN:0B).
"""

import sys
import os
import time
import json
import argparse
from typing import Dict, List, Tuple

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import serial_io
import stats_collector


def restore_eeprom(port: str, json_path: str, dry_run: bool = False, inter_write_delay: float = 0.04) -> bool:
    print(f"=== SPECTRA EEPROM Restoration Tool ===")
    print(f"Target Port:      {port}")
    print(f"Model Spec:       {json_path}")
    print(f"Dry Run Mode:     {'YES (Read-only simulation)' if dry_run else 'NO (Live EEPROM Write)'}")

    if not os.path.exists(json_path):
        print(f"Error: Model file '{json_path}' not found.")
        return False

    with open(json_path, "r", encoding="utf-8") as f:
        model_spec = json.load(f)

    target_words: Dict[str, str] = dict(model_spec.get("non_zero_eeprom", {}))
    if not target_words:
        print("Error: No 'non_zero_eeprom' mapping found in model specification.")
        return False

    print(f"Loaded {len(target_words)} target register words from specification.")

    print(f"\nConnecting to {port} at 9600 baud...")
    conn = serial_io.JuraSerialConnection(port, baudrate=9600, timeout=1.0)

    # Verify machine type
    ty_resp = conn.query_ascii("TY:", timeout=1.0)
    print(f"Machine identification query (TY:): {ty_resp}")
    if not ty_resp or not ty_resp.lower().startswith("ty:"):
        print("Error: Machine did not reply to TY: identification.")
        conn.close()
        return False

    hw_ef = ty_resp[3:].strip().split()[0].upper()
    spec_ef = model_spec.get("ef_code", "").upper()
    if hw_ef and spec_ef and not hw_ef.startswith(spec_ef[:5]):
        print(f"Warning: Hardware EF code '{hw_ef}' does not match specification '{spec_ef}'!")
        resp = input("Proceed anyway? (y/N): ")
        if resp.strip().lower() != "y":
            conn.close()
            return False

    # Check differences
    print("\nComparing current machine EEPROM against target specification...")
    mismatched: Dict[str, Tuple[str, str]] = {}
    for idx, (addr_str, exp_val) in enumerate(sorted(target_words.items())):
        curr = conn.query_ascii(f"RE:{addr_str}", timeout=0.8)
        curr_val = curr[3:].strip().upper() if curr and curr.startswith("re:") else "ERR"
        if curr_val != exp_val.upper():
            mismatched[addr_str] = (curr_val, exp_val.upper())
        if (idx + 1) % 25 == 0 or (idx + 1) == len(target_words):
            print(f"  Verified {idx + 1}/{len(target_words)} registers...", flush=True)

    print(f"Registers requiring update: {len(mismatched)} / {len(target_words)}", flush=True)
    if not mismatched:
        print("All target registers match hardware EEPROM! Nothing to write.")
        conn.close()
        return True

    for addr_str, (curr_v, exp_v) in sorted(mismatched.items())[:15]:
        print(f"  0x{addr_str}: Current=0x{curr_v} -> Target=0x{exp_v}")
    if len(mismatched) > 15:
        print(f"  ... and {len(mismatched) - 15} more registers.")

    if dry_run:
        print("\n[Dry Run] No writes performed.")
        conn.close()
        return True

    print(f"\nWriting {len(mismatched)} words to physical EEPROM (WE:<ADDR>,<VAL>)...")
    success_count = 0
    failed: List[str] = []
    t0 = time.time()

    for idx, (addr_str, (curr_v, exp_v)) in enumerate(sorted(mismatched.items())):
        cmd = f"WE:{addr_str},{exp_v}"
        ans = conn.query_ascii(cmd, timeout=1.2)
        time.sleep(inter_write_delay)

        # Verification read-back
        verify_ans = conn.query_ascii(f"RE:{addr_str}", timeout=0.8)
        read_back = verify_ans[3:].strip().upper() if verify_ans and verify_ans.startswith("re:") else ""

        if read_back == exp_v:
            success_count += 1
            if (idx + 1) % 10 == 0 or (idx + 1) == len(mismatched):
                print(f"[{idx+1:02d}/{len(mismatched)}] Restored 0x{addr_str} = 0x{exp_v} (Verified OK)")
        else:
            print(f"ERROR on 0x{addr_str}: write='{ans}', read_back='{read_back}' != '{exp_v}'")
            failed.append(addr_str)

    elapsed = time.time() - t0
    print(f"\nWrite completed in {elapsed:.1f}s: {success_count}/{len(mismatched)} verified OK, {len(failed)} failed.")

    # Rebuild CRC
    print("\nRebuilding internal EEPROM checksum via AN:0B...")
    crc_ans = conn.query_ascii("AN:0B", timeout=1.5)
    print(f"AN:0B response: {crc_ans}")
    new_crc = conn.query_ascii("RE:0075", timeout=1.0)
    print(f"Recalculated CRC register (RE:0075): {new_crc}")

    conn.close()
    return len(failed) == 0


if __name__ == "__main__":
    default_spec = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "docs",
        "models",
        "EF518M_IMPRESSA_XJ5_Professional_GII.json",
    )
    parser = argparse.ArgumentParser(description="Restore Jura EEPROM registers from JSON spec")
    parser.add_argument("--port", default="/dev/ttyUSB0", help="Serial port (/dev/ttyUSB0)")
    parser.add_argument("--spec", default=default_spec, help="Path to model JSON")
    parser.add_argument("--dry-run", action="store_true", help="Simulate without writing")
    args = parser.parse_args()

    success = restore_eeprom(args.port, args.spec, dry_run=args.dry_run)
    sys.exit(0 if success else 1)
