# CQSentinel Installation Guide

## ⚠️ Windows Users: Read This First!

CQSentinel has complex dependencies (PyQt6, PyTorch, audio libraries) that can be challenging on Windows. **We strongly recommend using Conda** for installation.

### Quick Start (Windows with Conda/Radioconda)

You have **radioconda** installed! Here's the fastest way to get started:

```cmd
# Open Anaconda Prompt (radioconda)
conda create -n cqsentinel python=3.10
conda activate cqsentinel

# Navigate to CQSentinel directory
cd X:\Storage\Documents\CQSentinel

# Install using environment.yml
conda env update -f environment.yml

# OR install manually:
conda install -c conda-forge pyqt librosa numpy scipy pyyaml tqdm sounddevice
conda install pytorch torchaudio -c pytorch
pip install faster-whisper resemblyzer noisereduce silero-vad
```

**Then in VSCode**: Press `Ctrl+Shift+P` → "Python: Select Interpreter" → Choose `cqsentinel` environment

**Common Issue**: If you see `PyQt6 build failed`, you're using MSYS2/MinGW Python. Switch to conda or native Windows Python.

---

## Windows Development Setup (For Full Features)

### Installing Voice Fingerprinting Support

Voice fingerprinting (Phase 4 feature) requires compiling native C++ extensions. **Two options**:

---

#### Option A: Build with WSL Ubuntu (Recommended)

If you have WSL Ubuntu, this is **much faster** than installing Visual Studio Build Tools (no 6-8 GB download!).

**Step 1: Install build tools in WSL**

Open **Ubuntu** in WSL:

```bash
# Update packages
sudo apt update

# Install build tools
sudo apt install -y python3.10 python3.10-dev python3-pip build-essential

# Verify
python3.10 --version
gcc --version
```

**Step 2: Build webrtcvad wheel in WSL**

In WSL Ubuntu terminal:

```bash
# Install wheel builder
pip3 install wheel setuptools

# Download and build webrtcvad
pip3 download webrtcvad --no-binary webrtcvad
tar -xzf webrtcvad-*.tar.gz
cd webrtcvad-*

# Build wheel
python3.10 setup.py bdist_wheel

# Wheel is created in dist/
ls dist/
# webrtcvad-2.0.10-cp310-cp310-linux_x86_64.whl
```

**Step 3: Install in Windows conda environment**

Copy the wheel to Windows and install it:

In **WSL**:
```bash
# Copy wheel to Windows filesystem
cp dist/webrtcvad-*.whl /mnt/x/Storage/Documents/CQSentinel/
```

In **Windows PowerShell** (VSCode terminal with cqsentinel activated):
```powershell
# Install the wheel
pip install webrtcvad-2.0.10-cp310-cp310-linux_x86_64.whl

# Install resemblyzer
pip install resemblyzer

# Verify
python -c "from resemblyzer import VoiceEncoder; print('✓ Voice fingerprinting ready')"
```

**Note**: The Linux wheel **won't work** on Windows. We need to build for Windows in WSL. See **Option B** below for cross-compilation.

---

#### Option B: Cross-compile for Windows in WSL (Advanced)

Install MinGW cross-compiler in WSL to build Windows DLLs:

```bash
# In WSL Ubuntu
sudo apt install -y mingw-w64 python3-pip

# Install crossenv for cross-compilation
pip3 install crossenv

# This is complex - use Option C instead
```

---

#### Option C: Use Pre-built Wheel (Easiest)

Try a pre-built Windows wheel (if available):

In **Windows PowerShell** (cqsentinel environment):

```powershell
# Try installing from wheel repository
pip install --only-binary :all: webrtcvad

# If that fails, try direct URL
pip install https://files.pythonhosted.org/packages/.../webrtcvad-2.0.10-cp310-cp310-win_amd64.whl

# Then install resemblyzer
pip install resemblyzer
```

---

#### Option D: Visual Studio Build Tools (Original Method)

**Download**: https://visualstudio.microsoft.com/visual-cpp-build-tools/

Or direct link: https://aka.ms/vs/17/release/vs_BuildTools.exe

**Installation Steps**:
1. Run `vs_BuildTools.exe`
2. In the installer, select **"Desktop development with C++"**
3. In the right panel, ensure these are checked:
   - ✅ **MSVC v143 - VS 2022 C++ x64/x86 build tools** (latest)
   - ✅ **Windows 11 SDK** (or Windows 10 SDK)
   - ✅ **C++ CMake tools for Windows**
4. Click **Install**
5. **Download size**: ~6-8 GB
6. **Install time**: ~10-15 minutes
7. **Restart your computer** after installation completes

