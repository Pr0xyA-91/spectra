#!/usr/bin/env python3
"""Unified KalermHmiInspector class composed from cohesive domain mixins."""

import subprocess
import threading
from typing import Dict, Optional, Any

from spectra_hmi.elf_tools import DialogUnavailableError, HmiElfMixin
from spectra_hmi.audit import HmiAuditMixin
from spectra_hmi.patcher import HmiPatcherMixin
from spectra_hmi.reporting import HmiReportingMixin
from spectra_hmi.dialogs import HmiDialogsMixin
from spectra_hmi.ollama_service import HmiOllamaMixin
from spectra_hmi.semantic_audit import HmiSemanticAuditMixin


class KalermHmiInspector(
    HmiElfMixin,
    HmiAuditMixin,
    HmiPatcherMixin,
    HmiReportingMixin,
    HmiDialogsMixin,
    HmiOllamaMixin,
    HmiSemanticAuditMixin,
):
    """
    Headless Engine for inspecting, auditing, and patching Kalerm Linux HMI binaries.
    """

    DialogUnavailableError = DialogUnavailableError
    _ollama_process: Optional[subprocess.Popen] = None
    _download_lock: threading.Lock = threading.Lock()
    _download_state: Dict[str, Any] = {
        "active": False,
        "status": "IDLE",  # IDLE | INSTALLING_ENGINE | STARTING_ENGINE | PULLING_MODEL | VERIFYING | COMPLETED | ERROR | CANCELLED
        "model": "",
        "phase_label": "",
        "status_text": "",
        "completed_bytes": 0,
        "total_bytes": 0,
        "percent": 0.0,
        "speed_mbps": 0.0,
        "eta_sec": 0,
        "error": "",
        "cancel_requested": False,
    }

    _semantic_progress_lock: threading.Lock = threading.Lock()
    _semantic_progress: Dict[str, Any] = {
        "active": False,
        "status": "IDLE",  # IDLE | TIER1 | TIER2 | TIER3_STARTUP | TIER3_INFERENCE | COMPLETED | ERROR
        "percent": 0.0,
        "current": 0,
        "total": 0,
        "phase_label": "",
        "detail_text": "",
        "model": "",
        "started_at": 0.0,
        "elapsed_sec": 0.0,
        "eta_sec": 0,
    }



prompt_file_browser = KalermHmiInspector.prompt_file_browser
prompt_save_file_dialog = KalermHmiInspector.prompt_save_file_dialog
