#!/usr/bin/env bash
set -euo pipefail

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

# Extract build number and RC numeric version parts from version.py
BUILD_NUMBER="$(python3 -c "import sys; sys.path.insert(0, '$ROOT_DIR'); from version import __build__; print(__build__)")"
RC_VER_TUPLE="$(python3 -c "
b = '${BUILD_NUMBER}'
parts = b.split('.')
ymd = parts[0] if parts and len(parts[0]) == 8 and parts[0].isdigit() else '20260101'
hm = parts[1] if len(parts) > 1 and parts[1].isdigit() else '0'
print(f'{int(ymd[:4])},{int(ymd[4:])},{int(hm)},0')
")"
echo "[*] Building SPECTRA Windows Suite for Build: $BUILD_NUMBER (RC $RC_VER_TUPLE)"

# Stamp current build identifier into C launcher/installer/updater sources and tracked .rc templates
for c_src in "$SCRIPT_DIR/launcher.c" "$SCRIPT_DIR/installer.c" "$SCRIPT_DIR/updater.c"; do
    if [ -f "$c_src" ]; then
        sed -i -E "s|^#define[[:space:]]+SPECTRA_BUILD[[:space:]]+\"[^\"]*\"|#define SPECTRA_BUILD        \"${BUILD_NUMBER}\"|" "$c_src"
        sed -i -E "s|^#define[[:space:]]+SPECTRA_VERSION[[:space:]]+\"[^\"]*\"|#define SPECTRA_VERSION      \"Build ${BUILD_NUMBER}\"|" "$c_src"
    fi
done

for rc_src in "$SCRIPT_DIR/resources.rc" "$SCRIPT_DIR/installer.rc" "$SCRIPT_DIR/updater.rc"; do
    if [ -f "$rc_src" ]; then
        sed -i -E "s|^FILEVERSION[[:space:]]+.*|FILEVERSION     ${RC_VER_TUPLE}|" "$rc_src"
        sed -i -E "s|^PRODUCTVERSION[[:space:]]+.*|PRODUCTVERSION  ${RC_VER_TUPLE}|" "$rc_src"
        sed -i -E "s|VALUE \"FileVersion\",[[:space:]]+\"[^\"]*\"|VALUE \"FileVersion\",      \"Build ${BUILD_NUMBER}\"|" "$rc_src"
        sed -i -E "s|VALUE \"ProductVersion\",[[:space:]]+\"[^\"]*\"|VALUE \"ProductVersion\",   \"Build ${BUILD_NUMBER}\"|" "$rc_src"
        sed -i -E "s|VALUE \"BuildNumber\",[[:space:]]+\"[^\"]*\"|VALUE \"BuildNumber\",      \"${BUILD_NUMBER}\"|" "$rc_src"
        sed -i -E "s|spectra_setup_build[0-9.]+\.exe|spectra_setup_build${BUILD_NUMBER}.exe|" "$rc_src"
        sed -i -E "s|spectra_update_build[0-9.]+\.exe|spectra_update_build${BUILD_NUMBER}.exe|" "$rc_src"
    fi
done

# Private per-build staging directory (eliminates predictable /tmp symlink & collision hazards)
STAGE_DIR="$(mktemp -d "${TMPDIR:-/tmp}/spectra_winbuild.XXXXXX")"
chmod 700 "$STAGE_DIR"
trap 'rm -rf "$STAGE_DIR"' EXIT

# Pinned supply-chain SHA-256 digests (F-13)
PYEMBED_SHA256="0d57bb6cb078b74d23dbfe91f77d6780d45bed328911609f1f7ee2ba1606bf44"
PYSERIAL_SHA256="c4451db6ba391ca6ca299fb3ec7bae67a5c55dde170964c7a14ceefec02f2cf0"
CERTIFI_SHA256="e9b54de76e530bb6cf0ccd036787103acb58fd42ba930ea8bf948ddbaa2f61d1"

WHEELS_CACHE="$ROOT_DIR/vendor/wheels_win_amd64"
PYEMBED_CACHE="${XDG_CACHE_HOME:-$HOME/.cache}/spectra_winbuild"
mkdir -p "$WHEELS_CACHE" "$PYEMBED_CACHE"

if [ ! -f "$WHEELS_CACHE/pyserial-3.5-py2.py3-none-any.whl" ]; then
    echo "[*] Downloading pyserial 3.5 wheel..."
    curl -sSL --proto '=https' --tlsv1.2 \
        https://files.pythonhosted.org/packages/07/bc/587a445451b253b285629263eb51c2d8e9bcea4fc97826266d186f96f558/pyserial-3.5-py2.py3-none-any.whl \
        -o "$WHEELS_CACHE/pyserial-3.5-py2.py3-none-any.whl"
