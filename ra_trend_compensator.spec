# -*- mode: python ; coding: utf-8 -*-

import os
import sys

block_cipher = None

a = Analysis(
    ['main.py'],
    pathex=['.'],
    binaries=[],
    datas=[
        # Include default config file alongside the executable if present
        ('config.json', '.') if os.path.exists('config.json') else None,
    ],
    hiddenimports=[
        'win32com',
        'win32com.client',
        'pythoncom',
        'win32api',
        'matplotlib.backends.backend_tkagg',
        'tkinter',
        'src',
        'src.config',
        'src.model',
        'src.model.constants',
        'src.model.data_logger',
        'src.model.drift_history',
        'src.model.mount_controller',
        'src.model.phd2_client',
        'src.model.polar_alignment',
        'src.model.real_session_profiles',
        'src.model.simulated_mount',
        'src.model.simulated_phd2_source',
        'src.model.trend_estimator',
        'src.view',
        'src.view.drift_chart',
        'src.view.main_window',
        'src.view.settings_dialog',
        'src.viewmodel',
        'src.viewmodel.view_model',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

# Filter out any None entries from datas
a.datas = [d for d in a.datas if d is not None]

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='RA_TrendCompensator',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,  # Set to True if a console window is needed for debugging
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,  # Path to icon file (e.g., 'icon.ico') if available
)
