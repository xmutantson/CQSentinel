"""
Subprocess-based transcription worker pool for Windows compatibility

Uses multiprocessing to run faster-whisper in separate processes,
avoiding threading issues that cause crashes on Windows.
"""

import multiprocessing as mp
import numpy as np
import logging
import os
import sys
from typing import Optional, List
from dataclasses import dataclass
import time

logger = logging.getLogger(__name__)


@dataclass
class TranscriptionRequest:
    """Request to transcribe audio"""
    audio: np.ndarray
    sample_rate: int
    request_id: int
    worker_id: int = -1  # Assigned by pool


@dataclass
class TranscriptionResult:
    """Result of transcription"""
    request_id: int
    text: str
    success: bool
    worker_id: int = -1
    error: Optional[str] = None
    # Speech detection info from Whisper
    has_speech: bool = False  # True if any segment has speech
    speech_ratio: float = 0.0  # Ratio of audio segments with speech (0.0-1.0)
    avg_no_speech_prob: float = 1.0  # Average no_speech_prob across segments


def _get_models_directory():
    """Get the models directory for the current environment."""
    if getattr(sys, 'frozen', False):
        # PyInstaller frozen executable
        base_dir = os.path.dirname(sys.executable)
        return os.path.join(base_dir, 'models')
    else:
        # Development mode
        return os.path.join(os.path.dirname(__file__), '..', '..', 'models')


