#!/usr/bin/env python3
"""
SPECTRA — Developer Memory Mapper & Differential Logic Scope Tool
Backward-compatible facade & CLI entrypoint backed by the `spectra_mapper` package.
"""

from spectra_mapper import (
    STATUS_MAPPED,
    STATUS_THEORETICAL,
    STATUS_UNKNOWN,
    STATUS_BLANK,
    SAFE_READ_PREFIXES,
    FORBIDDEN_WRITE_COMMANDS,
    TWO_DIGIT_ADDRESS_EFS,
    UNIVERSAL_REGISTERS,
    THEORETICAL_REGISTERS,
    RegisterEntry,
    MemorySnapshot,
    MemoryMapperEngine,
    HAS_RUST_CORE,
    _rust_core,
    SCRIPT_DIR,
    ANSI,
    print_banner,
    run_cli,
    HAS_GTK,
    main,
)

if HAS_GTK:
    from spectra_mapper import MemoryMapperWindow

__all__ = [
    "STATUS_MAPPED",
    "STATUS_THEORETICAL",
    "STATUS_UNKNOWN",
    "STATUS_BLANK",
    "SAFE_READ_PREFIXES",
    "FORBIDDEN_WRITE_COMMANDS",
    "TWO_DIGIT_ADDRESS_EFS",
    "UNIVERSAL_REGISTERS",
    "THEORETICAL_REGISTERS",
    "RegisterEntry",
    "MemorySnapshot",
    "MemoryMapperEngine",
    "HAS_RUST_CORE",
    "_rust_core",
    "SCRIPT_DIR",
    "ANSI",
    "print_banner",
    "run_cli",
    "HAS_GTK",
    "main",
]
if HAS_GTK:
    __all__.append("MemoryMapperWindow")


if __name__ == "__main__":
    main()
