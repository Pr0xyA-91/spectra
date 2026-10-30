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

# Start Python hardware API server on port 8080 in background if not already running
if ! ss -tulpn | grep -q ":8080 "; then
    echo "[*] Starting SPECTRA Hardware REST API Server on http://127.0.0.1:8080 ..."
    python3 "$PROJECT_DIR/web_server.py" &
    SERVER_PID=$!
    trap 'kill $SERVER_PID 2>/dev/null || true' EXIT
    sleep 0.8
fi

cd "$PROJECT_DIR/web"
MODE="${1:---dev}"

if [ "$MODE" = "--build" ] || [ ! -d "dist" ]; then
    echo "[*] Building production bundle..."
    npm run build
fi

if [ "$MODE" = "--prod" ] || [ "$MODE" = "--preview" ]; then
    echo "[*] Launching Production Interface at http://127.0.0.1:8080 ..."
    (sleep 1 && (xdg-open "http://127.0.0.1:8080" 2>/dev/null || true)) &
    wait $SERVER_PID
else
    echo "[*] Launching SPECTRA Interactive Dev Workspace at http://127.0.0.1:5173 ..."
    (sleep 1 && (xdg-open "http://127.0.0.1:5173" 2>/dev/null || true)) &
    exec npm run dev -- --host 127.0.0.1 --port 5173
fi
