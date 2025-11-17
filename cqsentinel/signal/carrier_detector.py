"""
Carrier Detection and Signal Analysis

Detects presence of SSB voice signals and verifies proper frequency centering
before initiating transcription recording.
"""

import numpy as np
import logging
from typing import Tuple, Optional
from enum import Enum
from dataclasses import dataclass

logger = logging.getLogger(__name__)


class SignalState(Enum):
    """State machine for carrier detection"""
    IDLE = "idle"  # No signal detected
    SIGNAL_DETECTED = "signal_detected"  # S-meter shows signal
    VOICE_PRESENT = "voice_present"  # Audio contains voice (not just carrier)
    CENTERED = "centered"  # Properly tuned (voice pitch is natural)
    RECORDING = "recording"  # Capturing 90s of audio
    ANALYZING = "analyzing"  # Processing transcript


@dataclass
class SignalInfo:
    """Information about the current signal"""
    s_meter: float = 0.0  # S-units (0-9+)
    audio_rms_db: float = -100.0  # dB level
    speech_band_ratio: float = 0.0  # Ratio of energy in speech band
    estimated_pitch: float = 0.0  # Detected pitch in Hz
    is_signal_present: bool = False
    is_voice_present: bool = False
    is_centered: bool = False
    tuning_correction_hz: float = 0.0  # Suggested tuning adjustment


