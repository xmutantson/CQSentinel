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

Build Speed Optimizations:
    - Avoid collect_data_files('torch') and collect_submodules('torch')
      These scan 500+ modules and take 20-30 minutes!
    - Use selective imports for large packages
    - Exclude unused packages (pandas, matplotlib, etc.)
    - Typical build time: 2-5 minutes (down from 30+ minutes)
"""

import sys
from PyInstaller.utils.hooks import collect_data_files, collect_submodules, collect_dynamic_libs
import os

block_cipher = None

# Collect all data files from packages
datas = []
binaries = []

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
# NOTE: Avoid collect_data_files('torch') - it's extremely slow!
# PyTorch data files are usually not needed for inference-only use
# datas += collect_data_files('torch')  # DISABLED - saves 10+ minutes!
# datas += collect_data_files('torchaudio')  # DISABLED - saves 5+ minutes!
datas += collect_data_files('librosa')
datas += collect_data_files('sounddevice')

# AI model packages - include data files
try:
    datas += collect_data_files('av')
    print("✓ Including PyAV data files")
except:
    print("⚠ PyAV (av) not found")

try:
    datas += collect_data_files('faster_whisper')
    print("✓ Including faster-whisper data files")
except:
    print("⚠ faster-whisper not found - AI features will be limited")

try:
    datas += collect_data_files('ctranslate2')
    binaries += collect_dynamic_libs('ctranslate2')
    print("✓ Including ctranslate2 data files and dynamic libraries")
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
    'av',  # PyAV - required by faster-whisper
    'av.audio',
    'av.video',
    'av.container',
    'av.codec',
    'faster_whisper',
    'ctranslate2',
    'resemblyzer',
    'webrtcvad',
]

# Add torch submodules - SELECTIVE IMPORT for speed!
# NOTE: collect_submodules('torch') scans 500+ modules and takes 20+ minutes!
# Instead, only include what Resemblyzer and Silero VAD actually need:
torch_modules = [
    'torch',
    'torch.nn',
    'torch.nn.functional',
    'torch.nn.modules',
    'torch.nn.modules.activation',
    'torch.nn.modules.container',
    'torch.nn.modules.conv',
    'torch.nn.modules.linear',
    'torch.nn.modules.normalization',
    'torch.nn.modules.pooling',
    'torch.nn.modules.rnn',  # For Resemblyzer's LSTM
    'torch.autograd',
    'torch.jit',
    'torch.serialization',
    'torch.utils',
    'torch.utils.data',
    'torch._utils',
    'torch.hub',  # For Silero VAD model loading
    'torch.hub.load',
]
hiddenimports += torch_modules

# TorchAudio - only if you're using it (for Whisper, faster-whisper doesn't need it)
# hiddenimports += collect_submodules('torchaudio')  # DISABLED - saves 10+ minutes!
# If you DO need torchaudio, use selective imports like above

# Add AI package submodules - SELECTIVE for speed!
# NOTE: Only use collect_submodules() for small packages
# For large packages, manually list what you need

try:
    # faster-whisper is small, collect_submodules is OK
    hiddenimports += collect_submodules('faster_whisper')
    print("✓ Including faster-whisper submodules")
except:
    pass

try:
    # ctranslate2 is moderate size, but essential for faster-whisper
    hiddenimports += collect_submodules('ctranslate2')
    print("✓ Including ctranslate2 submodules")
except:
    pass

try:
    # resemblyzer is small, collect_submodules is OK
    hiddenimports += collect_submodules('resemblyzer')
    print("✓ Including resemblyzer submodules")
except:
    pass

# PyAV (av) - can be large, use selective imports if build is slow
try:
    # Option 1: Collect all (slower but safer)
    hiddenimports += collect_submodules('av')
    print("✓ Including PyAV submodules")

    # Option 2: Selective (faster, uncomment if Option 1 is too slow):
    # av_modules = ['av', 'av.audio', 'av.video', 'av.container', 'av.codec', 'av.stream']
    # hiddenimports += av_modules
    # print("✓ Including PyAV submodules (selective)")
except:
    pass

# Analysis - what files to include
a = Analysis(
    ['cqsentinel/main.py'],
    pathex=[],
    binaries=binaries,
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
        'pandas',      # Exclude if not using
        'PIL',         # Exclude if not using images
        'PIL.Image',
        'pytest',      # Testing framework not needed in exe
        'sphinx',      # Documentation not needed
        '_pytest',
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
    console=True,  # Show console window for debugging
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
