"""
SSB Auto-Tuner using F0 pitch detection

Automatically centers SSB signals by detecting fundamental frequency.
Voice-independent approach works for any speaker.
"""

import numpy as np
import logging
from typing import Tuple, Optional
from dataclasses import dataclass

from .pitch import PitchDetector, PitchAnalysis

logger = logging.getLogger(__name__)


@dataclass
class CenteringResult:
    """Result of auto-centering attempt"""
    success: bool              # Successfully centered
    final_frequency: int       # Final VFO frequency (Hz)
    iterations: int            # Number of iterations used
    initial_offset: int        # Initial frequency offset (Hz)
    final_offset: int          # Final frequency offset (Hz)
    confidence: float          # Centering confidence (0-1)
    pitch_analysis: Optional[PitchAnalysis] = None


class SSBAutoTuner:
    """
    Automatic SSB signal centering using F0 detection

    Uses voice pitch (fundamental frequency) to determine if signal is
    properly tuned, then adjusts VFO to center it.

    Works for any voice type - male, female, accented.
    """

    def __init__(
        self,
        sample_rate: int = 16000,
        max_iterations: int = 3,
        tolerance_hz: int = 50,
        sideband: str = "USB"
    ):
        """
        Initialize auto-tuner

        Args:
            sample_rate: Audio sample rate
            max_iterations: Maximum tuning iterations
            tolerance_hz: Frequency tolerance (Hz)
            sideband: 'USB' or 'LSB'
        """
        self.sample_rate = sample_rate
        self.max_iterations = max_iterations
        self.tolerance_hz = tolerance_hz
        self.sideband = sideband.upper()

        # Initialize pitch detector
        self.pitch_detector = PitchDetector(sample_rate=sample_rate)

        logger.info(
            f"SSBAutoTuner initialized: sideband={sideband}, "
            f"max_iter={max_iterations}, tolerance={tolerance_hz} Hz"
        )

    def analyze_centering(
        self,
        audio: np.ndarray,
        current_frequency: int
    ) -> Tuple[bool, int, PitchAnalysis]:
        """
        Analyze if signal is centered and calculate correction

        Args:
            audio: Audio signal from radio
            current_frequency: Current VFO frequency (Hz)

        Returns:
            (is_centered, correction_hz, pitch_analysis)
        """
        # Analyze pitch
        analysis = self.pitch_detector.analyze_pitch(audio)

        if analysis.confidence < 0.5 or analysis.voiced_ratio < 0.3:
            logger.debug("Insufficient speech for analysis")
            return False, 0, analysis

        # Check if centered
        is_centered = analysis.is_centered and abs(analysis.estimated_offset_hz) < self.tolerance_hz

        # Calculate correction
        correction = self._calculate_correction(analysis.estimated_offset_hz)

        logger.debug(
            f"Centering analysis: F0={analysis.median_f0:.1f} Hz, "
            f"centered={is_centered}, correction={correction} Hz"
        )

        return is_centered, correction, analysis

    def _calculate_correction(self, offset_hz: int) -> int:
        """
        Calculate VFO correction from pitch offset

        Args:
            offset_hz: Estimated offset from pitch analysis

        Returns:
            VFO correction in Hz
        """
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

    def auto_center(
        self,
        radio_controller,
        audio_capture_func,
        initial_frequency: int,
        capture_duration: float = 3.0
    ) -> CenteringResult:
        """
        Automatically center SSB signal on frequency

        Args:
            radio_controller: Radio control object with set_frequency()
            audio_capture_func: Function that captures audio, returns np.ndarray
            initial_frequency: Starting VFO frequency (Hz)
            capture_duration: Audio capture duration (seconds)

        Returns:
            CenteringResult with details
        """
        current_freq = initial_frequency
        initial_offset = None

        logger.info(f"Auto-centering starting at {current_freq/1e6:.4f} MHz")

        for iteration in range(self.max_iterations):
            logger.debug(f"Iteration {iteration + 1}/{self.max_iterations}")

            # Capture audio
            try:
                audio = audio_capture_func(duration=capture_duration)
            except Exception as e:
                logger.error(f"Audio capture failed: {e}")
                return CenteringResult(
                    success=False,
                    final_frequency=current_freq,
                    iterations=iteration,
                    initial_offset=0,
                    final_offset=0,
                    confidence=0.0
                )

            # Analyze centering
            is_centered, correction, analysis = self.analyze_centering(
                audio,
                current_freq
            )

            # Save initial offset
            if iteration == 0:
                initial_offset = analysis.estimated_offset_hz

            # Check if centered
            if is_centered:
                logger.info(
                    f"✓ Signal centered at {current_freq/1e6:.4f} MHz "
                    f"after {iteration + 1} iteration(s)"
                )
                return CenteringResult(
                    success=True,
                    final_frequency=current_freq,
                    iterations=iteration + 1,
                    initial_offset=initial_offset or 0,
                    final_offset=analysis.estimated_offset_hz,
                    confidence=analysis.confidence,
                    pitch_analysis=analysis
                )

            # Apply correction
            if abs(correction) < self.tolerance_hz:
                # Close enough
                logger.info(
                    f"✓ Signal acceptably centered at {current_freq/1e6:.4f} MHz "
                    f"(offset: {correction} Hz)"
                )
                return CenteringResult(
                    success=True,
                    final_frequency=current_freq,
                    iterations=iteration + 1,
                    initial_offset=initial_offset or 0,
                    final_offset=correction,
                    confidence=analysis.confidence,
                    pitch_analysis=analysis
                )

            # Adjust frequency
            new_freq = current_freq + correction

            logger.info(
                f"Adjusting: {current_freq/1e6:.4f} → {new_freq/1e6:.4f} MHz "
                f"(correction: {correction:+d} Hz)"
            )

            # Set new frequency
            try:
                radio_controller.set_frequency(new_freq)
                current_freq = new_freq

                # Let radio settle
                import time
                time.sleep(0.5)

            except Exception as e:
                logger.error(f"Failed to set frequency: {e}")
                return CenteringResult(
                    success=False,
                    final_frequency=current_freq,
                    iterations=iteration + 1,
                    initial_offset=initial_offset or 0,
                    final_offset=correction,
                    confidence=analysis.confidence,
                    pitch_analysis=analysis
                )

        # Max iterations reached
        logger.warning(
            f"⚠ Could not center signal after {self.max_iterations} iterations"
        )

        # Get final analysis
        audio = audio_capture_func(duration=capture_duration)
        _, _, final_analysis = self.analyze_centering(audio, current_freq)

        return CenteringResult(
            success=False,
            final_frequency=current_freq,
            iterations=self.max_iterations,
            initial_offset=initial_offset or 0,
            final_offset=final_analysis.estimated_offset_hz,
            confidence=final_analysis.confidence,
            pitch_analysis=final_analysis
        )

    def set_sideband(self, sideband: str):
        """Change sideband mode"""
        self.sideband = sideband.upper()
        logger.info(f"Sideband set to {self.sideband}")

    def validate_with_spectral_analysis(
        self,
        audio: np.ndarray
    ) -> Tuple[bool, float]:
        """
        Validate centering using spectral energy distribution

        Secondary validation method to confirm F0-based centering.

        Args:
            audio: Audio signal

        Returns:
            (is_valid, voice_energy_ratio)
        """
        from scipy import signal

        # Compute power spectral density
        freqs, psd = signal.welch(
            audio,
            fs=self.sample_rate,
            nperseg=1024
        )

        # Voice energy should be in 300-3400 Hz (telephone bandwidth)
        voice_mask = (freqs >= 300) & (freqs <= 3400)
        voice_energy = np.sum(psd[voice_mask])

        # Check energy outside voice band
        too_low_mask = (freqs >= 100) & (freqs < 300)
        too_high_mask = (freqs > 3400) & (freqs <= 5000)

        low_energy = np.sum(psd[too_low_mask])
        high_energy = np.sum(psd[too_high_mask])
        total_energy = np.sum(psd)

        # Calculate voice ratio
        voice_ratio = voice_energy / (total_energy + 1e-10)

        # Well-tuned: >60% energy in voice band
        is_valid = voice_ratio > 0.6

        logger.debug(f"Spectral validation: voice_ratio={voice_ratio:.1%}, valid={is_valid}")

        return is_valid, voice_ratio
