# CQSentinel AI Models

This directory contains the AI models used by CQSentinel for speech recognition, voice fingerprinting, and audio processing.

## Required Models

### 1. Whisper (Speech-to-Text)

**faster-whisper** models will be downloaded automatically on first run.

Manual download (optional):
```bash
python -c "from faster_whisper import WhisperModel; WhisperModel('small', device='cpu', compute_type='int8')"
```

Model sizes:
- **tiny**: 39 MB, fastest, least accurate
- **base**: 74 MB
- **small**: 244 MB (RECOMMENDED)
- **medium**: 769 MB
- **large**: 1550 MB

### 2. Silero VAD (Voice Activity Detection)

Downloads automatically on first use via `silero-vad` package.

### 3. Resemblyzer (Voice Fingerprinting)

Downloads automatically on first import.

### 4. RNNoise (Noise Reduction)

Included with `noisereduce` package, no separate download needed.

## Optional Models

### CREPE (GPU-Accelerated Pitch Detection)

For high-accuracy SSB auto-centering on systems with GPU:

```bash
pip install crepe
```

Then enable in settings: `audio.use_crepe_pitch = True`

## Model Storage

Models are cached in:
- **Linux/Mac**: `~/.cache/huggingface/`, `~/.cache/torch/`
- **Windows**: `%USERPROFILE%\.cache\huggingface\`, `%USERPROFILE%\.cache\torch\`

## Disk Space Requirements

- Minimum (basic functionality): ~500 MB
- Recommended (small Whisper): ~800 MB
- Maximum (medium Whisper + CREPE): ~1.5 GB

## Network Requirements

First run requires internet connection to download models.
After initial download, CQSentinel runs **100% offline**.

## Manual Model Download Script

```python
#!/usr/bin/env python3
"""Download all CQSentinel models"""

print("Downloading Whisper model...")
from faster_whisper import WhisperModel
model = WhisperModel("small", device="cpu", compute_type="int8")
print("✓ Whisper downloaded")

print("Downloading Silero VAD...")
import torch
from silero_vad import load_silero_vad
vad = load_silero_vad()
print("✓ Silero VAD downloaded")

print("Downloading Resemblyzer...")
from resemblyzer import VoiceEncoder
encoder = VoiceEncoder()
print("✓ Resemblyzer downloaded")

print("\nAll models downloaded successfully!")
print("CQSentinel can now run offline.")
```

Save as `download_models.py` and run: `python download_models.py`
