"""
OpenAI Whisper API Transcriber

Uses the OpenAI Whisper API for cloud-based transcription.
Supersedes local Whisper when API key is provided.
"""

import numpy as np
import logging
import io
import wave
import tempfile
import os
import threading
import queue
from typing import Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class OpenAITranscriptionResult:
    """Result from OpenAI Whisper API"""
    request_id: int = 0
    text: str = ""
    success: bool = False
    error: Optional[str] = None


class OpenAITranscriber:
    """
    Transcriber using OpenAI Whisper API.

    Sends audio to OpenAI cloud for transcription.
    Costs ~$0.006 per minute of audio.
    """

    def __init__(self, api_key: str, model: str = "whisper-1"):
        """
        Initialize OpenAI transcriber.

        Args:
            api_key: OpenAI API key
            model: Whisper model to use (default: whisper-1)
        """
        self.api_key = api_key
        self.model = model
        self._client = None

        # Lazy import openai to avoid dependency issues
        self._openai = None

        # Async interface (to match SubprocessTranscriber)
        self._request_counter = 0
        self._result_queue = queue.Queue()
        self._active_threads = []

        # Track readiness (always ready for OpenAI)
        self.is_ready = True

        logger.info(f"OpenAITranscriber initialized with model={model}")

    def _ensure_client(self):
        """Lazy-load OpenAI client."""
        if self._client is None:
            try:
                import openai
                self._openai = openai
                self._client = openai.OpenAI(api_key=self.api_key)
                logger.info("OpenAI client initialized")
            except ImportError:
                raise ImportError(
                    "openai package not installed. "
                    "Install with: pip install openai"
                )

    def transcribe(self, audio: np.ndarray, sample_rate: int = 16000) -> OpenAITranscriptionResult:
        """
        Transcribe audio using OpenAI Whisper API.

        Args:
            audio: Audio samples as numpy array (float32, -1 to 1)
            sample_rate: Sample rate in Hz

        Returns:
            OpenAITranscriptionResult with transcription text
        """
        try:
            self._ensure_client()

            # Convert numpy audio to WAV file
            audio_bytes = self._audio_to_wav(audio, sample_rate)

            # Create a temporary file for the API call
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp_file:
                tmp_file.write(audio_bytes)
                tmp_path = tmp_file.name

            try:
                # Send to OpenAI API
                logger.debug(f"Sending {len(audio)/sample_rate:.1f}s audio to OpenAI API...")

                with open(tmp_path, "rb") as audio_file:
                    response = self._client.audio.transcriptions.create(
                        model=self.model,
                        file=audio_file,
                        language="en",
                        response_format="text"
                    )

                # Response is just the text string
                text = response.strip() if isinstance(response, str) else str(response).strip()

                logger.debug(f"OpenAI transcription: {text[:100]}...")

                return OpenAITranscriptionResult(
                    text=text,
                    success=True
                )

            finally:
                # Clean up temp file
                try:
                    os.unlink(tmp_path)
                except Exception:
                    pass

        except Exception as e:
            logger.error(f"OpenAI transcription failed: {e}")
            return OpenAITranscriptionResult(
                text="",
                success=False,
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

    def test_connection(self) -> bool:
        """
        Test if OpenAI API connection works.

        Returns:
            True if connection successful, False otherwise
        """
        try:
            self._ensure_client()

            # Generate 1 second of silence to test
            silence = np.zeros(16000, dtype=np.float32)
            result = self.transcribe(silence, 16000)

            if result.success:
                logger.info("OpenAI API connection test passed")
                return True
            else:
                logger.error(f"OpenAI API test failed: {result.error}")
                return False

        except Exception as e:
            logger.error(f"OpenAI API connection test failed: {e}")
            return False

    def transcribe_async(self, audio: np.ndarray, sample_rate: int = 16000) -> int:
        """
        Asynchronously transcribe audio using OpenAI API.

        Starts transcription in a background thread.

        Args:
            audio: Audio samples as numpy array (float32, -1 to 1)
            sample_rate: Sample rate in Hz

        Returns:
            Request ID for tracking the transcription
        """
        self._request_counter += 1
        request_id = self._request_counter

        def worker():
            result = self.transcribe(audio, sample_rate)
            # Convert to async result format
            async_result = OpenAITranscriptionResult(
                request_id=request_id,
                text=result.text,
                success=result.success,
                error=result.error
            )
            self._result_queue.put(async_result)

        thread = threading.Thread(target=worker, daemon=True)
        thread.start()
        self._active_threads.append(thread)

        logger.debug(f"Started async transcription request {request_id}")
        return request_id

    def get_result(self, timeout: float = 0) -> Optional[OpenAITranscriptionResult]:
        """
        Get transcription result (non-blocking).

        Args:
            timeout: Timeout in seconds (0 = non-blocking)

        Returns:
            OpenAITranscriptionResult if available, None otherwise
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
        """Check if transcriber is active (always True for API)."""
        return True

    def stop(self):
        """Stop transcriber (wait for pending threads)."""
        for thread in self._active_threads:
            thread.join(timeout=5.0)
        self._active_threads.clear()
        logger.info("OpenAI transcriber stopped")