def transcription_worker(worker_id: int, input_queue: mp.Queue, output_queue: mp.Queue,
                         model_size: str, device: str, use_fp16: bool, models_dir: str,
                         beam_size: int = 5, temperature: float = 0.0,
                         no_speech_threshold: float = 0.6):
    """
    Worker process that loads Whisper model and processes transcription requests.

    This runs in a separate process to avoid Windows threading issues with ctranslate2.

    Args:
        worker_id: Unique identifier for this worker
        input_queue: Queue for receiving TranscriptionRequest objects
        output_queue: Queue for sending TranscriptionResult objects
        model_size: Whisper model size (e.g., "medium.en")
        device: Device to load model on ("cpu" or "cuda")
        use_fp16: Use fp16 precision (True for GPU, False for CPU)
        models_dir: Directory where models are stored (for offline operation)
        beam_size: Beam search size for decoding (default: 5)
        temperature: Temperature for decoding (default: 0.0 for deterministic)
        no_speech_threshold: Threshold for detecting no speech (default: 0.6)
    """
    # Helper for safe flushing (stdout/stderr can be None in subprocess on Windows)
    def safe_flush():
        if sys.stdout is not None:
            try:
                sys.stdout.flush()
            except Exception:
                pass
        if sys.stderr is not None:
            try:
                sys.stderr.flush()
            except Exception:
                pass

    # Helper for immediate output (handles None stdout in subprocess)
    def log(msg):
        if sys.stdout is not None:
            try:
                print(f"[WORKER-{worker_id}] {msg}", flush=True)
            except Exception:
                pass
        safe_flush()

    # CRITICAL: Fix None stdout/stderr in PyInstaller frozen subprocess
    # whisper internally writes to stdout/stderr (tqdm progress, warnings, etc.)
    # even with verbose=False. If these are None, it causes AttributeError.
    class NullWriter:
        """Dummy writer that ignores all writes. Used when stdout/stderr is None."""
        def __init__(self):
            # Open devnull for fileno() support (needed by faulthandler)
            self._devnull = None
            try:
                self._devnull = open(os.devnull, 'w')
            except Exception:
                pass

        def write(self, s):
            pass

        def flush(self):
            pass

        def isatty(self):
            return False

        def fileno(self):
            # Return devnull file descriptor if available
            if self._devnull is not None:
                return self._devnull.fileno()
            # Otherwise return -1 (invalid fd)
            return -1

    if sys.stdout is None:
        sys.stdout = NullWriter()
        log("Replaced None stdout with NullWriter")

    if sys.stderr is None:
        sys.stderr = NullWriter()
        log("Replaced None stderr with NullWriter")

    # Import inside subprocess to avoid loading in main process
    try:
        # CRITICAL: Enable faulthandler for C++ crash diagnostics in worker
        # This will print stack trace on SIGSEGV, SIGABRT, etc.
        import faulthandler
        if sys.stderr is not None:
            try:
                faulthandler.enable(file=sys.stderr)
                log(f"Faulthandler enabled in worker subprocess")
            except Exception as fh_e:
                log(f"Warning: Could not enable faulthandler: {fh_e}")
        else:
            # Try to enable to default stderr (may not work)
            try:
                faulthandler.enable()
                log(f"Faulthandler enabled (default stderr)")
            except Exception:
                pass

        # Set NumPy/MKL threading to single-threaded (prevent threading conflicts)
        os.environ['OMP_NUM_THREADS'] = '1'
        os.environ['MKL_NUM_THREADS'] = '1'
        os.environ['NUMEXPR_NUM_THREADS'] = '1'
        os.environ['OPENBLAS_NUM_THREADS'] = '1'

        # Set environment variables to prevent network access
        # HuggingFace will look in cache first
        os.environ['HF_HOME'] = os.path.join(models_dir, 'huggingface')
        os.environ['TORCH_HOME'] = os.path.join(models_dir, 'torch')
        os.environ['TRANSFORMERS_OFFLINE'] = '1'  # Force offline mode
        os.environ['HF_HUB_OFFLINE'] = '1'  # Force HuggingFace Hub offline

        # Use openai-whisper instead of faster-whisper for Windows PyInstaller stability
        # faster-whisper uses ctranslate2 which crashes on Windows frozen builds

        import whisper

        # Load Whisper model using openai-whisper (PyTorch backend - more stable)
        log(f"Loading Whisper {model_size} model on {device} (fp16={use_fp16})...")
        log(f"Models directory: {models_dir}")
        log(f"TORCH_HOME: {os.environ['TORCH_HOME']}")
        log(f"Decoding params: beam_size={beam_size}, temperature={temperature}, no_speech_threshold={no_speech_threshold}")

        # openai-whisper downloads models to ~/.cache/whisper by default
        # Set download_root to our models directory
        whisper_cache = os.path.join(models_dir, 'whisper')
        os.makedirs(whisper_cache, exist_ok=True)
        log(f"Whisper cache directory: {whisper_cache}")

        # Load model on specified device
        model = whisper.load_model(
            model_size,
            device=device,
            download_root=whisper_cache
        )

        # NOTE: Don't call model.half() manually - let transcribe() handle fp16 conversion
        # via the fp16 parameter. Manual conversion causes dtype mismatch errors.
        log(f"Whisper model loaded on {device} (fp16={use_fp16} during inference)")

        # Test model with silence to verify it works
        log(f"Testing model with 1-second silence...")
        test_audio = np.zeros(16000, dtype=np.float32)
        try:
            # openai-whisper expects audio as float32 numpy array at 16kHz
            test_result = model.transcribe(test_audio, language="en", fp16=use_fp16)
            log(f"Model test PASSED: transcribed silence successfully")
        except Exception as test_e:
            log(f"Model test FAILED: {test_e}")
            raise RuntimeError(f"Model failed basic transcription test: {test_e}")

        # Signal that we're ready
        output_queue.put(TranscriptionResult(
            request_id=-1,
            text="READY",
            success=True,
            worker_id=worker_id
        ))

    except Exception as e:
        log(f"Failed to load models: {e}")
        import traceback
        if sys.stderr is not None:
            try:
                traceback.print_exc()
            except Exception:
                pass
        safe_flush()
        output_queue.put(TranscriptionResult(
            request_id=-1,
            text="ERROR",
            success=False,
            worker_id=worker_id,
            error=str(e)
        ))
        return

    # Process requests until shutdown signal
    log(f"Ready to process transcription requests")
    while True:
        try:
            # Wait for request (blocking)
            request = input_queue.get()

            # Shutdown signal
            if request is None:
                log(f"Received shutdown signal")
                break

            log(f"Processing request {request.request_id}, audio duration: {len(request.audio)/request.sample_rate:.1f}s")
            processing_start = time.time()

            # Validate audio data after unpickling
            log(f"Audio validation: dtype={request.audio.dtype}, shape={request.audio.shape}, range=[{request.audio.min():.3f}, {request.audio.max():.3f}]")
            if not np.isfinite(request.audio).all():
                log(f"WARNING: Audio contains NaN or Inf values!")
            if request.audio.dtype != np.float32:
                log(f"Converting audio to float32 (was {request.audio.dtype})")
                request.audio = request.audio.astype(np.float32)

            # CRITICAL: Ensure audio is C-contiguous for ctranslate2
            if not request.audio.flags['C_CONTIGUOUS']:
                log(f"WARNING: Audio not C-contiguous, fixing...")
                request.audio = np.ascontiguousarray(request.audio)
                log(f"Audio now C-contiguous: {request.audio.flags['C_CONTIGUOUS']}")

            # Process transcription
            try:
                log(f"Transcribing...")
                log(f"About to call model.transcribe() with audio shape={request.audio.shape}")

                # DIAGNOSTIC: Verify model is still valid
                log(f"Model object type: {type(model)}")
                log(f"Audio memory flags: C_CONTIGUOUS={request.audio.flags['C_CONTIGUOUS']}, OWNDATA={request.audio.flags['OWNDATA']}")
                safe_flush()

                transcribe_start = time.time()
                try:
                    log(f"Calling model.transcribe()...")
                    safe_flush()

                    # Initial prompt to provide context for amateur radio communications
                    # This biases Whisper towards ham radio vocabulary and patterns
                    # CRITICAL: Explicitly instruct to avoid hallucinations on silence/noise
                    ham_radio_prompt = (
                        "Single-sideband amateur radio contest exchange in North America. "
                        "Operators use the NATO phonetic alphabet (Whiskey Seven Whiskey Alpha), "
                        "give callsigns, short signal reports like 'five nine', serial numbers, "
                        "and ARRL Sweepstakes style exchanges with precedence letters, check, and section "
                        "(for example 'one alpha, seventy nine, Northern New Jersey'). "
                        "Transcribe only what is clearly spoken on the air. "
                        "Do not add any extra words or filler; if you are unsure or there is only noise, "
                        "leave the transcription empty."
                    )

                    # openai-whisper API (returns dict with 'text' and 'segments')
                    # Enhanced decoding parameters for better accuracy
                    result = model.transcribe(
                        request.audio,
                        language="en",
                        fp16=use_fp16,  # Use fp16 on GPU, fp32 on CPU
                        verbose=False,  # Don't print progress

                        # Provide ham radio context to bias decoder
                        initial_prompt=ham_radio_prompt,

                        # Decoding parameters for better contest audio transcription
                        beam_size=beam_size,  # Beam search (5 is good balance)
                        best_of=beam_size if temperature > 0 else 1,  # Only sample when using temperature
                        temperature=temperature,  # 0.0 for deterministic

                        # Hallucination reduction
                        no_speech_threshold=no_speech_threshold,  # Higher = fewer false positives
                        logprob_threshold=-1.0,  # Filter low-confidence tokens
                        condition_on_previous_text=False,  # Each segment independent (better for short audio)
                    )

                    log(f"model.transcribe() completed in {time.time() - transcribe_start:.2f}s")
                    log(f"Detected language: {result.get('language', 'unknown')}")
                    safe_flush()

                    # Extract text from result and speech detection info
                    texts = []
                    no_speech_probs = []
                    segments_with_speech = 0
                    total_segments = 0

                    if 'segments' in result:
                        segment_count = len(result['segments'])
                        log(f"Processing {segment_count} segments...")
                        for i, seg in enumerate(result['segments']):
                            seg_text = seg.get('text', '').strip()
                            no_speech_prob = seg.get('no_speech_prob', 1.0)
                            no_speech_probs.append(no_speech_prob)
                            total_segments += 1

                            # Consider segment has speech if no_speech_prob < threshold
                            has_segment_speech = no_speech_prob < no_speech_threshold
                            if has_segment_speech:
                                segments_with_speech += 1

                            log(f"Segment {i+1}: [{seg.get('start', 0):.2f}-{seg.get('end', 0):.2f}] no_speech_prob={no_speech_prob:.3f} '{seg_text}'")
                            if seg_text:
                                texts.append(seg_text)
                            safe_flush()
                    else:
                        # Fallback to full text if no segments
                        full_text = result.get('text', '').strip()
                        if full_text:
                            texts.append(full_text)
                            # Assume speech if we got text
                            segments_with_speech = 1
                            total_segments = 1
                            no_speech_probs.append(0.0)

                    # Calculate speech detection metrics
                    has_speech = segments_with_speech > 0
                    speech_ratio = segments_with_speech / total_segments if total_segments > 0 else 0.0
                    avg_no_speech_prob = sum(no_speech_probs) / len(no_speech_probs) if no_speech_probs else 1.0

                    log(f"Transcription complete: {len(texts)} text segments, speech_ratio={speech_ratio:.2f}, avg_no_speech_prob={avg_no_speech_prob:.3f}")
                except Exception as te:
                    log(f"model.transcribe() EXCEPTION: {te}")
                    import traceback
                    if sys.stderr is not None:
                        try:
                            traceback.print_exc()
                        except Exception:
                            pass
                    safe_flush()
                    raise

                result_text = " ".join(texts)

                total_time = time.time() - processing_start
                log(f"Transcription complete in {total_time:.2f}s: {result_text}")

                # Send result with speech detection info
                output_queue.put(TranscriptionResult(
                    request_id=request.request_id,
                    text=result_text,
                    success=True,
                    worker_id=worker_id,
                    has_speech=has_speech,
                    speech_ratio=speech_ratio,
                    avg_no_speech_prob=avg_no_speech_prob
                ))

            except Exception as e:
                log(f"Transcription failed: {e}")
                import traceback
                if sys.stderr is not None:
                    try:
                        traceback.print_exc()
                    except Exception:
                        pass
                safe_flush()
                output_queue.put(TranscriptionResult(
                    request_id=request.request_id,
                    text="",
                    success=False,
                    worker_id=worker_id,
                    error=str(e)
                ))

        except Exception as e:
            log(f"Error in worker loop: {e}")
            import traceback
            if sys.stderr is not None:
                try:
                    traceback.print_exc()
                except Exception:
                    pass
            safe_flush()
            # Continue processing

    log(f"Worker shutting down - cleaning up GPU resources...")

    # CRITICAL: Clean up CUDA resources to prevent BSOD on abrupt termination
    try:
        # Delete model to free GPU memory
        if 'model' in dir():
            del model
            log(f"Model deleted from memory")

        # Clean up CUDA cache if using GPU
        if device == "cuda":
            try:
                import torch
                if torch.cuda.is_available():
                    # Synchronize to ensure all GPU operations complete
                    torch.cuda.synchronize()
                    log(f"CUDA operations synchronized")

                    # Empty CUDA cache to free GPU memory
                    torch.cuda.empty_cache()
                    log(f"CUDA cache cleared")

                    # Reset peak memory stats (diagnostic)
                    torch.cuda.reset_peak_memory_stats()
                    log(f"CUDA memory stats reset")
            except Exception as cuda_e:
                log(f"Warning: CUDA cleanup error (non-fatal): {cuda_e}")

        log(f"GPU cleanup complete")
    except Exception as cleanup_e:
        log(f"Error during GPU cleanup: {cleanup_e}")

    log(f"Worker shutdown complete")


