"""
Pitch detection for SSB auto-centering

Uses fundamental frequency (F0) detection to determine if SSB signal is properly tuned.
Voice-independent approach works for male, female, and accented voices.
"""

import numpy as np
import librosa
import logging
from typing import Tuple, Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class PitchAnalysis:
    """Result of pitch analysis"""
    median_f0: float           # Median F0 in Hz
    f0_range: Tuple[float, float]  # (min, max) F0
    is_centered: bool          # Signal properly tuned
    confidence: float          # Analysis confidence (0-1)
    voiced_ratio: float        # Ratio of voiced frames (0-1)
    estimated_offset_hz: int   # Estimated frequency offset


class PitchDetector:
    """
    Fundamental frequency (F0) detection for SSB signals

    Uses pYIN algorithm (probabilistic YIN) for robust pitch detection
    in noisy conditions.
    """

    # Normal human speech F0 ranges
    NORMAL_F0_MIN = 75   # Hz (below this = tuned too low)
    NORMAL_F0_MAX = 400  # Hz (above this = tuned too high)
    TYPICAL_MALE_F0 = 120    # Hz (reference for offset calculation)
    TYPICAL_FEMALE_F0 = 220  # Hz

    def __init__(
        self,
        sample_rate: int = 16000,
        fmin: int = 50,      # Minimum F0 to detect
        fmax: int = 600,     # Maximum F0 to detect
        frame_length: int = 2048
    ):
        """
        Initialize pitch detector

        Args:
            sample_rate: Audio sample rate
            fmin: Minimum F0 frequency (Hz)
            fmax: Maximum F0 frequency (Hz)
            frame_length: Frame size for analysis
        """
        self.sample_rate = sample_rate
        self.fmin = fmin
        self.fmax = fmax
        self.frame_length = frame_length

        logger.info(f"PitchDetector initialized: fmin={fmin}, fmax={fmax}")

    def detect_f0(
        self,
        audio: np.ndarray,
        return_all: bool = False
    ) -> Tuple[np.ndarray, np.ndarray]:
        """
        Detect fundamental frequency using pYIN

        Args:
            audio: Audio signal (mono, float32)
            return_all: If True, return all F0 values; else only voiced

        Returns:
            (f0_values, voiced_flag) - F0 in Hz and voicing probability
        """
        if len(audio) < self.frame_length:
            logger.warning("Audio too short for F0 detection")
            return np.array([]), np.array([])

        try:
            # Use librosa pYIN for robust F0 detection
            f0, voiced_flag, voiced_probs = librosa.pyin(
                audio,
                sr=self.sample_rate,
                fmin=self.fmin,
                fmax=self.fmax,
                frame_length=self.frame_length,
                fill_na=None  # Keep NaN for unvoiced frames
            )

            # Filter to voiced frames only (unless return_all)
            if not return_all:
                voiced_mask = ~np.isnan(f0) & (voiced_probs > 0.5)
                f0_voiced = f0[voiced_mask]
                probs_voiced = voiced_probs[voiced_mask]
            else:
                f0_voiced = f0
                probs_voiced = voiced_probs

            logger.debug(f"Detected F0: {len(f0_voiced)} voiced frames")

            return f0_voiced, probs_voiced

        except Exception as e:
            logger.error(f"F0 detection failed: {e}")
            return np.array([]), np.array([])

    def analyze_pitch(
        self,
        audio: np.ndarray,
        min_voiced_ratio: float = 0.3
    ) -> PitchAnalysis:
        """
        Analyze pitch to determine if SSB signal is centered

        Args:
            audio: Audio signal
            min_voiced_ratio: Minimum voiced ratio to consider valid

        Returns:
            PitchAnalysis with results
        """
        # Detect F0
        f0_values, voiced_probs = self.detect_f0(audio, return_all=False)

        if len(f0_values) == 0:
            # No voiced speech detected
            return PitchAnalysis(
                median_f0=0.0,
                f0_range=(0.0, 0.0),
                is_centered=False,
                confidence=0.0,
                voiced_ratio=0.0,
                estimated_offset_hz=0
            )

        # Calculate statistics
        median_f0 = float(np.median(f0_values))
        f0_min = float(np.min(f0_values))
        f0_max = float(np.max(f0_values))
        confidence = float(np.mean(voiced_probs))

        # Calculate voiced ratio
        f0_all, _ = self.detect_f0(audio, return_all=True)
        voiced_ratio = len(f0_values) / len(f0_all) if len(f0_all) > 0 else 0.0

        # Check if enough voiced speech
        if voiced_ratio < min_voiced_ratio:
            logger.debug(f"Not enough voiced speech: {voiced_ratio:.1%}")
            return PitchAnalysis(
                median_f0=median_f0,
                f0_range=(f0_min, f0_max),
                is_centered=False,
                confidence=confidence,
                voiced_ratio=voiced_ratio,
                estimated_offset_hz=0
            )

        # Determine if properly centered
        is_centered = self.NORMAL_F0_MIN <= median_f0 <= self.NORMAL_F0_MAX

        # Calculate estimated offset
        estimated_offset = self._calculate_offset(median_f0)

        logger.debug(
            f"F0 analysis: median={median_f0:.1f} Hz, "
            f"range=[{f0_min:.1f}, {f0_max:.1f}], "
            f"centered={is_centered}, "
            f"offset={estimated_offset} Hz"
        )

        return PitchAnalysis(
            median_f0=median_f0,
            f0_range=(f0_min, f0_max),
            is_centered=is_centered,
            confidence=confidence,
            voiced_ratio=voiced_ratio,
            estimated_offset_hz=estimated_offset
        )

    def _calculate_offset(self, measured_f0: float) -> int:
        """
        Calculate frequency offset from measured F0

        Args:
            measured_f0: Measured fundamental frequency

        Returns:
            Estimated offset in Hz (negative = tune up, positive = tune down)
        """
        if measured_f0 < self.NORMAL_F0_MIN:
            # F0 too low → we're tuned too low → need to tune UP
            # Estimate based on typical male voice
            offset = -(self.TYPICAL_MALE_F0 - measured_f0)
            # Scale to VFO offset (rough approximation)
            offset = int(offset * 15)  # Empirical scaling factor
            return max(offset, -2000)  # Limit to ±2 kHz

        elif measured_f0 > self.NORMAL_F0_MAX:
            # F0 too high → we're tuned too high → need to tune DOWN
            # "Donald Duck" effect
            offset = int((measured_f0 - self.TYPICAL_FEMALE_F0) * 5)
            return min(offset, 2000)  # Limit to ±2 kHz

        else:
            # Already centered
            return 0

    def quick_check(self, audio: np.ndarray) -> bool:
        """
        Quick check if signal has reasonable F0 (is centered)

        Args:
            audio: Audio signal

        Returns:
            True if F0 is in normal range
        """
        result = self.analyze_pitch(audio)
        return result.is_centered and result.confidence > 0.5
