"""
Complete audio processing pipeline

Integrates denoising, VAD, and transcription into single pipeline.
"""

import numpy as np
import logging
from typing import List, Dict, Optional
from dataclasses import dataclass

from .denoiser import AudioDenoiser
from .vad import VoiceActivityDetector
from ..speech.transcription import SpeechTranscriber, TranscriptSegment

logger = logging.getLogger(__name__)


@dataclass
class ProcessedAudio:
    """Result of audio processing pipeline"""
    raw_audio: np.ndarray
    clean_audio: np.ndarray
    has_speech: bool
    speech_ratio: float
    transcripts: List[TranscriptSegment]
    duration: float


class AudioPipeline:
    """
    Complete audio processing pipeline for SSB signals

    Processes audio through:
    1. Noise reduction (RNNoise)
    2. Voice activity detection (Silero VAD)
    3. Speech-to-text (Whisper)
    """

    def __init__(
        self,
        sample_rate: int = 16000,
        denoise_level: str = "medium",
        vad_threshold: float = 0.5,
        whisper_model: str = "small"
    ):
        """
        Initialize audio pipeline

        Args:
            sample_rate: Audio sample rate
            denoise_level: 'off', 'low', 'medium', 'high'
            vad_threshold: VAD sensitivity (0.0-1.0)
            whisper_model: Whisper model size
        """
        self.sample_rate = sample_rate

        # Initialize components
        self.denoiser = AudioDenoiser(sample_rate=sample_rate)
        self.denoiser.set_strength(denoise_level)

        self.vad = VoiceActivityDetector(
            sample_rate=sample_rate,
            threshold=vad_threshold
        )

        self.transcriber = SpeechTranscriber(
            model_size=whisper_model,
            device="cpu",
            compute_type="int8"
        )

        logger.info(f"AudioPipeline initialized: denoise={denoise_level}, whisper={whisper_model}")

    def process(
        self,
        audio: np.ndarray,
        skip_if_no_voice: bool = True
    ) -> ProcessedAudio:
        """
        Process audio through complete pipeline

        Args:
            audio: Raw audio signal (mono, float32)
            skip_if_no_voice: Skip transcription if no voice detected

        Returns:
            ProcessedAudio with results
        """
        duration = len(audio) / self.sample_rate

        logger.debug(f"Processing {duration:.1f}s of audio")

        # Step 1: Denoise
        clean_audio = self.denoiser.denoise(audio)

        # Step 2: Voice activity detection
        speech_ratio = self.vad.get_speech_ratio(clean_audio)
        has_speech = speech_ratio > 0.1  # At least 10% speech

        logger.debug(f"Speech ratio: {speech_ratio:.2%}")

        # Step 3: Transcribe (if speech detected)
        transcripts = []

        if has_speech or not skip_if_no_voice:
            try:
                transcripts = self.transcriber.transcribe(
                    clean_audio,
                    sample_rate=self.sample_rate,
                    vad_filter=True
                )

                logger.debug(f"Transcribed {len(transcripts)} segments")

            except Exception as e:
                logger.error(f"Transcription failed: {e}")

        return ProcessedAudio(
            raw_audio=audio,
            clean_audio=clean_audio,
            has_speech=has_speech,
            speech_ratio=speech_ratio,
            transcripts=transcripts,
            duration=duration
        )

    def process_quick(
        self,
        audio: np.ndarray,
        check_voice_only: bool = False
    ) -> Dict:
        """
        Quick processing for band scanning (no transcription)

        Args:
            audio: Audio signal
            check_voice_only: Only check for voice, don't denoise

        Returns:
            Dict with has_speech, speech_ratio
        """
        if check_voice_only:
            # Skip denoising for speed
            has_speech = self.vad.has_speech(audio)
            speech_ratio = self.vad.get_speech_ratio(audio) if has_speech else 0.0
        else:
            # Full processing without transcription
            clean = self.denoiser.denoise(audio)
            has_speech = self.vad.has_speech(clean)
            speech_ratio = self.vad.get_speech_ratio(clean)

        return {
            'has_speech': has_speech,
            'speech_ratio': speech_ratio,
            'duration': len(audio) / self.sample_rate
        }

    def get_transcript_text(self, audio: np.ndarray) -> str:
        """
        Get simple text transcript

        Args:
            audio: Audio signal

        Returns:
            Transcript as string
        """
        result = self.process(audio)

        if not result.transcripts:
            return ""

        return " ".join(seg.text for seg in result.transcripts)

    def process_with_timestamps(
        self,
        audio: np.ndarray
    ) -> List[Dict]:
        """
        Process and return transcripts with timestamps

        Args:
            audio: Audio signal

        Returns:
            List of transcript dicts with timestamps
        """
        result = self.process(audio)

        return [
            {
                'start': seg.start,
                'end': seg.end,
                'text': seg.text,
                'confidence': seg.confidence,
                'duration': seg.end - seg.start
            }
            for seg in result.transcripts
        ]

    def set_denoise_level(self, level: str):
        """Set denoising strength"""
        self.denoiser.set_strength(level)
        logger.info(f"Denoise level set to {level}")

    def set_vad_sensitivity(self, level: str):
        """Set VAD sensitivity"""
        self.vad.set_sensitivity(level)
        logger.info(f"VAD sensitivity set to {level}")

    @property
    def is_ready(self) -> bool:
        """Check if all components are loaded and ready"""
        try:
            # This will trigger lazy loading
            return self.transcriber.is_model_available()
        except:
            return False
