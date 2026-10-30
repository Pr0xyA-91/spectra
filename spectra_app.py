#!/usr/bin/env python3
"""
SPECTRA — Universal Hardware Telemetry & Logic Board Diagnostics
Main Application Dispatcher & Standalone Executable Entrypoint

Modes:
- Web Dashboard (Default when double-clicked with no CLI arguments):
  Spins up the zero-dependency telemetry server and automatically opens
  the default web browser (Edge, Chrome, Firefox) to http://127.0.0.1:8080.
- Command-Line Interface (CLI):
  Invoked when flags are passed (e.g. --port COM3, --demo, --sensors, --help).
"""

import sys
import os

# Enable per-monitor High-DPI awareness on Windows
if sys.platform.startswith("win"):
    try:
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            import ctypes
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


def main():
    args = sys.argv[1:]

    # Explicit web mode flag
    if "--web" in args or "--gui" in args:
        if "--web" in args:
            sys.argv.remove("--web")
        if "--gui" in args:
            sys.argv.remove("--gui")
        import web_server
        web_server.main(auto_open=True)
        return

    # If launched with no arguments (typical double-click on Windows), open Web Dashboard
    if not args:
        import web_server
        web_server.main(auto_open=True)
        return

    # Otherwise, pass through to CLI engine
    import cli
    cli.main()


if __name__ == "__main__":
    main()
