# Auto-Centering Analysis and Proposed Improvements

## Executive Summary

CQSentinel has TWO auto-centering systems that are not properly integrated:
1. **SSBAutoTuner**: Full iterative auto-tuning (not currently used)
2. **CarrierDetector**: Simple pitch validation (currently active)

The main issues are:
- **No active auto-centering**: The sophisticated SSBAutoTuner exists but isn't called
- **No mode awareness**: System doesn't adapt to USB vs LSB vs FM
- **No FM support**: FM signals require different centering approach
- **LSB pitch reversal not handled in CarrierDetector**: Simple centering check doesn't account for sideband differences

## Current Implementation Analysis

### 1. SSBAutoTuner (cqsentinel/radio/auto_tuner.py)

**Status**: Implemented but NOT integrated into pipeline

**Features**:
- Iterative pitch-based centering (up to 3 iterations)
- Mode-aware correction logic:
  - **USB**: `correction = -offset_hz` (high pitch → tune DOWN)
  - **LSB**: `correction = +offset_hz` (high pitch → tune UP)
- Uses PitchDetector (pYIN or CREPE)
- Spectral validation (checks energy in 300-3400 Hz voice band)
- ±2 kHz max correction per iteration
- 50 Hz tolerance threshold

**Code**:
```python
# Lines 120-133 in auto_tuner.py
def _calculate_correction(self, offset_hz: int) -> int:
    """Calculate VFO correction from pitch offset"""
    if abs(offset_hz) < self.tolerance_hz:
        return 0

    # Sideband-dependent correction
    # USB: positive offset = signal too high in passband = tune DOWN
    # LSB: positive offset = signal too low in passband = tune UP

    if self.sideband == "USB":
        correction = -offset_hz
    else:  # LSB
        correction = offset_hz

    # Limit correction magnitude
    max_correction = 2000  # ±2 kHz max per iteration
    correction = max(-max_correction, min(max_correction, correction))

    return correction
```

**Problem**: This excellent code is NEVER CALLED in the actual signal scanning pipeline!

### 2. CarrierDetector (cqsentinel/signal/carrier_detector.py)

**Status**: Active in RecordingSession

**Features**:
- Simple pitch range check (150-700 Hz = "centered")
- Provides tuning suggestions (±50 Hz fixed)
- NO mode awareness
- NO sideband-specific logic

**Problem Code** (lines 295-309):
```python
# 7. Centering check (pitch in natural range)
if pitch_valid and info.is_voice_present:
    if self.pitch_min_hz <= pitch <= self.pitch_max_hz:
        info.is_centered = True
        info.tuning_correction_hz = 0.0
    elif pitch < self.pitch_min_hz:
        # Voice too low = frequency too high, tune UP
        info.is_centered = False
        info.tuning_correction_hz = +50.0  # Tune up 50 Hz
    else:
        # Voice too high = frequency too low, tune DOWN
        info.is_centered = False
        info.tuning_correction_hz = -50.0  # Tune down 50 Hz
```

**Critical Issue**: This logic ASSUMES USB! On LSB, the corrections are backwards.
- LSB with low pitch (< 150 Hz) should tune DOWN, not UP
- LSB with high pitch (> 700 Hz) should tune UP, not DOWN

### 3. PitchDetector (cqsentinel/radio/pitch.py)

**Features**:
- Two backends: librosa.pyin (CPU) or CREPE (GPU optional)
- F0 detection in 50-600 Hz range
- Estimates offset but NO mode awareness

**Code** (lines 263-289):
```python
def _calculate_offset(self, measured_f0: float) -> int:
    """Calculate frequency offset from measured F0"""
    if measured_f0 < self.NORMAL_F0_MIN:
        # F0 too low → we're tuned too low → need to tune UP
        offset = -(self.TYPICAL_MALE_F0 - measured_f0)
        offset = int(offset * 15)  # Empirical scaling factor
        return max(offset, -2000)  # Limit to ±2 kHz

    elif measured_f0 > self.NORMAL_F0_MAX:
        # F0 too high → we're tuned too high → need to tune DOWN
        offset = int((measured_f0 - self.TYPICAL_FEMALE_F0) * 5)
        return min(offset, 2000)  # Limit to ±2 kHz

    else:
        # Already centered
        return 0
```

