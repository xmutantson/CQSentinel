"""
Audio monitoring and diagnostic tools.

Allows multiple consumers of audio stream and provides playback
at different processing stages for diagnostics.
"""

import numpy as np
import sounddevice as sd
import logging
import threading
import time
from typing import List, Callable, Optional
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)


class AudioStage(Enum):
    """Audio processing stages for monitoring"""
    RAW = "raw"  # Raw input from soundcard
    DENOISED = "denoised"  # After noise reduction
    VAD_PROCESSED = "vad_processed"  # After VAD processing


@dataclass
class AudioChunk:
    """Audio data at a specific processing stage"""
    stage: AudioStage
    data: np.ndarray
    sample_rate: int
    timestamp: float
    metadata: Optional[dict] = field(default_factory=dict)


class AudioBuffer:
    """
    Buffers small audio chunks into larger segments for processing.

    Speech detection needs context - typically 0.5-1 second of audio.
    This buffers small chunks (64ms) from sounddevice into larger
    segments (1s) suitable for VAD/transcription.
    """

    def __init__(self, buffer_duration: float = 1.0, sample_rate: int = 16000):
        """
        Initialize audio buffer.

        Args:
            buffer_duration: Target buffer size in seconds
            sample_rate: Audio sample rate
        """
        self.buffer_duration = buffer_duration
        self.sample_rate = sample_rate
        self.buffer_size_samples = int(buffer_duration * sample_rate)

        self._buffer = np.array([], dtype='float32')
        self._lock = threading.Lock()
        self._chunks_buffered = 0
        self._buffers_released = 0

        logger.info(
            f"AudioBuffer initialized: {buffer_duration}s buffer "
            f"({self.buffer_size_samples} samples @ {sample_rate}Hz)"
        )

    def add_chunk(self, audio_chunk: np.ndarray) -> Optional[np.ndarray]:
        """
        Add audio chunk to buffer.

        Args:
            audio_chunk: Audio data to add

        Returns:
            Full buffer if ready, None otherwise
        """
        with self._lock:
            # Append to buffer
            self._buffer = np.concatenate([self._buffer, audio_chunk])
            self._chunks_buffered += 1

            # Check if buffer is full
            if len(self._buffer) >= self.buffer_size_samples:
                # Extract full buffer
                full_buffer = self._buffer[:self.buffer_size_samples]

                # Keep overflow for next buffer (overlap)
                # Use 50% overlap for better speech boundary detection
                overlap_size = self.buffer_size_samples // 2
                self._buffer = self._buffer[overlap_size:]

                self._buffers_released += 1

                # Log every 10 buffers
                if self._buffers_released % 10 == 0:
                    logger.debug(
                        f"AudioBuffer: released {self._buffers_released} buffers, "
                        f"buffered {self._chunks_buffered} chunks"
                    )

                return full_buffer

            return None

    def get_stats(self) -> dict:
        """Get buffer statistics"""
        with self._lock:
            return {
                'buffer_duration': self.buffer_duration,
                'current_samples': len(self._buffer),
                'target_samples': self.buffer_size_samples,
                'fill_percent': (len(self._buffer) / self.buffer_size_samples) * 100,
                'chunks_buffered': self._chunks_buffered,
                'buffers_released': self._buffers_released
            }


class AudioBroadcaster:
    """
    Broadcasts audio to multiple consumers.

    Allows multiple callbacks to receive the same audio stream,
    enabling simultaneous audio metering, VAD, playback, etc.
    """

    def __init__(self):
        """Initialize broadcaster"""
        self.consumers: List[Callable[[AudioChunk], None]] = []
        self._enabled = True

    def register_consumer(self, callback: Callable[[AudioChunk], None]) -> int:
        """
        Register a consumer callback.

        Args:
            callback: Function to call with audio chunks
                     signature: callback(chunk: AudioChunk) -> None

        Returns:
            Consumer ID for unregistering
        """
        self.consumers.append(callback)
        consumer_id = len(self.consumers) - 1
        logger.debug(f"Registered audio consumer #{consumer_id}")
        return consumer_id

    def unregister_consumer(self, consumer_id: int):
        """Remove a consumer by ID"""
        if 0 <= consumer_id < len(self.consumers):
            self.consumers[consumer_id] = None
            logger.debug(f"Unregistered audio consumer #{consumer_id}")

    def broadcast(self, chunk: AudioChunk):
        """
        Broadcast audio chunk to all registered consumers.

        Args:
            chunk: AudioChunk to broadcast
        """
        if not self._enabled:
            return

        for callback in self.consumers:
            if callback is not None:
                try:
                    callback(chunk)
                except Exception as e:
                    logger.error(f"Audio consumer error: {e}", exc_info=True)

    def clear(self):
        """Clear all consumers"""
        self.consumers.clear()

    def enable(self):
        """Enable broadcasting"""
        self._enabled = True

    def disable(self):
        """Disable broadcasting"""
        self._enabled = False