fi
echo "${PYSERIAL_SHA256}  $WHEELS_CACHE/pyserial-3.5-py2.py3-none-any.whl" | sha256sum -c -
if [ -f "$WHEELS_CACHE/certifi-2026.10.23-py3-none-any.whl" ]; then
    echo "${CERTIFI_SHA256}  $WHEELS_CACHE/certifi-2026.10.23-py3-none-any.whl" | sha256sum -c -
fi

PYEMBED_ZIP="$PYEMBED_CACHE/python-3.12.7-embed-amd64.zip"
if [ ! -f "$PYEMBED_ZIP" ]; then
    if [ -f /tmp/pyembed/pyembed.zip ]; then
        cp /tmp/pyembed/pyembed.zip "$PYEMBED_ZIP"
    else
        echo "[*] Downloading Python 3.12.7 64-bit embeddable runtime..."
        curl -sSL --proto '=https' --tlsv1.2 \
            https://www.python.org/ftp/python/3.12.7/python-3.12.7-embed-amd64.zip \
            -o "$PYEMBED_ZIP"
    fi
fi
echo "${PYEMBED_SHA256}  $PYEMBED_ZIP" | sha256sum -c -

PYEMBED_DIR="$STAGE_DIR/pyembed"
mkdir -p "$PYEMBED_DIR"
unzip -q -o "$PYEMBED_ZIP" -d "$PYEMBED_DIR/"

echo "[*] Unpacking verified Windows runtime wheels (pyserial, certifi)..."
python3 -c "
import zipfile, os, shutil

wheels_dir = '$WHEELS_CACHE'
target_dir = '$PYEMBED_DIR'

for f in sorted(os.listdir(wheels_dir)):
    if not f.endswith('.whl'):
        continue
    p = os.path.join(wheels_dir, f)
    with zipfile.ZipFile(p, 'r') as z:
        z.extractall(target_dir)

shutil.rmtree(os.path.join(target_dir, 'certifi', 'tests'), ignore_errors=True)
"

# Helper to generate stamped RC files pointing to isolated STAGE_DIR bundles
write_rc_file() {
    local out_rc="$1"
    local rcdata_zip="$2"
    local desc="$3"
    local internal_name="$4"
    local orig_fname="$5"
    {
        echo "1 ICON \"$ROOT_DIR/icon.ico\""
        if [ -n "$rcdata_zip" ]; then
            echo "101 RCDATA \"$rcdata_zip\""
        fi
        cat <<EOF

1 VERSIONINFO
FILEVERSION     ${RC_VER_TUPLE}
PRODUCTVERSION  ${RC_VER_TUPLE}
FILEFLAGSMASK   0X3FL
FILEFLAGS       0X0L
FILEOS          0X40004L
FILETYPE        0X1L
FILESUBTYPE     0X0L
BEGIN
    BLOCK "StringFileInfo"
    BEGIN
        BLOCK "040904B0"
        BEGIN
            VALUE "CompanyName",      "SPECTRA Diagnostic Suite"
            VALUE "FileDescription",  "${desc}"
            VALUE "FileVersion",      "Build ${BUILD_NUMBER}"
            VALUE "InternalName",     "${internal_name}"
            VALUE "LegalCopyright",   "Copyright (c) 2026 SPECTRA Contributors (MIT License)"
            VALUE "OriginalFilename", "${orig_fname}"
            VALUE "ProductName",      "SPECTRA Universal Diagnostics"
            VALUE "ProductVersion",   "Build ${BUILD_NUMBER}"
            VALUE "BuildNumber",      "${BUILD_NUMBER}"
        END
    END
    BLOCK "VarFileInfo"
    BEGIN
        VALUE "Translation", 0x0409, 1200
    END
END
EOF
    } > "$out_rc"
}

# 0. Compile Thin Installed Launcher Stub (no embedded RCDATA — avoids 28 MB double-bundling!)
echo "[*] Compiling thin PE32+ installed launcher stub (spectra_thin.exe)..."
write_rc_file "$STAGE_DIR/launcher_thin.rc" "" \
    "SPECTRA Hardware Telemetry & Logic Board Diagnostics" \
    "spectra" "spectra.exe"
llvm-rc /fo "$STAGE_DIR/launcher_thin.res" "$STAGE_DIR/launcher_thin.rc"
"$ZIG_CMD" cc -target x86_64-windows -O2 -s -Wl,/subsystem:windows -municode \
    "$SCRIPT_DIR/launcher.c" "$STAGE_DIR/launcher_thin.res" \
    -o "$STAGE_DIR/spectra_thin.exe" -luser32 -lshell32 -lgdi32 -ladvapi32

