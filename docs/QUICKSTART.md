# CQSentinel Quick Start Guide

## What's Working Now (Phase 1)

✅ **Radio CAT Control** via Hamlib
✅ **Audio Device Detection**
✅ **Basic GUI** with frequency/mode/S-meter display
✅ **Configuration System**
✅ **Logging Framework**

## Testing Phase 1

### 1. Install Dependencies

```bash
# Create virtual environment
python3 -m venv venv
source venv/bin/activate  # Linux/Mac
# or
venv\Scripts\activate  # Windows

# Install requirements
pip install PyQt6 sounddevice colorlog pyyaml numpy
```

### 2. Start rigctld (Simulated Radio)

If you don't have a physical radio, use Hamlib's dummy mode:

```bash
# Install Hamlib
sudo apt install libhamlib-utils  # Linux
brew install hamlib                # Mac

# Start dummy rigctld (no hardware needed)
rigctld -m 1 -r /dev/null
```

For **Icom IC-705**:
```bash
rigctld -m 3085 -r /dev/ttyUSB0 -s 115200
```

### 3. Run CQSentinel

```bash
# From project root
python -m cqsentinel.main
```

You should see:
1. Main window with band checkboxes
2. "Connect Radio" button
3. Frequency display (0.000 MHz initially)
4. Log panel with instructions

### 4. Test Radio Connection

1. Click **"Connect Radio"** button
2. If rigctld is running, you'll see:
   - "Connected to radio: X.XXX MHz, USB"
   - Frequency display updates
   - S-meter shows signal strength
   - Button changes to "Disconnect Radio"

### 5. Test Audio Device Detection

```python
# Test script: test_audio.py
from cqsentinel.audio import list_audio_devices

devices = list_audio_devices()
for dev in devices:
    print(f"[{dev.index}] {dev.name}")
    print(f"    Channels: {dev.channels}, Rate: {dev.sample_rate} Hz")
    if dev.is_default:
        print("    (DEFAULT)")
```

Run: `python test_audio.py`

### 6. Test Configuration

```python
# Test script: test_config.py
from cqsentinel.config import get_config_manager

manager = get_config_manager()
config = manager.load()

print(f"Radio: {config.radio.model}")
print(f"rigctld: {config.radio.rigctld_host}:{config.radio.rigctld_port}")
print(f"Bands: {config.scan.enabled_bands}")

# Modify and save
config.scan.enabled_bands = ["20m", "40m", "15m"]
manager.save()

print("Config saved to:", manager.config_file)
```

Run: `python test_config.py`

## Current Functionality

### GUI Features

- **Band Selection**: Checkboxes for 160m-10m
- **Contest Profile**: Dropdown (UI only, not functional yet)
- **Radio Control**:
  - Connect/Disconnect
  - Real-time frequency display (updates every 1 second)
  - Mode display (USB/LSB/etc.)
  - S-meter reading
- **Activity Log**: Text display for messages
- **Menu System**: File, Radio, Help menus

### Radio Control (via Hamlib)

```python
from cqsentinel.radio import HamlibController

radio = HamlibController(host="localhost", port=4532)
radio.connect()

# Get info
freq = radio.get_frequency()
mode, bw = radio.get_mode()
strength = radio.get_strength()

print(f"Frequency: {freq/1e6:.3f} MHz")
print(f"Mode: {mode}, BW: {bw} Hz")
print(f"S-meter: {strength}")

# Set frequency
radio.set_frequency(14_250_000)  # 14.250 MHz

# Set mode
radio.set_mode("USB", 2400)

radio.disconnect()
```

### Audio Capture

```python
from cqsentinel.audio import AudioCapture
import numpy as np

# Record 5 seconds
audio = AudioCapture(sample_rate=16000)
recording = audio.record(duration=5.0)

print(f"Recorded {len(recording)} samples")
print(f"Max amplitude: {np.max(np.abs(recording))}")

# Streaming mode
def callback(audio_chunk):
    print(f"Received {len(audio_chunk)} samples")

audio.start_stream(callback)
# ... audio streams continuously ...
audio.stop_stream()
```

## What's NOT Working Yet

❌ Band scanning
❌ Speech recognition (Whisper)
❌ Voice fingerprinting
❌ SSB auto-centering
❌ Contest behavior detection
❌ N3FJP integration
❌ Band map visualization

These features will be added in Phases 2-10 (see PROJECT_PLAN.md).

## Troubleshooting

### "Failed to connect to rigctld"

```bash
# Check if rigctld is running
ps aux | grep rigctld

# Test manually
telnet localhost 4532
f   # Should return frequency
```

### "ModuleNotFoundError: No module named 'PyQt6'"

```bash
pip install PyQt6
```

### "No audio devices found"

- Check USB connection to radio
- Run: `python -m sounddevice` to list devices
- Linux: May need `sudo apt install portaudio19-dev`

### rigctld not found

```bash
# Linux
sudo apt install libhamlib-utils

# Mac
brew install hamlib

# Windows
# Download from: https://github.com/Hamlib/Hamlib/releases
```

## File Structure

```
CQSentinel/
├── cqsentinel/
│   ├── __init__.py         # Package metadata
│   ├── main.py             # Application entry point
│   ├── config.py           # Configuration management
│   ├── audio/
│   │   ├── __init__.py
│   │   └── capture.py      # Audio I/O
│   ├── radio/
│   │   ├── __init__.py
│   │   └── hamlib_controller.py  # CAT control
│   ├── gui/
│   │   ├── __init__.py
│   │   └── main_window.py  # Main GUI
│   └── utils/
│       ├── __init__.py
│       └── logging.py      # Logging setup
├── requirements.txt
├── setup.py
├── README.md
├── PROJECT_PLAN.md
├── INSTALL.md
└── QUICKSTART.md (this file)
```

## Next Steps

Phase 1 is complete! Next development phases:

- **Phase 2**: Audio Processing (RNNoise, VAD, Whisper ASR)
- **Phase 3**: SSB Auto-Centering (F0 pitch detection)
- **Phase 4**: Voice Fingerprinting (Resemblyzer)

See PROJECT_PLAN.md for full roadmap.

## Running Tests

```bash
# Test radio controller
python -m pytest tests/test_radio.py -v

# Test audio capture
python -m pytest tests/test_audio.py -v

# Run all tests
python -m pytest tests/ -v
```

*(Tests not yet implemented)*

## Getting Help

- **Documentation**: See `docs/` folder
- **GitHub Issues**: https://github.com/xmutantson/CQSentinel/issues
- **PROJECT_PLAN.md**: Complete technical specification

## Example Session

```bash
$ source venv/bin/activate
$ rigctld -m 1 -r /dev/null &  # Start dummy rigctld
$ python -m cqsentinel.main

[GUI appears]
Click "Connect Radio"
→ "Connected to radio: 14.250 MHz, USB"
→ S-meter shows S0-S9
→ Frequency updates every second

[Working!]
```

## License

TBD (likely MIT or GPL v3)

---

**73 de CQSentinel Team**
*Phase 1 Complete - Radio Control & GUI Foundation*
