# CQSentinel

**The First SSB Contest Band Scanner with AI Voice Recognition**

[![License: TBD](https://img.shields.io/badge/License-TBD-blue.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Status: Planning](https://img.shields.io/badge/status-planning-yellow.svg)](PROJECT_PLAN.md)

## What is CQSentinel?

CQSentinel is a Windows application that automatically scans SSB phone segments during ham radio contests, uses AI to identify contest activity, fingerprints operator voices, and integrates with N3FJP logging software.

Think **"CW Skimmer for SSB"** - the tool contesters have wanted for 15+ years, now finally feasible with modern AI.

## Key Features

- **Universal Radio Support**: Works with 200+ radios via Hamlib (primary target: Icom IC-705)
- **Intelligent SSB Auto-Centering**: Uses speech F0 detection to accurately tune signals (not naive fixed-frequency assumptions)
- **Voice Fingerprinting**: Tracks operators by voice across frequencies, not just by frequency
- **Offline AI Processing**: All speech recognition runs locally - no cloud dependencies
- **Contest-Aware**: Pre-configured profiles for Field Day, Winter Field Day, CQWW, CQWPX, WA Salmon Run
- **N3FJP Integration**: Real-time dupe checking and multiplier highlighting
- **Waterfall Band Map**: Visual representation of contest activity across the band

## How It Works

```
Radio (IC-705) → CAT Control + Audio
    ↓
Scan Phone Segments (configurable bands)
    ↓
AI Auto-Center Signal (F0 pitch detection)
    ↓
Noise Reduction (RNNoise) → Voice Detection (Silero VAD)
    ↓
Speech-to-Text (Whisper offline) + Voice ID (Resemblyzer)
    ↓
Contest Behavior Detection (contestness scoring)
    ↓
N3FJP Dupe Check → Band Map Display
```

## Technology Stack

- **Python 3.10+** with PyQt6 GUI
- **Hamlib** for CAT control
- **faster-whisper** for offline speech recognition
- **Resemblyzer** for voice fingerprinting (256-dim embeddings)
- **librosa pYIN** for F0-based SSB centering
- **RNNoise** for audio cleanup
- **PyHamTools** for callsign validation

**100% offline** - all models bundled, no internet required.

## The Innovation: Voice-Independent SSB Auto-Centering

Previous attempts at SSB auto-tuning assumed a fixed audio center frequency (e.g., 1500 Hz). **This is wrong** because different voices have different fundamental frequencies:

- Male: 80-180 Hz
- Female: 165-255 Hz
- Children: 250-450 Hz

**CQSentinel uses speech F0 (pitch) detection** to determine if the signal is properly tuned:
1. Extract fundamental frequency using **pYIN** algorithm
2. Check if F0 is in normal human speech range (75-400 Hz)
3. If not, calculate offset and retune
4. Validate with spectral energy distribution

**Result**: Accurate auto-centering for any voice, any accent, USB or LSB.

## Why This Matters

### For Contesters

- **Find new stations faster**: Automated band scanning reveals contest activity you'd miss manually
- **Never work the same op twice**: Voice fingerprinting tracks operators even if they QSY
- **Maximize multipliers**: Visual band map highlights new sections/zones/DXCCs
- **Save time**: Let the computer scan while you make QSOs

### For the Ham Radio Community

- **First practical SSB Skimmer**: Fills a gap that's existed since CW Skimmer in 2009
- **Open source**: Community can contribute, extend, improve
- **Privacy-focused**: No cloud, no tracking, runs entirely on your PC
- **Educational**: Demonstrates modern AI applied to ham radio

## Project Status

**Current Phase**: Planning (as of November 2025)

See [PROJECT_PLAN.md](PROJECT_PLAN.md) for complete technical specification and development roadmap.

**Estimated Timeline**: 20-26 weeks (~5-6 months)
**Target First Release**: Q2 2026 (Field Day 2026)

## Development Roadmap

1. **Phase 1**: Core Infrastructure (CAT + audio + basic GUI)
2. **Phase 2**: Audio Intelligence (noise reduction, VAD, ASR)
3. **Phase 3**: SSB Auto-Centering (F0 detection)
4. **Phase 4**: Voice Fingerprinting (speaker diarization)
5. **Phase 5**: Contest Logic (behavior detection, exchange parsing)
6. **Phase 6**: Band Map GUI (visualization)
7. **Phase 7**: N3FJP Integration (dupe checking)
8. **Phase 8**: Band Scanning Engine (automated sweeping)
9. **Phase 9**: Contest Profiles (FD, WFD, CQWW, CQWPX, Salmon Run)
10. **Phase 10**: Polish & Distribution (packaging, docs, testing)

## Quick Start (Coming Soon)

```bash
# Installation (future)
pip install cqsentinel

# Or download Windows installer
# CQSentinel-1.0-setup.exe

# Run
cqsentinel
```

## Documentation

- **[PROJECT_PLAN.md](PROJECT_PLAN.md)** - Complete technical specification
- **User Guide** - Coming soon
- **Developer Guide** - Coming soon
- **API Reference** - Coming soon

## Hardware Requirements

**Minimum**:
- Windows 10/11 (64-bit)
- Intel i5 8th gen or equivalent
- 4 GB RAM
- USB port for radio connection
- Hamlib-compatible radio (200+ models supported)

**Recommended**:
- Intel i7 or AMD Ryzen 7
- 8 GB RAM
- GPU (optional, for CREPE high-accuracy pitch detection)
- Icom IC-705 or similar modern transceiver

## Software Requirements

- **Python 3.10+**
- **Hamlib** (rigctld)
- **N3FJP Logging Software** (optional, for dupe checking)

All AI models are bundled with the application (~800 MB total).

## Contest Profiles Included

1. **ARRL Field Day** - Class + Section
2. **Winter Field Day** - Class + Section
3. **CQ World Wide DX** - RST + CQ Zone
4. **CQ WPX** - RST + Serial
5. **Washington State Salmon Run** - RST + County/SPC

More profiles can be added by the community.

## Research & Prior Art

Our research confirmed that **no SSB skimmer currently exists**:

- CW Skimmer (VE3NEA) revolutionized CW contesting in 2009
- Digital skimmers exist for PSK, RTTY, FT8
- SSB Skimmer has been discussed as "conceptual" since 2010
- No turnkey product has shipped as of 2025

**CQSentinel is the first practical implementation.**

Key academic references:
- YIN/pYIN pitch detection algorithms (De Cheveigné 2002, Mauch 2014)
- CREPE neural pitch tracking (Kim 2018)
- Whisper speech recognition (Radford 2022)
- Resemblyzer speaker embeddings (Wan 2018)
- SSB AFC patents (US4625331A)

## Contributing

**Project is in planning phase.** Contributions will be welcome once Phase 1 begins.

Areas where help will be needed:
- Testing with various radio models
- Contest profile development
- GUI/UX design
- Documentation
- Translation (future)

## License

TBD (likely MIT or GPL v3)

## Acknowledgments

- **VE3NEA** for pioneering CW Skimmer, inspiring this project
- **OpenAI** for Whisper speech recognition
- **Resemble.AI** for Resemblyzer voice encoder
- **Hamlib team** for universal radio control
- **N3FJP** for excellent logging software and open API
- The entire **ham radio contesting community** for feedback and inspiration

## Contact

- **Project Repository**: https://github.com/xmutantson/CQSentinel
- **Issues**: https://github.com/xmutantson/CQSentinel/issues
- **Discussions**: https://github.com/xmutantson/CQSentinel/discussions

## Disclaimer

This software is for **receive-only monitoring** and must be operated by a licensed amateur radio operator in compliance with local regulations. It does not transmit, does not auto-post to DX clusters, and does not violate assisted/unassisted contest rules when used properly.

**73 de CQSentinel Team**

---

*"Bringing AI to SSB Contesting - One QSO at a Time"*
