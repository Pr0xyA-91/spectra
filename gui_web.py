#!/usr/bin/env python3
"""
SPECTRA — Universal Hardware Telemetry & Logic Board Diagnostics — Web Dashboard
Backward-compatible compatibility shim delegating HTTP serving to `web_server` / `spectra_web`.
"""

import os
import sys
from http.server import HTTPServer, ThreadingHTTPServer, BaseHTTPRequestHandler
from typing import Any, Dict, Optional

from version import __version__, __build__, __edition__
import web_server
from spectra_web import (
    SpectraApiHandler,
    SpectraThreadingHTTPServer,
    is_valid_port,
    find_free_port,
    bind_http_server,
    main,
    cleanup_resources,
)

SpectraWebHandler = SpectraApiHandler
WRATWebHandler = SpectraApiHandler


def get_resource_path(filename: str) -> str:
    """Resolve file path across dev, PyInstaller _MEIPASS, and frozen exe directories."""
    if hasattr(sys, "_MEIPASS"):
        bundled = os.path.join(sys._MEIPASS, filename)
        if os.path.exists(bundled):
            return bundled
    if getattr(sys, "frozen", False):
        adjacent = os.path.join(os.path.dirname(sys.executable), filename)
        if os.path.exists(adjacent):
            return adjacent
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), filename)


if __name__ == "__main__":
    main(auto_open=True)
