# CQSentinel Configuration/UI Gap Analysis

## Summary
Configuration mismatch analysis between `config.py`, `settings_dialog.py`, and actual codebase implementation. Identified 4 categories of issues:

---

## 1. CONFIG PARAMETERS NOT USED ANYWHERE (DEAD CODE)

### In ScanConfig:
- **auto_center_enabled** (default: True)
  - Defined in: config.py line 59
  - Configured in: settings_dialog.py (NO UI CONTROL)
  - Used in: NOWHERE
  - Impact: Feature appears ready but is completely unused

- **center_tolerance_hz** (default: 50)
  - Defined in: config.py line 60
  - Configured in: settings_dialog.py (NO UI CONTROL)
  - Used in: NOWHERE
  - Impact: Related to SSB auto-centering which isn't configurable

- **max_center_iterations** (default: 3)
  - Defined in: config.py line 61
  - Configured in: settings_dialog.py (NO UI CONTROL)
  - Used in: NOWHERE
  - Impact: Auto-tuner may have this hard-coded

### In AudioConfig:
- **pitch_fmin** (default: 50 Hz)
  - Defined in: config.py line 88
  - UI Control: NONE
  - Used in: NOWHERE
  - Impact: Pitch detection is disabled (use_crepe_pitch = False by default)

- **pitch_fmax** (default: 600 Hz)
  - Defined in: config.py line 89
  - UI Control: NONE
  - Used in: NOWHERE
  - Impact: Pitch detection is disabled

### In VoiceDBConfig:
- **auto_reset_days** (default: 0)
  - Defined in: config.py line 106
  - UI Control: NONE
  - Used in: NOWHERE
  - Impact: Voice database feature is disabled/deprecated

- **database_file** (default: "voice_database.pkl")
  - Defined in: config.py line 108
  - UI Control: NONE
  - Used in: NOWHERE
  - Impact: Voice database feature appears disabled

---

## 2. HARD-CODED VALUES THAT SHOULD BE CONFIGURABLE

### Voice Embedding Parameters
- **similarity_threshold** (voice speaker detection)
  - Configured in: config.voice_db.similarity_threshold (default: 0.75)
  - Hard-coded in: main_window.py lines 411, 539
  - Impact: Configuration value is ignored; hard-coded 0.75 always used
  - Fix: Should pass config.voice_db.similarity_threshold to detect_speaker_changes()

```python
# Current (ignores config):
speaker_segments = self._voice_embedder.detect_speaker_changes(
    self._audio,
    sample_rate=self._sample_rate,
    window_duration=2.5,        # HARD-CODED
    stride=1.0,                  # HARD-CODED
    similarity_threshold=0.75    # HARD-CODED (ignores config!)
)

# Should be:
speaker_segments = self._voice_embedder.detect_speaker_changes(
    self._audio,
    sample_rate=self._sample_rate,
    window_duration=self.config.audio.voice_window_duration,  # ADD CONFIG
    stride=self.config.audio.voice_stride,                    # ADD CONFIG
    similarity_threshold=self.config.voice_db.similarity_threshold
)
```

- **window_duration** (2.5 seconds)
  - Hard-coded in: main_window.py lines 409, 537
  - Should be configurable: YES (affects speaker detection sensitivity)
  - Not in config.py

- **stride** (1.0 second)
  - Hard-coded in: main_window.py lines 410, 538
  - Should be configurable: YES (affects detection granularity)
  - Not in config.py

### VAD (Voice Activity Detection) Parameters
- **min_speech_duration_ms** (250 ms)
  - Hard-coded in: audio/vad.py line 41, speech/transcription.py line 132
  - Configured in: config.py - NO (should be in AudioConfig)
  - Affects: Minimum speech segment length
  - Impact: Shorter audio clips may not be detected

- **min_silence_duration_ms** (100 ms)
  - Hard-coded in: audio/vad.py line 42, speech/transcription.py line 133
  - Configured in: config.py - NO
  - Affects: Silence duration between speech segments

- **VAD Sensitivity Thresholds**
  - Hard-coded in: audio/vad.py lines 252-254
  - Values: low=0.7, medium=0.5, high=0.3
  - Current mechanism: Uses config.audio.noise_reduction_level to map to sensitivity
  - Issue: These threshold values are hard-coded; no way to tune them
  - Should be: Configurable in AudioConfig with individual thresholds

```python
# Current (hard-coded mapping):
sensitivity_map = {
    'low': 0.7,      
    'medium': 0.5,   
    'high': 0.3      
}
```

