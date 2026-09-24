# -*- mode: python ; coding: utf-8 -*-
"""build_executable.spec -- PyInstaller spec file for FSOC Coarse-Alignment Simulator (SIH 26169)."""

import os
from pathlib import Path
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

block_cipher = None

project_root = os.path.abspath(os.path.join(SPECPATH, ".."))

datas = [
    (os.path.join(project_root, "config", "default_config.yaml"), "config"),
    (os.path.join(project_root, "ui", "style.qss"), "ui"),
]

# Check if assets directory exists and add it if present
assets_dir = os.path.join(project_root, "assets")
if os.path.exists(assets_dir):
    datas.append((assets_dir, "assets"))

hiddenimports = [
    "scipy.special",
    "scipy.ndimage",
    "scipy.linalg",
    "cv2",
    "filterpy",
    "filterpy.kalman",
    "filterpy.common",
    "PySide6.QtCore",
    "PySide6.QtGui",
    "PySide6.QtWidgets",
    "PySide6.QtCharts",
    "yaml",
]

a = Analysis(
    [os.path.join(project_root, "ui", "main_window.py")],
    pathex=[project_root],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="fsoc_sim",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="fsoc_sim",
)
