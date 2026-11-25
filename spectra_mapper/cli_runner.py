#!/usr/bin/env python3
"""SPECTRA Memory Mapper interactive terminal CLI and entrypoint."""

import sys
import time
import datetime
import argparse
from typing import Optional

import serial_io

try:
    from version import __version__, __build__
except ImportError:
    __build__ = "20261112.1820"
    __version__ = f"Build {__build__}"

from spectra_mapper.models import (
    STATUS_MAPPED,
    STATUS_THEORETICAL,
    STATUS_UNKNOWN,
    STATUS_BLANK,
    RegisterEntry,
)
from spectra_mapper.engine import MemoryMapperEngine
from spectra_mapper.gtk_ui import HAS_GTK

if HAS_GTK:
    from spectra_mapper.gtk_ui import Gtk, MemoryMapperWindow

# ============================================================================
# Terminal ANSI Color & Formatting Utilities
# ============================================================================

class ANSI:
    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    UNDERLINE = "\033[4m"

    GREEN = "\033[92m"
    ORANGE = "\033[38;5;214m"
    RED = "\033[91m"
    GRAY = "\033[90m"
    CYAN = "\033[96m"
    YELLOW = "\033[93m"
    WHITE = "\033[97m"

    BG_DARK = "\033[48;5;235m"
    BG_GREEN = "\033[48;5;22m"
    BG_ORANGE = "\033[48;5;130m"
    BG_RED = "\033[48;5;52m"

    @classmethod
    def badge(cls, status: str) -> str:
        if status == STATUS_MAPPED:
            return f"{cls.GREEN}● MAPPED     {cls.RESET}"
        elif status == STATUS_THEORETICAL:
            return f"{cls.ORANGE}▲ THEORETICAL{cls.RESET}"
        elif status == STATUS_UNKNOWN:
            return f"{cls.RED}■ UNKNOWN    {cls.RESET}"
        else:
            return f"{cls.GRAY}○ BLANK      {cls.RESET}"


def print_banner():
    banner = f"""{ANSI.BOLD}{ANSI.CYAN}
================================================================================
       SPECTRA — Developer Memory Mapper & Differential Logic Scope
                               (Build {__build__})
================================================================================{ANSI.RESET}"""
    print(banner)


# ============================================================================
# Terminal Interactive CLI
# ============================================================================