**Issue**: Comment says "we're tuned too low" but this is only true for USB. On LSB, it's reversed.

## Mode-Specific Centering Requirements

### USB (Upper Sideband)
- Audio passband: VFO frequency + 300 to VFO + 3000 Hz
- **High pitch (> 400 Hz)**: Signal too high in passband → **Decrease VFO**
- **Low pitch (< 150 Hz)**: Signal too low in passband → **Increase VFO**
- Example: Voice at 500 Hz pitched → sounds like "Donald Duck" → tune DOWN to normalize

### LSB (Lower Sideband)
- Audio passband: VFO frequency - 300 to VFO - 3000 Hz
- **High pitch (> 400 Hz)**: Signal too LOW in passband (flipped!) → **Increase VFO**
- **Low pitch (< 150 Hz)**: Signal too HIGH in passband (flipped!) → **Decrease VFO**
- Example: Voice at 500 Hz pitched → sounds like "Donald Duck" → tune UP to normalize
- **Pitch shifts are REVERSED from USB!**

### FM (Frequency Modulation)
- **Capture Effect**: Stronger signal "captures" receiver, suppressing weaker signals
- **No pitch shifting**: FM voice sounds natural at any offset (within deviation)
- **Problem**: Can't use pitch to determine centering
- **Solution**: Power-based centering using signal edges

#### Proposed FM Centering Algorithm:

1. **Detect signal edges**:
   - Temporarily switch to CW mode with narrow filter (200-500 Hz)
   - Scan ±5 kHz from current frequency
   - Record power at each 100 Hz step
   - Find signal edges (where power rises/falls significantly)

2. **Calculate center**:
   - Signal start: frequency where power > threshold
   - Signal end: frequency where power drops < threshold
   - Center frequency = (start + end) / 2

3. **Return to FM and tune**:
   - Switch back to FM mode with normal deviation (±5 kHz typical)
   - Set VFO to calculated center frequency
   - Verify signal is still present

