#!/usr/bin/env bash
# SPECTRA Next-Gen Telemetry & Logic Analyzer UI Testbed
set -e

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_DIR"

# Automatically adopt uucp group if member in /etc/group but current session has not reloaded
if ! id -Gn | grep -qw "uucp" && getent group uucp 2>/dev/null | grep -qw "$USER"; then
    cmd="exec bash $(printf "%q" "$PROJECT_DIR/run_ui.sh")"
    for arg in "$@"; do
        cmd+=" $(printf "%q" "$arg")"
    done
    exec newgrp uucp -c "$cmd"
fi

MODE="${1:---app}"

# 1. Native Standalone Desktop App Mode (Default)
if [ "$MODE" = "--app" ] || [ -z "$1" ]; then
    cd "$PROJECT_DIR/web"
    if [ ! -d "dist" ]; then
        if command -v npm >/dev/null 2>&1 && [ -d "node_modules" ]; then
            echo "[*] Building production web assets..."
            npm run build || true
        fi
    fi
    cd "$PROJECT_DIR"
    echo "[*] Launching SPECTRA Standalone Native Desktop App..."
    exec python3 "$PROJECT_DIR/spectra_app.py" "$@"
fi

# 2. Browser Tab Production Mode
if [ "$MODE" = "--browser" ] || [ "$MODE" = "--prod" ] || [ "$MODE" = "--preview" ]; then
    cd "$PROJECT_DIR/web"
    if [ ! -d "dist" ]; then
        if command -v npm >/dev/null 2>&1 && [ -d "node_modules" ]; then
            echo "[*] Building production web assets..."
            npm run build || true
        fi
    fi
    cd "$PROJECT_DIR"
    echo "[*] Launching SPECTRA in browser mode..."
    exec python3 "$PROJECT_DIR/spectra_app.py" --browser
fi

# 3. Interactive Vite Dev Mode
# Start Python hardware API server on port 8080 in background if not already running
if ! ss -tulpn 2>/dev/null | grep -q ":8080 "; then
    echo "[*] Starting SPECTRA Hardware REST API Server on http://127.0.0.1:8080 ..."
    python3 "$PROJECT_DIR/web_server.py" &
    SERVER_PID=$!
    trap 'kill $SERVER_PID 2>/dev/null || true' EXIT
    sleep 0.8
fi

cd "$PROJECT_DIR/web"
if [ ! -d "node_modules" ]; then
    if command -v npm >/dev/null 2>&1; then
        echo "[*] Installing web dependencies for dev workspace..."
        npm install || true
    fi
fi

if [ ! -x "./node_modules/.bin/vite" ]; then
    echo "[!] Vite dev dependencies not available. Launching standalone app..."
    cd "$PROJECT_DIR"
    exec python3 "$PROJECT_DIR/spectra_app.py"
fi

echo "[*] Launching SPECTRA Interactive Dev Workspace at http://127.0.0.1:5173 ..."
(sleep 0.8 && (xdg-open "http://127.0.0.1:5173" 2>/dev/null || sensible-browser "http://127.0.0.1:5173" 2>/dev/null || true)) &
npm run dev -- --host 127.0.0.1 --port 5173