def run_cli(engine: MemoryMapperEngine, initial_sweep: bool = True):
    """Interactive command-line logic scope and memory mapping REPL."""
    print_banner()
    print(f"[*] Connected Appliance: {ANSI.BOLD}{engine.model_family} ({engine.ef_code}){ANSI.RESET}")
    print(f"[*] Specification File:  {ANSI.DIM}{engine.spec_file_path or 'Draft'}{ANSI.RESET}")

    if initial_sweep:
        print("[*] Performing initial 512-word EEPROM sweep...")
        engine.sweep_eeprom(lambda cur, tot, msg: sys.stdout.write(f"\r    [{'=' * cur}{' ' * (tot - cur)}] {cur}/{tot} {msg}"))
        print("\n[*] Initial sweep complete! Baseline captured.")
        engine.capture_baseline()

    stats = engine.get_summary_stats()
    print(f"[*] Coverage: {ANSI.GREEN}🟢 {stats['mapped']} Mapped{ANSI.RESET} | "
          f"{ANSI.ORANGE}🟠 {stats['theoretical']} Theoretical{ANSI.RESET} | "
          f"{ANSI.RED}🔴 {stats['unknown']} Unknown{ANSI.RESET} | "
          f"{ANSI.GRAY}⚪ {stats['blank']} Blank{ANSI.RESET} ({stats['coverage_pct']}%)")
    print(f"[*] Type {ANSI.CYAN}'help'{ANSI.RESET} or {ANSI.CYAN}'?'{ANSI.RESET} for commands.\n")

    prompt = f"{ANSI.BOLD}spectra-mapper> {ANSI.RESET}"
    while True:
        try:
            line = input(prompt).strip()
        except (EOFError, KeyboardInterrupt):
            print("\nExiting Memory Mapper.")
            break

        if not line:
            continue

        parts = line.split()
        cmd = parts[0].lower()
        args = parts[1:]

        if cmd in ("exit", "quit", "q"):
            print("Exiting Memory Mapper.")
            break

        elif cmd in ("help", "?"):
            print(f"""
{ANSI.BOLD}Available Commands:{ANSI.RESET}
  {ANSI.CYAN}read / sweep{ANSI.RESET}              Perform full 512-word sweep from machine
  {ANSI.CYAN}baseline{ANSI.RESET}                  Capture current snapshot as baseline
  {ANSI.CYAN}diff / delta{ANSI.RESET}              Show registers changed since baseline
  {ANSI.CYAN}watch [sec]{ANSI.RESET}               Continuous differential watch loop (default: 1.5s)
  {ANSI.CYAN}list [filter]{ANSI.RESET}             Display registers: all, mapped, theoretical, unknown, blank, diff
  {ANSI.CYAN}inspect <addr>{ANSI.RESET}            Inspect word in hex, dec, ASCII, and 16-bit binary
  {ANSI.CYAN}map <addr> <name> <desc>{ANSI.RESET} Map register and persist to docs/models/<EF>_*.json
  {ANSI.CYAN}stats{ANSI.RESET}                     Display coverage metrics and health scorecards
  {ANSI.CYAN}sim <addr> <hex_val>{ANSI.RESET}      Simulate EEPROM register change (Demo mode only)
  {ANSI.CYAN}help / ?{ANSI.RESET}                  Display this reference
  {ANSI.CYAN}quit / exit{ANSI.RESET}               Exit the tool
""")

        elif cmd in ("read", "sweep"):
            print("[*] Sweeping 512 EEPROM registers...")
            engine.sweep_eeprom(lambda cur, tot, msg: sys.stdout.write(f"\r    [{'=' * cur}{' ' * (tot - cur)}] {cur}/{tot} {msg}"))
            print("\n[+] Sweep complete.")
            diff_res = engine.compute_diff()
            if diff_res["total_changed_words"] > 0:
                print(f"[*] {ANSI.YELLOW}⚡ {diff_res['total_changed_words']} word(s) modified since baseline! Run 'diff' to inspect.{ANSI.RESET}")
            else:
                print("[*] No changes detected relative to baseline.")

        elif cmd == "baseline":
            engine.capture_baseline()
            print(f"[+] Baseline captured successfully ({len(engine.current_eeprom)} words recorded).")

        elif cmd in ("diff", "delta"):
            diff_res = engine.compute_diff()
            changed = diff_res["changed_registers"]
            if not changed:
                print(f"{ANSI.GREEN}✓ No changes detected since baseline.{ANSI.RESET}")
            else:
                print(f"\n{ANSI.BOLD}{ANSI.YELLOW}⚡ {len(changed)} Register(s) Changed ({diff_res['total_bit_flips']} bits flipped):{ANSI.RESET}")
                print(f"{ANSI.BOLD}ADDR   HEX     BASE    DELTA   STATUS        NAME                     BITS FLIPPED{ANSI.RESET}")
                print("-" * 80)
                for r in changed:
                    delta_str = f"{r.delta:+d}"
                    bits_str = ", ".join(f"b{b}" for b in r.bits_flipped)
                    print(f"0x{r.hex_addr} 0x{r.val:04X}  0x{r.baseline_val:04X}  {delta_str:<6} "
                          f"{ANSI.badge(r.status)} {r.name:<24} {bits_str}")
                print()

        elif cmd == "watch":
            interval = 1.5
            if args:
                try:
                    interval = float(args[0])
                except ValueError:
                    pass
            print(f"[*] Entering live differential scope watch mode ({interval}s interval)... Press Ctrl+C to stop.")
            try:
                sweep_count = 0
                while True:
                    time.sleep(interval)
                    sweep_count += 1
                    engine.sweep_eeprom()
                    diff_res = engine.compute_diff()
                    changed = diff_res["changed_registers"]
                    timestamp = datetime.datetime.now().strftime("%H:%M:%S")
                    if changed:
                        print(f"\n[{timestamp}] {ANSI.YELLOW}⚡ CHANGE DETECTED (Sweep #{sweep_count}):{ANSI.RESET}")
                        for r in changed:
                            bits_str = ", ".join(f"b{b}" for b in r.bits_flipped)
                            print(f"    - 0x{r.hex_addr} ({r.name}): 0x{r.baseline_val:04X} -> {ANSI.BOLD}0x{r.val:04X}{ANSI.RESET} "
                                  f"({r.delta:+d}) [Flipped: {bits_str}]")
                    else:
                        sys.stdout.write(f"\r[{timestamp}] Sweep #{sweep_count} OK (No changes)   ")
                        sys.stdout.flush()
            except KeyboardInterrupt:
                print("\n[*] Live watch stopped.")

        elif cmd in ("list", "show"):
            flt = args[0].lower() if args else "all"
            entries = engine.classified_registers or engine.classify_all()

            if flt == "mapped":
                filtered = [r for r in entries if r.status == STATUS_MAPPED]
            elif flt in ("theoretical", "theor"):
                filtered = [r for r in entries if r.status == STATUS_THEORETICAL]
            elif flt in ("unknown", "unmapped"):
                filtered = [r for r in entries if r.status == STATUS_UNKNOWN]
            elif flt == "blank":
                filtered = [r for r in entries if r.status == STATUS_BLANK]
            elif flt in ("diff", "changed"):
                filtered = [r for r in entries if r.is_changed]
            elif flt in ("nonzero", "active"):
                filtered = [r for r in entries if r.val != 0]
            else:
                filtered = entries

            print(f"\n{ANSI.BOLD}ADDR   HEX    DEC    STATUS        NAME                     DESCRIPTION{ANSI.RESET}")
            print("-" * 88)
            for r in filtered:
                print(f"0x{r.hex_addr} {r.val:04X}  {r.val:5d}  {ANSI.badge(r.status)} {r.name:<24} {r.desc[:34]}")
            print(f"Total shown: {len(filtered)} registers.\n")

        elif cmd == "inspect":
            if not args:
                print("Usage: inspect <hex_address> (e.g., inspect 0040)")
                continue
            try:
                addr = int(args[0], 16)
            except ValueError:
                print(f"Invalid hexadecimal address: '{args[0]}'")
                continue

            if not (0 <= addr < engine.max_words):
                print(f"Address out of range (0x0000..0x{engine.max_words - 1:04X}): 0x{addr:04X}")
                continue

            entries = {r.addr: r for r in (engine.classified_registers or engine.classify_all())}
            r = entries.get(addr)
            if not r:
                val = engine.current_eeprom.get(addr, 0)
                r = RegisterEntry(addr, val, STATUS_UNKNOWN, f"Unmapped_0x{addr:04X}", "")

            # Binary representation breakdown
            bin_str = f"{r.val:016b}"
            grouped_bin = f"{bin_str[0:4]} {bin_str[4:8]} {bin_str[8:12]} {bin_str[12:16]}"

            print(f"\n{ANSI.BOLD}=== Register 0x{r.hex_addr} Inspection ==={ANSI.RESET}")
            print(f"  Name:        {ANSI.BOLD}{r.name}{ANSI.RESET}")
            print(f"  Status:      {ANSI.badge(r.status)}")
            print(f"  Description: {r.desc}")
            print(f"  Category:    {r.category} (Unit: {r.unit or 'N/A'})")
            print(f"  Value Hex:   0x{r.val:04X}")
            print(f"  Value Dec:   {r.val} (Signed: {r.signed_val})")
            print(f"  High Byte:   0x{r.high_byte:02X} ({r.high_byte}) | Low Byte: 0x{r.low_byte:02X} ({r.low_byte})")
            print(f"  ASCII:       '{r.ascii_repr}'")
            print(f"  Binary (16): {ANSI.CYAN}{grouped_bin}{ANSI.RESET} (b15 .. b0)")

            # Visual Bitfield breakdown
            bits_header = "  Bits:        "
            bits_row =    "               "
            for b in range(15, -1, -1):
                bit_val = (r.val >> b) & 1
                flipped = b in r.bits_flipped
                col = ANSI.YELLOW if flipped else (ANSI.GREEN if bit_val else ANSI.GRAY)
                bits_row += f"{col}{bit_val}{ANSI.RESET} "
                bits_header += f"{b:2d} "
            print(bits_header)
            print(bits_row)

            if r.is_changed:
                print(f"  {ANSI.YELLOW}⚡ Changed from baseline (0x{r.baseline_val:04X}): Delta {r.delta:+d}{ANSI.RESET}")
            print()

        elif cmd == "map":
            if len(args) < 3:
                print("Usage: map <addr_hex> <name> <description> [category] [unit]")
                continue
            try:
                addr = int(args[0], 16)
            except ValueError:
                print(f"Invalid address: '{args[0]}'")
                continue

            name = args[1]
            desc = args[2]
            cat = args[3] if len(args) > 3 else "settings"
            unit = args[4] if len(args) > 4 else ""

            ok, msg = engine.map_register(addr, name, desc, category=cat, unit=unit)
            if ok:
                print(f"{ANSI.GREEN}✓ {msg}{ANSI.RESET}")
            else:
                print(f"{ANSI.RED}✗ Error: {msg}{ANSI.RESET}")

        elif cmd == "stats":
            stats = engine.get_summary_stats()
            print(f"\n{ANSI.BOLD}Specification Coverage Metrics:{ANSI.RESET}")
            print(f"  Model Family:     {engine.model_family} ({engine.ef_code})")
            print(f"  Total EEPROM:     {stats['total_words']} words (1,024 bytes)")
            print(f"  Active Non-Zero:  {stats['nonzero']} words")
            print(f"  🟢 Mapped:        {stats['mapped']} words")
            print(f"  🟠 Theoretical:   {stats['theoretical']} words")
            print(f"  🔴 Unknown:       {stats['unknown']} words")
            print(f"  ⚪ Blank (0x0000):{stats['blank']} words")
            print(f"  Coverage:         {ANSI.BOLD}{ANSI.GREEN}{stats['coverage_pct']}%{ANSI.RESET} of active registers documented\n")

        elif cmd == "sim":
            if not engine.conn.is_demo:
                print("The 'sim' command is only available when connected to a DEMO / SIMULATION port.")
                continue
            if len(args) < 2:
                print("Usage: sim <addr_hex> <val_hex> (e.g. sim 0014 0004)")
                continue
            try:
                addr = int(args[0], 16)
                val = int(args[1], 16)
            except ValueError:
                print("Invalid hex address or value.")
                continue

            engine.conn.set_mock_eeprom_word(addr, val)
            print(f"[+] Simulated EEPROM update: 0x{addr:04X} := 0x{val:04X}. Run 'read' or 'diff' to see change.")

        else:
            print(f"Unknown command: '{cmd}'. Type 'help' for available commands.")



