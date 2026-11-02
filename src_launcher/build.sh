#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
ZIG_BIN="${ZIG_BIN:-$HOME/.local/share/mise/installs/zig/0.14.1/bin/zig}"

if ! command -v "$ZIG_BIN" &>/dev/null && ! command -v zig &>/dev/null; then
    echo "[-] Error: zig compiler not found."
    exit 1
fi

if ! command -v llvm-rc &>/dev/null; then
    echo "[-] Error: llvm-rc resource compiler not found."
    exit 1
fi

ZIG_CMD="$(command -v "$ZIG_BIN" 2>/dev/null || command -v zig)"

# Extract build number from version.py
BUILD_NUMBER="$(python3 -c "import sys; sys.path.insert(0, '$ROOT_DIR'); from version import __build__; print(__build__)")"
echo "[*] Building SPECTRA Windows Suite for Build: $BUILD_NUMBER"

# Check or download python embeddable package
if [ ! -d /tmp/pyembed ] || [ ! -f /tmp/pyembed/python.exe ]; then
    echo "[*] Downloading Python 3.12 64-bit embeddable runtime..."
    mkdir -p /tmp/pyembed
    curl -sSL https://www.python.org/ftp/python/3.12.7/python-3.12.7-embed-amd64.zip -o /tmp/pyembed/pyembed.zip
    unzip -q -o /tmp/pyembed/pyembed.zip -d /tmp/pyembed/
    curl -sSL https://files.pythonhosted.org/packages/07/bc/587a445451b253b285629263eb51c2d8e9bcea4fc97826266d186f96f558/pyserial-3.5-py2.py3-none-any.whl -o /tmp/pyembed/pyserial.whl
    unzip -q -o /tmp/pyembed/pyserial.whl -d /tmp/pyembed/
fi

# 1. Assemble Application-Only Payload (for fast updater)
echo "[*] Assembling lightweight update bundle in /tmp/update_bundle..."
rm -rf /tmp/update_bundle /tmp/update_bundle.zip
mkdir -p /tmp/update_bundle

cp "$ROOT_DIR"/*.py /tmp/update_bundle/
cp "$ROOT_DIR"/profiles_data.json /tmp/update_bundle/
cp "$ROOT_DIR"/icon.ico /tmp/update_bundle/
mkdir -p /tmp/update_bundle/docs
cp -r "$ROOT_DIR"/docs/models /tmp/update_bundle/docs/
mkdir -p /tmp/update_bundle/web
cp -r "$ROOT_DIR"/web/dist /tmp/update_bundle/web/
if [ -d "$ROOT_DIR"/drivers ]; then
    cp -r "$ROOT_DIR"/drivers /tmp/update_bundle/
fi

(cd /tmp/update_bundle && zip -q -r /tmp/update_bundle.zip .)

# 2. Assemble Full Standalone Bundle (Runtime + PySerial + App)
echo "[*] Assembling full standalone bundle in /tmp/spectra_bundle..."
rm -rf /tmp/spectra_bundle /tmp/bundle.zip
mkdir -p /tmp/spectra_bundle

cp -r /tmp/pyembed/*.dll /tmp/pyembed/*.pyd /tmp/pyembed/*.zip /tmp/pyembed/python.exe /tmp/pyembed/pythonw.exe /tmp/spectra_bundle/
cp -r /tmp/pyembed/serial /tmp/spectra_bundle/
cp -r /tmp/update_bundle/* /tmp/spectra_bundle/

echo "python312.zip" > /tmp/spectra_bundle/python312._pth
echo "." >> /tmp/spectra_bundle/python312._pth
echo "import site" >> /tmp/spectra_bundle/python312._pth

(cd /tmp/spectra_bundle && zip -q -r /tmp/bundle.zip .)

# 3. Compile Standalone Launcher (bin/spectra.exe)
echo "[*] Compiling Launcher resources..."
llvm-rc /fo "$SCRIPT_DIR/resources.res" "$SCRIPT_DIR/resources.rc"

echo "[*] Compiling PE32+ standalone launcher with zig..."
"$ZIG_CMD" cc -target x86_64-windows -O2 -s -municode \
    "$SCRIPT_DIR/launcher.c" "$SCRIPT_DIR/resources.res" \
    -o "$ROOT_DIR/spectra.exe" -luser32 -lshell32 -ladvapi32

rm -f "$SCRIPT_DIR/resources.res"

mkdir -p "$ROOT_DIR/bin"
cp "$ROOT_DIR/spectra.exe" "$ROOT_DIR/bin/spectra_build${BUILD_NUMBER}.exe"
cp "$ROOT_DIR/spectra.exe" "$ROOT_DIR/bin/spectra.exe"

# Inject compiled launcher into bundles so installer extracts it ready-to-run
cp "$ROOT_DIR/spectra.exe" /tmp/spectra_bundle/
(cd /tmp/spectra_bundle && zip -q -u /tmp/bundle.zip spectra.exe)

# 4. Compile Offline Installer (dist/spectra_setup_build<BUILD>.exe)
echo "[*] Compiling Offline Installer resources..."
llvm-rc /fo "$SCRIPT_DIR/installer.res" "$SCRIPT_DIR/installer.rc"

echo "[*] Compiling PE32+ offline installer with zig..."
mkdir -p "$ROOT_DIR/dist"
"$ZIG_CMD" cc -target x86_64-windows -O2 -s -municode \
    "$SCRIPT_DIR/installer.c" "$SCRIPT_DIR/installer.res" \
    -o "$ROOT_DIR/dist/spectra_setup_build${BUILD_NUMBER}.exe" \
    -luser32 -lshell32 -ladvapi32

cp "$ROOT_DIR/dist/spectra_setup_build${BUILD_NUMBER}.exe" "$ROOT_DIR/dist/spectra_setup.exe"
rm -f "$SCRIPT_DIR/installer.res"

# 5. Compile Fast In-Place Updater (dist/spectra_update_build<BUILD>.exe)
echo "[*] Compiling In-Place Updater resources..."
llvm-rc /fo "$SCRIPT_DIR/updater.res" "$SCRIPT_DIR/updater.rc"

echo "[*] Compiling PE32+ fast updater with zig..."
"$ZIG_CMD" cc -target x86_64-windows -O2 -s -municode \
    "$SCRIPT_DIR/updater.c" "$SCRIPT_DIR/updater.res" \
    -o "$ROOT_DIR/dist/spectra_update_build${BUILD_NUMBER}.exe" \
    -luser32 -lshell32 -ladvapi32

cp "$ROOT_DIR/dist/spectra_update_build${BUILD_NUMBER}.exe" "$ROOT_DIR/dist/spectra_update.exe"
rm -f "$SCRIPT_DIR/updater.res"

echo "================================================================================"
echo "[✓] Build ${BUILD_NUMBER} completed successfully!"
echo "--------------------------------------------------------------------------------"
echo "  Standalone Launcher: bin/spectra.exe ($(du -h "$ROOT_DIR/bin/spectra.exe" | cut -f1))"
echo "  Launcher (versioned): bin/spectra_build${BUILD_NUMBER}.exe"
echo "  Offline Installer:   dist/spectra_setup_build${BUILD_NUMBER}.exe ($(du -h "$ROOT_DIR/dist/spectra_setup_build${BUILD_NUMBER}.exe" | cut -f1))"
echo "  Fast In-Place Update: dist/spectra_update_build${BUILD_NUMBER}.exe ($(du -h "$ROOT_DIR/dist/spectra_update_build${BUILD_NUMBER}.exe" | cut -f1))"
echo "================================================================================"
