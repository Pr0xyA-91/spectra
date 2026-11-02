#!/usr/bin/env python3
"""
SPECTRA Diagnostics Suite — Centralized Build Metadata
Provides build-number-only branding (dropping semantic versions):
- __build__: Date-and-time build identifier (format: YYYYMMDD.HHMM, e.g. "20261102.1435")
- __version__: Build number representation (e.g. "Build 20261102.1435")
- BUILD_NUMBER / VERSION: Exported aliases for full cross-module compatibility
- __edition__: Branch / target platform designation
- Helper formatters and CLI bump utility
"""

import sys
import re
from datetime import datetime
from pathlib import Path

__build__ = "20261102.1605"
__version__ = f"Build {__build__}"
BUILD_NUMBER = __build__
VERSION = __version__
__edition__ = "Linux Multi-Manufacturer & Rust Hybrid"


def get_version_string(with_build: bool = True) -> str:
    """Return formatted version string using build number only: 'Build 20261102.1520'."""
    return f"Build {__build__}"


def get_full_title(app_name: str = "SPECTRA") -> str:
    """Return full application title including build number."""
    return f"{app_name} — {get_version_string(with_build=True)}"


def get_full_version() -> str:
    """Return full version string using build number only."""
    return f"Build {__build__}"


def update_build(new_build: str = None) -> str:
    """Update __build__ in this version.py file in-place."""
    if not new_build:
        new_build = datetime.now().strftime("%Y%m%d.%H%M")

    file_path = Path(__file__).resolve()
    content = file_path.read_text(encoding="utf-8")

    updated = re.sub(
        r'__build__\s*=\s*"[^"]*"',
        f'__build__ = "{new_build}"',
        content
    )
    file_path.write_text(updated, encoding="utf-8")
    return new_build


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] in ("--bump", "-b"):
        nb = update_build()
        print(f"[+] Updated SPECTRA build number to: {nb}")
    elif len(sys.argv) > 2 and sys.argv[1] in ("--set", "-s"):
        nb = update_build(sys.argv[2])
        print(f"[+] Set SPECTRA build number to: {nb}")
    else:
        print(f"SPECTRA {get_version_string(with_build=True)} [{__edition__}]")