#### 2. Enable Resemblyzer in environment.yml

After installing Build Tools, uncomment resemblyzer:

**Edit `environment.yml` line 63**:
```yaml
# BEFORE (commented out):
# - resemblyzer>=0.1.1  # Uncomment after installing Visual Studio Build Tools

# AFTER (uncommented):
- resemblyzer>=0.1.1  # Voice fingerprinting
```

#### 3. Install Voice Fingerprinting Package

In **VSCode PowerShell** (with `cqsentinel` environment activated):

```powershell
# After restarting computer, activate environment
conda activate cqsentinel

# Install resemblyzer (will compile webrtcvad)
pip install resemblyzer

# Verify installation
python -c "from resemblyzer import VoiceEncoder; print('✓ Voice fingerprinting ready')"
```

**Expected output**:
```
Downloading Resemblyzer model...
✓ Voice fingerprinting ready
```

#### 4. Verify in VSCode

Test that all imports work:

```powershell
# Test all critical imports
python -c "import torch; print('✓ PyTorch')"
python -c "from PyQt5 import QtCore; print('✓ PyQt5')"
python -c "import librosa; print('✓ librosa')"
python -c "import faster_whisper; print('✓ Whisper')"
python -c "from resemblyzer import VoiceEncoder; print('✓ Resemblyzer')"
```

All should show ✓ checkmarks.

---

### VSCode Setup for Development

#### 1. Initialize Conda in PowerShell (One-Time)

In VSCode's integrated PowerShell terminal:

```powershell
# Initialize conda
& C:\Users\<YOUR_USERNAME>\radioconda\Scripts\conda.exe init powershell

# Restart terminal (click trash icon, open new terminal)
```

After restart, you should see `(base)` in your prompt.

#### 2. Set Execution Policy (One-Time)

If you see "scripts disabled" error:

```powershell
# Allow scripts for current user
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser

# Type: Y and press Enter
```

#### 3. Select Python Interpreter

In VSCode:
1. Press **`Ctrl+Shift+P`**
2. Type: **"Python: Select Interpreter"**
3. Choose: **`Python 3.10.x ('cqsentinel')`**

Verify in bottom-left status bar: should show `3.10.x ('cqsentinel')`

#### 4. Configure VSCode Settings (Optional)

Create `.vscode/settings.json` in your project root:

```json
{
    "python.defaultInterpreterPath": "C:\\Users\\<YOUR_USERNAME>\\radioconda\\envs\\cqsentinel\\python.exe",
    "python.terminal.activateEnvironment": true,
    "terminal.integrated.defaultProfile.windows": "PowerShell",
    "python.linting.enabled": true,
    "python.linting.flake8Enabled": true,
    "python.formatting.provider": "black",
    "editor.formatOnSave": true
}
```

Replace `<YOUR_USERNAME>` with your Windows username.

---

### Troubleshooting Build Errors

#### Error: "Microsoft Visual C++ 14.0 or greater is required"

**Cause**: Build Tools not installed or not found

**Solutions**:
1. Install Visual Studio Build Tools (see above)
2. Restart computer after installation
3. Verify installation:
   ```powershell
   # Check if cl.exe (C++ compiler) is accessible
   & "C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools\VC\Auxiliary\Build\vcvars64.bat"
   cl
   ```

#### Error: "conda: command not found" in PowerShell

**Cause**: Conda not initialized in PowerShell

**Solution**:
```powershell
# Initialize conda for PowerShell
& C:\Users\<YOUR_USERNAME>\radioconda\Scripts\conda.exe init powershell

# Restart terminal
```

#### Error: "Failed building wheel for webrtcvad"

**Cause**: Build Tools missing components

**Solution**:
1. Re-run Build Tools installer
2. Ensure "Desktop development with C++" is selected
3. Ensure "MSVC" and "Windows SDK" are checked
4. Restart computer

#### Import Error After Installation

**Verify each package individually**:

```powershell
python -c "import torch; print('PyTorch version:', torch.__version__)"
python -c "import librosa; print('librosa version:', librosa.__version__)"
python -c "from resemblyzer import VoiceEncoder; print('Resemblyzer OK')"
```

If any fail, reinstall that specific package:
```powershell
pip uninstall <package-name>
pip install <package-name>
```

---

## Prerequisites

### 1. Python 3.10 or higher

**Windows**:
```bash
# Download from python.org
# During installation, check "Add Python to PATH"
```

**Linux (Ubuntu/Debian)**:
```bash
sudo apt update
sudo apt install python3.10 python3-pip python3-venv
```

### 2. Hamlib (for CAT control)