# ============================================================================
# Main Entry Point
# ============================================================================

def main():
    parser = argparse.ArgumentParser(description="SPECTRA Developer Memory Mapper & Differential Scope Tool")
    parser.add_argument("--port", type=str, default="", help="Serial port or simulation profile (e.g. /dev/ttyUSB0)")
    parser.add_argument("--cli", action="store_true", help="Launch interactive terminal CLI mode")
    parser.add_argument("--gui", action="store_true", help="Launch graphical GTK3 interface")
    parser.add_argument("--diff", action="store_true", help="Capture baseline and watch for differential changes")
    parser.add_argument("--watch", type=float, nargs="?", const=1.5, help="Continuous watch loop with interval in seconds")
    parser.add_argument("--demo", action="store_true", help="Force DEMO / SIMULATION mode")

    args = parser.parse_args()

    port = args.port
    if args.demo and not port:
        port = "DEMO / SIMULATION (Jura Impressa XJ5)"

    # If no port specified, scan or pick demo
    if not port:
        available_ports = serial_io.list_serial_ports()
        if available_ports:
            port = available_ports[0]
        else:
            port = "DEMO / SIMULATION (Jura Impressa XJ5)"

    # Determine mode: default to GUI if GTK is available and CLI not explicitly requested
    launch_gui = args.gui or (HAS_GTK and not (args.cli or args.diff or args.watch is not None))

    if launch_gui and HAS_GTK:
        app = MemoryMapperWindow(initial_port=port)
        app.connect("destroy", Gtk.main_quit)
        app.show_all()
        Gtk.main()
    else:
        conn = serial_io.JuraSerialConnection(port)
        engine = MemoryMapperEngine(conn)
        if args.watch is not None:
            engine.sweep_eeprom()
            engine.capture_baseline()
            # Directly run watch
            run_cli(engine, initial_sweep=False)
        else:
            run_cli(engine, initial_sweep=True)

