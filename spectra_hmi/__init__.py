"""SPECTRA Kalerm HMI Firmware & Translation Inspector cohesive package."""

from spectra_hmi.elf_tools import (
    DEFAULT_KALERM_DIR,
    ELF_MAGIC,
    HAS_CRYPTO,
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
)
from spectra_hmi.inspector import (
    KalermHmiInspector,
    prompt_file_browser,
    prompt_save_file_dialog,
)
from spectra_hmi.gtk_ui import HAS_GTK, launch_hmi_inspector_gui
from spectra_hmi.cli_runner import main

if HAS_GTK:
    from spectra_hmi.gtk_ui import HmiInspectorDialog