### Radio Mode/Bandwidth
- **Mode-specific bandwidth values**
  - FM bandwidth: 12000 Hz (hard-coded)
  - USB/LSB bandwidth: 2400 Hz (hard-coded)
  - Location: main_window.py lines 96, 99, 102
  - Should be: Configurable in RadioConfig or mode profiles
  - Impact: Cannot tune bandwidth for different modes/bands

### Whisper Transcription Parameters
- **whisper_temperature** (0.0)
  - Configured in: config.audio.whisper_temperature
  - Used in: main_window.py (getattr with default 0.0)
  - Issue: Configuration exists but not always applied; uses getattr fallback
  - Status: Properly configured but check for consistency

- **whisper_no_speech_threshold** (0.6)
  - Configured in: config.audio.whisper_no_speech_threshold
  - Used in: main_window.py (getattr with default 0.6)
  - Status: Properly configured but check for consistency

- **openai_whisper_model** ("whisper-1")
  - Configured in: config.audio.openai_whisper_model
  - Used in: main_window.py (getattr)
  - UI Control: NONE (API key only)
  - Impact: Users can't choose different OpenAI model versions

- **Whisper model size** ("medium.en")
  - Hard-coded everywhere:
    - main_window.py line 1467: `model_size="medium.en"`
    - gui/model_downloader_dialog.py: `model_size="medium.en"`
    - speech/subprocess_transcriber.py: `model_size="medium.en"`
    - speech/gpu_utils.py: `model_name = "medium.en"`
  - Config: NO (marked as "Hardcoded for best accuracy")
  - Impact: Cannot use different model sizes
  - Note: Comments suggest intentional design choice for "best balance"

---

## 3. MISSING UI CONTROLS FOR CONFIGURED PARAMETERS

### In Advanced Tab (settings_dialog.py):
- **quick_check_duration** (default: 2.0 seconds)
  - Config: Defined in scanner/profiles.py, default 2.0s
  - UI: NONE
  - Impact: Cannot adjust quick voice detection timing
  - Used by: BandScanner.__init__() parameter

- **min_contestness_score** (default: 40.0)
  - Config: Defined in profiles.py, range 40.0-60.0 per profile
  - UI: NONE (but contestness_threshold is in config)
  - Impact: Cannot tune contest filtering threshold
  - Note: Different from contestness_threshold - controls minimum station quality

### Scan Tab Gaps:
- **No control for VAD parameters:**
  - min_speech_duration_ms
  - min_silence_duration_ms
  - VAD sensitivity level values

- **No fine-tuning for speaker detection:**
  - Voice window_duration (affects speaker separation)
  - Voice stride (affects detection granularity)

- **No step size control in UI**
  - step_size_hz is in config (default: 1000 Hz)
  - UI has NO CONTROL (uses default always)
  - Used by: main_window.py line 2476

---

## 4. INCONSISTENT CONFIGURATION USAGE

### contestness_threshold Issues:
- **Configured:** YES (config.contest.contestness_threshold, default: 70)
- **UI Control:** YES (settings_dialog.py line 308-312)
- **Actually Used:** PARTIALLY AND INCONSISTENTLY
  - Used in: BehaviorAnalyzer.is_contest_activity() as parameter
  - Hard-coded fallback in: behavior.py line 438 (threshold=70.0)
  - Profile-based override: scanner/profiles.py defines min_contestness_score per band (40-60)
- **Problem:** Configuration hierarchy unclear:
  1. Global config.contest.contestness_threshold (70)
  2. Profile-based min_contestness_score (varies by band: 40-60)
  3. Hard-coded scanner default (40.0 in engine.py)
  - Which one takes precedence? Not obvious from code.

