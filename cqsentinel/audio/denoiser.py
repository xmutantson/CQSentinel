"""
Audio noise reduction using noisereduce library

RNNoise-based denoising for SSB radio signals.
"""

import numpy as np
import logging
from typing import Optional
import noisereduce as nr

logger = logging.getLogger(__name__)


class AudioDenoiser:
    """
    Audio noise reduction using noisereduce (RNNoise-based)

    Reduces background noise, static, and QRM from SSB signals.
    """

    def __init__(
        self,
        sample_rate: int = 16000,
        stationary: bool = True,
        prop_decrease: float = 1.0
    ):
        """
        Initialize audio denoiser

        Args:
            sample_rate: Audio sample rate in Hz
            stationary: True for stationary noise (recommended for SSB)
            prop_decrease: Proportion of noise to reduce (0.0-1.0, 1.0=maximum)
        """
        self.sample_rate = sample_rate
        self.stationary = stationary
        self.prop_decrease = prop_decrease

        logger.info(f"AudioDenoiser initialized: sr={sample_rate}, stationary={stationary}")

    def denoise(
        self,
        audio: np.ndarray,
        noise_profile: Optional[np.ndarray] = None
    ) -> np.ndarray:
        """
        Remove noise from audio signal

        Args:
            audio: Audio signal (mono, float32)
            noise_profile: Optional noise-only sample for profile estimation.
                          If None, uses first 0.5 seconds as noise estimate.

        Returns:
            Denoised audio signal
        """
        if len(audio) == 0:
            logger.warning("Empty audio provided to denoiser")
            return audio

        try:
            # Ensure correct dtype
            audio = audio.astype(np.float32)

            # Apply noise reduction
            if self.stationary:
                # Stationary noise reduction (better for SSB)
                reduced = nr.reduce_noise(
                    y=audio,
                    sr=self.sample_rate,
                    stationary=True,
                    prop_decrease=self.prop_decrease,
                    y_noise=noise_profile
                )
            else:
                # Non-stationary noise reduction
                reduced = nr.reduce_noise(
                    y=audio,
                    sr=self.sample_rate,
                    stationary=False,
                    prop_decrease=self.prop_decrease
                )

            logger.debug(f"Denoised {len(audio)} samples")
            return reduced.astype(np.float32)

        except Exception as e:
            logger.error(f"Denoising failed: {e}")
            return audio  # Return original on error

    def estimate_noise_profile(
        self,
        audio: np.ndarray,
        duration_sec: float = 0.5
    ) -> np.ndarray:
        """
        Estimate noise profile from audio sample

        Args:
            audio: Audio signal containing noise
            duration_sec: Duration to use for noise estimation

        Returns:
            Noise profile for use in denoise()
        """
        samples = int(duration_sec * self.sample_rate)
        noise_sample = audio[:min(samples, len(audio))]

        logger.debug(f"Estimated noise profile from {len(noise_sample)} samples")
        return noise_sample

    def set_strength(self, level: str):
        """
        Set denoising strength

        Args:
            level: 'off', 'low', 'medium', 'high'
        """
        strength_map = {
            'off': 0.0,
            'low': 0.5,
            'medium': 0.8,
            'high': 1.0
        }

        self.prop_decrease = strength_map.get(level, 0.8)
        logger.info(f"Denoising strength set to {level} (prop_decrease={self.prop_decrease})")
