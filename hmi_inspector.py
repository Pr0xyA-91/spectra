#!/usr/bin/env python3
"""
SPECTRA — Kalerm HMI Firmware & Translation Inspector / Auditor.
Backward-compatible facade & CLI entrypoint backed by the `spectra_hmi` package.
"""

import os
import sys

from spectra_hmi import (
    DEFAULT_KALERM_DIR,
    ELF_MAGIC,
    HAS_CRYPTO,
    HAS_GTK,
    HAS_RUST_CORE,
    _rust_core,
    __build__,
    __version__,
    DialogUnavailableError,
    ElfSegment,
    ElfSection,
    encode_arm_movw_movt,
    decode_arm_movw_movt,
    AutoGlossary,
    KalermHmiInspector,
    prompt_file_browser,
    prompt_save_file_dialog,
    launch_hmi_inspector_gui,
    main,
)

if HAS_GTK:
    from spectra_hmi import HmiInspectorDialog

__all__ = [
    "DEFAULT_KALERM_DIR",
    "ELF_MAGIC",
    "HAS_CRYPTO",
    "HAS_GTK",
    "HAS_RUST_CORE",
    "_rust_core",
    "__build__",
    "__version__",
    "DialogUnavailableError",
    "ElfSegment",
    "ElfSection",
    "encode_arm_movw_movt",
    "decode_arm_movw_movt",
    "AutoGlossary",
    "KalermHmiInspector",
    "prompt_file_browser",
    "prompt_save_file_dialog",
    "launch_hmi_inspector_gui",
    "main",
]
if HAS_GTK:
    __all__.append("HmiInspectorDialog")


if __name__ == "__main__":
    main()
