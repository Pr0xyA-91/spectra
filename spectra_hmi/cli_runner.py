#!/usr/bin/env python3
"""SPECTRA HMI Inspector standalone CLI entrypoint."""

import sys

from spectra_hmi.elf_tools import DEFAULT_KALERM_DIR, __build__
from spectra_hmi.inspector import KalermHmiInspector
from spectra_hmi.gtk_ui import HAS_GTK, launch_hmi_inspector_gui

def main():
    import argparse

    parser = argparse.ArgumentParser(
        description=f"SPECTRA Kalerm HMI Firmware & Translation Auditor (Build {__build__})"
    )
    parser.add_argument("path", nargs="?", default=DEFAULT_KALERM_DIR, help="Path to ELF binary or update folder")
    parser.add_argument("--gui", action="store_true", help="Launch GTK3 visual inspector dialog")
    parser.add_argument("--audit", action="store_true", help="Run automated safety and localization audit")
    parser.add_argument("--search", metavar="QUERY", help="Search strings/keys in firmware")
    parser.add_argument("--lang", default="cs-CZ", help="Locale for search (default: cs-CZ)")
    parser.add_argument("--patch", nargs="?", const="", metavar="OUT_PATH", help="Create patched lab binary")
    parser.add_argument("--export-report", metavar="REPORT_PATH", help="Export Markdown/HTML/PDF audit report")

    args = parser.parse_args()

    if args.gui:
        if not HAS_GTK:
            print("[-] GTK3 is not available. Please run in CLI mode.")
            sys.exit(1)
        launch_hmi_inspector_gui(initial_path=args.path)
        sys.exit(0)

    try:
        inspector = KalermHmiInspector(args.path)
    except Exception as e:
        print(f"[-] ERROR initializing inspector for {args.path}: {e}")
        sys.exit(1)

    sig = inspector.verify_signature()
    print(f"[*] Target Binary: {inspector.binary_path}")
    print(f"[*] Binary Size:   {inspector.file_size:,} bytes")
    print(f"[*] SHA-256:       {sig['sha256']}")
    print(f"[*] Signature:     {sig['status_label']}")
    if sig["warning"]:
        print(f"    Notice: {sig['warning']}")

    if args.search:
        print(f"\n[*] Searching for '{args.search}' in locale {args.lang}...")
        langs = inspector.extract_all_languages()
        lang_data = langs.get(args.lang) or inspector.extract_language(args.lang)
        if not lang_data:
            print(f"[-] Locale {args.lang} not found. Available: {', '.join(langs.keys())}")
            sys.exit(1)

        matches = 0
        q = args.search.lower()
        for k, p in lang_data["phrases"].items():
            if q in k.lower() or q in p["val"].lower():
                matches += 1
                print(f"[{p['index']:3d}] Key: {k}")
                print(f"      Value:     {repr(p['val'])}")
                print(f"      Value VMA: 0x{p['val_vma']:08x} (file offset: 0x{p['val_file_off']:08x})")
                print(f"      Slot file: 0x{p['slot_file_off']:08x}")
                print("-" * 60)
        print(f"[*] Total matches found: {matches}")

    if args.audit or (not args.search and not args.patch and not args.export_report):
        print("\n" + "=" * 78)
        print("SPECTRA AUTOMATED FIRMWARE & LOCALIZATION AUDIT FINDINGS")
        print("=" * 78)
        findings = inspector.run_audit()
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

    if args.patch is not None:
        out_p = args.patch if args.patch else None
        print("\n[*] Applying safety and localization fixes to binary...")
        res = inspector.apply_patches(out_p)
        print(f"[+] Patched binary successfully created: {res['output_path']}")
        print(f"[+] Patched SHA-256: {res['sha256']}")
        print(f"[+] Applied {len(res['patches_applied'])} patch operations.")

    if args.export_report:
        print(f"\n[*] Exporting audit report to {args.export_report}...")
        saved = inspector.export_bug_report(args.export_report)
        print(f"[+] Report exported successfully to: {saved}")

