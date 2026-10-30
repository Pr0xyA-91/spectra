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

echo "[*] Assembling Windows standalone bundle in /tmp/spectra_bundle..."
rm -rf /tmp/spectra_bundle /tmp/bundle.zip
mkdir -p /tmp/spectra_bundle

# Check or download python embeddable package
if [ ! -d /tmp/pyembed ] || [ ! -f /tmp/pyembed/python.exe ]; then
    echo "[*] Downloading Python 3.12 64-bit embeddable runtime..."
    mkdir -p /tmp/pyembed
    curl -sSL https://www.python.org/ftp/python/3.12.7/python-3.12.7-embed-amd64.zip -o /tmp/pyembed/pyembed.zip
    unzip -q -o /tmp/pyembed/pyembed.zip -d /tmp/pyembed/
    curl -sSL https://files.pythonhosted.org/packages/07/bc/587a445451b253b285629263eb51c2d8e9bcea4fc97826266d186f96f558/pyserial-3.5-py2.py3-none-any.whl -o /tmp/pyembed/pyserial.whl
    unzip -q -o /tmp/pyembed/pyserial.whl -d /tmp/pyembed/
fi

cp -r /tmp/pyembed/*.dll /tmp/pyembed/*.pyd /tmp/pyembed/*.zip /tmp/pyembed/python.exe /tmp/pyembed/pythonw.exe /tmp/spectra_bundle/
cp -r /tmp/pyembed/serial /tmp/spectra_bundle/
cp "$ROOT_DIR"/*.py /tmp/spectra_bundle/
cp "$ROOT_DIR"/profiles_data.json /tmp/spectra_bundle/
cp "$ROOT_DIR"/icon.ico /tmp/spectra_bundle/
mkdir -p /tmp/spectra_bundle/docs
cp -r "$ROOT_DIR"/docs/models /tmp/spectra_bundle/docs/
mkdir -p /tmp/spectra_bundle/web
cp -r "$ROOT_DIR"/web/dist /tmp/spectra_bundle/web/
if [ -d "$ROOT_DIR"/drivers ]; then
    cp -r "$ROOT_DIR"/drivers /tmp/spectra_bundle/
fi

echo "python312.zip" > /tmp/spectra_bundle/python312._pth
echo "." >> /tmp/spectra_bundle/python312._pth
echo "import site" >> /tmp/spectra_bundle/python312._pth

(cd /tmp/spectra_bundle && zip -q -r /tmp/bundle.zip .)

echo "[*] Compiling Windows resources..."
llvm-rc /fo "$SCRIPT_DIR/resources.res" "$SCRIPT_DIR/resources.rc"

echo "[*] Compiling PE32+ executable with zig..."
"$ZIG_CMD" cc -target x86_64-windows -O2 -s -municode \
    "$SCRIPT_DIR/launcher.c" "$SCRIPT_DIR/resources.res" \
    -o "$ROOT_DIR/spectra.exe" -luser32 -lshell32

rm -f "$SCRIPT_DIR/resources.res"

mkdir -p "$ROOT_DIR/bin"
cp "$ROOT_DIR/spectra.exe" "$ROOT_DIR/bin/spectra_build20261030.1630.exe"
cp "$ROOT_DIR/spectra.exe" "$ROOT_DIR/bin/spectra.exe"

echo "[✓] Standalone Windows executable compiled successfully:"
ls -lh "$ROOT_DIR/spectra.exe" "$ROOT_DIR/bin/spectra_build20261030.1630.exe"
