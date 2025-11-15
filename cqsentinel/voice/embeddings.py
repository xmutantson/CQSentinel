"""
Voice embedding extraction using Resemblyzer.

This module extracts 256-dimensional voice embeddings that uniquely identify
speakers, allowing operator tracking across frequencies and sessions.
"""

import logging
from dataclasses import dataclass
from typing import List, Optional, Tuple
import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class VoiceSegment:
    """
    Represents a voice segment with its embedding.
    """
    start_time: float  # seconds
    end_time: float  # seconds
    embedding: np.ndarray  # 256-dim vector
    duration: float  # seconds
    confidence: float  # 0-1, based on segment length and quality

    @property
    def duration_calculated(self) -> float:
        """Calculate duration from timestamps."""
        return self.end_time - self.start_time


class VoiceEmbedder:
    """
    Extracts voice embeddings from audio using Resemblyzer.

    Resemblyzer produces 256-dimensional embeddings that are:
    - Consistent for the same speaker
    - Distinct between different speakers
    - Robust to noise, pitch variations, and channel effects

    Usage:
        embedder = VoiceEmbedder()
        segments = embedder.extract_embeddings(audio, speech_timestamps)

        for segment in segments:
            print(f"Speaker at {segment.start_time:.1f}s: {segment.embedding.shape}")
    """

    def __init__(self):
        """
        Initialize the voice embedder.

        Downloads and caches the Resemblyzer model on first use (~60 MB).
        """
        self.encoder = None
        self._sample_rate = 16000  # Resemblyzer expects 16 kHz

        logger.info("VoiceEmbedder initialized (model loads on first use)")

    def _ensure_model_loaded(self):
        """Lazy-load the Resemblyzer model."""
        if self.encoder is None:
            try:
                from resemblyzer import VoiceEncoder
                logger.info("Loading Resemblyzer model...")
                self.encoder = VoiceEncoder()
                logger.info("Resemblyzer model loaded successfully")
            except ImportError:
                logger.error(
                    "Resemblyzer not installed. Install with: pip install resemblyzer"
                )
                raise
            except Exception as e:
                logger.error(f"Failed to load Resemblyzer model: {e}")
                raise

    def extract_embeddings(
        self,
        audio: np.ndarray,
        speech_timestamps: List[dict],
        sample_rate: int = 16000,
        min_duration: float = 0.5,
    ) -> List[VoiceSegment]:
        """
        Extract voice embeddings for each speech segment.

        Args:
            audio: Audio data as numpy array (float32, mono)
            speech_timestamps: List of speech segments from VAD
                               Format: [{'start': 0.5, 'end': 2.3}, ...]
            sample_rate: Sample rate of the audio (default: 16000 Hz)
            min_duration: Minimum segment duration in seconds (default: 0.5s)

        Returns:
            List of VoiceSegment objects with embeddings

        Example:
            >>> audio = np.random.randn(16000 * 10)  # 10 seconds
            >>> timestamps = [{'start': 1.0, 'end': 3.5}, {'start': 5.0, 'end': 7.0}]
            >>> embedder = VoiceEmbedder()
            >>> segments = embedder.extract_embeddings(audio, timestamps)
            >>> print(len(segments))
            2
            >>> print(segments[0].embedding.shape)
            (256,)
        """
        self._ensure_model_loaded()

        segments = []

        for ts in speech_timestamps:
            start_time = ts['start']
            end_time = ts['end']
            duration = end_time - start_time

            # Skip very short segments (unreliable embeddings)
            if duration < min_duration:
                logger.debug(
                    f"Skipping short segment ({duration:.2f}s < {min_duration:.2f}s)"
                )
                continue

            # Extract audio segment
            start_sample = int(start_time * sample_rate)
            end_sample = int(end_time * sample_rate)
            segment_audio = audio[start_sample:end_sample]

            # Resample if needed (Resemblyzer expects 16 kHz)
            if sample_rate != self._sample_rate:
                segment_audio = self._resample(segment_audio, sample_rate, self._sample_rate)

            # Extract embedding
            try:
                # Resemblyzer's preprocess_wav normalizes the audio
                from resemblyzer import preprocess_wav
                processed = preprocess_wav(segment_audio, source_sr=self._sample_rate)
                embedding = self.encoder.embed_utterance(processed)

                # Calculate confidence based on segment duration
                # Longer segments = more reliable embeddings
                confidence = min(1.0, duration / 3.0)  # Max confidence at 3+ seconds

                segment = VoiceSegment(
                    start_time=start_time,
                    end_time=end_time,
                    embedding=embedding,
                    duration=duration,
                    confidence=confidence
                )

                segments.append(segment)
                logger.debug(
                    f"Extracted embedding for segment {start_time:.1f}-{end_time:.1f}s "
                    f"(confidence: {confidence:.2f})"
                )

            except Exception as e:
                logger.warning(
                    f"Failed to extract embedding for segment {start_time:.1f}-{end_time:.1f}s: {e}"
                )
                continue

        logger.info(f"Extracted {len(segments)} voice embeddings")
        return segments

    def _resample(
        self,
        audio: np.ndarray,
        orig_sr: int,
        target_sr: int
    ) -> np.ndarray:
        """
        Resample audio to target sample rate.

        Args:
            audio: Input audio
            orig_sr: Original sample rate
            target_sr: Target sample rate

        Returns:
            Resampled audio
        """
        try:
            from scipy.signal import resample
            target_length = int(len(audio) * target_sr / orig_sr)
            resampled = resample(audio, target_length)
            return resampled.astype(np.float32)
        except ImportError:
            logger.warning(
                "scipy not available for resampling, using naive approach"
            )
            # Fallback: simple decimation/interpolation
            ratio = target_sr / orig_sr
            if ratio < 1:
                # Downsample
                step = int(1 / ratio)
                return audio[::step]
            else:
                # Upsample (repeat samples)
                repeat = int(ratio)
                return np.repeat(audio, repeat)

    def compute_similarity(
        self,
        embedding1: np.ndarray,
        embedding2: np.ndarray
    ) -> float:
        """
        Compute cosine similarity between two voice embeddings.

        Args:
            embedding1: First embedding (256-dim)
            embedding2: Second embedding (256-dim)

        Returns:
            Similarity score between 0 and 1 (1 = identical voices)

        Typical thresholds:
            - > 0.85: Very likely same speaker
            - 0.75-0.85: Likely same speaker
            - 0.65-0.75: Possibly same speaker
            - < 0.65: Different speakers

        Example:
            >>> embedder = VoiceEmbedder()
            >>> emb1 = np.random.randn(256)
            >>> emb2 = emb1 + 0.1 * np.random.randn(256)  # Similar
            >>> similarity = embedder.compute_similarity(emb1, emb2)
            >>> print(f"Similarity: {similarity:.2f}")
        """
        # Cosine similarity: dot product of normalized vectors
        norm1 = np.linalg.norm(embedding1)
        norm2 = np.linalg.norm(embedding2)

        if norm1 == 0 or norm2 == 0:
            logger.warning("Zero-norm embedding encountered")
            return 0.0

        similarity = np.dot(embedding1, embedding2) / (norm1 * norm2)

        # Clip to [0, 1] range (cosine similarity can be [-1, 1])
        # For voice embeddings, negative similarities are rare
        return float(np.clip(similarity, 0.0, 1.0))

    def cluster_speakers(
        self,
        segments: List[VoiceSegment],
        threshold: float = 0.75
    ) -> List[int]:
        """
        Cluster voice segments into speaker IDs.

        Groups segments that likely belong to the same speaker based on
        embedding similarity.

        Args:
            segments: List of VoiceSegment objects
            threshold: Similarity threshold for clustering (default: 0.75)

        Returns:
            List of speaker IDs (integers) for each segment

        Example:
            >>> segments = embedder.extract_embeddings(audio, timestamps)
            >>> speaker_ids = embedder.cluster_speakers(segments, threshold=0.75)
            >>> print(f"Found {len(set(speaker_ids))} unique speakers")
        """
        if not segments:
            return []

        if len(segments) == 1:
            return [0]

        try:
            from sklearn.cluster import AgglomerativeClustering

            # Extract embeddings into matrix
            embeddings = np.array([seg.embedding for seg in segments])

            # Use agglomerative clustering with cosine distance
            # distance_threshold = 1 - similarity_threshold
            clustering = AgglomerativeClustering(
                n_clusters=None,
                distance_threshold=1.0 - threshold,
                metric='cosine',
                linkage='average'
            )

            speaker_ids = clustering.fit_predict(embeddings)

            n_speakers = len(set(speaker_ids))
            logger.info(
                f"Clustered {len(segments)} segments into {n_speakers} speakers "
                f"(threshold={threshold:.2f})"
            )

            return speaker_ids.tolist()

        except ImportError:
            logger.warning(
                "scikit-learn not available for clustering, assigning unique IDs"
            )
            # Fallback: assign unique ID to each segment
            return list(range(len(segments)))

    def detect_speaker_changes(
        self,
        audio: np.ndarray,
        sample_rate: int = 16000,
        window_duration: float = 2.5,
        stride: float = 1.0,
        similarity_threshold: float = 0.75
    ) -> List[dict]:
        """
        Detect speaker changes in audio using sliding window analysis.

        Uses overlapping windows to extract voice embeddings and detects
        speaker changes when similarity drops below threshold.

        Args:
            audio: Audio data as numpy array (float32, mono)
            sample_rate: Sample rate of the audio (default: 16000 Hz)
            window_duration: Duration of each window in seconds (default: 2.5s)
            stride: Time step between windows in seconds (default: 1.0s)
            similarity_threshold: Threshold for speaker change detection (default: 0.75)
                                 < 0.75 indicates likely different speaker

        Returns:
            List of speaker segments with format:
            [{'start': 0.0, 'end': 3.5, 'speaker': 0, 'embedding': ndarray},
             {'start': 3.5, 'end': 7.0, 'speaker': 1, 'embedding': ndarray}, ...]

        Example:
            >>> audio = np.random.randn(16000 * 10)  # 10 seconds
            >>> embedder = VoiceEmbedder()
            >>> segments = embedder.detect_speaker_changes(audio)
            >>> print(f"Found {len(set(s['speaker'] for s in segments))} speakers")
        """
        self._ensure_model_loaded()

        duration = len(audio) / sample_rate

        # Can't detect speakers in very short audio
        if duration < window_duration:
            logger.warning(f"Audio too short ({duration:.1f}s) for speaker detection (need {window_duration}s)")
            return [{
                'start': 0.0,
                'end': duration,
                'speaker': 0,
                'embedding': None
            }]

        # Extract embeddings for overlapping windows
        windows = []
        current_time = 0.0

        while current_time + window_duration <= duration:
            start_sample = int(current_time * sample_rate)
            end_sample = int((current_time + window_duration) * sample_rate)
            window_audio = audio[start_sample:end_sample]

            try:
                # Resample if needed
                if sample_rate != self._sample_rate:
                    window_audio = self._resample(window_audio, sample_rate, self._sample_rate)

                # Extract embedding
                from resemblyzer import preprocess_wav
                processed = preprocess_wav(window_audio, source_sr=self._sample_rate)
                embedding = self.encoder.embed_utterance(processed)

                windows.append({
                    'start': current_time,
                    'end': current_time + window_duration,
                    'embedding': embedding
                })

            except Exception as e:
                logger.debug(f"Failed to extract embedding for window {current_time:.1f}s: {e}")

            current_time += stride

        if not windows:
            logger.warning("No embeddings extracted from audio")
            return [{
                'start': 0.0,
                'end': duration,
                'speaker': 0,
                'embedding': None
            }]

        # Detect speaker changes based on embedding similarity
        speaker_segments = []
        current_speaker = 0
        segment_start = 0.0
        current_embedding = windows[0]['embedding']

        for i in range(1, len(windows)):
            prev_embedding = windows[i-1]['embedding']
            curr_embedding = windows[i]['embedding']

            # Compute similarity between consecutive windows
            similarity = self.compute_similarity(prev_embedding, curr_embedding)

            # Speaker change detected
            if similarity < similarity_threshold:
                # Close current segment
                speaker_segments.append({
                    'start': segment_start,
                    'end': windows[i-1]['end'],
                    'speaker': current_speaker,
                    'embedding': current_embedding
                })

                # Start new segment
                current_speaker += 1
                segment_start = windows[i]['start']
                current_embedding = curr_embedding

                logger.debug(
                    f"Speaker change detected at {windows[i]['start']:.1f}s "
                    f"(similarity: {similarity:.2f} < {similarity_threshold})"
                )

        # Add final segment
        speaker_segments.append({
            'start': segment_start,
            'end': duration,
            'speaker': current_speaker,
            'embedding': current_embedding
        })

        logger.info(
            f"Detected {current_speaker + 1} speaker(s) in {duration:.1f}s audio "
            f"({len(speaker_segments)} segments)"
        )

        return speaker_segments

    @property
    def sample_rate(self) -> int:
        """Expected sample rate for audio input."""
        return self._sample_rate
