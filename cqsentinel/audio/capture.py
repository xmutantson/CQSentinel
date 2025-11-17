"""
Audio Capture Module

Handles audio input from radio via USB or sound card.
"""

import sounddevice as sd
import numpy as np
import logging
from typing import Optional, Callable, List
from dataclasses import dataclass
import queue
import threading

logger = logging.getLogger(__name__)


@dataclass
class AudioDevice:
    """Audio device information"""
    index: int
    name: str
    channels: int
    sample_rate: float
    is_input: bool
    is_default: bool


def list_audio_devices() -> List[AudioDevice]:
    """
    List all available audio input devices

    Returns:
        List of AudioDevice objects
    """
    devices = []

    try:
        device_list = sd.query_devices()
        default_input = sd.default.device[0]  # Input device index

        for idx, dev in enumerate(device_list):
            if dev['max_input_channels'] > 0:
                devices.append(AudioDevice(
                    index=idx,
                    name=dev['name'],
                    channels=dev['max_input_channels'],
                    sample_rate=dev['default_samplerate'],
                    is_input=True,
                    is_default=(idx == default_input)
                ))

        logger.info(f"Found {len(devices)} audio input devices")

    except Exception as e:
        logger.error(f"Failed to list audio devices: {e}")

    return devices


def list_audio_output_devices() -> List[AudioDevice]:
    """
    List all available audio output devices

    Returns:
        List of AudioDevice objects
    """
    devices = []

    try:
        device_list = sd.query_devices()
        default_output = sd.default.device[1]  # Output device index

        for idx, dev in enumerate(device_list):
            if dev['max_output_channels'] > 0:
                devices.append(AudioDevice(
                    index=idx,
                    name=dev['name'],
                    channels=dev['max_output_channels'],
                    sample_rate=dev['default_samplerate'],
                    is_input=False,
                    is_default=(idx == default_output)
                ))

        logger.info(f"Found {len(devices)} audio output devices")

    except Exception as e:
        logger.error(f"Failed to list output devices: {e}")

    return devices


class AudioCapture:
    """
    Audio capture from sound device

    Supports both blocking (record) and streaming (callback) modes.
    """

    def __init__(
        self,
        device: Optional[int] = None,
        sample_rate: int = 16000,
        channels: int = 1,
        dtype: str = 'float32'
    ):
        """
        Initialize audio capture

        Args:
            device: Device index (None for default)
            sample_rate: Sample rate in Hz
            channels: Number of channels (1 = mono)
            dtype: Data type ('float32', 'int16')
        """
        self.device = device
        self.sample_rate = sample_rate
        self.channels = channels
        self.dtype = dtype

        self._stream: Optional[sd.InputStream] = None
        self._recording = False
        self._callback_func: Optional[Callable] = None

        logger.info(
            f"AudioCapture initialized: device={device}, "
            f"sample_rate={sample_rate}, channels={channels}"
        )

    def record(self, duration: float) -> np.ndarray:
        """
        Record audio for a fixed duration (blocking)

        Args:
            duration: Recording duration in seconds

        Returns:
            Audio data as numpy array
        """
        try:
            logger.debug(f"Recording {duration}s of audio...")

            audio = sd.rec(
                int(duration * self.sample_rate),
                samplerate=self.sample_rate,
                channels=self.channels,
                dtype=self.dtype,
                device=self.device
            )

            sd.wait()  # Wait until recording is finished

            logger.debug(f"Recorded {len(audio)} samples")

            # Convert to mono if needed
            if audio.ndim > 1:
                audio = audio.mean(axis=1)

            return audio.flatten()

        except Exception as e:
            logger.error(f"Recording failed: {e}")
            return np.array([], dtype=self.dtype)

    def interrupt_recording(self):
        """
        Interrupt any ongoing blocking recording (sd.rec + sd.wait).

        This is useful for implementing a 'skip' feature that immediately
        stops audio capture.
        """
        try:
            sd.stop()
            logger.info("Recording interrupted by user request")
        except Exception as e:
            logger.warning(f"Error interrupting recording: {e}")

    def start_stream(self, callback: Callable[[np.ndarray], None]) -> bool:
        """
        Start streaming audio with callback (non-blocking)

        Args:
            callback: Function called with audio chunks
                      signature: callback(audio_chunk: np.ndarray) -> None

        Returns:
            True if stream started successfully
        """
        if self._recording:
            logger.warning("Stream already running")
            return False

        self._callback_func = callback

        try:
            # Create queue for audio data
            audio_queue = queue.Queue()

            def audio_callback(indata, frames, time_info, status):
                """Called by sounddevice for each audio block"""
                if status:
                    logger.warning(f"Audio callback status: {status}")

                # Copy data to queue
                audio_queue.put(indata.copy())

            # Start input stream
            self._stream = sd.InputStream(
                device=self.device,
                channels=self.channels,
                samplerate=self.sample_rate,
                dtype=self.dtype,
                callback=audio_callback
            )

            self._stream.start()
            self._recording = True

            # Start worker thread to process audio
            def worker():
                consecutive_errors = 0
                while self._recording:
                    try:
                        audio_chunk = audio_queue.get(timeout=0.1)

                        # Convert to mono if needed
                        if audio_chunk.ndim > 1:
                            audio_chunk = audio_chunk.mean(axis=1)

                        # Call user callback
                        if self._callback_func:
                            self._callback_func(audio_chunk.flatten())

                        # Reset error counter on success
                        consecutive_errors = 0

                    except queue.Empty:
                        continue
                    except Exception as e:
                        # CRITICAL: Log with full traceback to see what's failing!
                        logger.error(f"Audio processing error: {e}", exc_info=True)
                        consecutive_errors += 1

                        # Stop if too many consecutive errors (callback is broken)
                        if consecutive_errors >= 10:
                            logger.critical(f"Audio worker stopping after {consecutive_errors} consecutive errors!")
                            self._recording = False
                            break

            self._worker_thread = threading.Thread(target=worker, daemon=True)
            self._worker_thread.start()

            logger.info("Audio stream started")
            return True

        except Exception as e:
            logger.error(f"Failed to start audio stream: {e}")
            self._recording = False
            return False

    def stop_stream(self):
        """Stop streaming audio"""
        if not self._recording:
            return

        self._recording = False

        if self._stream:
            try:
                self._stream.stop()
                self._stream.close()
            except:
                pass
            self._stream = None

        logger.info("Audio stream stopped")

    @property
    def is_recording(self) -> bool:
        """Check if currently recording"""
        return self._recording

    def __enter__(self):
        """Context manager entry"""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit"""
        self.stop_stream()

    def __repr__(self):
        status = "recording" if self._recording else "idle"
        return f"<AudioCapture device={self.device} rate={self.sample_rate} ({status})>"
