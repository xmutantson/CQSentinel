# CQSentinel: SSB Contest Band Scanner
## Complete Project Plan & Technical Specification

**Version:** 1.0
**Last Updated:** 2025-11-13
**Status:** Planning Phase

---

## Table of Contents

1. [Executive Summary](#executive-summary)
2. [Background & Motivation](#background--motivation)
3. [System Architecture](#system-architecture)
4. [Core Features](#core-features)
5. [Technical Stack](#technical-stack)
6. [SSB Auto-Centering Algorithm](#ssb-auto-centering-algorithm)
7. [Audio Processing Pipeline](#audio-processing-pipeline)
8. [Voice Fingerprinting](#voice-fingerprinting)
9. [Contest Behavior Detection](#contest-behavior-detection)
10. [N3FJP Integration](#n3fjp-integration)
11. [User Interface Design](#user-interface-design)
12. [Contest Profiles](#contest-profiles)
13. [Configuration & Settings](#configuration--settings)
14. [Development Phases](#development-phases)
15. [Dependencies & Packaging](#dependencies--packaging)
16. [Performance Targets](#performance-targets)
17. [Known Limitations](#known-limitations)
18. [Future Enhancements](#future-enhancements)

---

## Executive Summary

**CQSentinel** is a Windows-based ham radio application that automatically scans SSB phone segments during contests, uses AI to identify contest activity, fingerprints operator voices, and integrates with N3FJP logging software. It represents the first practical implementation of a true "SSB Skimmer" for voice contesting.

### Key Innovations

- **Universal Radio Support**: Works with 200+ radio models via Hamlib (primary target: Icom IC-705)
- **Offline AI Processing**: All speech recognition, noise suppression, and voice fingerprinting runs locally
- **Voice-Based Operator Tracking**: Recognizes operators by voice across frequencies, not just frequency-based detection
- **Intelligent Auto-Centering**: Uses speech F0 (fundamental frequency) detection to accurately tune SSB signals
- **Contest-Aware**: Pre-configured profiles for major contests with exchange parsing and multiplier detection
- **Deep N3FJP Integration**: Real-time dupe checking and multiplier highlighting

### Technology Stack

- **Language**: Python 3.10+
- **GUI**: PyQt6
- **CAT Control**: Hamlib (rigctld)
- **Noise Reduction**: RNNoise (pyrnnoise)
- **Voice Activity Detection**: Silero VAD
- **Speech-to-Text**: faster-whisper (Whisper offline)
- **Voice Fingerprinting**: Resemblyzer
- **Pitch Detection**: librosa (pYIN) or CREPE
- **Ham Utilities**: PyHamTools

---

## Background & Motivation

### The Problem

Contest operators need to know:
- Where are the active contest stations on the band?
- Have I already worked this operator?
- What multipliers are available?

Currently, they rely on:
- Manual tuning and listening (time-consuming)
- DX cluster spots (often stale, SSB-only spots are rare)
- Memory (error-prone, especially in long contests)

### The SSB Skimmer Gap

**CW Skimmer** revolutionized CW contesting by automatically decoding Morse code across entire bands. However, no equivalent exists for SSB phone contests because:
- Voice recognition is harder than CW decoding
- Operator voices vary (accent, pitch, speed)
- Background noise and QRM complicate detection
- No one has integrated all the necessary technologies

**CQSentinel bridges this gap** by combining modern AI speech recognition, speaker diarization, and classic ham radio CAT control.

### Research Findings

Our research confirmed:
- **No existing SSB skimmer products** as of 2025
- **SSB Skimmer remains "conceptual"** in ham radio literature
- **All necessary building blocks exist** as separate libraries
- **Recent AI advances** (Whisper, Resemblyzer) make this feasible
- **The ham community has wanted this for 15+ years**

---

## System Architecture

### High-Level Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    CQSentinel Application                    │
│                                                              │
│  ┌──────────────┐  ┌────────────────┐  ┌─────────────────┐ │
│  │  GUI Layer   │  │ Scanner Engine │  │ Contest Engine  │ │
│  │  (PyQt6)     │  │                │  │  (Profiles)     │ │
│  │              │  │  - Band Sweep  │  │                 │ │
│  │ - Band Map   │  │  - Auto-center │  │ - FD / WFD      │ │
│  │ - Settings   │  │  - Dwell Logic │  │ - CQWW / CQWPX  │ │
│  │ - Transcript │  │                │  │ - Salmon Run    │ │
│  └──────────────┘  └────────────────┘  └─────────────────┘ │
│                                                              │
│  ┌──────────────┐  ┌────────────────┐  ┌─────────────────┐ │
│  │   CAT Ctrl   │  │  Audio DSP     │  │   N3FJP API     │ │
│  │  (Hamlib)    │  │   Pipeline     │  │   (TCP 1100)    │ │
│  │              │  │                │  │                 │ │
│  │ - rigctld    │  │ - RNNoise      │  │ - Dupe check   │ │
│  │ - Freq ctrl  │  │ - Silero VAD   │  │ - Mult check   │ │
│  │ - S-meter    │  │ - F0 Detection │  │ - Log QSO      │ │
│  │              │  │ - Whisper ASR  │  │                 │ │
│  │              │  │ - Resemblyzer  │  │                 │ │
│  └──────────────┘  └────────────────┘  └─────────────────┘ │
│                                                              │
│  ┌──────────────────────────────────────────────────────┐   │
│  │          Voice Database (Worked Operators)           │   │
│  │  - 256-dim embeddings                                │   │
│  │  - Metadata (call, freq, timestamp, exchange)        │   │
│  │  - Age tracking (warn if >5d old)                    │   │
│  └──────────────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────────────┘
         ↓                      ↓                        ↓
    ┌─────────┐          ┌───────────┐          ┌──────────────┐
    │ Radio   │          │  PC Audio │          │   N3FJP      │
    │ (USB)   │          │  Interface│          │   Logger     │
    │ IC-705  │          │  (USB)    │          │  (TCP API)   │
    └─────────┘          └───────────┘          └──────────────┘
```

### Component Interactions

1. **Scanner Engine** controls radio via CAT, captures audio
2. **Audio DSP Pipeline** processes raw audio into structured data
3. **Contest Engine** applies contest-specific logic to classify activity
4. **N3FJP API Client** checks dupes and multipliers
5. **Voice Database** maintains persistent operator identities
6. **GUI** displays results and accepts user input

---

## Core Features

### 1. Universal Radio Support

- **Hamlib Backend**: Supports 200+ radio models
- **Primary Target**: Icom IC-705 via USB
- **Connection**: Direct USB for both CAT control and audio I/O
- **Tested Rigs**: IC-705 (primary), with extensibility to any Hamlib-supported radio
- **No wfview dependency**: Direct CAT/audio over USB

### 2. Intelligent Band Scanning

**Band Coverage**:
- 160m, 80m, 40m, 20m, 15m, 10m (WARC bands excluded)
- User-selectable via checkboxes
- Sequential or prioritized scanning

**Band Plan**:
- Default: US phone segments
- Configurable band edges per band
- Examples:
  - 160m: 1.800 - 2.000 MHz
  - 40m: 7.125 - 7.300 MHz
  - 20m: 14.150 - 14.350 MHz

**Scan Strategy**:
- Configurable step size (default: 1 kHz)
- Configurable dwell time (default: 60s with voice)
- **Adaptive early exit**: Skip if no voice in 5s
- **Auto-centering**: Detect and correct off-frequency signals

### 3. SSB Auto-Centering (CRITICAL INNOVATION)

**Problem**: SSB signals must be precisely tuned for intelligible audio. Off-frequency tuning causes "Donald Duck" effect or unintelligible speech.

**Solution**: Use speech fundamental frequency (F0) detection, NOT fixed audio frequency assumptions.

**Approach**:
- Capture 2-3 second audio sample
- Extract fundamental frequency (F0) using **pYIN** or **CREPE** algorithm
- Compare F0 to expected range:
  - Normal human speech: 75-400 Hz
  - Male voices: 80-180 Hz
  - Female voices: 165-255 Hz
- Calculate frequency offset based on F0 deviation
- Retune radio and validate

**Why F0 Detection Works**:
- Voice-independent (works for any speaker)
- Robust to noise (pYIN uses probabilistic tracking)
- Real-time capable (~10ms latency)
- Does NOT assume fixed audio center frequency

**See detailed algorithm in [SSB Auto-Centering Algorithm](#ssb-auto-centering-algorithm) section.**

### 4. Advanced Audio Processing Pipeline

```
Radio USB Audio (16-bit PCM, 16 kHz mono)
    ↓
RNNoise AI Noise Suppression
    ↓
Voice Activity Detection (Silero VAD)
    ↓
Signal Centering Detection (F0 analysis) → Auto-tune if needed
    ↓
Speech-to-Text (Whisper offline)
    ↓
Speaker Diarization (Resemblyzer voice fingerprinting)
    ↓
Contest Behavior Analysis (Contestness scoring)
    ↓
Band Map Update
```

### 5. Flexible Phonetics Parsing

**NATO Phonetics**: Standard Alpha/Bravo/Charlie/etc.

**Creative Variations**: Must handle non-standard phonetics
- "Kilowatt" instead of "Kilo"
- "America" instead of "Alpha"
- "Ocean" instead of "Oscar"
- Regional variations and operator-specific phonetics

**Approach**:
- Post-process Whisper transcripts through phonetic dictionary
- Fuzzy matching for mishearings
- Callsign validation with PyHamTools
- Context-aware parsing (e.g., "five nine" → "59")

### 6. Voice Fingerprinting & Operator Tracking

**Technology**: Resemblyzer (256-dimensional voice embeddings)

**Capabilities**:
- Extract unique voiceprint from 10-30 seconds of speech
- Compare voices using cosine similarity
- Track operators across frequencies
- Persistent until manual reset

**Use Case**:
1. Operator W7XYZ works you on 14.250 MHz
2. Mark as "worked" by voice ID
3. W7XYZ QSYs to 7.240 MHz
4. CQSentinel recognizes voice → marks as DUPE automatically

**Metadata Tracked**:
- Voice embedding centroid
- First/last heard timestamps
- Frequencies heard on
- Estimated QSO count
- Contest exchange
- Worked status

**Age Warning**: Alert if database >5 days old (stale data)

### 7. Contest Behavior Classification

**Run Station Indicators**:
- One dominant voice (>60% airtime over 60s)
- Keywords: "CQ TEST", "QRZ", "contest", contest name
- Many unique callers (>3 voices in 60s)
- Short exchanges (<30s per QSO)
- High callsign density in transcript

**Ragchew Indicators**:
- 2-3 balanced speakers
- Long speaking turns (>60s)
- Conversational content, low callsign density
- No repetitive CQ pattern

**Contestness Score**: 0-100 weighted composite

### 8. N3FJP Integration

**TCP API Connection**:
- Default port: 1100 (configurable)
- Local LAN only (no internet)

**Operations**:
- **Dupe Checking**: Query if call+band+mode already worked
- **Multiplier Detection**: Identify new states/sections/countries
- **Optional Logging**: Push confirmed QSOs to N3FJP
- **Real-time Updates**: Sync with N3FJP log changes

**Visual Feedback**:
- Green: New station/multiplier
- Red: Dupe (already worked)
- Yellow: Needs checking

### 9. Waterfall-Style Band Map GUI

Visual representation showing:
- Frequency (Y-axis)
- Time (color intensity)
- Station callsigns
- Contest status (new/dupe/mult)
- Signal strength
- Contestness score
- Estimated QSO rate

**Interaction**:
- Click station → radio tunes to that frequency
- Right-click → mark as worked, ignore, etc.
- Hover → show full details (exchange, transcript)

### 10. Pre-Configured Contest Profiles

**Included Profiles**:
1. **ARRL Field Day** - Class + Section
2. **Winter Field Day** - Class + Section
3. **CQ WW DX Contest** - RST + CQ Zone
4. **CQ WPX Contest** - RST + Serial
5. **WA State Salmon Run** - RST + County/SPC

Each profile includes:
- Exchange format regex
- Common keywords/phrases
- Multiplier definitions
- Scoring rules
- Custom phonetic variations

---

## Technical Stack

### Programming Language

**Python 3.10+** (3.10 recommended for compatibility)

**Why Python**:
- Rich ecosystem for audio/ML
- Easy to package as Windows .exe
- Rapid development
- Excellent library support

### Core Libraries

| Category | Library | Purpose | Offline |
|----------|---------|---------|---------|
| **GUI** | PyQt6 | Professional cross-platform GUI | ✓ |
| **Radio Control** | Hamlib (rigctld) | CAT control for 200+ radios | ✓ |
| **Audio I/O** | sounddevice | Cross-platform audio capture | ✓ |
| **Noise Reduction** | pyrnnoise | RNNoise bindings | ✓ |
| **VAD** | silero-vad | Voice activity detection | ✓ |
| **Pitch Detection** | librosa (pYIN) | Fundamental frequency detection | ✓ |
| **Speech-to-Text** | faster-whisper | Optimized Whisper implementation | ✓ |
| **Voice Fingerprinting** | Resemblyzer | Speaker embeddings | ✓ |
| **Callsign Tools** | PyHamTools | Validation, DXCC, zones | ✓ |
| **Math/DSP** | numpy, scipy | Signal processing | ✓ |
| **ML Backend** | PyTorch | For Resemblyzer | ✓ |
| **Network** | socket (stdlib) | N3FJP TCP API | ✓ |

### Optional High-Accuracy Libraries

| Library | Purpose | Requirement |
|---------|---------|-------------|
| **CREPE** | Neural pitch tracking | GPU recommended |
| **pyannote.audio** | Advanced diarization | GPU recommended |

### Bundled AI Models

- **Whisper Small (quantized)**: ~461 MB
- **Silero VAD**: ~1.5 MB
- **Resemblyzer voice encoder**: ~20 MB
- **RNNoise model**: <1 MB

**Total app size**: ~600-800 MB (including models + Python runtime)

---

## SSB Auto-Centering Algorithm

### The Challenge

Human speech does NOT have a fixed center frequency in the audio passband. Different voices have different fundamental frequencies (F0):
- Male: 80-180 Hz
- Female: 165-255 Hz
- Children: 250-450 Hz

**Previous naive approach** (WRONG): Assume voice centers at 1500 Hz audio
**Correct approach**: Detect F0 and validate it's in expected range

### Prior Art

1. **Patent US4625331A**: SSB AFC using spectral comparison and ±100 Hz tolerance
2. **Speech Processing Research**: F0 detection via YIN/pYIN algorithms
3. **UT Dallas Research**: Deep learning for SSB frequency offset detection

### F0 Detection Fundamentals

**Fundamental Frequency (F0)**:
- The lowest frequency of a periodic waveform (vocal cord vibration rate)
- Creates harmonic structure: F0, 2×F0, 3×F0, ... (comb pattern in spectrum)

**When SSB is mis-tuned**:
- BFO reinserts carrier at wrong frequency
- Entire harmonic structure shifts up or down
- F0 appears abnormally high (>400 Hz, "Donald Duck") or low (<70 Hz, muffled)

### Multi-Method Detection Approach

#### Method 1: Pitch (F0) Detection - PRIMARY

```python
import librosa
import numpy as np

def detect_ssb_tuning(audio_chunk, sample_rate=16000):
    """
    Detect if SSB signal is properly tuned using F0 analysis
    Returns: (is_centered, estimated_offset_hz, confidence)
    """

    # Extract fundamental frequency using pYIN
    f0, voiced_flag, voiced_prob = librosa.pyin(
        audio_chunk,
        sr=sample_rate,
        fmin=50,   # Below normal speech range (detect too-low tuning)
        fmax=600   # Above normal speech range (detect too-high tuning)
    )

    # Filter to voiced segments only
    voiced_f0 = f0[voiced_flag]

    if len(voiced_f0) < 5:  # Not enough voiced speech
        return False, 0, 0.0

    # Calculate median F0 (more robust than mean)
    median_f0 = np.median(voiced_f0)
    confidence = np.mean(voiced_prob[voiced_flag])

    # Define "normal" F0 range for human speech
    NORMAL_F0_MIN = 75   # Hz
    NORMAL_F0_MAX = 400  # Hz (accommodate female and some male voices)
    IDEAL_MALE_F0 = 120  # Hz (typical male voice)

    # Check if in normal range
    if NORMAL_F0_MIN <= median_f0 <= NORMAL_F0_MAX:
        # Properly tuned
        return True, 0, confidence

    # Estimate frequency offset
    if median_f0 < NORMAL_F0_MIN:
        # F0 too low → we're tuned too low → need to tune UP
        estimated_offset = -(IDEAL_MALE_F0 - median_f0)
    elif median_f0 > NORMAL_F0_MAX:
        # F0 too high → we're tuned too high → need to tune DOWN
        estimated_offset = (median_f0 - IDEAL_MALE_F0)

    return False, estimated_offset, confidence
```

**Why librosa.pyin()**:
- Probabilistic YIN algorithm
- Robust to noise
- Returns confidence scores
- Real-time capable (~100× realtime on modern CPU)
- Well-maintained library

**Alternative: CREPE** (optional, GPU-accelerated):
- State-of-the-art neural pitch tracker
- Higher accuracy on noisy signals
- Requires TensorFlow backend
- Use in "high accuracy" mode

#### Method 2: Spectral Energy Distribution - VALIDATION

```python
def check_spectral_centering(audio_chunk, sample_rate=16000):
    """
    Check if voice energy is distributed in expected frequency range
    Validates F0-based tuning decision
    """

    # Compute FFT
    fft = np.fft.rfft(audio_chunk)
    freqs = np.fft.rfftfreq(len(audio_chunk), 1/sample_rate)
    magnitude = np.abs(fft)

    # Voice energy should be concentrated in 300-3400 Hz
    # (standard telephone bandwidth, good proxy for intelligibility)
    voice_band_mask = (freqs >= 300) & (freqs <= 3400)
    voice_energy = np.sum(magnitude[voice_band_mask])

    # Check energy outside voice band
    too_low_mask = (freqs >= 100) & (freqs < 300)
    too_high_mask = (freqs > 3400) & (freqs <= 5000)

    low_energy = np.sum(magnitude[too_low_mask])
    high_energy = np.sum(magnitude[too_high_mask])
    total_energy = np.sum(magnitude)

    # Well-tuned signal: >70% of energy in voice band
    voice_ratio = voice_energy / (total_energy + 1e-10)

    if voice_ratio > 0.7:
        return True, 0  # Well centered

    # Estimate direction of offset
    if low_energy > high_energy:
        return False, -200  # Tuned too low
    else:
        return False, +200  # Tuned too high
```

### Combined Auto-Centering Implementation

```python
class SSBAutoTuner:
    def __init__(self, radio_controller):
        self.radio = radio_controller
        self.sample_rate = 16000

    def auto_center_signal(self, initial_freq):
        """
        Automatically tune to center an SSB signal
        Returns: (final_freq, success, confidence)
        """

        max_iterations = 3
        tolerance_hz = 50  # Within 50 Hz is acceptable

        current_freq = initial_freq

        for iteration in range(max_iterations):
            # Tune radio
            self.radio.set_frequency(current_freq)
            time.sleep(0.5)  # Let AGC settle

            # Capture audio sample
            audio = self.capture_audio(duration=3.0)  # 3 second sample

            # Method 1: F0 detection (primary)
            centered, f0_offset, confidence = detect_ssb_tuning(
                audio, self.sample_rate
            )

            if centered and confidence > 0.6:
                # Method 2: Validate with spectral check
                spectral_ok, spectral_offset = check_spectral_centering(
                    audio, self.sample_rate
                )

                if spectral_ok:
                    return current_freq, True, confidence

            # Not centered - apply correction
            if abs(f0_offset) < tolerance_hz:
                # Close enough
                return current_freq, True, confidence

            # Adjust frequency
            # Note: offset direction depends on sideband
            # For USB: positive F0 offset = tune DOWN
            # For LSB: positive F0 offset = tune UP
            sideband = self.radio.get_mode()  # 'USB' or 'LSB'

            if sideband == 'USB':
                correction = -f0_offset  # Invert for USB
            else:
                correction = f0_offset   # Direct for LSB

            current_freq += correction

            logger.info(
                f"Auto-tune iteration {iteration+1}: "
                f"Offset={f0_offset} Hz, New freq={current_freq/1e6:.4f} MHz"
            )

        # Max iterations reached
        return current_freq, False, confidence
```

### Integration in Scan Loop

```python
# Main scanning loop with auto-centering
for freq in band_sweep(14.150e6, 14.350e6, step=1000):
    # Initial tune
    radio.set_frequency(freq)
    time.sleep(0.3)

    # Quick check for voice activity
    quick_sample = capture_audio(duration=2.0)
    if not has_voice_activity(quick_sample):
        continue  # Skip to next freq

    # AUTO-CENTER THE SIGNAL (key innovation!)
    centered_freq, success, confidence = auto_tuner.auto_center_signal(freq)

    if success:
        # Now capture full 60-second sample for analysis
        full_sample = capture_audio(duration=60.0)
        analyze_and_update_bandmap(centered_freq, full_sample)
    else:
        logger.warning(f"Could not center signal at {freq/1e6:.3f} MHz")
        # Still might be worth analyzing if confidence > 0.5
        if confidence > 0.5:
            full_sample = capture_audio(duration=60.0)
            analyze_and_update_bandmap(centered_freq, full_sample)
```

### Performance Characteristics

| Metric | Value |
|--------|-------|
| **Initial detection time** | 2-3 seconds |
| **Centering iterations** | 1-3 (typically 1-2) |
| **Frequency accuracy** | ±50 Hz |
| **Success rate (clean signals)** | >95% |
| **Success rate (noisy signals)** | >80% |
| **CPU overhead** | <5% on modern CPU |

---

## Audio Processing Pipeline

### Pipeline Overview

```
1. Audio Capture (sounddevice)
   ↓
2. Noise Suppression (RNNoise)
   ↓
3. Voice Activity Detection (Silero VAD)
   ↓
4. Signal Centering Check (F0 analysis)
   ↓ (if off-center: retune and restart)
5. Speech-to-Text (Whisper)
   ↓
6. Speaker Diarization (Resemblyzer)
   ↓
7. Callsign Extraction & Validation
   ↓
8. Contest Behavior Classification
   ↓
9. N3FJP Dupe Check
   ↓
10. Band Map Update
```

### Stage Details

#### 1. Audio Capture

**Library**: sounddevice
**Format**: 16-bit PCM, mono, 16 kHz sample rate
**Source**: USB audio device from IC-705

```python
import sounddevice as sd

def capture_audio(duration=60.0, device=None):
    sample_rate = 16000
    audio = sd.rec(
        int(duration * sample_rate),
        samplerate=sample_rate,
        channels=1,
        dtype='float32',
        device=device
    )
    sd.wait()
    return audio.flatten()
```

#### 2. Noise Suppression

**Library**: pyrnnoise (RNNoise bindings)
**Purpose**: Remove background noise, static, QRM

```python
from pyrnnoise import RNNoise

denoiser = RNNoise()

def denoise_audio(audio, sample_rate=16000):
    # RNNoise expects 48 kHz, resample if needed
    if sample_rate != 48000:
        from scipy.signal import resample
        audio_48k = resample(audio, int(len(audio) * 48000 / sample_rate))
    else:
        audio_48k = audio

    denoised = denoiser.process(audio_48k)

    # Resample back to 16 kHz
    if sample_rate != 48000:
        denoised = resample(denoised, len(audio))

    return denoised
```

#### 3. Voice Activity Detection

**Library**: silero-vad
**Purpose**: Identify speech segments vs silence/noise

```python
import torch
from silero_vad import load_silero_vad, get_speech_timestamps

vad_model = load_silero_vad()

def detect_voice_activity(audio, sample_rate=16000):
    audio_tensor = torch.from_numpy(audio).float()

    speech_timestamps = get_speech_timestamps(
        audio_tensor,
        vad_model,
        sampling_rate=sample_rate,
        threshold=0.5
    )

    return speech_timestamps  # List of {start, end} dicts
```

#### 4. Speech-to-Text

**Library**: faster-whisper
**Model**: Small (quantized, ~461 MB)

```python
from faster_whisper import WhisperModel

whisper_model = WhisperModel("small", device="cpu", compute_type="int8")

def transcribe_audio(audio, sample_rate=16000):
    segments, info = whisper_model.transcribe(
        audio,
        language="en",
        beam_size=5,
        vad_filter=True
    )

    transcript = []
    for segment in segments:
        transcript.append({
            'start': segment.start,
            'end': segment.end,
            'text': segment.text.strip()
        })

    return transcript
```

#### 5. Speaker Diarization

**Library**: Resemblyzer
**Purpose**: Identify "who spoke when"

```python
from resemblyzer import VoiceEncoder, preprocess_wav
import numpy as np

voice_encoder = VoiceEncoder()

def extract_speaker_embeddings(audio, speech_timestamps, sample_rate=16000):
    embeddings = []

    for ts in speech_timestamps:
        start_sample = int(ts['start'] * sample_rate)
        end_sample = int(ts['end'] * sample_rate)
        segment = audio[start_sample:end_sample]

        # Resemblyzer expects 16 kHz
        wav = preprocess_wav(segment, source_sr=sample_rate)
        embedding = voice_encoder.embed_utterance(wav)

        embeddings.append({
            'start': ts['start'],
            'end': ts['end'],
            'embedding': embedding
        })

    return embeddings

def cluster_speakers(embeddings, threshold=0.75):
    """
    Cluster embeddings into speaker IDs using cosine similarity
    """
    from sklearn.cluster import AgglomerativeClustering

    embedding_matrix = np.array([e['embedding'] for e in embeddings])

    clustering = AgglomerativeClustering(
        n_clusters=None,
        distance_threshold=1 - threshold,  # Convert similarity to distance
        metric='cosine',
        linkage='average'
    )

    speaker_ids = clustering.fit_predict(embedding_matrix)

    for i, emb in enumerate(embeddings):
        emb['speaker_id'] = speaker_ids[i]

    return embeddings
```

---

## Voice Fingerprinting

### Database Schema

```python
from dataclasses import dataclass
from datetime import datetime
from typing import Optional, List
import numpy as np

@dataclass
class OperatorVoice:
    # Identification
    voice_id: str  # UUID
    callsign: Optional[str]  # May be None until confirmed

    # Voice fingerprint
    embedding: np.ndarray  # 256-dim vector from Resemblyzer
    embedding_samples: List[np.ndarray]  # All samples for refinement

    # Metadata
    first_heard: datetime
    last_heard: datetime
    total_airtime_seconds: float

    # Activity
    frequencies_heard: List[float]  # [14.250, 14.287.5, ...]
    estimated_qso_count: int
    is_run_station: bool

    # Contest data
    exchange: Optional[str]  # e.g., "2A WWA"
    contestness_score: float  # 0-100

    # Status
    worked: bool
    worked_timestamp: Optional[datetime]
```

### Voice Database Operations

```python
import uuid
from sklearn.metrics.pairwise import cosine_similarity

class VoiceDatabase:
    def __init__(self):
        self.operators: Dict[str, OperatorVoice] = {}
        self.created_at: datetime = datetime.now()

    def get_age_days(self) -> float:
        return (datetime.now() - self.created_at).total_seconds() / 86400

    def find_matching_voice(
        self,
        embedding: np.ndarray,
        threshold: float = 0.75
    ) -> Optional[str]:
        """
        Find operator with similar voice embedding
        Returns voice_id if match found, else None
        """
        for voice_id, operator in self.operators.items():
            similarity = cosine_similarity(
                embedding.reshape(1, -1),
                operator.embedding.reshape(1, -1)
            )[0, 0]

            if similarity > threshold:
                return voice_id

        return None

    def add_or_update(self, embedding, metadata):
        voice_id = self.find_matching_voice(embedding)

        if voice_id:
            # Update existing operator
            operator = self.operators[voice_id]
            operator.last_heard = datetime.now()
            operator.total_airtime_seconds += metadata.get('airtime', 0)
            operator.frequencies_heard.append(metadata.get('frequency'))
            operator.embedding_samples.append(embedding)

            # Refine embedding (running average)
            operator.embedding = np.mean(operator.embedding_samples, axis=0)

            # Update other fields
            if metadata.get('callsign'):
                operator.callsign = metadata['callsign']
            if metadata.get('exchange'):
                operator.exchange = metadata['exchange']
        else:
            # Create new operator
            new_id = str(uuid.uuid4())
            self.operators[new_id] = OperatorVoice(
                voice_id=new_id,
                embedding=embedding,
                embedding_samples=[embedding],
                first_heard=datetime.now(),
                last_heard=datetime.now(),
                total_airtime_seconds=metadata.get('airtime', 0),
                frequencies_heard=[metadata.get('frequency')],
                estimated_qso_count=0,
                is_run_station=metadata.get('is_run_station', False),
                callsign=metadata.get('callsign'),
                exchange=metadata.get('exchange'),
                contestness_score=metadata.get('contestness_score', 0),
                worked=False,
                worked_timestamp=None
            )

    def mark_worked(self, voice_id: str):
        if voice_id in self.operators:
            self.operators[voice_id].worked = True
            self.operators[voice_id].worked_timestamp = datetime.now()

    def save_to_file(self, filepath: str):
        import pickle
        with open(filepath, 'wb') as f:
            pickle.dump(self, f)

    @staticmethod
    def load_from_file(filepath: str):
        import pickle
        with open(filepath, 'rb') as f:
            return pickle.load(f)
```

### Persistence & Age Warnings

```python
# On application startup
if os.path.exists('voice_database.pkl'):
    voice_db = VoiceDatabase.load_from_file('voice_database.pkl')

    age_days = voice_db.get_age_days()
    if age_days > 5:
        logger.warning(
            f"Voice database is {age_days:.1f} days old. "
            "Consider resetting for current contest."
        )
        # Show GUI warning
        show_warning_dialog(
            f"Worked operator database is {age_days:.1f} days old.\n"
            "Reset now or continue with existing data?"
        )
else:
    voice_db = VoiceDatabase()

# On application exit
voice_db.save_to_file('voice_database.pkl')
```

---

## Contest Behavior Detection

### Contestness Score Algorithm

```python
def calculate_contestness_score(
    transcript: List[dict],
    speaker_info: List[dict],
    duration_seconds: float
) -> float:
    """
    Calculate 0-100 score indicating likelihood this is contest activity
    """

    score = 0.0
    weights = {
        'keywords': 20,
        'callsign_density': 25,
        'speaker_dominance': 20,
        'qso_rate': 20,
        'exchange_pattern': 15
    }

    # 1. Keyword Detection
    keywords = ['cq', 'test', 'contest', 'qrz', 'field day', 'copy', 'qsl']
    full_text = ' '.join([seg['text'].lower() for seg in transcript])

    keyword_hits = sum(1 for kw in keywords if kw in full_text)
    score += (keyword_hits / len(keywords)) * weights['keywords']

    # 2. Callsign Density
    callsigns = extract_callsigns(transcript)
    callsign_density = len(callsigns) / (duration_seconds / 60)  # Per minute

    # Expect 5-20 callsigns per minute in contests
    density_score = min(callsign_density / 20, 1.0)
    score += density_score * weights['callsign_density']

    # 3. Speaker Dominance (one voice running the frequency)
    speaker_times = {}
    for spkr in speaker_info:
        sid = spkr['speaker_id']
        airtime = spkr['end'] - spkr['start']
        speaker_times[sid] = speaker_times.get(sid, 0) + airtime

    if speaker_times:
        max_airtime = max(speaker_times.values())
        dominance = max_airtime / duration_seconds

        # Run station typically has >60% airtime
        if dominance > 0.6:
            score += weights['speaker_dominance']
        elif dominance > 0.4:
            score += 0.5 * weights['speaker_dominance']

    # 4. QSO Rate (estimated)
    unique_speakers = len(speaker_times)
    estimated_qsos = unique_speakers - 1  # Exclude run station
    qso_rate = estimated_qsos / (duration_seconds / 60)  # Per minute

    # Contest rates: 30-60+ QSOs/hour = 0.5-1.0+ QSOs/minute
    rate_score = min(qso_rate / 1.0, 1.0)
    score += rate_score * weights['qso_rate']

    # 5. Exchange Pattern Detection
    has_exchange = detect_exchange_pattern(transcript, full_text)
    if has_exchange:
        score += weights['exchange_pattern']

    return min(score, 100.0)
```

### Run Station vs. Ragchew

```python
def classify_station_type(contestness_score, speaker_info, duration):
    """
    Classify as: run_station, s&p_station, ragchew, unclear
    """

    if contestness_score < 40:
        return 'ragchew'

    # Analyze speaker dominance
    speaker_times = {}
    for spkr in speaker_info:
        sid = spkr['speaker_id']
        airtime = spkr['end'] - spkr['start']
        speaker_times[sid] = speaker_times.get(sid, 0) + airtime

    if not speaker_times:
        return 'unclear'

    max_airtime = max(speaker_times.values())
    dominance = max_airtime / duration
    unique_speakers = len(speaker_times)

    if dominance > 0.6 and unique_speakers >= 3:
        return 'run_station'
    elif unique_speakers <= 2 and contestness_score > 60:
        return 's&p_station'  # Search & Pounce
    elif unique_speakers >= 3:
        return 'unclear'
    else:
        return 'ragchew'
```

---

## N3FJP Integration

### TCP API Client

```python
import socket
import time

class N3FJPClient:
    def __init__(self, host='localhost', port=1100):
        self.host = host
        self.port = port
        self.sock = None

    def connect(self):
        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.sock.connect((self.host, self.port))
            return True
        except Exception as e:
            logger.error(f"Failed to connect to N3FJP: {e}")
            return False

    def send_command(self, command: str) -> str:
        try:
            self.sock.sendall(f"{command}\r\n".encode())
            response = self.sock.recv(4096).decode().strip()
            return response
        except Exception as e:
            logger.error(f"N3FJP command error: {e}")
            return ""

    def check_dupe(self, callsign: str, band: str, mode: str) -> bool:
        """
        Check if callsign is already in log for this band/mode
        """
        # N3FJP command format varies by contest
        # This is a simplified example
        cmd = f"<CMD><CHECKDUPE>{callsign}</CHECKDUPE></CMD>"
        response = self.send_command(cmd)

        # Parse response (format varies by contest logger)
        return 'DUPE' in response.upper()

    def get_call_info(self, callsign: str) -> dict:
        """
        Get information about a callsign (DXCC, zone, etc.)
        """
        cmd = f"<CMD><GETCALLINFO>{callsign}</GETCALLINFO></CMD>"
        response = self.send_command(cmd)

        # Parse XML response
        info = parse_n3fjp_response(response)
        return info

    def close(self):
        if self.sock:
            self.sock.close()
```

### Dupe Checking Integration

```python
def update_bandmap_with_dupes(bandmap_stations, n3fjp_client):
    for station in bandmap_stations:
        callsign = station.callsign
        band = freq_to_band(station.frequency)
        mode = 'SSB'

        is_dupe = n3fjp_client.check_dupe(callsign, band, mode)
        call_info = n3fjp_client.get_call_info(callsign)

        station.is_dupe = is_dupe
        station.is_new_mult = check_if_new_mult(call_info, band)
        station.dxcc = call_info.get('dxcc')
        station.cq_zone = call_info.get('cq_zone')
```

---

## User Interface Design

### Main Window Layout

```
┌─────────────────────────────────────────────────────────────────┐
│  CQSentinel - SSB Contest Scanner            [Radio: IC-705]    │
├─────────────────────────────────────────────────────────────────┤
│  ┌─────────────────────────────────────────────────────────────┐│
│  │ Menu: File | Edit | Scan | Contest | N3FJP | Help          ││
│  └─────────────────────────────────────────────────────────────┘│
├─────────────────────────────────────────────────────────────────┤
│  Bands: [✓]160m [✓]80m [✓]40m [✓]20m [✓]15m [✓]10m             │
│  Contest: [Field Day ▼]     Scan: [●Running] [Pause] [Reset DB] │
├─────────────────────────────────────────────────────────────────┤
│  ┌───────────────────────────┬───────────────────────────────┐  │
│  │                           │                               │  │
│  │  20m Band Map             │   Station Detail Panel        │  │
│  │  (14.150 - 14.350 MHz)    │                               │  │
│  │  Last Scan: 2m ago        │   Freq: 14.287.5 MHz          │  │
│  │                           │   Call: K7ABC                 │  │
│  │  [Waterfall display       │   Status: NEW (run station)   │  │
│  │   showing stations        │   S-meter: S8                 │  │
│  │   at various frequencies  │   Contestness: 87/100         │  │
│  │   with color coding]      │   Exchange: 2A WWA            │  │
│  │                           │   Rate: ~45 QSOs/hr           │  │
│  │                           │                               │  │
│  │  ● 14.340 W7XYZ [NEW]     │   Last Heard:                 │  │
│  │  ● 14.320 K1ABC [DUPE]    │   "CQ Field Day Kilo Seven    │  │
│  │  ● 14.300 N6TEST [RUN]    │    Alpha Bravo Charlie"       │  │
│  │  ● 14.287 K7ABC [NEW]     │                               │  │
│  │  ● 14.265 VE7XYZ [MULT]   │   [Tune To] [Mark Worked]     │  │
│  │                           │   [Ignore]  [Details...]      │  │
│  └───────────────────────────┴───────────────────────────────┘  │
│                                                                  │
│  ┌─────────────────────────────────────────────────────────────┐│
│  │ Transcript (Live)                                           ││
│  │ [14.287.5] K7ABC: "CQ Field Day K7ABC Kilo Seven Alpha..."  ││
│  │ [14.287.5] W1XYZ: "Whiskey One X-Ray Yankee Zulu"           ││
│  │ [14.287.5] K7ABC: "W1XYZ you're 59 2A Washington QSL?"      ││
│  └─────────────────────────────────────────────────────────────┘│
│                                                                  │
│  Status: Scanning 20m | Current: 14.295 MHz | Worked: 47 ops   │
│  N3FJP: Connected | Voice DB: 2d 4h old                         │
└─────────────────────────────────────────────────────────────────┘
```

### Color Coding

| Color | Meaning |
|-------|---------|
| **Green** | New station (not worked) |
| **Gold/Yellow** | New multiplier |
| **Red** | Dupe (already worked) |
| **Gray** | Low contestness (ragchew) |
| **Blue** | High contestness but not yet classified |

### Waterfall Band Map

- **Y-axis**: Frequency
- **X-axis**: Time (rightmost = current)
- **Intensity**: Signal strength / activity
- **Markers**: Station callsigns with status indicators
- **Click**: Tune radio to that frequency
- **Right-click**: Context menu (mark worked, ignore, details)

---

## Contest Profiles

### Profile Data Structure

```python
@dataclass
class ContestProfile:
    name: str
    short_name: str  # "FD", "WFD", "CQWW", etc.

    # Exchange parsing
    exchange_fields: List[str]  # e.g., ["class", "section"]
    exchange_regex: str

    # Keywords for detection
    keywords: List[str]
    cq_phrases: List[str]

    # Multipliers
    mult_fields: List[str]
    mult_lookup: Dict[str, List[str]]

    # Phonetic variations
    custom_phonetics: Dict[str, str]

    # Scoring (optional)
    points_per_qso: int
    mult_type: str  # "additive", "multiplicative"
```

### Pre-Configured Profiles

#### 1. ARRL Field Day

```python
FIELD_DAY = ContestProfile(
    name="ARRL Field Day",
    short_name="FD",
    exchange_fields=["class", "section"],
    exchange_regex=r"(\d+[A-F])\s+([A-Z]{2,3})",
    keywords=["field day", "class", "section", "emergency"],
    cq_phrases=["CQ Field Day", "CQ FD"],
    mult_fields=["section"],
    mult_lookup={
        "section": [
            "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA",
            "HI", "ID", "IL", "IN", "IA", "KS", "KY", "LA", "ME", "MD",
            "MA", "MI", "MN", "MS", "MO", "MT", "NE", "NV", "NH", "NJ",
            "NM", "NY", "NC", "ND", "OH", "OK", "OR", "PA", "RI", "SC",
            "SD", "TN", "TX", "UT", "VT", "VA", "WA", "WV", "WI", "WY",
            "AB", "BC", "MB", "NB", "NL", "NS", "NT", "ON", "PE", "QC",
            "SK", "YT",
            "DX"
        ]
    },
    custom_phonetics={"kilowatt": "K", "ocean": "O"},
    points_per_qso=1,
    mult_type="additive"
)
```

#### 2. Winter Field Day

```python
WINTER_FIELD_DAY = ContestProfile(
    name="Winter Field Day",
    short_name="WFD",
    exchange_fields=["class", "section"],
    exchange_regex=r"(\d+[O-I])\s+([A-Z]{2,3})",
    keywords=["winter field day", "wfd", "class", "section"],
    cq_phrases=["CQ Winter Field Day", "CQ WFD"],
    mult_fields=["section"],
    mult_lookup={
        "section": [/* same as Field Day */]
    },
    custom_phonetics={"india": "I", "ocean": "O"},
    points_per_qso=1,
    mult_type="additive"
)
```

#### 3. CQ WW DX Contest

```python
CQ_WW_DX = ContestProfile(
    name="CQ World Wide DX Contest",
    short_name="CQWW",
    exchange_fields=["rst", "cq_zone"],
    exchange_regex=r"(5[79]9?)\s+(\d{1,2})",
    keywords=["cq world wide", "cq ww", "zone"],
    cq_phrases=["CQ WW", "CQ Contest"],
    mult_fields=["cq_zone", "country"],
    mult_lookup={
        "cq_zone": [str(i) for i in range(1, 41)]
    },
    custom_phonetics={},
    points_per_qso=3,  # Varies by distance
    mult_type="multiplicative"
)
```

#### 4. CQ WPX Contest

```python
CQ_WPX = ContestProfile(
    name="CQ WPX Contest",
    short_name="CQWPX",
    exchange_fields=["rst", "serial"],
    exchange_regex=r"(5[79]9?)\s+(\d{3,4})",
    keywords=["wpx", "serial"],
    cq_phrases=["CQ WPX", "CQ Contest"],
    mult_fields=["prefix"],
    mult_lookup={},  # Prefixes computed dynamically
    custom_phonetics={},
    points_per_qso=1,
    mult_type="multiplicative"
)
```

#### 5. WA State Salmon Run

```python
SALMON_RUN = ContestProfile(
    name="Washington State Salmon Run",
    short_name="WASR",
    exchange_fields=["rst", "qth"],
    exchange_regex=r"(5[79]9?)\s+([A-Z]{2,10})",
    keywords=["salmon run", "washington", "county"],
    cq_phrases=["CQ Salmon Run", "CQ WASR"],
    mult_fields=["county"],
    mult_lookup={
        "county": [
            "ADAMS", "ASOTIN", "BENTON", "CHELAN", "CLALLAM", "CLARK",
            "COLUMBIA", "COWLITZ", "DOUGLAS", "FERRY", "FRANKLIN",
            "GARFIELD", "GRANT", "GRAYS HARBOR", "ISLAND", "JEFFERSON",
            "KING", "KITSAP", "KITTITAS", "KLICKITAT", "LEWIS", "LINCOLN",
            "MASON", "OKANOGAN", "PACIFIC", "PEND OREILLE", "PIERCE",
            "SAN JUAN", "SKAGIT", "SKAMANIA", "SNOHOMISH", "SPOKANE",
            "STEVENS", "THURSTON", "WAHKIAKUM", "WALLA WALLA", "WHATCOM",
            "WHITMAN", "YAKIMA"
        ]
    },
    custom_phonetics={},
    points_per_qso=1,
    mult_type="additive"
)
```

---

## Configuration & Settings

### Radio Settings

```python
@dataclass
class RadioConfig:
    model: str  # "Icom IC-705"
    cat_interface: str  # "USB" or serial port
    cat_baud: int = 115200
    audio_device: str  # OS audio device name
    rigctld_host: str = "localhost"
    rigctld_port: int = 4532
```

### Band Plan Configuration

```python
BAND_PLANS = {
    'US': {
        '160m': (1.800e6, 2.000e6),
        '80m': (3.700e6, 4.000e6),
        '40m': (7.125e6, 7.300e6),
        '20m': (14.150e6, 14.350e6),
        '15m': (21.200e6, 21.450e6),
        '10m': (28.300e6, 29.700e6)
    },
    'IARU_1': {
        # European band plan
        '160m': (1.810e6, 1.850e6),
        # ... etc
    }
}
```

### Scan Settings

```python
@dataclass
class ScanConfig:
    step_size_hz: int = 1000  # 1 kHz
    dwell_with_voice_sec: int = 60
    dwell_without_voice_sec: int = 5
    auto_center_enabled: bool = True
    center_tolerance_hz: int = 50
    max_center_iterations: int = 3
```

### Audio Processing Settings

```python
@dataclass
class AudioConfig:
    sample_rate: int = 16000
    noise_reduction: str = "medium"  # off, low, medium, high
    vad_sensitivity: float = 0.5  # 0-1
    whisper_model: str = "small"  # tiny, base, small, medium
    use_crepe_pitch: bool = False  # GPU-accelerated pitch detection
```

### Contest Settings

```python
@dataclass
class ContestConfig:
    active_profile: str = "FD"
    contestness_threshold: int = 70
    n3fjp_enabled: bool = True
    n3fjp_host: str = "localhost"
    n3fjp_port: int = 1100
```

### Voice Database Settings

```python
@dataclass
class VoiceDBConfig:
    similarity_threshold: float = 0.75  # 0.5-0.95
    auto_reset_days: int = 0  # 0 = never
    warn_age_days: int = 5
```

---

## Development Phases

### Phase 1: Core Infrastructure (MVP)
**Duration**: 2-3 weeks
**Goal**: Prove basic radio control and audio capture

**Tasks**:
- Set up Python project structure
- Implement Hamlib CAT control wrapper
- Test IC-705 connection and frequency control
- Implement audio capture from USB
- Build basic GUI with frequency display
- Manual tuning controls

**Deliverables**:
- Can connect to IC-705
- Can tune to arbitrary frequencies
- Can capture audio to file
- Simple GUI shows current frequency and S-meter

---

### Phase 2: Audio Intelligence
**Duration**: 2-3 weeks
**Goal**: Process audio into text

**Tasks**:
- Integrate RNNoise for noise reduction
- Implement Silero VAD
- Set up faster-whisper ASR
- Display real-time transcripts in GUI
- Audio quality testing and tuning

**Deliverables**:
- Clean audio from noisy signals
- Accurate voice activity detection
- Working speech-to-text pipeline
- Transcript display in GUI

---

### Phase 3: SSB Auto-Centering
**Duration**: 1-2 weeks
**Goal**: Automatically tune to center SSB signals

**Tasks**:
- Implement librosa pYIN pitch detection
- Build auto-centering algorithm
- Test with various voices (male/female/accented)
- Add spectral energy validation
- Performance optimization

**Deliverables**:
- Accurate F0 detection
- Auto-centering success rate >90%
- Handles diverse voice types
- Fast (<3 seconds to center)

---

### Phase 4: Voice Fingerprinting
**Duration**: 2 weeks
**Goal**: Identify and track operators by voice

**Tasks**:
- Integrate Resemblyzer
- Implement speaker diarization
- Build voice database with persistence
- Test cross-frequency voice tracking
- Similarity threshold tuning

**Deliverables**:
- Extract voice embeddings
- Cluster speakers accurately
- Persistent voice database
- "Already worked" detection across frequencies

---

### Phase 5: Contest Logic
**Duration**: 2-3 weeks
**Goal**: Detect contest activity and parse exchanges

**Tasks**:
- Implement callsign extraction from transcripts
- Build phonetics parser (NATO + creative)
- Develop contestness scoring algorithm
- Implement run station vs. ragchew detection
- PyHamTools integration for callsign validation

**Deliverables**:
- Accurate callsign extraction
- Flexible phonetics handling
- Contestness score calculation
- Station type classification

---

### Phase 6: Band Map & Visualization
**Duration**: 2-3 weeks
**Goal**: Visual representation of band activity

**Tasks**:
- Design waterfall-style band map widget
- Implement color-coded station markers
- Real-time updates during scan
- Click-to-tune functionality
- Station detail panel

**Deliverables**:
- Professional band map GUI
- Intuitive visual design
- Responsive updates
- Easy navigation

---

### Phase 7: N3FJP Integration
**Duration**: 1-2 weeks
**Goal**: Connect to N3FJP for dupe checking

**Tasks**:
- Build N3FJP TCP API client
- Implement dupe checking
- Multiplier detection logic
- Visual indicators on band map
- Error handling and reconnection

**Deliverables**:
- Working N3FJP connection
- Real-time dupe status
- Multiplier highlighting
- Robust error handling

---

### Phase 8: Band Scanning Engine
**Duration**: 2 weeks
**Goal**: Automated band sweeping with intelligence

**Tasks**:
- Implement band sweep logic
- Integrate auto-centering into scan loop
- Adaptive dwell time (early exit)
- Multi-band coordination
- Scan progress tracking

**Deliverables**:
- Efficient band scanning
- Smart dwell time management
- Accurate frequency coverage
- Progress indicators

---

### Phase 9: Contest Profiles
**Duration**: 2 weeks
**Goal**: Support major contests with pre-configured profiles

**Tasks**:
- Implement profile data structure
- Create Field Day profile
- Create Winter Field Day profile
- Create CQWW profile
- Create CQWPX profile
- Create WA Salmon Run profile
- Profile selection UI
- Exchange parsing per profile

**Deliverables**:
- 5 complete contest profiles
- Profile selection in GUI
- Contest-specific exchange parsing
- Multiplier detection per contest

---

### Phase 10: Polish & Distribution
**Duration**: 2-3 weeks
**Goal**: Production-ready application

**Tasks**:
- Settings persistence (config file)
- User documentation
- Help system in GUI
- Windows packaging (PyInstaller)
- Installer creation
- Beta testing
- Bug fixes
- Performance optimization

**Deliverables**:
- Windows installer
- User manual
- Stable, tested application
- Public release

---

**Total Estimated Timeline**: 20-26 weeks (~5-6 months)

---

## Dependencies & Packaging

### Python Requirements

```
# requirements.txt
python>=3.10

# GUI
PyQt6>=6.5.0

# Audio
sounddevice>=0.4.6
pyrnnoise>=0.1.0

# VAD
silero-vad>=4.0.0

# Speech Recognition
faster-whisper>=0.10.0

# Pitch Detection
librosa>=0.10.0
crepe>=0.0.12  # Optional, for GPU-accelerated pitch

# Voice Fingerprinting
resemblyzer>=0.1.1

# Ham Radio Utilities
pyhamtools>=0.7.5

# Math/DSP
numpy>=1.24.0
scipy>=1.10.0
scikit-learn>=1.3.0

# ML Backend
torch>=2.0.0
torchaudio>=2.0.0

# Misc
pyserial>=3.5
configparser>=5.3.0
```

### Hamlib Installation

**Windows**:
- Download pre-built binaries from hamlib.github.io
- Or use rigctld via network (can run on separate machine)

**Python Bindings**:
- Use TCP connection to rigctld (simplest)
- Or compile Hamlib with Python bindings

### Model Files

Bundle these with the application:

```
models/
├── whisper-small-ct2/          # faster-whisper model (~461 MB)
├── silero_vad.onnx             # VAD model (~1.5 MB)
├── resemblyzer_encoder.pt      # Voice encoder (~20 MB)
└── rnnoise.rnnn                # Noise reduction (<1 MB)
```

### Packaging for Windows

```bash
# Build with PyInstaller
pyinstaller \
    --onedir \
    --windowed \
    --name CQSentinel \
    --icon resources/icon.ico \
    --add-data "models:models" \
    --add-data "contest_profiles:contest_profiles" \
    --add-data "resources:resources" \
    --hidden-import torch \
    --hidden-import resemblyzer \
    --hidden-import faster_whisper \
    --hidden-import librosa \
    cqsentinel/main.py
```

**Output**: `dist/CQSentinel/` folder with:
- `CQSentinel.exe`
- All dependencies
- Model files
- Total size: ~800 MB

### Installer Creation

Use **Inno Setup** to create Windows installer:
- Single .exe installer
- Start menu shortcuts
- Desktop icon
- Uninstaller
- License agreement

---

## Performance Targets

| Metric | Target | Notes |
|--------|--------|-------|
| **Scan rate** | 30-60 freq/hour | Depends on dwell time config |
| **CPU usage** | <25% | On modern CPU (i5/i7 8th gen+) |
| **RAM usage** | 2-3 GB | Models loaded in memory |
| **ASR latency** | <500 ms | Audio → transcript |
| **Voice ID accuracy** | >90% | Clean signals, S7+ |
| **Callsign extraction** | >85% | Good audio quality |
| **Auto-center success** | >95% | Clean signals |
| **Auto-center time** | 2-5 seconds | Typically 1-2 iterations |
| **Startup time** | <15 seconds | Model loading |

---

## Known Limitations

### Technical Limitations

1. **Audio Quality Dependent**: Weak signals (S3-S5) may not transcribe accurately
2. **Accents & QRM**: Heavy accents or interference reduce ASR accuracy
3. **Split Operations**: Cannot detect split-frequency DX operations
4. **Pileups**: Simultaneous speakers confuse diarization
5. **Non-English**: Optimized for English; other languages need different models
6. **AGC Pumping**: Very strong signals may cause audio artifacts

### Operational Limitations

1. **Single Radio**: Monitors one radio at a time (Phase 1)
2. **SSB Only**: Does not handle CW, digital modes, or AM
3. **Phone Segments Only**: Limited to configured band edges
4. **No Transmit**: Receive-only; does not make contacts
5. **Windows Only**: Initial release; Linux/Mac in future

### Regulatory Limitations

1. **Local Operation**: Must be operated by licensed amateur
2. **No Automatic Spotting**: Does not auto-post to DX clusters (would violate assisted rules)
3. **Operator Judgment Required**: AI suggestions must be verified by operator

---

## Future Enhancements (Post-V1)

### Near-Term (V1.1 - V1.3)

- **Multi-radio support**: Monitor 2-3 radios simultaneously
- **Linux/macOS ports**: Cross-platform builds
- **More contest profiles**: ARRL 10m, CW contests (via CW Skimmer integration)
- **SDR direct integration**: Process IQ samples directly (bypass radio audio)
- **Voice profile library**: Share voice fingerprints with friends (opt-in)
- **Historical analysis**: Track band openings, propagation

### Mid-Term (V2.0)

- **Mobile app**: Remote control via phone/tablet
- **Cloud spot sharing**: Opt-in shared band map (like RBN)
- **Contest submission**: Auto-generate Cabrillo files
- **Multi-language support**: Spanish, German, Japanese ASR models
- **Advanced ML**: Train custom models on ham radio speech

### Long-Term (V3.0+)

- **Automatic QSO**: AI makes contacts autonomously (controversial, regulatory concerns)
- **Real-time translation**: Translate foreign language QSOs
- **Predictive band mapping**: ML predicts where stations will appear
- **Full-duplex monitoring**: Use separate RX antenna for scanning while transmitting

---

## References & Prior Art

### Academic Papers

1. **SSB AFC**: US Patent 4625331A - "Automatic frequency control system for an SSB receiver"
2. **YIN Algorithm**: De Cheveigné, A., & Kawahara, H. (2002). "YIN, a fundamental frequency estimator for speech and music"
3. **pYIN**: Mauch, M., & Dixon, S. (2014). "pYIN: A fundamental frequency estimator using probabilistic threshold distributions"
4. **CREPE**: Kim, J. W., et al. (2018). "CREPE: A Convolutional Representation for Pitch Estimation"
5. **Resemblyzer**: Wan, L., et al. (2018). "Generalized End-to-End Loss for Speaker Verification"
6. **Whisper**: Radford, A., et al. (2022). "Robust Speech Recognition via Large-Scale Weak Supervision"

### Ham Radio References

- ARRL Handbook (Chapter on SSB)
- CW Skimmer documentation (VE3NEA)
- N3FJP API documentation
- Hamlib documentation

### Software Libraries

- faster-whisper: github.com/guillaumekln/faster-whisper
- Resemblyzer: github.com/resemble-ai/Resemblyzer
- librosa: librosa.org
- PyHamTools: github.com/dh1tw/pyhamtools
- Hamlib: hamlib.github.io

---

## Project Repository Structure

```
CQSentinel/
├── README.md
├── PROJECT_PLAN.md (this file)
├── LICENSE
├── requirements.txt
├── setup.py
├── .gitignore
├── docs/
│   ├── user_guide.md
│   ├── developer_guide.md
│   └── api_reference.md
├── cqsentinel/
│   ├── __init__.py
│   ├── main.py
│   ├── config.py
│   ├── gui/
│   │   ├── __init__.py
│   │   ├── main_window.py
│   │   ├── band_map.py
│   │   └── settings_dialog.py
│   ├── radio/
│   │   ├── __init__.py
│   │   ├── hamlib_controller.py
│   │   └── auto_tuner.py
│   ├── audio/
│   │   ├── __init__.py
│   │   ├── capture.py
│   │   ├── noise_reduction.py
│   │   ├── vad.py
│   │   └── pitch_detection.py
│   ├── speech/
│   │   ├── __init__.py
│   │   ├── transcription.py
│   │   ├── phonetics.py
│   │   └── callsign_parser.py
│   ├── voice/
│   │   ├── __init__.py
│   │   ├── diarization.py
│   │   ├── fingerprinting.py
│   │   └── voice_db.py
│   ├── contest/
│   │   ├── __init__.py
│   │   ├── profiles.py
│   │   ├── behavior_detection.py
│   │   └── exchange_parser.py
│   ├── n3fjp/
│   │   ├── __init__.py
│   │   └── api_client.py
│   └── scanner/
│       ├── __init__.py
│       ├── band_scanner.py
│       └── station_tracker.py
├── models/
│   └── README.md (download instructions)
├── contest_profiles/
│   ├── field_day.json
│   ├── winter_field_day.json
│   ├── cqww.json
│   ├── cqwpx.json
│   └── salmon_run.json
├── resources/
│   ├── icon.ico
│   └── ui/
│       └── stylesheets/
├── tests/
│   ├── test_radio.py
│   ├── test_audio.py
│   ├── test_speech.py
│   └── test_contest.py
└── scripts/
    ├── download_models.py
    └── build_installer.py
```

---

## Conclusion

**CQSentinel** represents a significant advancement in ham radio contesting technology. By combining:

- Universal radio control
- Offline AI speech recognition
- Voice-based operator fingerprinting
- Intelligent SSB auto-centering (using F0 detection)
- Contest-aware heuristics
- Deep N3FJP integration

...we create the first practical "SSB Skimmer" that the ham community has wanted for over a decade.

The project is **technically feasible** with existing open-source libraries, **legally compliant** with amateur radio regulations, and **addresses a real need** in the contesting community.

**Next Steps**:
1. Set up development environment
2. Begin Phase 1: Core Infrastructure
3. Validate IC-705 CAT control and audio capture
4. Iterate through development phases
5. Beta test with real contests
6. Public release

**Target First Release**: Q2 2026 (Field Day 2026)

---

**Document Version**: 1.0
**Last Updated**: 2025-11-13
**Author**: CQSentinel Development Team
**License**: MIT (TBD)
