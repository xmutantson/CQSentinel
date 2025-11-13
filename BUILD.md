# Building CQSentinel for Windows

This guide explains how to build a self-contained Windows executable for CQSentinel.

## Prerequisites

### 1. Python 3.10+

Download and install from [python.org](https://www.python.org/downloads/)

During installation, **check "Add Python to PATH"**

### 2. PyInstaller

```bash
pip install pyinstaller
```

### 3. All Dependencies

```bash
pip install -r requirements.txt
```

### 4. Inno Setup (Optional - for installer)

Download from [jrsoftware.org/isinfo.php](https://jrsoftware.org/isinfo.php)

Only needed if you want to create a Windows installer (.exe setup file)

## Build Methods

### Method 1: Quick Build (Recommended)

**Windows users:**

```bash
scripts\build_windows.bat
```

This will:
- Check dependencies
- Build executable with PyInstaller
- Create portable ZIP file
- Output to `dist/CQSentinel/`

**Linux/Mac users (cross-compile not recommended):**

```bash
python scripts/build_windows.py --clean --zip
```

### Method 2: Manual PyInstaller

```bash
# Clean previous builds
rmdir /s /q build dist

# Build with spec file
pyinstaller cqsentinel.spec

# Output: dist/CQSentinel/CQSentinel.exe
```

### Method 3: Direct PyInstaller (without spec)

```bash
pyinstaller --name CQSentinel ^
            --windowed ^
            --onedir ^
            --add-data "models;models" ^
            --hidden-import PyQt6 ^
            --hidden-import torch ^
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
    │   ├── PyQt6/
    │   ├── torch/
    │   ├── librosa/
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
| PyQt6 dependencies | ~80 MB |
| Torch dependencies | ~200 MB |
| Whisper models | ~500 MB |
| **Total (with models)** | **~800 MB - 1 GB** |

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

### "PyInstaller not found"

```bash
pip install pyinstaller
```

### "Failed to execute script"

- Check antivirus isn't blocking
- Run from command prompt to see error message
- Check `cqsentinel.spec` hiddenimports

### Missing DLL errors

Common fixes:
- Install Visual C++ Redistributable
- Use `--hidden-import` for missing modules
- Check PyInstaller hooks

### Import errors at runtime

Add to `cqsentinel.spec`:
```python
hiddenimports=[
    'your.missing.module',
]
```

### "Permission denied" during build

- Close any running instances
- Run as Administrator
- Delete `build/` and `dist/` manually

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

**Quick build:**
```bash
scripts\build_windows.bat
```

**Output:**
- `dist/CQSentinel/CQSentinel.exe`
- `CQSentinel-windows-portable.zip`

**For installer:**
```bash
# 1. Build executable
scripts\build_windows.bat

# 2. Open Inno Setup
# 3. Compile scripts/build_installer.iss
# 4. Get Output/CQSentinel-Setup-0.1.0.exe
```

**Done!** You now have a distributable Windows executable.