4. **Advantages**:
   - Works even with no voice (carrier centering)
   - Takes advantage of FM capture effect (once centered, stays locked)
   - More reliable than pitch-based (which doesn't work for FM)

**Example Power-Based Edge Detection**:
```
Frequency (kHz)  Power (dB)   State
146.520         -120         Noise
146.521         -90          Signal start ← Edge
146.522         -60          Signal
146.523         -55          Signal (peak)
146.524         -60          Signal
146.525         -90          Signal end ← Edge
146.526         -120         Noise

Center = (146.521 + 146.525) / 2 = 146.523 MHz
```

### CW/RTTY/Data Modes
- Similar to FM: pitch doesn't indicate centering
- Use carrier/tone detection and power-based centering
- Could detect tone frequency and center on it

## Proposed Implementation

### Phase 1: Integrate SSBAutoTuner into RecordingSession

**Modify**: `cqsentinel/signal/recording_session.py`

Add auto-centering step between VOICE_PRESENT and CENTERED states:

```python
def _handle_detecting(self) -> Optional[SessionResult]:
    """DETECTING state: Validate signal and check centering."""
    signal_state = self.carrier_detector.update_state(self.detection_buffer)

    if signal_state == SignalState.IDLE:
        self._set_state(SessionState.IDLE)
        return None

    if signal_state == SignalState.CENTERED:
        # Perform VAD check
        if self._validate_vad():
            self._start_recording()
        else:
            self.vad_check_failures += 1
            if self.vad_check_failures >= self.max_vad_failures:
                # Report stuck event for noise tracking
                if self.on_stuck and self.current_frequency_hz > 0:
                    self.on_stuck(self.current_frequency_hz)
                self._set_state(SessionState.IDLE)

    elif signal_state == SignalState.VOICE_PRESENT:
        # NEW: Auto-center the signal before recording
        if self.auto_center_enabled and not self.centering_attempted:
            self._attempt_auto_center()

    return None

def _attempt_auto_center(self):
    """Attempt to auto-center signal using mode-specific algorithm."""
    if not self.radio or not self.auto_tuner:
        # No radio control or auto-tuner available
        return

    try:
        # Get current mode
        mode, bandwidth = self.radio.get_mode()
        mode = mode.upper()

        # Set auto-tuner mode
        if mode in ["USB", "LSB"]:
            self.auto_tuner.set_sideband(mode)

            # Perform auto-centering
            result = self.auto_tuner.auto_center(
                radio_controller=self.radio,
                audio_capture_func=self._capture_audio_for_centering,
                initial_frequency=self.current_frequency_hz,
                capture_duration=2.0  # 2 seconds per iteration
            )

            if result.success:
                logger.info(
                    f"Auto-centered on {mode}: {result.final_frequency/1e6:.4f} MHz "
                    f"(offset: {result.final_offset} Hz, {result.iterations} iterations)"
                )
            else:
                logger.warning(
                    f"Auto-centering failed after {result.iterations} iterations, "
                    f"proceeding anyway"
                )

        elif mode == "FM":
            # Use FM-specific power-based centering
            self._auto_center_fm()

        else:
            logger.debug(f"Auto-centering not supported for mode {mode}")

    except Exception as e:
        logger.error(f"Auto-centering failed: {e}")

    finally:
        self.centering_attempted = True
```

### Phase 2: Add FM Auto-Centering

**New file**: `cqsentinel/radio/fm_tuner.py`

```python
"""
FM Auto-Tuner using power-based edge detection

FM signals don't exhibit pitch shifting, so we use signal power
edges to find the center frequency. Takes advantage of FM capture effect.
"""

import numpy as np
import logging
import time
from typing import Tuple, Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class FMCenteringResult:
    """Result of FM auto-centering attempt"""
    success: bool
    final_frequency: int  # Hz
    signal_start_hz: int  # Signal lower edge
    signal_end_hz: int    # Signal upper edge
    bandwidth_hz: int     # Detected signal bandwidth
    peak_power_db: float


class FMAutoTuner:
    """
    Automatic FM signal centering using power-based edge detection.

    Uses narrow CW filter to find signal edges, then centers on midpoint.
    Takes advantage of FM capture effect for reliable locking.
    """

    def __init__(
        self,
        sample_rate: int = 16000,
        scan_range_hz: int = 10000,  # ±10 kHz scan
        scan_step_hz: int = 100,     # 100 Hz steps
        power_threshold_db: float = -80.0,  # Signal threshold
        edge_hysteresis_db: float = 10.0,   # Hysteresis for edge detection
    ):
        """
        Initialize FM auto-tuner

        Args:
            sample_rate: Audio sample rate
            scan_range_hz: Frequency range to scan (±)
            scan_step_hz: Step size for scanning
            power_threshold_db: Power threshold for signal detection
            edge_hysteresis_db: Hysteresis to avoid noise triggering edges
        """
        self.sample_rate = sample_rate
        self.scan_range_hz = scan_range_hz
        self.scan_step_hz = scan_step_hz
        self.power_threshold_db = power_threshold_db
        self.edge_hysteresis_db = edge_hysteresis_db

        logger.info(
            f"FMAutoTuner initialized: scan=±{scan_range_hz/1000}kHz, "
            f"step={scan_step_hz}Hz, threshold={power_threshold_db}dB"
        )

    def measure_power(self, audio: np.ndarray) -> float:
        """
        Measure audio power in dB

        Args:
            audio: Audio samples

        Returns:
            Power in dB
        """
        if len(audio) == 0:
            return -120.0

        rms = np.sqrt(np.mean(audio.astype(np.float64) ** 2))
        if rms > 1e-10:
            return 20 * np.log10(rms)
        else:
            return -120.0

    def find_signal_edges(
        self,
        radio_controller,
        audio_capture_func,
        center_frequency: int
    ) -> Tuple[Optional[int], Optional[int], float]:
        """
        Find FM signal edges using power scanning

        Args:
            radio_controller: Radio control interface
            audio_capture_func: Function to capture audio
            center_frequency: Starting frequency

        Returns:
            (start_hz, end_hz, peak_power_db) or (None, None, -120.0)
        """
        # Save current mode
        original_mode, original_bw = radio_controller.get_mode()

        try:
            # Switch to CW with narrow filter for edge detection
            logger.info("Switching to CW narrow filter for edge detection")
            radio_controller.set_mode("CW", bandwidth=500)
            time.sleep(0.2)  # Let filter settle

            # Scan power across frequency range
            frequencies = []
            powers = []

            start_freq = center_frequency - self.scan_range_hz
            end_freq = center_frequency + self.scan_range_hz

            logger.info(f"Scanning {start_freq/1e6:.4f} - {end_freq/1e6:.4f} MHz")

            current_freq = start_freq
            while current_freq <= end_freq:
                # Tune to frequency
                radio_controller.set_frequency(current_freq)
                time.sleep(0.05)  # Brief settle time

                # Capture audio and measure power
                audio = audio_capture_func(duration=0.2)
                power = self.measure_power(audio)

                frequencies.append(current_freq)
                powers.append(power)

                current_freq += self.scan_step_hz

            # Find signal edges using threshold with hysteresis
            peak_power = max(powers)
            threshold = self.power_threshold_db

            # Find lower edge (first point above threshold)
            signal_start = None
            for freq, power in zip(frequencies, powers):
                if power > threshold:
                    signal_start = freq
                    break

            # Find upper edge (last point above threshold)
            signal_end = None
            for freq, power in zip(reversed(frequencies), reversed(powers)):
                if power > threshold:
                    signal_end = freq
                    break

            logger.info(
                f"Edge detection: start={signal_start/1e6:.4f if signal_start else None} MHz, "
                f"end={signal_end/1e6:.4f if signal_end else None} MHz, "
                f"peak={peak_power:.1f} dB"
            )

            return signal_start, signal_end, peak_power

        finally:
            # Restore original mode
            logger.info(f"Restoring mode {original_mode}")
            radio_controller.set_mode(original_mode, original_bw)
            time.sleep(0.2)

    def auto_center(
        self,
        radio_controller,
        audio_capture_func,
        initial_frequency: int
    ) -> FMCenteringResult:
        """
        Automatically center FM signal

        Args:
            radio_controller: Radio control interface
            audio_capture_func: Function to capture audio
            initial_frequency: Starting frequency

        Returns:
            FMCenteringResult with centering details
        """
        logger.info(f"FM auto-centering starting at {initial_frequency/1e6:.4f} MHz")

        # Find signal edges
        start_hz, end_hz, peak_power = self.find_signal_edges(
            radio_controller,
            audio_capture_func,
            initial_frequency
        )

        if start_hz is None or end_hz is None:
            logger.warning("Could not detect FM signal edges")
            return FMCenteringResult(
                success=False,
                final_frequency=initial_frequency,
                signal_start_hz=0,
                signal_end_hz=0,
                bandwidth_hz=0,
                peak_power_db=peak_power
            )

        # Calculate center frequency
        center_hz = (start_hz + end_hz) // 2
        bandwidth = end_hz - start_hz

        logger.info(
            f"FM signal detected: {start_hz/1e6:.4f} - {end_hz/1e6:.4f} MHz "
            f"(BW: {bandwidth/1000:.1f} kHz)"
        )

        # Tune to calculated center
        logger.info(f"Centering on {center_hz/1e6:.4f} MHz")
        try:
            radio_controller.set_frequency(center_hz)
            time.sleep(0.5)  # Let radio settle and capture effect lock

            return FMCenteringResult(
                success=True,
                final_frequency=center_hz,
                signal_start_hz=start_hz,
                signal_end_hz=end_hz,
                bandwidth_hz=bandwidth,
                peak_power_db=peak_power
            )

        except Exception as e:
            logger.error(f"Failed to set center frequency: {e}")
            return FMCenteringResult(
                success=False,
                final_frequency=initial_frequency,
                signal_start_hz=start_hz,
                signal_end_hz=end_hz,
                bandwidth_hz=bandwidth,
                peak_power_db=peak_power
            )
```

### Phase 3: Fix CarrierDetector LSB Support

**Modify**: `cqsentinel/signal/carrier_detector.py`

Add mode awareness to centering check:

```python
class CarrierDetector:
    def __init__(self, ..., radio=None, ...):
        self.radio = radio  # Need radio to query mode
        ...

    def analyze_signal(self, audio: np.ndarray) -> SignalInfo:
        """Comprehensive signal analysis."""
        info = SignalInfo()

        # ... existing code ...

        # 7. Centering check (pitch in natural range) - MODE AWARE
        if pitch_valid and info.is_voice_present:
            # Get current radio mode
            mode = "USB"  # Default assumption
            if self.radio:
                try:
                    mode, _ = self.radio.get_mode()
                    mode = mode.upper()
                except:
                    pass

            if self.pitch_min_hz <= pitch <= self.pitch_max_hz:
                info.is_centered = True
                info.tuning_correction_hz = 0.0

            elif pitch < self.pitch_min_hz:
                # Voice too low - correction depends on mode
                if mode == "LSB":
                    # LSB: low pitch = tune DOWN (reversed from USB)
                    info.tuning_correction_hz = -50.0
                else:
                    # USB: low pitch = tune UP
                    info.tuning_correction_hz = +50.0
                info.is_centered = False

            else:  # pitch > self.pitch_max_hz
                # Voice too high - correction depends on mode
                if mode == "LSB":
                    # LSB: high pitch = tune UP (reversed from USB)
                    info.tuning_correction_hz = +50.0
                else:
                    # USB: high pitch = tune DOWN
                    info.tuning_correction_hz = -50.0
                info.is_centered = False

        else:
            info.is_centered = False

        # ... rest of code ...
```

## Configuration Changes

**Add to**: `cqsentinel/config.py`

```python
@dataclass
class ScanConfig:
    # ... existing fields ...

    # Auto-centering configuration
    auto_center_enabled: bool = True
    auto_center_modes: list = field(default_factory=lambda: ["USB", "LSB", "FM"])
    auto_center_fm_enabled: bool = True  # Use power-based FM centering
    center_tolerance_hz: int = 50
    max_center_iterations: int = 3

    # FM-specific centering
    fm_scan_range_hz: int = 10000  # ±10 kHz
    fm_scan_step_hz: int = 100     # 100 Hz steps
    fm_power_threshold_db: float = -80.0
```

## Testing Recommendations

### 1. USB Testing
- Deliberately offset frequency by +1 kHz, verify auto-tuner tunes DOWN
- Deliberately offset frequency by -1 kHz, verify auto-tuner tunes UP
- Test with male and female voices
- Test with various accents

### 2. LSB Testing
- **Critical**: Deliberately offset frequency by +1 kHz, verify auto-tuner tunes UP (opposite of USB!)
- Deliberately offset frequency by -1 kHz, verify auto-tuner tunes DOWN (opposite of USB!)
- Verify pitch detection still works (voice should sound low-pitched when offset high, etc.)

### 3. FM Testing
- Test with strong FM signal (repeater)
- Test with weak FM signal
- Test with off-center signals (±3 kHz, ±5 kHz)
- Verify capture effect works after centering
- Test with and without voice (carrier-only centering)

### 4. Edge Cases
- Rapid frequency drift during centering
- Very weak signals near noise floor
- Multiple overlapping signals (should center on strongest due to capture effect in FM)
- Mode changes during operation

## Priority Recommendations

**High Priority**:
1. ✅ Fix LSB pitch correction logic in CarrierDetector (lines 295-309)
2. ✅ Add mode awareness to CarrierDetector
3. ✅ Integrate SSBAutoTuner into RecordingSession

**Medium Priority**:
4. Implement FM power-based auto-centering
5. Add configuration UI for auto-centering parameters
6. Add logging/metrics for centering success rate

**Low Priority**:
7. CW/RTTY tone-based centering
8. Adaptive pitch thresholds based on observed voice characteristics
9. Multi-signal handling (center on strongest/loudest)

## Implementation Checklist

- [ ] Fix LSB pitch correction in carrier_detector.py
- [ ] Add radio mode querying to CarrierDetector
- [ ] Create SSBAutoTuner instance in SignalScanner
- [ ] Integrate auto-centering into RecordingSession state machine
- [ ] Implement FMAutoTuner class
- [ ] Add configuration parameters
- [ ] Add settings UI controls
- [ ] Write unit tests for pitch correction logic
- [ ] Write integration tests for USB/LSB/FM
- [ ] Document in user guide

## References

- **SSB Pitch Shifting**: [https://www.nonstopsystems.com/radio/frank_radio_ssb.htm](https://www.nonstopsystems.com/radio/frank_radio_ssb.htm)
- **FM Capture Effect**: [https://en.wikipedia.org/wiki/Capture_effect](https://en.wikipedia.org/wiki/Capture_effect)
- **Voice F0 Ranges**: Male 85-180 Hz, Female 165-255 Hz (typical)
- **SSB Filter Characteristics**: Typically 300-3000 Hz or 300-2400 Hz
