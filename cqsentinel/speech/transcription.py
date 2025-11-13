"""
Speech-to-Text transcription using faster-whisper

Offline speech recognition optimized for real-time performance.
"""

import numpy as np
import logging
from typing import List, Dict, Optional, Iterator
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class TranscriptSegment:
    """Single transcribed segment"""
    start: float        # Start time in seconds
    end: float          # End time in seconds
    text: str           # Transcribed text
    confidence: float   # Confidence score (0.0-1.0)
    language: str = "en"


class SpeechTranscriber:
    """
    Speech-to-text transcription using faster-whisper

    Provides offline speech recognition with optimized performance.
    """

    def __init__(
        self,
        model_size: str = "small",
        device: str = "cpu",
        compute_type: str = "int8",
        language: str = "en"
    ):
        """
        Initialize transcriber

        Args:
            model_size: Whisper model size (tiny, base, small, medium, large)
            device: 'cpu' or 'cuda'
            compute_type: 'int8', 'int8_float16', 'float16', 'float32'
            language: Language code (default: 'en')
        """
        self.model_size = model_size
        self.device = device
        self.compute_type = compute_type
        self.language = language

        self.model = None

        logger.info(
            f"SpeechTranscriber initialized: model={model_size}, "
            f"device={device}, compute_type={compute_type}"
        )

    def _load_model(self):
        """Lazy-load faster-whisper model"""
        if self.model is not None:
            return

        try:
            logger.info(f"Loading Whisper {self.model_size} model...")

            from faster_whisper import WhisperModel

            self.model = WhisperModel(
                self.model_size,
                device=self.device,
                compute_type=self.compute_type,
                download_root=None  # Use default cache
            )

            logger.info(f"✓ Whisper {self.model_size} model loaded")

        except ImportError:
            logger.error("faster-whisper not installed. Install with: pip install faster-whisper")
            raise
        except Exception as e:
            logger.error(f"Failed to load Whisper model: {e}")
            raise

    def transcribe(
        self,
        audio: np.ndarray,
        sample_rate: int = 16000,
        vad_filter: bool = True,
        beam_size: int = 5
    ) -> List[TranscriptSegment]:
        """
        Transcribe audio to text

        Args:
            audio: Audio signal (mono, float32)
            sample_rate: Audio sample rate
            vad_filter: Use VAD to filter non-speech
            beam_size: Beam search size (higher = more accurate, slower)

        Returns:
            List of TranscriptSegment objects
        """
        self._load_model()

        if len(audio) == 0:
            logger.warning("Empty audio provided to transcriber")
            return []

        try:
            # Ensure correct format
            audio = audio.astype(np.float32)

            # Transcribe
            segments, info = self.model.transcribe(
                audio,
                language=self.language,
                beam_size=beam_size,
                vad_filter=vad_filter,
                vad_parameters={
                    "threshold": 0.5,
                    "min_speech_duration_ms": 250,
                    "min_silence_duration_ms": 100
                }
            )

            # Convert to our format
            results = []
            for seg in segments:
                results.append(TranscriptSegment(
                    start=seg.start,
                    end=seg.end,
                    text=seg.text.strip(),
                    confidence=getattr(seg, 'avg_logprob', 0.0),  # Approximate confidence
                    language=info.language
                ))

            logger.debug(f"Transcribed {len(results)} segments")
            return results

        except Exception as e:
            logger.error(f"Transcription failed: {e}")
            return []

    def transcribe_stream(
        self,
        audio: np.ndarray,
        sample_rate: int = 16000,
        chunk_duration: float = 30.0
    ) -> Iterator[TranscriptSegment]:
        """
        Stream transcription for long audio

        Args:
            audio: Audio signal
            sample_rate: Sample rate
            chunk_duration: Duration of each chunk (seconds)

        Yields:
            TranscriptSegment objects as they're processed
        """
        self._load_model()

        chunk_samples = int(chunk_duration * sample_rate)

        for i in range(0, len(audio), chunk_samples):
            chunk = audio[i:i + chunk_samples]

            if len(chunk) < sample_rate:  # Skip chunks < 1 second
                continue

            segments = self.transcribe(chunk, sample_rate)

            # Adjust timestamps for chunk position
            offset = i / sample_rate
            for seg in segments:
                seg.start += offset
                seg.end += offset
                yield seg

    def get_full_transcript(
        self,
        audio: np.ndarray,
        sample_rate: int = 16000,
        join_char: str = " "
    ) -> str:
        """
        Get complete transcript as single string

        Args:
            audio: Audio signal
            sample_rate: Sample rate
            join_char: Character to join segments

        Returns:
            Full transcript text
        """
        segments = self.transcribe(audio, sample_rate)
        return join_char.join(seg.text for seg in segments)

    def transcribe_with_timestamps(
        self,
        audio: np.ndarray,
        sample_rate: int = 16000
    ) -> List[Dict]:
        """
        Get transcript with detailed timestamp info

        Args:
            audio: Audio signal
            sample_rate: Sample rate

        Returns:
            List of dicts with text, start, end, confidence
        """
        segments = self.transcribe(audio, sample_rate)

        return [
            {
                'text': seg.text,
                'start': seg.start,
                'end': seg.end,
                'duration': seg.end - seg.start,
                'confidence': seg.confidence,
                'language': seg.language
            }
            for seg in segments
        ]

    def is_model_available(self) -> bool:
        """Check if model is downloaded and available"""
        try:
            self._load_model()
            return True
        except:
            return False

    @staticmethod
    def list_available_models() -> List[str]:
        """List available Whisper model sizes"""
        return ["tiny", "base", "small", "medium", "large", "large-v2", "large-v3"]

    @staticmethod
    def get_model_info(model_size: str) -> Dict:
        """Get information about a model size"""
        model_info = {
            "tiny": {"params": "39M", "size_mb": 39, "relative_speed": 32},
            "base": {"params": "74M", "size_mb": 74, "relative_speed": 16},
            "small": {"params": "244M", "size_mb": 244, "relative_speed": 6},
            "medium": {"params": "769M", "size_mb": 769, "relative_speed": 2},
            "large": {"params": "1550M", "size_mb": 1550, "relative_speed": 1},
            "large-v2": {"params": "1550M", "size_mb": 1550, "relative_speed": 1},
            "large-v3": {"params": "1550M", "size_mb": 1550, "relative_speed": 1},
        }

        return model_info.get(model_size, {})