# 1. Assemble Application-Only Payload (for fast in-place updater)
echo "[*] Assembling lightweight update bundle..."
UPDATE_BUNDLE_DIR="$STAGE_DIR/update_bundle"
UPDATE_BUNDLE_ZIP="$STAGE_DIR/update_bundle.zip"
mkdir -p "$UPDATE_BUNDLE_DIR"

cp "$ROOT_DIR"/*.py "$UPDATE_BUNDLE_DIR/"
cp "$ROOT_DIR"/profiles_data.json "$UPDATE_BUNDLE_DIR/"
cp "$ROOT_DIR"/icon.ico "$UPDATE_BUNDLE_DIR/"
cp "$ROOT_DIR"/icon.png "$UPDATE_BUNDLE_DIR/" 2>/dev/null || true
cp "$ROOT_DIR"/spectra_logo.svg "$UPDATE_BUNDLE_DIR/" 2>/dev/null || true
mkdir -p "$UPDATE_BUNDLE_DIR/docs"
cp -r "$ROOT_DIR"/docs/models "$UPDATE_BUNDLE_DIR/docs/"
mkdir -p "$UPDATE_BUNDLE_DIR/web"
cp -r "$ROOT_DIR"/web/dist "$UPDATE_BUNDLE_DIR/web/"
for pkg_dir in drivers spectra_mapper spectra_stats spectra_web spectra_hmi; do
    if [ -d "$ROOT_DIR/$pkg_dir" ]; then
        cp -r "$ROOT_DIR/$pkg_dir" "$UPDATE_BUNDLE_DIR/"
    fi
done

for pkg in serial certifi; do
    if [ -d "$PYEMBED_DIR/$pkg" ]; then
        cp -r "$PYEMBED_DIR/$pkg" "$UPDATE_BUNDLE_DIR/"
    fi
done

if [ -f "$ROOT_DIR/bin/spectra-shell.exe" ]; then
    cp "$ROOT_DIR/bin/spectra-shell.exe" "$UPDATE_BUNDLE_DIR/"
fi
if [ -f "$ROOT_DIR/bin/WebView2Loader.dll" ]; then
    cp "$ROOT_DIR/bin/WebView2Loader.dll" "$UPDATE_BUNDLE_DIR/"
fi
if [ -f "$ROOT_DIR/bin/spectra_py.pyd" ]; then
    cp "$ROOT_DIR/bin/spectra_py.pyd" "$UPDATE_BUNDLE_DIR/"
fi

# Package thin launcher stub into update bundle (never the fat portable EXE!)
cp "$STAGE_DIR/spectra_thin.exe" "$UPDATE_BUNDLE_DIR/spectra.exe"

find "$UPDATE_BUNDLE_DIR" -type d -name '__pycache__' -exec rm -rf {} + 2>/dev/null || true
(cd "$UPDATE_BUNDLE_DIR" && zip -q -r "$UPDATE_BUNDLE_ZIP" .)

# 2. Assemble Full Standalone Runtime Bundle (Python 3.12 + PySerial + Certifi + Native Rust + App)
# Notice: PYEMBED_ZIP lives in PYEMBED_CACHE outside PYEMBED_DIR, so ONLY python312.zip is copied!
echo "[*] Assembling full standalone runtime bundle..."
PORTABLE_BUNDLE_DIR="$STAGE_DIR/portable_bundle"
PORTABLE_BUNDLE_ZIP="$STAGE_DIR/portable_bundle.zip"
SETUP_BUNDLE_DIR="$STAGE_DIR/setup_bundle"
SETUP_BUNDLE_ZIP="$STAGE_DIR/setup_bundle.zip"
mkdir -p "$PORTABLE_BUNDLE_DIR"

cp -r "$PYEMBED_DIR"/*.dll "$PYEMBED_DIR"/*.pyd "$PYEMBED_DIR"/python312.zip "$PYEMBED_DIR"/python.exe "$PYEMBED_DIR"/pythonw.exe "$PORTABLE_BUNDLE_DIR/"
cp -r "$UPDATE_BUNDLE_DIR"/* "$PORTABLE_BUNDLE_DIR/"
rm -f "$PORTABLE_BUNDLE_DIR/spectra.exe"

printf "python312.zip\n.\nimport site\n" > "$PORTABLE_BUNDLE_DIR/python312._pth"
(cd "$PORTABLE_BUNDLE_DIR" && zip -q -r "$PORTABLE_BUNDLE_ZIP" .)

cp -r "$PORTABLE_BUNDLE_DIR" "$SETUP_BUNDLE_DIR"
cp "$STAGE_DIR/spectra_thin.exe" "$SETUP_BUNDLE_DIR/spectra.exe"
(cd "$SETUP_BUNDLE_DIR" && zip -q -r "$SETUP_BUNDLE_ZIP" .)

# 3. Compile Single-File Portable Launcher (bin/spectra.exe)
echo "[*] Compiling PE32+ single-file portable launcher (bin/spectra.exe)..."
write_rc_file "$STAGE_DIR/launcher_portable.rc" "$PORTABLE_BUNDLE_ZIP" \
    "SPECTRA Hardware Telemetry & Logic Board Diagnostics" \
    "spectra" "spectra.exe"
llvm-rc /fo "$STAGE_DIR/launcher_portable.res" "$STAGE_DIR/launcher_portable.rc"
"$ZIG_CMD" cc -target x86_64-windows -O2 -s -Wl,/subsystem:windows -municode \
    "$SCRIPT_DIR/launcher.c" "$STAGE_DIR/launcher_portable.res" \
    -o "$ROOT_DIR/spectra.exe" -luser32 -lshell32 -lgdi32 -ladvapi32

mkdir -p "$ROOT_DIR/bin"
cp "$ROOT_DIR/spectra.exe" "$ROOT_DIR/bin/spectra_build${BUILD_NUMBER}.exe"
cp "$ROOT_DIR/spectra.exe" "$ROOT_DIR/bin/spectra.exe"

# 4. Compile Offline Installer (dist/spectra_setup_build<BUILD>.exe)
echo "[*] Compiling PE32+ offline installer (dist/spectra_setup.exe)..."
mkdir -p "$ROOT_DIR/dist"
write_rc_file "$STAGE_DIR/installer.rc" "$SETUP_BUNDLE_ZIP" \
    "SPECTRA Hardware Telemetry Offline Installer" \
    "spectra_setup" "spectra_setup_build${BUILD_NUMBER}.exe"
llvm-rc /fo "$STAGE_DIR/installer.res" "$STAGE_DIR/installer.rc"
"$ZIG_CMD" cc -target x86_64-windows -O2 -s -municode \
    "$SCRIPT_DIR/installer.c" "$STAGE_DIR/installer.res" \
    -o "$ROOT_DIR/dist/spectra_setup_build${BUILD_NUMBER}.exe" \
    -luser32 -lshell32 -ladvapi32 -lole32 -luuid

cp "$ROOT_DIR/dist/spectra_setup_build${BUILD_NUMBER}.exe" "$ROOT_DIR/dist/spectra_setup.exe"

# 5. Compile Fast In-Place Updater (dist/spectra_update_build<BUILD>.exe)
echo "[*] Compiling PE32+ fast in-place updater (dist/spectra_update.exe)..."
write_rc_file "$STAGE_DIR/updater.rc" "$UPDATE_BUNDLE_ZIP" \
    "SPECTRA Hardware Telemetry Fast In-Place Updater" \
    "spectra_update" "spectra_update_build${BUILD_NUMBER}.exe"
llvm-rc /fo "$STAGE_DIR/updater.res" "$STAGE_DIR/updater.rc"
"$ZIG_CMD" cc -target x86_64-windows -O2 -s -municode \
    "$SCRIPT_DIR/updater.c" "$STAGE_DIR/updater.res" \
    -o "$ROOT_DIR/dist/spectra_update_build${BUILD_NUMBER}.exe" \
    -luser32 -lshell32 -ladvapi32

cp "$ROOT_DIR/dist/spectra_update_build${BUILD_NUMBER}.exe" "$ROOT_DIR/dist/spectra_update.exe"
if [ -d "$HOME/Work" ]; then
    cp "$ROOT_DIR/dist/spectra_update.exe" "$HOME/Work/spectra_update.exe"
    cp "$ROOT_DIR/dist/spectra_update_build${BUILD_NUMBER}.exe" "$HOME/Work/spectra_update_build${BUILD_NUMBER}.exe"
fi

echo "================================================================================"
echo "[✓] Build ${BUILD_NUMBER} completed successfully!"
echo "--------------------------------------------------------------------------------"
echo "  Thin Installed Stub:  spectra_thin.exe ($(du -h "$STAGE_DIR/spectra_thin.exe" | cut -f1))"
echo "  Standalone Portable:  bin/spectra.exe ($(du -h "$ROOT_DIR/bin/spectra.exe" | cut -f1))"
echo "  Offline Installer:    dist/spectra_setup_build${BUILD_NUMBER}.exe ($(du -h "$ROOT_DIR/dist/spectra_setup_build${BUILD_NUMBER}.exe" | cut -f1))"
echo "  Fast In-Place Update: dist/spectra_update_build${BUILD_NUMBER}.exe ($(du -h "$ROOT_DIR/dist/spectra_update_build${BUILD_NUMBER}.exe" | cut -f1))"
echo "================================================================================"
