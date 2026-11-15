#!/usr/bin/env bash
# ==============================================================================
# SPECTRA - Universal Hardware Telemetry & Logic Board Diagnostics - Launcher Script
# Appliance Diagnostics Engine (Jura Diagnostics Module)
# Supports modern Jura coffee machines (Generation 7+ & Smart Connect protocol)
# ==============================================================================

set -e
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_DIR"

# Automatically adopt uucp group if member in /etc/group but current session has not reloaded
if ! id -Gn | grep -qw "uucp" && getent group uucp 2>/dev/null | grep -qw "$USER"; then
    cmd="exec bash $(printf "%q" "$PROJECT_DIR/run.sh")"
    for arg in "$@"; do
        cmd+=" $(printf "%q" "$arg")"
    done
    exec newgrp uucp -c "$cmd"
fi

# Check if user requested legacy GTK GUI
if [[ "$*" == *"--legacy-gtk"* ]] || [[ "$*" == *"--gtk"* ]]; then
    exec python3 "$PROJECT_DIR/gui.py" "$@"
fi

# Check if user requested Vite dev hot-reload
if [[ "$*" == *"--dev"* ]]; then
    exec "$PROJECT_DIR/run_ui.sh" --dev
fi

# Check if user requested CLI mode or help
if [[ "$*" == *"--cli"* ]] || [[ "$*" == *"-h"* ]] || [[ "$*" == *"--help"* ]] || [[ "$*" == *"--list"* ]]; then
    exec python3 "$PROJECT_DIR/cli.py" "$@"
fi

# If specific arguments are passed that don't match web/app flags, pass them to cli.py
if [ $# -gt 0 ] && [[ "$*" != *"--app"* ]] && [[ "$*" != *"--ui"* ]] && [[ "$*" != *"--web"* ]] && [[ "$*" != *"--browser"* ]]; then
    exec python3 "$PROJECT_DIR/cli.py" "$@"
fi

# Check permissions for serial devices
if [ -e "/dev/ttyUSB0" ] && [ ! -r "/dev/ttyUSB0" ]; then
    echo "[!] Notice: /dev/ttyUSB0 exists but is not readable by $USER."
    echo "[!] To grant permanent permissions, run: sudo usermod -aG uucp $USER"
    echo "[!] Note: You must log out and log back in for usermod group changes to activate."
fi

# Launch Standalone Native Desktop App by default
exec python3 "$PROJECT_DIR/spectra_app.py" "$@"
