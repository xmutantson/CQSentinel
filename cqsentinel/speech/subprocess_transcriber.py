"""
Subprocess-based transcription worker for Windows compatibility

Uses multiprocessing to run faster-whisper in a separate process,
avoiding threading issues that cause crashes on Windows.
"""

import multiprocessing as mp
import numpy as np
import logging
from typing import Optional, Tuple
from dataclasses import dataclass
import time

logger = logging.getLogger(__name__)


@dataclass
class TranscriptionRequest:
    """Request to transcribe audio"""
    audio: np.ndarray
    sample_rate: int
    request_id: int


@dataclass
class TranscriptionResult:
    """Result of transcription"""
    request_id: int
    text: str
    success: bool
    error: Optional[str] = None


def transcription_worker(input_queue: mp.Queue, output_queue: mp.Queue, model_size: str, compute_type: str):
    """
    Worker process that loads Whisper model and processes transcription requests.

    This runs in a separate process to avoid Windows threading issues with ctranslate2.

    Args:
        input_queue: Queue for receiving TranscriptionRequest objects
        output_queue: Queue for sending TranscriptionResult objects
        model_size: Whisper model size (tiny, base, small, medium, large)
        compute_type: Compute type (float32, float16, int8)
    """
    # Import inside subprocess to avoid loading in main process
    try:
        from faster_whisper import WhisperModel

        # Load model once at subprocess startup
        print(f"[SUBPROCESS] Loading Whisper {model_size} model (compute_type={compute_type})...")
        model = WhisperModel(
            model_size,
            device="cpu",
            compute_type=compute_type,
            download_root=None
        )
        print(f"[SUBPROCESS] Model loaded successfully")

        # Signal that we're ready
        output_queue.put(TranscriptionResult(
            request_id=-1,
            text="READY",
            success=True
        ))

    except Exception as e:
        print(f"[SUBPROCESS] Failed to load model: {e}")
        import traceback
        traceback.print_exc()
        output_queue.put(TranscriptionResult(
            request_id=-1,
            text="ERROR",
            success=False,
            error=str(e)
        ))
        return

    # Process requests until shutdown signal
    print("[SUBPROCESS] Ready to process transcription requests")
    while True:
        try:
            # Wait for request (blocking)
            request = input_queue.get()

            # Shutdown signal
            if request is None:
                print("[SUBPROCESS] Received shutdown signal")
                break

            print(f"[SUBPROCESS] Processing request {request.request_id}, audio duration: {len(request.audio)/request.sample_rate:.1f}s")

            # Transcribe
            try:
                segments, info = model.transcribe(
                    request.audio,
                    language="en",
                    beam_size=5,
                    temperature=0.0,  # Disable fallback (Windows stability)
                    vad_filter=False  # VAD already applied
                )

                # Collect all segments
                texts = []
                for seg in segments:
                    if seg.text.strip():
                        texts.append(seg.text.strip())

                result_text = " ".join(texts)
                print(f"[SUBPROCESS] Transcription complete: {len(result_text)} chars")

                # Send result
                output_queue.put(TranscriptionResult(
                    request_id=request.request_id,
                    text=result_text,
                    success=True
                ))

            except Exception as e:
                print(f"[SUBPROCESS] Transcription failed: {e}")
                import traceback
                traceback.print_exc()
                output_queue.put(TranscriptionResult(
                    request_id=request.request_id,
                    text="",
                    success=False,
                    error=str(e)
                ))

        except Exception as e:
            print(f"[SUBPROCESS] Error in worker loop: {e}")
            import traceback
            traceback.print_exc()
            # Continue processing

    print("[SUBPROCESS] Worker shutting down")


