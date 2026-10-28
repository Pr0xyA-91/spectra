# SPECTRA — Architecture, Internals & Hardware Diagnostic Handbook
**Universal Hardware Telemetry, Real-Time Logic Board Diagnostics & Reverse-Engineering Suite for Jura Automatic Coffee Centers**

---

## Welcome to the SPECTRA Architecture Guide

This comprehensive handbook provides an in-depth, engineering-level explanation of how the SPECTRA diagnostics platform functions, how it communicates with Jura coffee machines, how each module operates, and why specific design decisions were made.

### Table of Contents

| Document | Key Topics Covered |
| :--- | :--- |
| **[1. System Architecture & Connection Overview](01_SYSTEM_OVERVIEW.md)** | End-to-end system block diagram, physical service interface, 4-pin pinout, Dual-MCU architecture (Main `EFxxxM` vs Display `EFxxxD` Sub-Bus), safety invariants. |
| **[2. Hardware Interfacing & Wire Protocols](02_HARDWARE_AND_PROTOCOLS.md)** | Optical transceiver timing, Top-Tronic 8-bit (2-digit hex) vs 16-bit (4-digit hex) addressing, ASCII command reference (`TY:`, `TY$:`, `RT:`, `RE:`, `HZ:`, `AS:`), detailed telemetry parsing, Smart Connect 4:1 wire carrier modulation and 4-step handshake. |
| **[3. Codebase Deep-Dive & Module Breakdown](03_CODEBASE_DEEP_DIVE.md)** | Exhaustive breakdown of every Python source file (`serial_io.py`, `jura_protocol.py`, `profiles_db.py`, `stats_collector.py`, `memory_mapper.py`, `gui.py`, `gui_widgets.py`, `cli.py`, `contrib/`), why each exists, and its key responsibilities. |
| **[4. Data Flows, State Machines & Pipelines](04_DATA_FLOWS_AND_STATE_MACHINES.md)** | The complete interrogation state machine, live telemetry event pipeline, optical bean sensor delta calculation, GS1 Serial & GTIN-14 check digit synthesis, Memory Mapper differential loop. |

---

## Quick Reference: Key Technical Conventions

### 1. Serial Port Communication Settings
* **Baud Rate**: `9600`
* **Data Bits**: `8`
* **Parity**: `None`
* **Stop Bits**: `1` (`8N1`)
* **Line Termination**: `\r\n` (CRLF)
* **Optical Inter-Frame Delay**: `30 ms` to `50 ms`

### 2. Addressing Formats
* **8-Bit Top-Tronic MCUs** (`address_width = 2`):
  - Max memory: 256 words (16 blocks: `RT:00` .. `RT:F0`).
  - Command syntax: `RE:xx` (e.g. `RE:30`, `RE:31`, `RE:32`).
  - Models: `EF642M`/`EF642D` (Z5 Gen II), `EF509M`, `EF511`, `EF527M` (C60/C65), `EF631D`, `EF632D`, `EF643D`, `EF644D`, `EPSILON`, `IOTA`, `UFO`.
* **16-Bit Top-Tronic MCUs** (`address_width = 4`):
  - Max memory: 512 words (32 blocks: `RT:0000` .. `RT:01F0`).
  - Command syntax: `RE:xxxx` (e.g. `RE:0030`, `RE:0031`, `RE:0032`).
  - Models: `EF518M` (XJ5), `EF520M`, `EF521M`, `EF523M`, `EF536M` (S8), `EF540M` (Z6), `EF708`.

### 3. Read-Only Safety Whitelist
* Allowed Commands: `TY:`, `TY$:`, `TL:`, `TL$:`, `CS$:`, `IC:`, `RT:`, `RE:`, `HZ:`, `AS:`, `@TR:`, `@TG:`, `@TF:`, `@T0`, `@T1`, `@t2:`
* Forbidden Commands: `WE:`, `WT:`, `DA:`, `FA:`, `@tw:`, `@TW:`
