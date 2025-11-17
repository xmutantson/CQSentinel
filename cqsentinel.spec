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

# NOTE: Resemblyzer removed - not effective for SSB audio
# try:
#     datas += collect_data_files('resemblyzer')
#     print("✓ Including resemblyzer data files")
# except:
#     print("⚠ resemblyzer not found")

try:
    datas += collect_data_files('whisper')
    print("✓ Including openai-whisper data files")
except:
    print("⚠ openai-whisper not found")

# CREPE pitch detection models (required for SSB auto-centering)
try:
    datas += collect_data_files('crepe')
    print("✓ Including CREPE pitch detection model files")
except:
    print("⚠ CREPE not found - SSB auto-centering will use fallback method")

# TensorFlow (required by CREPE)
# NOTE: TensorFlow is large, only include essential data files
try:
    # Include TensorFlow's essential data files (avoiding full collect which is huge)
    import tensorflow as tf
    tf_path = os.path.dirname(tf.__file__)
    # Include the lite models and core data
    if os.path.exists(os.path.join(tf_path, 'lite')):
        datas.append((os.path.join(tf_path, 'lite'), 'tensorflow/lite'))
    if os.path.exists(os.path.join(tf_path, 'python', '_pywrap_tensorflow_internal.pyd')):
        binaries.append((os.path.join(tf_path, 'python', '_pywrap_tensorflow_internal.pyd'), 'tensorflow/python'))
    print("✓ Including TensorFlow (for CREPE)")
except Exception as e:
    print(f"⚠ TensorFlow not found: {e}")

# CUDA libraries for GPU support
# Bundle PyTorch CUDA runtime libraries for GPU acceleration
try:
    import torch
    import glob

    if torch.cuda.is_available():
        print(f"✓ CUDA available (version {torch.version.cuda}), bundling CUDA libraries...")

        torch_lib_path = os.path.join(os.path.dirname(torch.__file__), 'lib')
        if os.path.exists(torch_lib_path):
            # Include all CUDA DLLs/SOs from PyTorch
            cuda_libs = []
            for ext in ['*.dll', '*.so', '*.so.*']:
                cuda_libs.extend(glob.glob(os.path.join(torch_lib_path, ext)))

            for lib in cuda_libs:
                lib_name = os.path.basename(lib)
                # Include CUDA-related libraries
                if any(x in lib_name.lower() for x in ['cuda', 'cublas', 'cudnn', 'cufft', 'curand', 'cusparse', 'cusolver', 'nvrtc', 'c10_cuda']):
                    binaries.append((lib, '.'))
                    print(f"  ✓ Including CUDA lib: {lib_name}")

            print(f"✓ Included {len([b for b in binaries if 'cuda' in b[0].lower() or 'cufft' in b[0].lower()])} CUDA libraries")
        else:
            print(f"⚠ PyTorch lib directory not found: {torch_lib_path}")

        # Also try to find CUDA runtime from system if not bundled with PyTorch
        # This handles cases where PyTorch uses system CUDA
        nvidia_path = None
        if sys.platform == 'win32':
            nvidia_path = os.environ.get('CUDA_PATH', r'C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA')
        else:
            nvidia_path = '/usr/local/cuda'

        if nvidia_path and os.path.exists(nvidia_path):
            cuda_bin = os.path.join(nvidia_path, 'bin' if sys.platform == 'win32' else 'lib64')
            if os.path.exists(cuda_bin):
                print(f"  Found system CUDA at {nvidia_path}")
                # Include essential CUDA runtime libraries
                for lib_pattern in ['cudart*.dll', 'cublas*.dll', 'cublasLt*.dll'] if sys.platform == 'win32' else ['libcudart.so*', 'libcublas.so*']:
                    for lib in glob.glob(os.path.join(cuda_bin, lib_pattern)):
                        if lib not in [b[0] for b in binaries]:
                            binaries.append((lib, '.'))
                            print(f"  ✓ Including system CUDA lib: {os.path.basename(lib)}")
    else:
        print("⚠ CUDA not available - building CPU-only version")
        print("  To enable GPU support, install PyTorch with CUDA support")
except ImportError:
    print("⚠ PyTorch not installed - skipping CUDA library bundling")
except Exception as e:
    print(f"⚠ Error bundling CUDA libraries: {e}")