### enabled_bands Handling:
- **Configured:** YES (config.scan.enabled_bands, default: ["20m", "40m", "15m"])
- **UI Control:** YES (but not in settings_dialog - it's in main_window band checkboxes)
- **Used:** Limited - only used for initial UI state in main_window.py
- **Issue:** UI state during scan startup overrides config every time

### similarity_threshold Double Definition:
- **In config:** voice_db.similarity_threshold (0.75)
- **In UI:** voice_widget.py shows "Similarity: {value}"
- **Actually used:** HARD-CODED 0.75 in main_window.py
- **Config value:** Loaded but ignored
- **Recommendation:** Fix main_window.py to use config value

---

## 5. CANDIDATE ADDITIONS TO CONFIG

These hard-coded values should be added to config.py:

```python
@dataclass
class AudioConfig:
    # ... existing fields ...
    
    # Voice embedding detection (MISSING)
    voice_window_duration: float = 2.5      # Speaker detection window (seconds)
    voice_stride: float = 1.0                # Speaker detection step (seconds)
    
    # VAD fine-tuning (MISSING)
    vad_min_speech_duration_ms: int = 250   # Minimum speech segment
    vad_min_silence_duration_ms: int = 100  # Silence between segments
    
    # Sensitivity thresholds (MISSING - currently hard-coded mapping)
    vad_sensitivity_low: float = 0.7        # Low sensitivity threshold
    vad_sensitivity_medium: float = 0.5     # Medium sensitivity threshold
    vad_sensitivity_high: float = 0.3       # High sensitivity threshold

@dataclass
class RadioConfig:
    # ... existing fields ...
    
    # Radio mode bandwidth (MISSING)
    ssb_bandwidth_hz: int = 2400
    fm_bandwidth_hz: int = 12000

@dataclass  
class ScanConfig:
    # ... existing fields ...
    
    # These are unused and should be either removed or implemented:
    # auto_center_enabled: bool = True          # UNUSED - remove or implement
    # center_tolerance_hz: int = 50             # UNUSED - remove or implement
    # max_center_iterations: int = 3            # UNUSED - remove or implement
    
    # Should add:
    quick_check_duration: float = 2.0         # Voice detection duration
    min_contestness_score: float = 40.0       # Minimum station quality score
```

---

## SUMMARY TABLE

| Parameter | Config | UI | Hard-Coded | Used | Status |
|-----------|--------|----|-----------:|------|--------|
| similarity_threshold | ✓ | ✓ | ✓ (0.75) | ✗ | **BROKEN** - ignores config |
| window_duration | ✗ | ✗ | ✓ (2.5) | ✓ | **MISSING** - should be config |
| stride | ✗ | ✗ | ✓ (1.0) | ✓ | **MISSING** - should be config |
| min_speech_duration_ms | ✗ | ✗ | ✓ (250) | ✓ | **MISSING** - should be config |
| min_silence_duration_ms | ✗ | ✗ | ✓ (100) | ✓ | **MISSING** - should be config |
| vad_thresholds | ✗ | ✗ | ✓ (0.3-0.7) | ✓ | **HARD-CODED** mapping only |
| fm_bandwidth | ✗ | ✗ | ✓ (12000) | ✓ | **MISSING** - should be config |
| ssb_bandwidth | ✗ | ✗ | ✓ (2400) | ✓ | **MISSING** - should be config |
| quick_check_duration | ✓* | ✗ | ✗ | ✓ | **NO UI** - in profiles only |
| min_contestness_score | ✓* | ✗ | ✗ | ✓ | **NO UI** - in profiles only |
| auto_center_enabled | ✓ | ✗ | ✗ | ✗ | **UNUSED** - dead code |
| center_tolerance_hz | ✓ | ✗ | ✗ | ✗ | **UNUSED** - dead code |
| max_center_iterations | ✓ | ✗ | ✗ | ✗ | **UNUSED** - dead code |
| pitch_fmin | ✓ | ✗ | ✗ | ✗ | **UNUSED** - feature disabled |
| pitch_fmax | ✓ | ✗ | ✗ | ✗ | **UNUSED** - feature disabled |
| auto_reset_days | ✓ | ✗ | ✗ | ✗ | **UNUSED** - feature disabled |
| database_file | ✓ | ✗ | ✗ | ✗ | **UNUSED** - feature disabled |
| contestness_threshold | ✓ | ✓ | ✓ (70) | ✓ | **INCONSISTENT** - multiple paths |
| enabled_bands | ✓ | ✓ | ✗ | ✓ | OK - but limited use |

---

## RECOMMENDATIONS

### Priority 1 - Fix Broken Behavior:
1. **Fix similarity_threshold** - Use config value in main_window.py speaker detection
2. **Fix contestness_threshold usage** - Clarify which threshold wins (config vs profile vs default)

### Priority 2 - Add Missing Config:
1. Add voice embedding parameters (window_duration, stride)
2. Add VAD parameters (min_speech_duration_ms, min_silence_duration_ms)
3. Add radio bandwidth parameters

### Priority 3 - Add UI Controls:
1. Add quick_check_duration to Advanced tab
2. Add min_contestness_score to Contest tab
3. Add VAD fine-tuning controls (min durations)
4. Add voice embedding controls (if not disabling the feature)

### Priority 4 - Clean Up:
1. Remove or implement: auto_center_enabled, center_tolerance_hz, max_center_iterations
2. Remove or re-enable: pitch_fmin, pitch_fmax (if CREPE pitch detection is being used)
3. Remove or re-enable: auto_reset_days, database_file (if voice DB is being maintained)

