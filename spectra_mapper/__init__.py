"""SPECTRA Memory Mapper cohesive package."""

from spectra_mapper.models import (
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
)
from spectra_mapper.engine import (
    MemoryMapperEngine,
    HAS_RUST_CORE,
    _rust_core,
    SCRIPT_DIR,
)
from spectra_mapper.cli_runner import (
    ANSI,
    print_banner,
    run_cli,
    main,
)
from spectra_mapper.gtk_ui import HAS_GTK

if HAS_GTK:
    from spectra_mapper.gtk_ui import MemoryMapperWindow

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