try:
    datas += collect_data_files('tiktoken')
    datas += collect_data_files('tiktoken_ext')
    binaries += collect_dynamic_libs('tiktoken')
    print("✓ Including tiktoken data files and dynamic libraries")

    # CRITICAL: Also find and include the native extension explicitly
    # because collect_dynamic_libs may not find it due to circular import issues
    # Search all Python paths without importing tiktoken
    import site
    import os as _os
    tiktoken_found = False

    # Build list of directories to search
    search_dirs = []
    try:
        search_dirs.extend(site.getsitepackages())
    except:
        pass
    try:
        search_dirs.append(site.getusersitepackages())
    except:
        pass
    # Also check sys.path for conda environments
    search_dirs.extend(sys.path)

    for search_dir in search_dirs:
        if not _os.path.isdir(search_dir):
            continue
        tiktoken_dir = _os.path.join(search_dir, 'tiktoken')
        if _os.path.isdir(tiktoken_dir):
            for fname in _os.listdir(tiktoken_dir):
                if fname.startswith('_tiktoken') and (fname.endswith('.pyd') or fname.endswith('.so')):
                    ext_path = _os.path.join(tiktoken_dir, fname)
                    # Add as (source, dest_folder)
                    binaries.append((ext_path, 'tiktoken'))
                    print(f"✓ Found tiktoken native extension: {ext_path}")
                    tiktoken_found = True
                    break
            if tiktoken_found:
                break
    if not tiktoken_found:
        print("⚠ tiktoken native extension (.pyd/.so) not found in any Python path")
except Exception as e:
    print(f"⚠ tiktoken not found: {e}")

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
    # NOTE: sklearn.neighbors.typedefs and quad_tree don't exist in sklearn 1.0+
    # They were refactored/removed. PyInstaller handles sklearn correctly now.
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
    # 'resemblyzer',  # Removed - not effective for SSB audio
    'webrtcvad',
    # openai-whisper (PyTorch-based, more stable on Windows)
    'whisper',
    'whisper.audio',
    'whisper.decoding',
    'whisper.model',
    'whisper.tokenizer',
    'whisper.transcribe',
    # tiktoken (required by openai-whisper for tokenization)
    'tiktoken',
    'tiktoken._tiktoken',  # Native extension
    'tiktoken.core',
    'tiktoken.load',
    'tiktoken.model',
    'tiktoken.registry',
    'tiktoken_ext',
    'tiktoken_ext.openai_public',
    # CREPE pitch detection (neural network-based F0 estimation)
    'crepe',
    'crepe.core',
    'crepe.decode',
    'tensorflow',
    'tensorflow.keras',
    'tensorflow.keras.models',
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
    'torch.nn.parameter',  # For model Parameters
    'torch.autograd',
    'torch.jit',
    'torch.jit._state',  # JIT internal state
    'torch.serialization',
    'torch.storage',  # For loading model weights
    'torch.cpu',  # CPU backend operations
    'torch.backends',  # Backend detection (even CPU-only needs this)
    'torch.backends.cpu',
    'torch.utils',
    'torch.utils.data',
    'torch._utils',
    'torch.hub',  # For Silero VAD model loading
    # CUDA support for GPU inference
    'torch.cuda',
    'torch.cuda.amp',  # Automatic mixed precision
    'torch.backends.cuda',
    'torch.backends.cudnn',
    # NOTE: torch.hub.load is a function, not a module - don't include it here
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

# NOTE: Resemblyzer removed - not effective for SSB audio
# try:
#     # resemblyzer is small, collect_submodules is OK
#     hiddenimports += collect_submodules('resemblyzer')
#     print("✓ Including resemblyzer submodules")
# except:
#     pass

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

# NOTE: collect_submodules('whisper') and collect_submodules('tiktoken') are NOT used here
# because they fail with circular import errors. Instead, we use custom analysis hooks
# in hooks/hook-whisper.py and hooks/hook-tiktoken.py that explicitly list all submodules.
# PyInstaller will automatically use those hooks when it sees these packages.
print("✓ Using custom hooks for openai-whisper and tiktoken (avoiding circular import)")

# Analysis - what files to include
# NOTE: We've carefully curated hiddenimports above, so we can use module_collection_mode
# to speed up analysis by not recursively scanning everything
a = Analysis(
    ['cqsentinel/main.py'],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=['hooks'],  # Custom hooks directory for tiktoken, whisper, etc.
    hooksconfig={},
    runtime_hooks=['hooks/rthook-tiktoken.py'],  # Runtime hook to fix tiktoken circular import
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
        # NOTE: Cannot exclude any torch.* modules from PyInstaller builds!
        # PyTorch's initialization imports various submodules to detect capabilities:
        # - torch.cuda (checks CUDA availability)
        # - torch.distributed (checks distributed training support)
        # - torch.testing (internal checks)
        # Excluding ANY of these causes "No module named 'torch.X'" errors at runtime
        # even if we're only using CPU-only inference mode.
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
    module_collection_mode={
        # Use 'pyz+py' for torch instead of 'pyz' because:
        # - PyTorch uses JIT compilation which requires source .py files
        # - Dynamic imports may fail with bytecode-only 'pyz' mode
        # - 'pyz+py' includes both .pyc (in archive) and .py (as data files)
        'torch': 'pyz+py',
    },
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
    upx=False,  # DISABLED - UPX compression is slow, increases build time significantly
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
    upx=False,  # DISABLED - UPX compression is VERY slow (adds 10-20 min for PyTorch libs)
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
