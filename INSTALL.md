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
