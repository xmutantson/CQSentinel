# Build Scripts

This directory contains scripts for building and packaging CQSentinel.

## Scripts

### `build_windows.py`
Python script to build Windows executable using PyInstaller.

**Usage:**
```bash
python scripts/build_windows.py [--clean] [--zip]
```

**Options:**
- `--clean` - Remove build artifacts before building
- `--zip` - Create portable ZIP file after build

**Output:**
- `dist/CQSentinel/CQSentinel.exe`
- `CQSentinel-windows-portable.zip` (if --zip)

### `build_windows.bat`
Windows batch file wrapper for `build_windows.py`.

**Usage:**
```bash
scripts\build_windows.bat
```

Automatically runs with `--clean --zip` flags.

### `build_installer.iss`
Inno Setup script to create Windows installer.

**Requirements:**
- Inno Setup 6.0+ (https://jrsoftware.org/isinfo.php)
- Built executable in `dist/CQSentinel/`

**Usage:**
1. Build executable first: `python scripts/build_windows.py`
2. Open `build_installer.iss` in Inno Setup Compiler
3. Click Build > Compile
4. Output: `Output/CQSentinel-Setup-0.1.0.exe`

### `download_models.py` (Future)
Script to download AI models for offline use.

Will download:
- Whisper speech recognition model
- Silero VAD model
- Resemblyzer voice encoder

## Quick Start

**Windows users:**
```bash
# Double-click or run:
scripts\build_windows.bat
```

**Linux/Mac users:**
```bash
python scripts/build_windows.py --clean --zip
```

## See Also

- `../BUILD.md` - Complete build documentation
- `../cqsentinel.spec` - PyInstaller specification file
- `../requirements.txt` - Python dependencies