class AudioMonitor:
    """
    Monitors and optionally plays back audio at different processing stages.

    Useful for diagnostics - hear what the audio sounds like before/after
    noise reduction, check if VAD is working correctly, etc.
    """

    def __init__(self, sample_rate: int = 16000, output_device: Optional[int] = None):
        """
        Initialize audio monitor.

        Args:
            sample_rate: Audio sample rate
            output_device: Output device index (None for default)
        """
        self.sample_rate = sample_rate
        self.output_device = output_device
        self._playback_stream: Optional[sd.OutputStream] = None
        self._monitoring_stage: Optional[AudioStage] = None
        self._volume = 1.0

        # Diagnostics counters
        self._chunks_received = 0
        self._chunks_played = 0
        self._last_chunk_time = None

        logger.info(f"AudioMonitor initialized: sample_rate={sample_rate}, output_device={output_device}")

    def start_monitoring(self, stage: AudioStage, volume: float = 1.0):
        """
        Start monitoring/playing back audio at a specific stage.

        Args:
            stage: Which processing stage to monitor
            volume: Playback volume (0.0-1.0)
        """
        if self._playback_stream is not None:
            self.stop_monitoring()

        self._monitoring_stage = stage
        self._volume = max(0.0, min(1.0, volume))

        # Reset diagnostics
        self._chunks_received = 0
        self._chunks_played = 0
        self._last_chunk_time = None

        try:
            # Create output stream for playback
            self._playback_stream = sd.OutputStream(
                samplerate=self.sample_rate,
                channels=1,
                dtype='float32',
                device=self.output_device
            )
            self._playback_stream.start()

            device_info = f" on device {self.output_device}" if self.output_device is not None else " on default device"
            logger.info(f"Started monitoring audio at stage: {stage.value}, volume: {self._volume:.1f}{device_info}")

        except Exception as e:
            logger.error(f"Failed to start audio monitoring: {e}")
            self._playback_stream = None

    def stop_monitoring(self):
        """Stop monitoring/playback"""
        if self._playback_stream is not None:
            try:
                self._playback_stream.stop()
                self._playback_stream.close()
            except:
                pass
            self._playback_stream = None

        self._monitoring_stage = None
        logger.info("Stopped audio monitoring")

    def process_chunk(self, chunk: AudioChunk):
        """
        Process audio chunk - play it back if monitoring this stage.

        Args:
            chunk: AudioChunk to process
        """
        import time

        # Track all chunks received (for diagnostics)
        if self._monitoring_stage is not None:
            self._chunks_received += 1
            self._last_chunk_time = time.time()

            # Log every 50 chunks for diagnostics
            if self._chunks_received % 50 == 0:
                logger.debug(
                    f"AudioMonitor: received {self._chunks_received} chunks total, "
                    f"played {self._chunks_played}, monitoring {self._monitoring_stage.value}, "
                    f"chunk stage: {chunk.stage.value}"
                )

        # Only play back if monitoring this stage
        if (self._playback_stream is not None and
            self._monitoring_stage == chunk.stage):

            try:
                # Apply volume and write to output stream
                audio_data = chunk.data * self._volume
                self._playback_stream.write(audio_data.astype('float32'))
                self._chunks_played += 1

                # Log first few chunks to confirm playback started
                if self._chunks_played <= 3:
                    logger.info(
                        f"AudioMonitor: playing chunk #{self._chunks_played} "
                        f"({len(audio_data)} samples, stage: {chunk.stage.value})"
                    )
            except Exception as e:
                logger.error(f"Playback error: {e}", exc_info=True)

    @property
    def is_monitoring(self) -> bool:
        """Check if currently monitoring"""
        return self._playback_stream is not None

    @property
    def monitoring_stage(self) -> Optional[AudioStage]:
        """Get current monitoring stage"""
        return self._monitoring_stage

    def get_diagnostics(self) -> dict:
        """
        Get monitoring diagnostics.

        Returns:
            Dict with diagnostics info
        """
        import time
        return {
            'monitoring_stage': self._monitoring_stage.value if self._monitoring_stage else None,
            'chunks_received': self._chunks_received,
            'chunks_played': self._chunks_played,
            'playback_active': self._playback_stream is not None,
            'last_chunk_time': self._last_chunk_time,
            'seconds_since_last_chunk': time.time() - self._last_chunk_time if self._last_chunk_time else None
        }


class AudioLevelMeter:
    """
    Measures audio levels (RMS, peak) from audio chunks.

    Thread-safe consumer for audio broadcaster.
    """

    def __init__(self):
        """Initialize level meter"""
        self.rms_level = 0.0  # 0.0 to 1.0
        self.peak_level = 0.0  # 0.0 to 1.0
        self._lock = threading.Lock()

    def process_chunk(self, chunk: AudioChunk):
        """
        Process audio chunk and update levels.

        Args:
            chunk: AudioChunk to measure
        """
        # Only measure raw audio to avoid confusion
        if chunk.stage != AudioStage.RAW:
            return

        audio_data = chunk.data

        # Calculate RMS
        rms = np.sqrt(np.mean(audio_data**2))

        # Calculate peak
        peak = np.max(np.abs(audio_data))

        # Update levels (thread-safe)
        # For float32 audio, RMS is typically 0.0-0.3 for normal speech
        # Scale by 3.0 to get better visual representation (0.3 -> 0.9)
        with self._lock:
            self.rms_level = min(1.0, rms * 3.0)  # Scale and clamp
            self.peak_level = min(1.0, peak * 1.5)  # Slight boost for peak

    def get_levels(self) -> tuple:
        """
        Get current levels (thread-safe).

        Returns:
            Tuple of (rms_level, peak_level) both 0.0-1.0
        """
        with self._lock:
            return (self.rms_level, self.peak_level)
