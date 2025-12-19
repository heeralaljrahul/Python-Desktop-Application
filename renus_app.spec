# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec file for RENUS AUTHENTIC DELIGHTS application.

Build Instructions:
1. Install PyInstaller: pip install pyinstaller
2. Run: pyinstaller renus_app.spec
3. The EXE will be in the 'dist' folder

For a single-file EXE (larger but easier to distribute):
    pyinstaller renus_app.spec --onefile

For a folder-based distribution (faster startup):
    pyinstaller renus_app.spec
"""

import sys
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

block_cipher = None

# Collect all customtkinter data files (themes, etc.)
ctk_datas = collect_data_files('customtkinter')

# Application metadata
APP_NAME = 'RenusDelights'
APP_VERSION = '1.0.0'

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('assets', 'assets'),  # Include assets folder
    ] + ctk_datas,
    hiddenimports=[
        'PIL._tkinter_finder',
        'customtkinter',
        'matplotlib',
        'matplotlib.backends.backend_tkagg',
        'matplotlib.backends.backend_agg',
        'reportlab',
        'reportlab.lib',
        'reportlab.lib.colors',
        'reportlab.lib.pagesizes',
        'reportlab.lib.units',
        'reportlab.pdfgen',
        'reportlab.pdfgen.canvas',
        'sqlite3',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'pytest',
        'unittest',
        'test',
        'tests',
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
    name=APP_NAME,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,  # Set to True for debugging
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='assets/logo.png' if sys.platform != 'win32' else None,  # Use .ico on Windows
)

# For folder-based distribution (uncomment if not using --onefile)
# coll = COLLECT(
#     exe,
#     a.binaries,
#     a.zipfiles,
#     a.datas,
#     strip=False,
#     upx=True,
#     upx_exclude=[],
#     name=APP_NAME,
# )