class CarrierDetector:
    """
    Detects and validates SSB voice signals before transcription.

    Combines CAT control (S-meter) with audio analysis (energy, pitch) to:
    1. Detect signal presence
    2. Verify voice activity (not just carrier/noise)
    3. Confirm proper frequency centering
    """

    def __init__(
        self,
        radio=None,
        pitch_detector=None,
        sample_rate: int = 16000,
        s_meter_threshold: float = 3.0,  # S3 minimum
        audio_rms_threshold_db: float = -40.0,  # dB minimum
        speech_band_ratio_threshold: float = 0.5,  # 50% energy in speech band
        pitch_min_hz: float = 150.0,  # Minimum natural speech pitch
        pitch_max_hz: float = 700.0,  # Maximum natural speech pitch
    ):
        """
        Initialize carrier detector.

        Args:
            radio: Radio control interface (for S-meter queries)
            pitch_detector: Pitch detection instance (for centering check)
            sample_rate: Audio sample rate
            s_meter_threshold: Minimum S-meter reading (S-units)
            audio_rms_threshold_db: Minimum audio level (dB)
            speech_band_ratio_threshold: Minimum ratio of speech band energy
            pitch_min_hz: Minimum expected natural pitch
            pitch_max_hz: Maximum expected natural pitch
        """
        self.radio = radio
        self.pitch_detector = pitch_detector
        self.sample_rate = sample_rate

        # Detection thresholds
        self.s_meter_threshold = s_meter_threshold
        self.audio_rms_threshold_db = audio_rms_threshold_db
        self.speech_band_ratio_threshold = speech_band_ratio_threshold
        self.pitch_min_hz = pitch_min_hz
        self.pitch_max_hz = pitch_max_hz

        # State
        self.state = SignalState.IDLE
        self.last_signal_info = SignalInfo()

        logger.info(
            f"CarrierDetector initialized: S-meter>{s_meter_threshold}, "
            f"RMS>{audio_rms_threshold_db}dB, speech_ratio>{speech_band_ratio_threshold}"
        )

    def get_s_meter(self) -> float:
        """
        Query S-meter from radio via CAT.

        Returns:
            S-meter reading in S-units (0-9+, >9 for S9+)
            Returns 0 if radio not available or error
        """
        if not self.radio:
            return 0.0

        try:
            # rigctld command: +l STRENGTH returns signal strength
            # This is radio-specific, some return dBm, others S-units
            strength = self.radio.get_signal_strength()

            # Convert to S-units if needed
            # S9 = -73 dBm, each S-unit is 6 dB
            if strength is not None:
                if strength < 0:  # Likely dBm
                    # Convert dBm to S-units
                    # S9 = -73 dBm, S1 = -121 dBm
                    s_units = (strength + 127) / 6.0
                    return max(0, s_units)
                else:
                    return float(strength)
        except Exception as e:
            logger.debug(f"S-meter query failed: {e}")

        return 0.0

    def calculate_audio_rms_db(self, audio: np.ndarray) -> float:
        """
        Calculate RMS level of audio in dB.

        Args:
            audio: Audio samples (float32, normalized to -1..1)

        Returns:
            RMS level in dB (0 dB = full scale)
        """
        if len(audio) == 0:
            return -100.0

        # Calculate RMS
        rms = np.sqrt(np.mean(audio.astype(np.float64) ** 2))

        # Convert to dB (avoid log of zero)
        if rms > 1e-10:
            rms_db = 20 * np.log10(rms)
        else:
            rms_db = -100.0

        return rms_db

    def calculate_speech_band_ratio(self, audio: np.ndarray) -> float:
        """
        Calculate ratio of energy in speech band (300-3000 Hz) vs total.

        SSB voice has most energy concentrated in speech frequencies.
        Noise/static has more uniform distribution.

        Args:
            audio: Audio samples (float32)

        Returns:
            Ratio of speech band energy to total energy (0.0-1.0)
        """
        if len(audio) < 1024:
            return 0.0

        try:
            # Compute FFT
            fft_size = min(8192, len(audio))
            fft = np.fft.rfft(audio[:fft_size])
            power = np.abs(fft) ** 2
            freqs = np.fft.rfftfreq(fft_size, 1.0 / self.sample_rate)

            # Find indices for speech band (300-3000 Hz)
            speech_low = np.searchsorted(freqs, 300)
            speech_high = np.searchsorted(freqs, 3000)

            # Calculate energy in speech band vs total
            total_energy = np.sum(power)
            speech_energy = np.sum(power[speech_low:speech_high])

            if total_energy > 0:
                ratio = speech_energy / total_energy
            else:
                ratio = 0.0

            return ratio

        except Exception as e:
            logger.debug(f"Speech band calculation failed: {e}")
            return 0.0

    def estimate_pitch(self, audio: np.ndarray) -> Tuple[float, bool]:
        """
        Estimate fundamental frequency (pitch) of voice.

        Natural speech has pitch in 150-700 Hz range.
        Off-frequency SSB shifts voice pitch proportionally.

        Args:
            audio: Audio samples

        Returns:
            Tuple of (pitch_hz, is_valid)
        """
        if self.pitch_detector is None:
            # Fallback: simple autocorrelation pitch detection
            return self._simple_pitch_detect(audio)

        try:
            pitch = self.pitch_detector.detect(audio)
            is_valid = pitch > 0 and pitch < 1000
            return (pitch, is_valid)
        except Exception as e:
            logger.debug(f"Pitch detection failed: {e}")
            return (0.0, False)

    def _simple_pitch_detect(self, audio: np.ndarray) -> Tuple[float, bool]:
        """
        Simple autocorrelation-based pitch detection.

        Fallback when no pitch detector is available.
        """
        if len(audio) < 2048:
            return (0.0, False)

        try:
            # Use autocorrelation
            # Pitch range: 100-800 Hz
            min_lag = int(self.sample_rate / 800)  # Max frequency
            max_lag = int(self.sample_rate / 100)  # Min frequency

            # Compute autocorrelation
            audio_centered = audio[:4096] - np.mean(audio[:4096])
            corr = np.correlate(audio_centered, audio_centered, mode='full')
            corr = corr[len(corr)//2:]  # Take positive lags only

            # Find peak in valid range
            if max_lag >= len(corr):
                max_lag = len(corr) - 1

            search_range = corr[min_lag:max_lag]
            if len(search_range) == 0:
                return (0.0, False)

            peak_idx = np.argmax(search_range) + min_lag
            peak_val = corr[peak_idx]

            # Check if peak is significant (voiced vs unvoiced)
            if peak_val > 0.3 * corr[0]:  # 30% of zero-lag
                pitch = self.sample_rate / peak_idx
                return (pitch, True)
            else:
                return (0.0, False)

        except Exception as e:
            logger.debug(f"Simple pitch detection failed: {e}")
            return (0.0, False)

    def analyze_signal(self, audio: np.ndarray) -> SignalInfo:
        """
        Comprehensive signal analysis.

        Args:
            audio: Audio samples (1-2 seconds recommended)

        Returns:
            SignalInfo with all detection results
        """
        info = SignalInfo()

        # 1. S-meter check (CAT)
        info.s_meter = self.get_s_meter()

        # 2. Audio RMS level
        info.audio_rms_db = self.calculate_audio_rms_db(audio)

        # 3. Speech band energy ratio
        info.speech_band_ratio = self.calculate_speech_band_ratio(audio)

        # 4. Pitch estimation
        pitch, pitch_valid = self.estimate_pitch(audio)
        info.estimated_pitch = pitch

        # 5. Signal presence (S-meter OR audio energy)
        info.is_signal_present = (
            info.s_meter >= self.s_meter_threshold or
            info.audio_rms_db >= self.audio_rms_threshold_db
        )

        # 6. Voice presence (speech band energy)
        info.is_voice_present = (
            info.is_signal_present and
            info.speech_band_ratio >= self.speech_band_ratio_threshold
        )

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
        else:
            info.is_centered = False

        self.last_signal_info = info

        logger.debug(
            f"Signal analysis: S={info.s_meter:.1f}, RMS={info.audio_rms_db:.1f}dB, "
            f"speech_ratio={info.speech_band_ratio:.2f}, pitch={info.estimated_pitch:.1f}Hz, "
            f"present={info.is_signal_present}, voice={info.is_voice_present}, "
            f"centered={info.is_centered}"
        )

        return info

    def update_state(self, audio: np.ndarray) -> SignalState:
        """
        Update state machine based on signal analysis.

        Args:
            audio: Recent audio samples

        Returns:
            Current state
        """
        info = self.analyze_signal(audio)

        # State transitions
        if self.state == SignalState.IDLE:
            if info.is_signal_present:
                self.state = SignalState.SIGNAL_DETECTED
                logger.info(f"Signal detected: S={info.s_meter:.1f}, RMS={info.audio_rms_db:.1f}dB")

        elif self.state == SignalState.SIGNAL_DETECTED:
            if not info.is_signal_present:
                self.state = SignalState.IDLE
                logger.info("Signal lost, returning to IDLE")
            elif info.is_voice_present:
                self.state = SignalState.VOICE_PRESENT
                logger.info(f"Voice detected: speech_ratio={info.speech_band_ratio:.2f}")

        elif self.state == SignalState.VOICE_PRESENT:
            if not info.is_signal_present:
                self.state = SignalState.IDLE
                logger.info("Signal lost, returning to IDLE")
            elif not info.is_voice_present:
                self.state = SignalState.SIGNAL_DETECTED
                logger.info("Voice lost, still have signal")
            elif info.is_centered:
                self.state = SignalState.CENTERED
                logger.info(f"Signal centered: pitch={info.estimated_pitch:.1f}Hz")

        elif self.state == SignalState.CENTERED:
            if not info.is_signal_present:
                self.state = SignalState.IDLE
                logger.info("Signal lost, returning to IDLE")
            elif not info.is_voice_present:
                self.state = SignalState.SIGNAL_DETECTED
                logger.info("Voice lost, still have signal")
            elif not info.is_centered:
                self.state = SignalState.VOICE_PRESENT
                logger.info(f"Lost centering, pitch={info.estimated_pitch:.1f}Hz")

        # RECORDING and ANALYZING states are managed externally

        return self.state

    def reset(self):
        """Reset to IDLE state"""
        self.state = SignalState.IDLE
        self.last_signal_info = SignalInfo()
        logger.info("CarrierDetector reset to IDLE")

    def is_ready_to_record(self) -> bool:
        """Check if we have a centered signal ready for recording"""
        return self.state == SignalState.CENTERED

    def get_tuning_suggestion(self) -> float:
        """
        Get suggested frequency adjustment.

        Returns:
            Adjustment in Hz (positive = tune up, negative = tune down)
        """
        return self.last_signal_info.tuning_correction_hz
