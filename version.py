#!/usr/bin/env python3
"""
SPECTRA Diagnostics Suite — Centralized Version and Build Metadata
Provides:
- __version__: Base semantic version (e.g. "0.5.1")
- __build__: Date-and-time build identifier (format: YYYYMMDD.HHMM, e.g. "20261029.1130")
- __edition__: Branch / target platform designation
- Helper formatters and CLI bump utility
"""

import sys
import re
from datetime import datetime
from pathlib import Path

__version__ = "0.5.1"
__build__ = "20261029.1354"
__edition__ = "Main (Linux Jura)"


def get_version_string(with_build: bool = True) -> str:
    """Return formatted version string: 'v0.5.1' or 'v0.5.1 (build 20261029.1130)'."""
    if with_build and __build__:
        return f"v{__version__} (build {__build__})"
    return f"v{__version__}"


def get_full_title(app_name: str = "SPECTRA") -> str:
    """Return full application title including edition and build number."""
    return f"{app_name} — {get_version_string(with_build=True)}"


def update_build(new_build: str = None) -> str:
    """Update __build__ in this version.py file in-place."""
    if not new_build:
        new_build = datetime.now().strftime("%Y%m%d.%H%M")

    file_path = Path(__file__).resolve()
    content = file_path.read_text(encoding="utf-8")

    updated = re.sub(
        r'__build__\s*=\s*"[^"]*"',
        f'__build__ = "20261029.1354"',
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
