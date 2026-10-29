# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller Specification for SPECTRA (Windows Standalone Executable)
Compiles spectra_app.py, embedding all profiles, assets, and serial communication modules.
Produces a single, portable 'spectra.exe' with zero external runtime dependencies.
"""

import os
import sys

block_cipher = None

added_files = [
    ('profiles_data.json', '.'),
    ('spectra_logo.svg', '.'),
    ('icon.ico', '.'),
]

a = Analysis(
    ['spectra_app.py'],
    pathex=['.'],
    binaries=[],
    datas=added_files,
    hiddenimports=[
        'serial',
        'serial.tools',
        'serial.tools.list_ports',
        'serial.tools.list_ports_windows',
        'http.server',
        'webbrowser',
        'json',
        'socket',
        'threading',
        'time',
        'datetime',
        're',
        'os',
        'sys',
        'math',
        'typing',
        'version',
        'stats_collector',
        'serial_io',
        'profiles_db',
        'spectra_engine',
        'wrat_engine',
        'jura_protocol',
        'memory_mapper',
        'drivers',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'tkinter',
        'matplotlib',
        'numpy',
        'scipy',
        'gi',
        'gtk',
        'cairo',
        'unittest',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='spectra',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='icon.ico',
)
