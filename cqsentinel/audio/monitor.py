"""
Audio monitoring and diagnostic tools.

Allows multiple consumers of audio stream and provides playback
at different processing stages for diagnostics.
"""

import numpy as np
import sounddevice as sd
import logging
from typing import List, Callable, Optional
from dataclasses import dataclass
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
    metadata: dict = None


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

    def __init__(self, sample_rate: int = 16000):
        """
        Initialize audio monitor.

        Args:
            sample_rate: Audio sample rate
        """
        self.sample_rate = sample_rate
        self._playback_stream: Optional[sd.OutputStream] = None
        self._monitoring_stage: Optional[AudioStage] = None
        self._volume = 1.0

        logger.info(f"AudioMonitor initialized: sample_rate={sample_rate}")

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

        try:
            # Create output stream for playback
            self._playback_stream = sd.OutputStream(
                samplerate=self.sample_rate,
                channels=1,
                dtype='float32'
            )
            self._playback_stream.start()

            logger.info(f"Started monitoring audio at stage: {stage.value}, volume: {self._volume:.1f}")

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
        # Only play back if monitoring this stage
        if (self._playback_stream is not None and
            self._monitoring_stage == chunk.stage):

            try:
                # Apply volume and write to output stream
                audio_data = chunk.data * self._volume
                self._playback_stream.write(audio_data.astype('float32'))
            except Exception as e:
                logger.debug(f"Playback error: {e}")

    @property
    def is_monitoring(self) -> bool:
        """Check if currently monitoring"""
        return self._playback_stream is not None

    @property
    def monitoring_stage(self) -> Optional[AudioStage]:
        """Get current monitoring stage"""
        return self._monitoring_stage


class AudioLevelMeter:
    """
    Measures audio levels (RMS, peak) from audio chunks.

    Thread-safe consumer for audio broadcaster.
    """

    def __init__(self):
        """Initialize level meter"""
        self.rms_level = 0.0  # 0.0 to 1.0
        self.peak_level = 0.0  # 0.0 to 1.0
        self._lock = __import__('threading').Lock()

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
        with self._lock:
            self.rms_level = min(1.0, rms * 10)  # Scale and clamp
            self.peak_level = min(1.0, peak)

    def get_levels(self) -> tuple:
        """
        Get current levels (thread-safe).

        Returns:
            Tuple of (rms_level, peak_level) both 0.0-1.0
        """
        with self._lock:
            return (self.rms_level, self.peak_level)
