"""
Network Whisper Transcriber

Uses a remote Whisper server (e.g., faster-whisper-server) for transcription.
Supports self-hosted Whisper models accessible over HTTP.
"""

import numpy as np
import logging
import io
import wave
import threading
import queue
import requests
from typing import Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class NetworkTranscriptionResult:
    """Result from network Whisper server"""
    request_id: int = 0
    text: str = ""
    success: bool = False
    error: Optional[str] = None
    frequency_hz: float = 0.0
    worker_id: int = -1
    # Speech detection (if server provides it)
    has_speech: bool = False
    speech_ratio: float = 0.0
    avg_no_speech_prob: float = 1.0


class NetworkTranscriber:
    """
    Transcriber using a remote Whisper server over HTTP.

    Compatible with:
    - faster-whisper-server (https://github.com/fedirz/faster-whisper-server)
    - whisper-asr-webservice
    - Any OpenAI-compatible Whisper API endpoint

    Example server URLs:
    - http://localhost:8000
    - http://192.168.1.100:8000
    - http://whisper-server.local:8000
    """

    def __init__(
        self,
        server_url: str = "http://localhost:8000",
        model: str = "medium.en",
        timeout: float = 30.0,
        language: str = "en"
    ):
        """
        Initialize network transcriber.

        Args:
            server_url: Base URL of Whisper server (e.g., http://192.168.1.100:8000)
            model: Whisper model name (server must have this model loaded)
            timeout: Request timeout in seconds
            language: Language code for transcription
        """
        self.server_url = server_url.rstrip('/')
        self.model = model
        self.timeout = timeout
        self.language = language

        # Async interface (to match SubprocessTranscriber)
        self._request_counter = 0
        self._result_queue = queue.Queue()
        self._active_threads = []

        # Track readiness
        self.is_ready = False

        logger.info(f"NetworkTranscriber initialized: server={server_url}, model={model}")

    def test_connection(self) -> bool:
        """
        Test if Whisper server is accessible.

        Returns:
            True if connection successful, False otherwise
        """
        try:
            # Try health check endpoint (faster-whisper-server)
            health_url = f"{self.server_url}/health"
            response = requests.get(health_url, timeout=5.0)

            if response.status_code == 200:
                logger.info(f"Network Whisper server health check passed: {self.server_url}")
                self.is_ready = True
                return True
            else:
                logger.warning(f"Server responded with status {response.status_code}")
                return False

        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to connect to Whisper server at {self.server_url}: {e}")
            return False

    def start(self) -> bool:
        """
        Initialize connection to server (compatibility with SubprocessTranscriber).

        Returns:
            True if server is accessible
        """
        return self.test_connection()

    def transcribe(
        self,
        audio: np.ndarray,
        sample_rate: int = 16000,
        frequency_hz: float = 0.0
    ) -> NetworkTranscriptionResult:
        """
        Transcribe audio using network Whisper server.

        Args:
            audio: Audio samples as numpy array (float32, -1 to 1)
            sample_rate: Sample rate in Hz
            frequency_hz: Frequency where audio was captured (for tracking)

        Returns:
            NetworkTranscriptionResult with transcription text
        """
        try:
            # Convert numpy audio to WAV bytes
            audio_bytes = self._audio_to_wav(audio, sample_rate)

            # Prepare multipart form data
            files = {
                'file': ('audio.wav', audio_bytes, 'audio/wav')
            }

            # Parameters for faster-whisper-server (OpenAI-compatible API)
            data = {
                'model': self.model,
                'language': self.language,
                'response_format': 'verbose_json'  # Get detailed response with segments
            }

            # Send to server
            logger.debug(f"Sending {len(audio)/sample_rate:.1f}s audio to {self.server_url}...")
            transcribe_url = f"{self.server_url}/v1/audio/transcriptions"

            response = requests.post(
                transcribe_url,
                files=files,
                data=data,
                timeout=self.timeout
            )

            if response.status_code != 200:
                raise Exception(f"Server returned status {response.status_code}: {response.text}")

            # Parse response
            result = response.json()

            # Extract text
            text = result.get('text', '').strip()

            # Extract speech detection info if available
            has_speech = False
            speech_ratio = 0.0
            avg_no_speech_prob = 1.0

            # Check if we have segments with no_speech_prob
            segments = result.get('segments', [])
            if segments:
                no_speech_probs = []
                segments_with_speech = 0

                for seg in segments:
                    no_speech_prob = seg.get('no_speech_prob', seg.get('no_speech_probability', 1.0))
                    no_speech_probs.append(no_speech_prob)

                    # Threshold for speech detection
                    if no_speech_prob < 0.6:
                        segments_with_speech += 1

                if no_speech_probs:
                    avg_no_speech_prob = sum(no_speech_probs) / len(no_speech_probs)
                    has_speech = segments_with_speech > 0
                    speech_ratio = segments_with_speech / len(segments)

            logger.debug(f"Network transcription: {text[:100]}... (speech_ratio={speech_ratio:.2f})")

            return NetworkTranscriptionResult(
                text=text,
                success=True,
                frequency_hz=frequency_hz,
                has_speech=has_speech,
                speech_ratio=speech_ratio,
                avg_no_speech_prob=avg_no_speech_prob
            )

        except requests.exceptions.Timeout:
            logger.error(f"Network transcription timeout after {self.timeout}s")
            return NetworkTranscriptionResult(
                text="",
                success=False,
                frequency_hz=frequency_hz,
                error="Request timeout"
            )

        except Exception as e:
            logger.error(f"Network transcription failed: {e}")
            return NetworkTranscriptionResult(
                text="",
                success=False,
                frequency_hz=frequency_hz,
                error=str(e)
            )

    def _audio_to_wav(self, audio: np.ndarray, sample_rate: int) -> bytes:
        """
        Convert numpy audio array to WAV file bytes.

        Args:
            audio: Float32 audio samples (-1 to 1)
            sample_rate: Sample rate in Hz

        Returns:
            WAV file as bytes
        """
        # Convert float32 to int16
        audio_int16 = (audio * 32767).astype(np.int16)

        # Write to WAV
        buffer = io.BytesIO()
        with wave.open(buffer, 'wb') as wav_file:
            wav_file.setnchannels(1)  # Mono
            wav_file.setsampwidth(2)  # 16-bit
            wav_file.setframerate(sample_rate)
            wav_file.writeframes(audio_int16.tobytes())

        return buffer.getvalue()

    def transcribe_async(
        self,
        audio: np.ndarray,
        sample_rate: int = 16000,
        frequency_hz: float = 0.0,
        voice_db=None
    ) -> int:
        """
        Asynchronously transcribe audio using network server.

        Starts transcription in a background thread.

        Args:
            audio: Audio samples as numpy array (float32, -1 to 1)
            sample_rate: Sample rate in Hz
            frequency_hz: Frequency where audio was captured
            voice_db: Deprecated - ignored (kept for backward compatibility)

        Returns:
            Request ID for tracking the transcription
        """
        self._request_counter += 1
        request_id = self._request_counter

        def worker():
            result = self.transcribe(audio, sample_rate, frequency_hz)
            # Add request ID to result
            result.request_id = request_id
            self._result_queue.put(result)

        thread = threading.Thread(target=worker, daemon=True)
        thread.start()
        self._active_threads.append(thread)

        logger.debug(f"Started async network transcription request {request_id} (frequency={frequency_hz/1e6:.3f} MHz)")
        return request_id

    def get_result(self, timeout: float = 0.1) -> Optional[NetworkTranscriptionResult]:
        """
        Get transcription result (non-blocking).

        Args:
            timeout: Timeout in seconds (0.1 for polling compatibility)

        Returns:
            NetworkTranscriptionResult if available, None otherwise
        """
        try:
            if timeout == 0:
                # Non-blocking
                return self._result_queue.get_nowait()
            else:
                return self._result_queue.get(timeout=timeout)
        except queue.Empty:
            return None

    def is_alive(self) -> bool:
        """Check if transcriber is active (always True for network)."""
        return self.is_ready

    def stop(self):
        """Stop transcriber (wait for pending threads)."""
        for thread in self._active_threads:
            thread.join(timeout=5.0)
        self._active_threads.clear()
        logger.info("Network transcriber stopped")

    def get_health_status(self) -> dict:
        """
        Get health status (compatibility with SubprocessTranscriber).

        Returns:
            Dict with health information
        """
        return {
            'alive_count': 1 if self.is_ready else 0,
            'dead_count': 0,
            'total_workers': 1,
            'expected_workers': 1,
            'is_ready': self.is_ready,
            'shutting_down': False,
            'server_url': self.server_url,
            'model': self.model
        }