**Windows**:
1. Download Hamlib from: https://github.com/Hamlib/Hamlib/releases
2. Extract to `C:\Program Files\Hamlib`
3. Add `C:\Program Files\Hamlib\bin` to PATH

**Linux**:
```bash
sudo apt install libhamlib-utils
```

**macOS**:
```bash
brew install hamlib
```

### 3. PortAudio (for audio capture)

**Windows**:
- Included with sounddevice package

**Linux**:
```bash
sudo apt install portaudio19-dev python3-pyaudio
```

**macOS**:
```bash
brew install portaudio
```

## Installation Methods

### Method 1: Install from Source (Development)

```bash
# Clone repository
git clone https://github.com/xmutantson/CQSentinel.git
cd CQSentinel

# Create virtual environment
python3 -m venv venv

# Activate virtual environment
# Windows:
venv\Scripts\activate
# Linux/Mac:
source venv/bin/activate

# Install dependencies
pip install --upgrade pip
pip install -e .

# Download AI models (requires internet)
python scripts/download_models.py
```

### Method 2: Install from PyPI (Coming Soon)

```bash
pip install cqsentinel
```

### Method 3: Windows Executable (Coming Soon)

Download `CQSentinel-Setup.exe` from releases page.

## Radio Setup

### Starting rigctld

**For Icom IC-705**:
```bash
# USB connection
rigctld -m 3085 -r /dev/ttyUSB0 -s 115200

# Network connection (if using wfview or other server)
rigctld -m 3085 -r localhost:4533 -s 115200
```

**For other radios**:
```bash
# Find your radio model number
rigctl -l | grep "Your Radio Brand"

# Start rigctld with your model number
rigctld -m YOUR_MODEL_NUMBER -r YOUR_SERIAL_PORT -s YOUR_BAUD_RATE
```

Common model numbers:
- IC-705: 3085
- IC-7300: 3073
- FT-891: 1035
- TS-590SG: 2014

## Audio Setup

### Windows

1. Plug in IC-705 via USB
2. Windows will install drivers automatically
3. Open CQSentinel
4. Audio device should be auto-detected as "IC-705"

### Linux

```bash
# List audio devices
arecord -l

# Test audio capture
arecord -d 5 -f cd test.wav

# If IC-705 not detected, may need to configure ALSA/PulseAudio
```

## Running CQSentinel

```bash
# Activate virtual environment (if using)
source venv/bin/activate  # Linux/Mac
venv\Scripts\activate     # Windows

# Run application
cqsentinel

# Or run directly
python -m cqsentinel.main
```

## First Run Checklist

1. ✓ Python 3.10+ installed
2. ✓ Hamlib installed
3. ✓ CQSentinel dependencies installed
4. ✓ AI models downloaded
5. ✓ Radio connected via USB
6. ✓ rigctld running
7. ✓ Audio device detected

## Troubleshooting

### "Failed to connect to rigctld"

- Is rigctld running? Check with `ps aux | grep rigctld`
- Is the port correct? Default is 4532
- Try: `telnet localhost 4532` then type `f` (should return frequency)

### "No audio devices found"

- Check USB connection to radio
- Linux: Check `arecord -l` output
- Windows: Check Device Manager > Sound devices

### "Model download failed"

- Check internet connection
- Try manual download: `python scripts/download_models.py`
- Check disk space (need ~1 GB free)

### "Import error: No module named 'PyQt6'"

```bash
pip install PyQt6
```

### Permission denied on Linux serial port

```bash
sudo usermod -a -G dialout $USER
# Log out and back in
```

## Advanced Configuration

Edit `~/.cqsentinel/config.yaml`:

```yaml
radio:
  model: "Icom IC-705"
  rigctld_host: "localhost"
  rigctld_port: 4532

audio:
  sample_rate: 16000
  whisper_model_size: "small"

scan:
  step_size_hz: 1000
  dwell_with_voice_sec: 60
```

## Updating

```bash
# From source
cd CQSentinel
git pull
pip install -e . --upgrade

# From PyPI (when available)
pip install --upgrade cqsentinel
```

## Uninstallation

```bash
# Remove package
pip uninstall cqsentinel

# Remove config and data
rm -rf ~/.cqsentinel

# Remove models cache (optional)
rm -rf ~/.cache/huggingface
rm -rf ~/.cache/torch
```

## Getting Help

- GitHub Issues: https://github.com/xmutantson/CQSentinel/issues
- Documentation: See `docs/` folder
- Hamlib documentation: https://hamlib.github.io/

## Next Steps

After installation, see:
- `docs/user_guide.md` - How to use CQSentinel
- `docs/contest_profiles.md` - Setting up for specific contests
- `PROJECT_PLAN.md` - Technical details and roadmap
