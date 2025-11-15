"""
Voice Activity Detection using Silero VAD

Detects when speech is present in audio, ignoring silence and noise.
"""

import numpy as np
import logging
from typing import List, Tuple, Optional, TYPE_CHECKING

# Lazy import for torch - only load when actually needed (saves ~10-15 seconds at startup)
if TYPE_CHECKING:
    import torch

logger = logging.getLogger(__name__)

_torch = None


def _get_torch():
    """Lazy import of torch (slow to load, ~10-15 seconds)"""
    global _torch
    if _torch is None:
        import torch
        _torch = torch
    return _torch


class VoiceActivityDetector:
    """
    Voice Activity Detection using Silero VAD

    Identifies speech segments in audio, filtering out silence and noise.
    """

    def __init__(
        self,
        sample_rate: int = 16000,
        threshold: float = 0.5,
        min_speech_duration_ms: int = 250,
        min_silence_duration_ms: int = 100
    ):
        """
        Initialize VAD

        Args:
            sample_rate: Audio sample rate (8000 or 16000)
            threshold: Speech probability threshold (0.0-1.0)
            min_speech_duration_ms: Minimum speech segment duration
            min_silence_duration_ms: Minimum silence to split segments
        """
        self.sample_rate = sample_rate
        self.threshold = threshold
        self.min_speech_duration_ms = min_speech_duration_ms
        self.min_silence_duration_ms = min_silence_duration_ms

        self.model = None
        self.utils = None

        logger.info(f"VAD initialized: sr={sample_rate}, threshold={threshold}")

    def _load_model(self):
        """Lazy-load Silero VAD model"""
        if self.model is not None:
            return

        try:
            logger.info("Loading Silero VAD model and PyTorch...")
            torch = _get_torch()  # Lazy import torch here

            # Load Silero VAD
            model, utils = torch.hub.load(
                repo_or_dir='snakers4/silero-vad',
                model='silero_vad',
                force_reload=False,
                onnx=False
            )

            self.model = model
            self.utils = utils

            logger.info("[OK] Silero VAD model loaded")

        except Exception as e:
            logger.error(f"Failed to load VAD model: {e}")
            raise

    def detect_speech(
        self,
        audio: np.ndarray,
        return_seconds: bool = True
    ) -> List[dict]:
        """
        Detect speech segments in audio

        Args:
            audio: Audio signal (mono, float32)
            return_seconds: If True, return timestamps in seconds; else samples

        Returns:
            List of dicts with 'start', 'end' timestamps for each speech segment
        """
        self._load_model()

        if len(audio) == 0:
            return []

        try:
            torch = _get_torch()  # Get torch for tensor conversion

            # Convert to tensor
            audio_tensor = torch.from_numpy(audio).float()

            # Get speech timestamps
            speech_timestamps = self.utils[0](
                audio_tensor,
                self.model,
                sampling_rate=self.sample_rate,
                threshold=self.threshold,
                min_speech_duration_ms=self.min_speech_duration_ms,
                min_silence_duration_ms=self.min_silence_duration_ms
            )

            # Convert to desired format
            segments = []
            for ts in speech_timestamps:
                start = ts['start']
                end = ts['end']

                if return_seconds:
                    start = start / self.sample_rate
                    end = end / self.sample_rate

                segments.append({
                    'start': start,
                    'end': end,
                    'duration': end - start if return_seconds else (end - start) / self.sample_rate
                })

            logger.debug(f"Detected {len(segments)} speech segments")
            return segments

        except Exception as e:
            logger.error(f"VAD detection failed: {e}")
            return []

    def has_speech(self, audio: np.ndarray, min_duration: float = 0.5) -> bool:
        """
        Quick check if audio contains speech

        Args:
            audio: Audio signal
            min_duration: Minimum speech duration to consider (seconds)

        Returns:
            True if speech detected above minimum duration
        """
        segments = self.detect_speech(audio, return_seconds=True)

        total_speech = sum(seg['duration'] for seg in segments)
        return total_speech >= min_duration

    def get_speech_ratio(self, audio: np.ndarray) -> float:
        """
        Calculate ratio of speech to total audio duration

        Args:
            audio: Audio signal

        Returns:
            Ratio of speech (0.0 - 1.0)
        """
        if len(audio) == 0:
            return 0.0

        segments = self.detect_speech(audio, return_seconds=True)
        total_speech = sum(seg['duration'] for seg in segments)
        total_duration = len(audio) / self.sample_rate

        return total_speech / total_duration if total_duration > 0 else 0.0

    def extract_speech_segments(
        self,
        audio: np.ndarray,
        padding_ms: int = 100
    ) -> List[Tuple[np.ndarray, dict]]:
        """
        Extract speech segments from audio with padding

        Args:
            audio: Audio signal
            padding_ms: Padding to add around speech (milliseconds)

        Returns:
            List of (segment_audio, metadata) tuples
        """
        segments = self.detect_speech(audio, return_seconds=False)

        padding_samples = int((padding_ms / 1000.0) * self.sample_rate)

        extracted = []
        for seg in segments:
            start = max(0, int(seg['start']) - padding_samples)
            end = min(len(audio), int(seg['end']) + padding_samples)

            segment_audio = audio[start:end]

            metadata = {
                'start': start / self.sample_rate,
                'end': end / self.sample_rate,
                'duration': len(segment_audio) / self.sample_rate,
                'start_sample': start,
                'end_sample': end
            }

            extracted.append((segment_audio, metadata))

        return extracted

    def set_sensitivity(self, level: str):
        """
        Set VAD sensitivity

        Args:
            level: 'low', 'medium', 'high'
        """
        sensitivity_map = {
            'low': 0.7,      # Less sensitive, fewer false positives
            'medium': 0.5,   # Balanced
            'high': 0.3      # More sensitive, catches more speech
        }

        self.threshold = sensitivity_map.get(level, 0.5)
        logger.info(f"VAD sensitivity set to {level} (threshold={self.threshold})")
