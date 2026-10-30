#!/usr/bin/env bash
# SPECTRA Next-Gen Telemetry & Logic Analyzer UI Testbed
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR/web"

MODE="${1:---dev}"

if [ "$MODE" = "--build" ] || [ ! -d "dist" ]; then
    echo "[*] Building production bundle..."
    npm run build
fi

if [ "$MODE" = "--preview" ] || [ "$MODE" = "--prod" ]; then
    echo "[*] Launching Production Preview at http://127.0.0.1:5173 ..."
    (sleep 1 && (xdg-open "http://127.0.0.1:5173" 2>/dev/null || true)) &
    exec npm run preview -- --host 127.0.0.1 --port 5173
else
    echo "[*] Launching SPECTRA Interactive UI Workspace at http://127.0.0.1:5173 ..."
    (sleep 1 && (xdg-open "http://127.0.0.1:5173" 2>/dev/null || true)) &
    exec npm run dev -- --host 127.0.0.1 --port 5173
fi
