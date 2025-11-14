# Building CQSentinel for Windows

This guide explains how to build a self-contained Windows executable for CQSentinel.

## Prerequisites

**Before building, you MUST complete the development environment setup from INSTALL.md:**

1. Install conda/radioconda
2. Create `cqsentinel` environment
3. Install all dependencies via `conda env update -f environment.yml`
4. Verify all imports work (PyQt5, PyTorch, librosa, resemblyzer)

If you haven't done this yet, **stop here** and follow INSTALL.md first.

**Quick verification** (should all show ✓):

```powershell
conda activate cqsentinel
python -c "from PyQt5 import QtCore; print('✓ PyQt5')"
python -c "import torch; print('✓ PyTorch')"
python -c "from resemblyzer import VoiceEncoder; print('✓ Resemblyzer')"
```

If any fail, go back to INSTALL.md.

## Step-by-Step Build Process

**Assumes you've completed INSTALL.md and verified all imports work.**

```powershell
# 1. Activate your conda environment
conda activate cqsentinel

# 2. Navigate to project directory
cd X:\Storage\Documents\CQSentinel\CQSentinel

# 3. Clean previous builds (if any)
if (Test-Path build) { Remove-Item -Recurse -Force build }
if (Test-Path dist) { Remove-Item -Recurse -Force dist }

# 4. Build with PyInstaller
pyinstaller cqsentinel.spec

# 5. Test the executable
.\dist\CQSentinel\CQSentinel.exe

# 6. (Optional) Create portable ZIP for distribution
Compress-Archive -Path dist\CQSentinel -DestinationPath CQSentinel-windows-portable.zip
```

**Output**: `dist/CQSentinel/CQSentinel.exe` (ready to distribute)

---

## Build Methods

### Method 1: Using Build Script (If Available)

**Windows users:**

```powershell
conda activate cqsentinel
.\scripts\build_windows.bat
```

This will:
- Check dependencies
- Build executable with PyInstaller
- Create portable ZIP file
- Output to `dist/CQSentinel/`

### Method 2: Manual PyInstaller (Recommended)

```powershell
# Make sure conda environment is activated!
conda activate cqsentinel

# Clean previous builds
if (Test-Path build) { Remove-Item -Recurse -Force build }
if (Test-Path dist) { Remove-Item -Recurse -Force dist }

# Build with spec file
pyinstaller cqsentinel.spec

# Output: dist/CQSentinel/CQSentinel.exe
```

### Method 3: Direct PyInstaller (without spec)

```powershell
conda activate cqsentinel

pyinstaller --name CQSentinel `
            --windowed `
            --onedir `
            --add-data "models;models" `
            --hidden-import PyQt5.QtCore `
            --hidden-import PyQt5.QtWidgets `
            --hidden-import torch `
            --hidden-import resemblyzer `
            cqsentinel/main.py
```

## Build Options

### Directory vs. Single File

**Directory mode** (default, recommended):
- Faster startup
- Easier debugging
- Output: `dist/CQSentinel/` folder with multiple files
- Use: `pyinstaller cqsentinel.spec`

**Single file mode**:
- Slower startup (extracts to temp on each run)
- Easier to distribute (one .exe file)
- Use: Edit `cqsentinel.spec` and uncomment the single-file EXE section

### Build Configuration

Edit `cqsentinel.spec` to customize:

```python
# Exclude unused libraries to reduce size
excludes=[
    'matplotlib',
    'IPython',
    'jupyter',
]

# Add your own data files
datas += [
    ('my_custom_profiles', 'contest_profiles'),
]

# Enable/disable compression
upx=True,  # Compress with UPX (requires UPX installed)
```

## Creating a Windows Installer

### 1. Build the executable first

```bash
python scripts/build_windows.py --clean
```

### 2. Compile with Inno Setup

1. Open Inno Setup Compiler
2. Load `scripts/build_installer.iss`
3. Click **Build > Compile**
4. Output: `Output/CQSentinel-Setup-0.1.0.exe`

### 3. Distribute the installer