class SubprocessTranscriber:
    """
    Manages a subprocess for transcription to avoid Windows threading issues.

    The subprocess loads the Whisper model once and processes transcription
    requests via queues.
    """

    def __init__(self, model_size: str = "small", compute_type: str = "float32"):
        """
        Initialize subprocess transcriber.

        Args:
            model_size: Whisper model size
            compute_type: Compute type (float32 recommended for Windows)
        """
        self.model_size = model_size
        self.compute_type = compute_type

        # IPC queues
        self.input_queue = mp.Queue(maxsize=10)
        self.output_queue = mp.Queue(maxsize=10)

        # Process
        self.process: Optional[mp.Process] = None
        self.is_ready = False
        self.request_counter = 0

        logger.info(f"SubprocessTranscriber initialized: model={model_size}, compute_type={compute_type}")

    def start(self) -> bool:
        """
        Start the transcription subprocess.

        Returns:
            True if subprocess started successfully
        """
        if self.process is not None and self.process.is_alive():
            logger.warning("Subprocess already running")
            return True

        try:
            logger.info("Starting transcription subprocess...")

            # Create subprocess
            self.process = mp.Process(
                target=transcription_worker,
                args=(self.input_queue, self.output_queue, self.model_size, self.compute_type),
                daemon=False  # Not daemon so we can clean shutdown
            )
            self.process.start()

            logger.info(f"Subprocess started (PID: {self.process.pid})")

            # Wait for READY signal (with timeout)
            timeout = 30.0  # Model loading can take time
            start_time = time.time()

            while time.time() - start_time < timeout:
                try:
                    result = self.output_queue.get(timeout=0.5)
                    if result.request_id == -1:
                        if result.success:
                            self.is_ready = True
                            logger.info("Subprocess ready to process requests")
                            return True
                        else:
                            logger.error(f"Subprocess failed to initialize: {result.error}")
                            self.stop()
                            return False
                except:
                    # No result yet, keep waiting
                    if not self.process.is_alive():
                        logger.error("Subprocess died during initialization")
                        return False

            logger.error("Timeout waiting for subprocess to initialize")
            self.stop()
            return False

        except Exception as e:
            logger.error(f"Failed to start subprocess: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return False

    def transcribe_async(self, audio: np.ndarray, sample_rate: int) -> int:
        """
        Submit audio for transcription (non-blocking).

        Args:
            audio: Audio signal (mono, float32)
            sample_rate: Sample rate

        Returns:
            Request ID to match with results
        """
        if not self.is_ready or not self.process or not self.process.is_alive():
            raise RuntimeError("Subprocess not ready")

        # Create request
        self.request_counter += 1
        request = TranscriptionRequest(
            audio=audio.copy(),  # Copy to avoid shared memory issues
            sample_rate=sample_rate,
            request_id=self.request_counter
        )

        # Send to subprocess
        self.input_queue.put(request)
        logger.debug(f"Submitted transcription request {request.request_id}")

        return request.request_id

    def get_result(self, timeout: float = 0.1) -> Optional[TranscriptionResult]:
        """
        Get transcription result if available (non-blocking).

        Args:
            timeout: Timeout in seconds (0 for non-blocking)

        Returns:
            TranscriptionResult if available, None otherwise
        """
        try:
            if timeout > 0:
                result = self.output_queue.get(timeout=timeout)
            else:
                result = self.output_queue.get_nowait()
            return result
        except:
            return None

    def stop(self):
        """Stop the subprocess."""
        if self.process is None:
            return

        try:
            if self.process.is_alive():
                logger.info("Stopping transcription subprocess...")

                # Send shutdown signal
                try:
                    self.input_queue.put(None, timeout=1.0)
                except:
                    pass

                # Wait for graceful shutdown
                self.process.join(timeout=5.0)

                # Force terminate if still alive
                if self.process.is_alive():
                    logger.warning("Subprocess didn't stop gracefully, terminating...")
                    self.process.terminate()
                    self.process.join(timeout=2.0)

                # Force kill if still alive
                if self.process.is_alive():
                    logger.error("Subprocess still alive, killing...")
                    self.process.kill()
                    self.process.join(timeout=1.0)

                logger.info("Subprocess stopped")

            self.process = None
            self.is_ready = False

        except Exception as e:
            logger.error(f"Error stopping subprocess: {e}")

    def is_alive(self) -> bool:
        """Check if subprocess is alive."""
        return self.process is not None and self.process.is_alive()

    def __del__(self):
        """Cleanup on deletion."""
        self.stop()
