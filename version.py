#!/usr/bin/env python3
"""
SPECTRA Diagnostics Suite — Centralized Version and Build Metadata (Windows Edition)
Provides:
- __version__: Base semantic version (e.g. "0.5.1_win")
- __build__: Date-and-time build identifier (format: YYYYMMDD.HHMM, e.g. "20261029.1130")
- __edition__: Branch / target platform designation
- Helper formatters and CLI bump utility
"""

import sys
import re
from datetime import datetime
from pathlib import Path

__version__ = "0.5.1_win"
__build__ = "20261029.1130"
__edition__ = "Windows Edition"


def get_version_string(with_build: bool = True) -> str:
    """Return formatted version string: 'v0.5.1_win' or 'v0.5.1_win (build 20261029.1130)'."""
    if with_build and __build__:
        return f"v{__version__} (build {__build__})"
    return f"v{__version__}"


def bump_build(new_build: str = None) -> str:
    """
    Generate or set a new build number based on current UTC/local date-time (YYYYMMDD.HHMM).
    Updates this file in-place.
    """
    if not new_build:
        new_build = datetime.now().strftime("%Y%m%d.%H%M")

    version_file = Path(__file__).resolve()
    content = version_file.read_text(encoding="utf-8")
    updated = re.sub(r'__build__\s*=\s*"[^"]*"', f'__build__ = "{new_build}"', content)
    version_file.write_text(updated, encoding="utf-8")
    return new_build


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--bump":
        b = bump_build()
        print(f"Bumped build number to: {b}")
        print(f"Full version string: {get_version_string()}")
    elif len(sys.argv) > 2 and sys.argv[1] == "--set":
        b = bump_build(sys.argv[2])
        print(f"Set build number to: {b}")
    elif len(sys.argv) > 1 and sys.argv[1] in ("-v", "--version"):
        print(get_version_string())
    elif len(sys.argv) > 1 and sys.argv[1] == "--build":
        print(__build__)
    else:
        print(f"SPECTRA Version Metadata ({__edition__})")
        print(f"  Version: {__version__}")
        print(f"  Build:   {__build__}")
        print(f"  Full:    {get_version_string()}")
        print("\nUsage:")
        print("  python3 version.py --bump       # Bump build number to current date/time")
        print("  python3 version.py --version    # Print version string")
        print("  python3 version.py --build      # Print build number")