The installer will:
- Install to `C:\Program Files\CQSentinel\`
- Create Start Menu shortcuts
- Create Desktop icon (optional)
- Set up user data directory in `%APPDATA%\CQSentinel\`

## Build Output

### Directory Structure

```
dist/
└── CQSentinel/
    ├── CQSentinel.exe          # Main executable
    ├── python310.dll           # Python runtime
    ├── _internal/              # Dependencies
    │   ├── PyQt5/
    │   ├── torch/
    │   ├── librosa/
    │   ├── resemblyzer/
    │   └── ... (all libraries)
    ├── models/                 # AI models (if bundled)
    └── contest_profiles/       # Contest configs
```

### Portable ZIP

```
CQSentinel-windows-portable.zip
└── (same as dist/CQSentinel/)
```

Users can extract and run directly, no installation needed.

### Installer

```
CQSentinel-Setup-0.1.0.exe
```

Traditional Windows installer with Start Menu integration.

## File Sizes

Expected sizes (approximate):

| Component | Size |
|-----------|------|
| Base executable | ~50 MB |
| PyQt5 dependencies | ~60 MB |
| Torch dependencies (CPU-only) | ~180 MB |
| Audio libraries (librosa, sounddevice) | ~40 MB |
| Resemblyzer + webrtcvad | ~20 MB |
| Whisper models (if bundled) | ~500 MB |
| **Total (without models)** | **~350 MB** |
| **Total (with models)** | **~850 MB** |

### Reducing Size

To reduce size:

1. **Don't bundle AI models**:
   - Comment out model bundling in `cqsentinel.spec`
   - Download models on first run instead
   - Reduces installer to ~300 MB

2. **Use UPX compression**:
   - Install UPX: [upx.github.io](https://upx.github.io/)
   - Enable in spec: `upx=True`
   - Can reduce size by 30-50%

3. **Exclude unused features**:
   ```python
   excludes=[
       'matplotlib',  # -50 MB
       'IPython',     # -30 MB
   ]
   ```

## Troubleshooting

### "conda: command not found"

Make sure conda is initialized in PowerShell:

```powershell
& C:\Users\<YOUR_USERNAME>\radioconda\Scripts\conda.exe init powershell
# Then restart PowerShell
```

### "PyInstaller not found"

```powershell
conda activate cqsentinel
pip install pyinstaller pyinstaller-hooks-contrib
```

### "The 'typing' package is an obsolete backport and is incompatible with PyInstaller"

**Cause**: Some pip packages (like `openai-whisper`) incorrectly depend on the obsolete `typing` backport. Python 3.10 has `typing` built-in.

**Solution**:
```powershell
conda activate cqsentinel
pip uninstall typing -y
# Then rebuild
pyinstaller cqsentinel.spec
```

**Prevention**: This is automatically handled in INSTALL.md, but if you recreate your environment without following that guide, you may encounter this error.

### "ModuleNotFoundError" during build

Make sure conda environment is activated:

```powershell
conda activate cqsentinel
# Verify with:
python -c "import PyQt5; print('OK')"
```

### "Failed to execute script" when running .exe

Common causes:
- Antivirus blocking the executable
- Missing hiddenimports in `cqsentinel.spec`
- DLL conflicts

**Debug steps**:
1. Run from command prompt to see full error:
   ```powershell
   .\dist\CQSentinel\CQSentinel.exe
   ```

2. Check if dependencies are bundled:
   ```powershell
   # Should show PyQt5, torch, etc.
   dir dist\CQSentinel\_internal\
   ```

3. Add missing imports to `cqsentinel.spec`:
   ```python
   hiddenimports=[
       'PyQt5.QtCore',
       'PyQt5.QtWidgets',
       'torch',
       'resemblyzer',
       'your.missing.module',
   ]
   ```

### Missing DLL errors

If end users see "VCRUNTIME140.dll not found":
- They need [Visual C++ Redistributable](https://aka.ms/vs/17/release/vc_redist.x64.exe)
- Or bundle DLLs in PyInstaller build

### Import errors at runtime

**Error**: "No module named 'PyQt5'"

This means PyQt5 wasn't bundled. Check:
1. Is conda environment activated during build?
2. Is PyQt5 installed? `conda list pyqt`
3. Add to hiddenimports in `cqsentinel.spec`

### "Permission denied" during build

- Close any running instances of CQSentinel
- Close any file explorers viewing dist/
- Run PowerShell as Administrator
- Manually delete build/ and dist/:
  ```powershell
  Remove-Item -Recurse -Force build, dist
  ```

### Build succeeds but exe crashes immediately

Check dependencies are from conda, not mixed sources:

```powershell
conda activate cqsentinel
conda list  # Should show PyQt5, torch, etc. from conda-forge/pytorch
```

If you see mixed pip/conda packages, recreate environment:

```powershell
conda env remove -n cqsentinel
conda create -n cqsentinel python=3.10
conda activate cqsentinel
conda env update -f environment.yml
```

### Large executable size

See "Reducing Size" section above

## CI/CD Build (Advanced)

For automated builds with GitHub Actions:

```yaml
# .github/workflows/build.yml
name: Build Windows Executable