class SubprocessTranscriber:
    """
    Manages a pool of subprocesses for transcription to handle concurrent requests.

    The subprocess pool loads the Whisper model in each worker and processes
    transcription requests via queues. Supports both CPU and GPU workers.
    """

    def __init__(
        self,
        model_size: str = "medium.en",  # Hardcoded to medium.en for best accuracy
        device: str = "cpu",  # "cpu" or "cuda"
        use_fp16: bool = False,  # True for GPU, False for CPU
        num_workers: int = 3,
        beam_size: int = 5,
        temperature: float = 0.0,
        no_speech_threshold: float = 0.6
    ):
        """
        Initialize subprocess transcriber pool.

        Args:
            model_size: Whisper model size (default: "medium.en")
            device: Device to run on ("cpu" or "cuda")
            use_fp16: Use fp16 precision (True for GPU, False for CPU)
            num_workers: Number of worker processes to spawn
            beam_size: Beam search size for decoding
            temperature: Temperature for decoding (0.0 for deterministic)
            no_speech_threshold: Threshold for detecting no speech
        """
        self.model_size = model_size
        self.device = device
        self.use_fp16 = use_fp16
        self.num_workers = num_workers
        self.beam_size = beam_size
        self.temperature = temperature
        self.no_speech_threshold = no_speech_threshold
        self.models_dir = _get_models_directory()

        # Shared IPC queues
        self.input_queue = mp.Queue(maxsize=50)  # Larger queue for pool
        self.output_queue = mp.Queue(maxsize=50)

        # Worker processes
        self.workers: List[mp.Process] = []
        self.worker_ids: List[int] = []  # Track which worker ID each process slot has
        self.workers_ready = 0
        self.is_ready = False
        self.request_counter = 0

        # Shutdown and respawn control
        self._shutting_down = False
        self._respawn_in_progress = False
        self._last_respawn_time = 0.0
        self._respawn_cooldown = 5.0  # Minimum seconds between respawn attempts
        self._worker_id_counter = 0  # For generating unique worker IDs
        self._last_alive_count = num_workers  # Track to avoid warning spam

        logger.info(
            f"SubprocessTranscriber pool initialized: model={model_size}, device={device}, "
            f"fp16={use_fp16}, workers={num_workers}, beam_size={beam_size}"
        )

    def start(self) -> bool:
        """
        Start the transcription worker pool.

        Returns:
            True if all workers started successfully
        """
        if self.workers:
            logger.warning("Worker pool already running")
            return True

        try:
            logger.info(f"Starting transcription worker pool ({self.num_workers} workers)...")

            # Start all workers
            for i in range(self.num_workers):
                worker_id = self._worker_id_counter
                self._worker_id_counter += 1
                worker = mp.Process(
                    target=transcription_worker,
                    args=(
                        worker_id,
                        self.input_queue,
                        self.output_queue,
                        self.model_size,
                        self.device,
                        self.use_fp16,
                        self.models_dir,
                        self.beam_size,
                        self.temperature,
                        self.no_speech_threshold
                    ),
                    daemon=False  # Not daemon so we can clean shutdown
                )
                worker.start()
                self.workers.append(worker)
                self.worker_ids.append(worker_id)
                logger.info(f"Worker {worker_id} started (PID: {worker.pid}, device={self.device})")

            # Wait for all workers to signal READY (with timeout)
            timeout = 60.0  # Model loading can take time, especially for multiple workers
            start_time = time.time()
            workers_ready = 0

            while workers_ready < self.num_workers and (time.time() - start_time) < timeout:
                try:
                    result = self.output_queue.get(timeout=1.0)
                    if result.request_id == -1:
                        if result.success:
                            workers_ready += 1
                            logger.info(f"Worker {result.worker_id} ready ({workers_ready}/{self.num_workers})")
                        else:
                            logger.error(f"Worker {result.worker_id} failed to initialize: {result.error}")
                            # Continue, we may have enough workers
                except:
                    # No result yet, keep waiting
                    # Check if any worker died
                    for i, worker in enumerate(self.workers):
                        if not worker.is_alive():
                            logger.error(f"Worker {self.worker_ids[i]} died during initialization")

            if workers_ready == 0:
                logger.error("No workers initialized successfully")
                self.stop()
                return False

            self.workers_ready = workers_ready
            self.is_ready = True

            if workers_ready < self.num_workers:
                logger.warning(f"Only {workers_ready}/{self.num_workers} workers initialized")
            else:
                logger.info(f"All {workers_ready} workers ready to process requests")

            return True

        except Exception as e:
            logger.error(f"Failed to start worker pool: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return False

    def transcribe_async(self, audio: np.ndarray, sample_rate: int, voice_db=None) -> int:
        """
        Submit audio for transcription (non-blocking).

        Args:
            audio: Audio signal (mono, float32)
            sample_rate: Sample rate
            voice_db: Deprecated - ignored (kept for backward compatibility)

        Returns:
            Request ID to match with results
        """
        if not self.is_ready or not self.is_alive():
            raise RuntimeError("Worker pool not ready")

        # Create request
        self.request_counter += 1
        request = TranscriptionRequest(
            audio=audio.copy(),  # Copy to avoid shared memory issues
            sample_rate=sample_rate,
            request_id=self.request_counter
        )

        # Send to pool (any available worker will pick it up)
        self.input_queue.put(request)
        logger.debug(f"Submitted transcription request {request.request_id} to pool")

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
        """Stop all worker processes."""
        # Set shutdown flag FIRST to suppress warning spam
        self._shutting_down = True

        if not self.workers:
            return

        try:
            logger.info(f"Stopping {len(self.workers)} worker processes...")

            # Send shutdown signal to all workers
            for i in range(len(self.workers)):
                try:
                    self.input_queue.put(None, timeout=1.0)
                except:
                    pass

            # Wait for graceful shutdown
            for i, worker in enumerate(self.workers):
                worker_id = self.worker_ids[i] if i < len(self.worker_ids) else i
                if worker.is_alive():
                    worker.join(timeout=5.0)

                    # Force terminate if still alive
                    if worker.is_alive():
                        logger.warning(f"Worker {worker_id} didn't stop gracefully, terminating...")
                        worker.terminate()
                        worker.join(timeout=2.0)

                    # Force kill if still alive
                    if worker.is_alive():
                        logger.error(f"Worker {worker_id} still alive, killing...")
                        worker.kill()
                        worker.join(timeout=1.0)

            logger.info("All workers stopped")

            self.workers = []
            self.worker_ids = []
            self.workers_ready = 0
            self.is_ready = False

        except Exception as e:
            logger.error(f"Error stopping worker pool: {e}")

    def is_alive(self) -> bool:
        """Check if any workers are alive."""
        if self._shutting_down:
            # Don't spam warnings during shutdown
            return False

        if not self.workers:
            return False

        # Check how many workers are still alive
        alive_count = sum(1 for w in self.workers if w.is_alive())

        # Only log if count changed (prevents spam)
        if alive_count != self._last_alive_count:
            if alive_count == 0:
                logger.warning("All workers have died")
            elif alive_count < self._last_alive_count:
                logger.warning(f"Workers died: {alive_count}/{self.num_workers} workers alive (was {self._last_alive_count})")
            else:
                logger.info(f"Workers recovered: {alive_count}/{self.num_workers} workers alive (was {self._last_alive_count})")
            self._last_alive_count = alive_count

        return alive_count > 0

    def get_alive_count(self) -> int:
        """Get the number of workers currently alive."""
        if not self.workers:
            return 0
        return sum(1 for w in self.workers if w.is_alive())

    def respawn_dead_workers(self) -> int:
        """
        Respawn any dead workers.

        Returns:
            Number of workers successfully respawned
        """
        if self._shutting_down:
            return 0

        if self._respawn_in_progress:
            logger.debug("Respawn already in progress, skipping")
            return 0

        # Check cooldown to avoid respawn storms
        current_time = time.time()
        if current_time - self._last_respawn_time < self._respawn_cooldown:
            logger.debug(f"Respawn cooldown in effect ({self._respawn_cooldown}s)")
            return 0

        self._respawn_in_progress = True
        self._last_respawn_time = current_time

        try:
            respawned_count = 0

            # Find dead workers
            for i in range(len(self.workers)):
                if not self.workers[i].is_alive():
                    old_worker_id = self.worker_ids[i]
                    old_pid = self.workers[i].pid
                    logger.info(f"Worker {old_worker_id} (PID {old_pid}) died, respawning...")

                    # Create new worker with new ID
                    new_worker_id = self._worker_id_counter
                    self._worker_id_counter += 1

                    new_worker = mp.Process(
                        target=transcription_worker,
                        args=(
                            new_worker_id,
                            self.input_queue,
                            self.output_queue,
                            self.model_size,
                            self.device,
                            self.use_fp16,
                            self.models_dir,
                            self.beam_size,
                            self.temperature,
                            self.no_speech_threshold
                        ),
                        daemon=False
                    )
                    new_worker.start()

                    # Replace in lists
                    self.workers[i] = new_worker
                    self.worker_ids[i] = new_worker_id

                    logger.info(f"Respawned worker {new_worker_id} (PID: {new_worker.pid})")
                    respawned_count += 1

            # Wait for respawned workers to become ready (with short timeout)
            if respawned_count > 0:
                logger.info(f"Waiting for {respawned_count} respawned workers to initialize...")
                timeout = 30.0
                start_time = time.time()
                ready_count = 0

                while ready_count < respawned_count and (time.time() - start_time) < timeout:
                    try:
                        result = self.output_queue.get(timeout=1.0)
                        if result.request_id == -1:
                            if result.success:
                                ready_count += 1
                                logger.info(f"Respawned worker {result.worker_id} ready ({ready_count}/{respawned_count})")
                            else:
                                logger.error(f"Respawned worker {result.worker_id} failed to initialize: {result.error}")
                    except:
                        # Check if any respawned worker died
                        pass

                if ready_count > 0:
                    logger.info(f"Successfully respawned {ready_count} workers")
                else:
                    logger.error("Failed to respawn any workers")

            return respawned_count

        except Exception as e:
            logger.error(f"Error respawning workers: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return 0

        finally:
            self._respawn_in_progress = False

    def clear_input_queue(self) -> int:
        """
        Clear the input queue to recover from overload.

        Returns:
            Number of requests cleared
        """
        cleared = 0
        try:
            while not self.input_queue.empty():
                try:
                    self.input_queue.get_nowait()
                    cleared += 1
                except:
                    break
            if cleared > 0:
                logger.warning(f"Cleared {cleared} pending transcription requests from queue (overload recovery)")
        except Exception as e:
            logger.error(f"Error clearing input queue: {e}")
        return cleared

    def get_health_status(self) -> dict:
        """
        Get detailed health status of the worker pool.

        Returns:
            Dict with health information
        """
        alive_workers = []
        dead_workers = []

        for i, worker in enumerate(self.workers):
            worker_info = {
                'worker_id': self.worker_ids[i] if i < len(self.worker_ids) else i,
                'pid': worker.pid,
                'exitcode': worker.exitcode
            }
            if worker.is_alive():
                alive_workers.append(worker_info)
            else:
                dead_workers.append(worker_info)

        return {
            'alive_count': len(alive_workers),
            'dead_count': len(dead_workers),
            'total_workers': len(self.workers),
            'expected_workers': self.num_workers,
            'is_ready': self.is_ready,
            'shutting_down': self._shutting_down,
            'alive_workers': alive_workers,
            'dead_workers': dead_workers,
            'input_queue_size': self.input_queue.qsize() if hasattr(self.input_queue, 'qsize') else -1,
            'output_queue_size': self.output_queue.qsize() if hasattr(self.output_queue, 'qsize') else -1
        }

    @property
    def process(self):
        """Backward compatibility - return first worker process."""
        return self.workers[0] if self.workers else None

    def __del__(self):
        """Cleanup on deletion."""
        self.stop()
