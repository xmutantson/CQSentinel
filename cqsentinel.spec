# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec file for CQSentinel
Builds a self-contained Windows executable with all dependencies

Usage:
    pyinstaller cqsentinel.spec

Output:
    dist/CQSentinel/CQSentinel.exe (directory mode)
    or
    dist/CQSentinel.exe (onefile mode - slower startup)
"""

import sys
from PyInstaller.utils.hooks import collect_data_files, collect_submodules
import os

block_cipher = None

# Collect all data files from packages
datas = []

# Add models directory (if exists)
if os.path.exists('models'):
    datas.append(('models', 'models'))

# Add contest profiles (when created)
if os.path.exists('contest_profiles'):
    datas.append(('contest_profiles', 'contest_profiles'))

# Add resources (when created)
if os.path.exists('resources'):
    datas.append(('resources', 'resources'))

# Add Hamlib binaries (if exists)
hamlib_dir = 'external/hamlib'
if os.path.exists(hamlib_dir):
    # Add entire hamlib directory to distribution
    datas.append((hamlib_dir, 'hamlib'))
    print(f"✓ Including Hamlib from {hamlib_dir}")

# Collect data files from packages
datas += collect_data_files('torch')
datas += collect_data_files('torchaudio')
datas += collect_data_files('librosa')
datas += collect_data_files('sounddevice')

# AI model packages - include data files
try:
    datas += collect_data_files('faster_whisper')
    print("✓ Including faster-whisper data files")
except:
    print("⚠ faster-whisper not found - AI features will be limited")

try:
    datas += collect_data_files('ctranslate2')
    print("✓ Including ctranslate2 data files")
except:
    print("⚠ ctranslate2 not found")

try:
    datas += collect_data_files('resemblyzer')
    print("✓ Including resemblyzer data files")
except:
    print("⚠ resemblyzer not found")

# Hidden imports - modules that PyInstaller might miss
hiddenimports = [
    'PyQt5.QtCore',
    'PyQt5.QtGui',
    'PyQt5.QtWidgets',
    'numpy',
    'scipy',
    'scipy.special',
    'scipy.linalg',
    'scipy.sparse',
    'sklearn',
    'sklearn.utils._cython_blas',
    'sklearn.neighbors.typedefs',
    'sklearn.neighbors.quad_tree',
    'sklearn.tree._utils',
    'sounddevice',
    'soundfile',
    'librosa',
    'librosa.core',
    'librosa.feature',
    'noisereduce',
    'colorlog',
    'yaml',
    # AI packages
    'faster_whisper',
    'ctranslate2',
    'resemblyzer',
    'webrtcvad',
]

# Add all torch submodules
hiddenimports += collect_submodules('torch')
hiddenimports += collect_submodules('torchaudio')

# Add AI package submodules
try:
    hiddenimports += collect_submodules('faster_whisper')
    print("✓ Including faster-whisper submodules")
except:
    pass

try:
    hiddenimports += collect_submodules('ctranslate2')
    print("✓ Including ctranslate2 submodules")
except:
    pass

try:
    hiddenimports += collect_submodules('resemblyzer')
    print("✓ Including resemblyzer submodules")
except:
    pass

# Analysis - what files to include
a = Analysis(
    ['cqsentinel/main.py'],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'matplotlib',  # Exclude if not needed
        'tkinter',     # We use PyQt5
        'IPython',
        'jupyter',
        'notebook',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

# Remove duplicate entries
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

# Executable options
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,  # For --onedir mode
    name='CQSentinel',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,  # Compress with UPX (optional)
    console=False,  # No console window (Windows GUI app)
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='resources/icon.ico' if os.path.exists('resources/icon.ico') else None,
)

# Collect all files into dist/CQSentinel/ directory
coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='CQSentinel',
)

# For single-file executable (uncomment and comment out above):
# exe = EXE(
#     pyz,
#     a.scripts,
#     a.binaries,
#     a.zipfiles,
#     a.datas,
#     [],
#     name='CQSentinel',
#     debug=False,
#     bootloader_ignore_signals=False,
#     strip=False,
#     upx=True,
#     upx_exclude=[],
#     runtime_tmpdir=None,
#     console=False,
#     disable_windowed_traceback=False,
#     argv_emulation=False,
#     target_arch=None,
#     codesign_identity=None,
#     entitlements_file=None,
#     icon='resources/icon.ico' if os.path.exists('resources/icon.ico') else None,
# )