on: [push, pull_request]

jobs:
  build:
    runs-on: windows-latest
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-python@v4
        with:
          python-version: '3.10'

      - name: Install dependencies
        run: |
          pip install -r requirements.txt
          pip install pyinstaller

      - name: Build executable
        run: python scripts/build_windows.py --clean --zip

      - name: Upload artifact
        uses: actions/upload-artifact@v3
        with:
          name: CQSentinel-Windows
          path: CQSentinel-windows-portable.zip
```

## Testing the Build

### 1. Test locally

```bash
# Run the built executable
dist\CQSentinel\CQSentinel.exe

# Or install and test installer
Output\CQSentinel-Setup-0.1.0.exe
```

### 2. Test on clean system

- Test on Windows VM without Python installed
- Verify all dependencies are bundled
- Check for missing DLL errors

### 3. Checklist

- [ ] Executable runs without Python installed
- [ ] GUI appears correctly
- [ ] Can connect to rigctld
- [ ] Audio device detection works
- [ ] Configuration saves correctly
- [ ] No console window appears (windowed mode)
- [ ] Icon displays correctly
- [ ] About dialog shows version

## Distribution

### For End Users

**Option 1: Portable ZIP**
- Best for: Tech-savvy users, testing
- Distribute: `CQSentinel-windows-portable.zip`
- Usage: Extract and run `CQSentinel.exe`

**Option 2: Installer**
- Best for: General users
- Distribute: `CQSentinel-Setup-0.1.0.exe`
- Usage: Double-click to install

**Option 3: GitHub Releases**
- Upload both ZIP and installer to GitHub Releases
- Include checksums (SHA256)
- Provide release notes

### Example Release

```
CQSentinel v0.1.0 - Phase 1 Release

Files:
- CQSentinel-Setup-0.1.0.exe (850 MB) - Windows Installer
- CQSentinel-windows-portable.zip (820 MB) - Portable ZIP
- checksums.txt - SHA256 hashes

Requirements:
- Windows 10/11 (64-bit)
- Hamlib rigctld for radio control
- Amateur radio license

Installation:
See INSTALL.md for detailed instructions
```

## Code Signing (Future)

For production releases, sign the executable:

```bash
# Requires code signing certificate
signtool sign /f certificate.pfx /p password /t http://timestamp.server dist\CQSentinel\CQSentinel.exe
```

This prevents Windows SmartScreen warnings.

## Summary

### Quick Reference

**Prerequisites**: Follow INSTALL.md to set up conda environment with all dependencies

**Build command**:
```powershell
conda activate cqsentinel
pyinstaller cqsentinel.spec
```

**Output files**:
- Executable: `dist/CQSentinel/CQSentinel.exe`
- Portable ZIP: `CQSentinel-windows-portable.zip` (~350 MB without models)
- Installer (optional): `Output/CQSentinel-Setup-0.1.0.exe`

**Key points**:
- ✅ Environment must be set up via INSTALL.md first
- ✅ Always activate `cqsentinel` conda environment before building
- ✅ Test the .exe on a clean machine without Python installed
- ✅ Use conda-forge packages to avoid compilation issues

**Done!** You now have a distributable Windows executable.
