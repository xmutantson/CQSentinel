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
from typing import Optional, Tuple, List
from dataclasses import dataclass
import time

logger = logging.getLogger(__name__)


@dataclass
class TranscriptionRequest:
    """Request to transcribe audio with voice identification"""
    audio: np.ndarray
    sample_rate: int
    request_id: int
    worker_id: int = -1  # Assigned by pool
    # Voice ID data (serializable)
    voice_db_embeddings: Optional[dict] = None  # {voice_id: (embedding, callsign, metadata)}


@dataclass
class TranscriptionResult:
    """Result of transcription with speaker identification"""
    request_id: int
    text: str
    success: bool
    worker_id: int = -1
    error: Optional[str] = None
    # Speaker identification results
    speaker_labels: Optional[list] = None  # List of {start, end, label, voice_id}
    new_speakers: Optional[dict] = None  # {voice_id: (embedding, metadata)} for new speakers detected


def _get_models_directory():
    """Get the models directory for the current environment."""
    if getattr(sys, 'frozen', False):
        # PyInstaller frozen executable
        base_dir = os.path.dirname(sys.executable)
        return os.path.join(base_dir, 'models')
    else:
        # Development mode
        return os.path.join(os.path.dirname(__file__), '..', '..', 'models')


def _detect_speaker_changes(voice_encoder, audio: np.ndarray, sample_rate: int,
                           window_duration: float = 2.5, stride: float = 1.0,
                           similarity_threshold: float = 0.75) -> list:
    """
    Detect speaker changes in audio using sliding window embeddings.

    Args:
        voice_encoder: Resemblyzer VoiceEncoder instance
        audio: Audio signal (mono, float32)
        sample_rate: Sample rate
        window_duration: Window duration in seconds
        stride: Stride in seconds
        similarity_threshold: Similarity threshold for same speaker

    Returns:
        List of speaker segments with embeddings
    """
    segments = []
    window_samples = int(window_duration * sample_rate)
    stride_samples = int(stride * sample_rate)

    current_speaker_idx = 0
    prev_embedding = None
    current_segment_start = 0.0

    for start_sample in range(0, len(audio) - window_samples + 1, stride_samples):
        end_sample = start_sample + window_samples
        window = audio[start_sample:end_sample]

        # Compute embedding for this window
        # Resemblyzer expects 16kHz, resample if needed
        if sample_rate != 16000:
            # Simple resampling
            from scipy import signal
            window = signal.resample(window, int(len(window) * 16000 / sample_rate))

        try:
            embedding = voice_encoder.embed_utterance(window)

            # Check if this is a different speaker
            is_new_speaker = False
            if prev_embedding is not None:
                from numpy import dot
                from numpy.linalg import norm
                similarity = dot(embedding, prev_embedding) / (norm(embedding) * norm(prev_embedding))
                if similarity < similarity_threshold:
                    is_new_speaker = True

            if is_new_speaker:
                # End current segment
                segment_end = start_sample / sample_rate
                segments.append({
                    'start': current_segment_start,
                    'end': segment_end,
                    'speaker_idx': current_speaker_idx,
                    'embedding': prev_embedding
                })

                # Start new segment
                current_speaker_idx += 1
                current_segment_start = segment_end

            prev_embedding = embedding

        except Exception as e:
            # Skip this window if embedding fails
            if sys.stdout is not None:
                try:
                    print(f"[WORKER] Failed to compute embedding for window: {e}")
                except Exception:
                    pass
            continue

    # Add final segment
    if prev_embedding is not None:
        segments.append({
            'start': current_segment_start,
            'end': len(audio) / sample_rate,
            'speaker_idx': current_speaker_idx,
            'embedding': prev_embedding
        })

    return segments


def _find_matching_voice(embedding: np.ndarray, voice_db_embeddings: dict,
                         similarity_threshold: float = 0.75) -> Optional[Tuple[str, str, float]]:
    """
    Find matching voice in database.

    Args:
        embedding: Voice embedding to match
        voice_db_embeddings: Dict of {voice_id: (embedding_list, callsign, metadata)}
        similarity_threshold: Minimum similarity threshold

    Returns:
        (voice_id, callsign, similarity) if match found, None otherwise
    """
    from numpy import dot, array
    from numpy.linalg import norm

    best_match = None
    best_similarity = similarity_threshold

    for voice_id, voice_data in voice_db_embeddings.items():
        # voice_data is (embedding_list, callsign, metadata)
        stored_embedding = array(voice_data[0])  # Convert list back to numpy array
        callsign = voice_data[1]

        # Compute cosine similarity
        similarity = dot(embedding, stored_embedding) / (norm(embedding) * norm(stored_embedding))

        if similarity > best_similarity:
            best_similarity = similarity
            best_match = (voice_id, callsign, similarity)

    return best_match


def transcription_worker(worker_id: int, input_queue: mp.Queue, output_queue: mp.Queue,
                         model_size: str, compute_type: str, models_dir: str):
    """
    Worker process that loads Whisper model and VoiceEmbedder, processes transcription requests with voice ID.

    This runs in a separate process to avoid Windows threading issues with ctranslate2 and resemblyzer.

    Args:
        worker_id: Unique identifier for this worker
        input_queue: Queue for receiving TranscriptionRequest objects
        output_queue: Queue for sending TranscriptionResult objects
        model_size: Whisper model size (tiny, base, small, medium, large)
        compute_type: Compute type (float32, float16, int8)
        models_dir: Directory where models are stored (for offline operation)
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

        from faster_whisper import WhisperModel
        from resemblyzer import VoiceEncoder
        import uuid

        # Load Whisper model - use SAME settings as model_downloader_dialog.py
        log(f"Loading Whisper {model_size} model (compute_type={compute_type})...")
        log(f"Models directory: {models_dir}")
        log(f"HF_HOME: {os.environ['HF_HOME']}")

        # CRITICAL: Use download_root=None to match how the model was downloaded
        # The HF_HOME environment variable will direct it to the correct cache
        # Using local_files_only=True prevents any network access
        log(f"Creating WhisperModel with cpu_threads=1, num_workers=1...")
        model = WhisperModel(
            model_size,
            device="cpu",
            compute_type=compute_type,
            download_root=None,  # Use default (respects HF_HOME env var)
            local_files_only=True,  # CRITICAL: Prevent any network access
            cpu_threads=1,  # CRITICAL: Single-threaded for Windows stability
            num_workers=1  # CRITICAL: Single worker for Windows stability
        )
        log(f"Whisper model loaded (offline mode, single-threaded)")

        # DIAGNOSTIC: Test model with short silence to verify it actually works
        log(f"Testing model with 1-second silence...")
        test_audio = np.zeros(16000, dtype=np.float32)  # 1 second of silence
        try:
            test_segments, test_info = model.transcribe(test_audio, language="en", beam_size=1)
            test_result = list(test_segments)  # Force generator evaluation
            log(f"Model test PASSED: transcribed {len(test_result)} segments from silence")
        except Exception as test_e:
            log(f"Model test FAILED: {test_e}")
            import traceback
            if sys.stderr is not None:
                try:
                    traceback.print_exc()
                except Exception:
                    pass
            raise RuntimeError(f"Model failed basic transcription test: {test_e}")

        # Load VoiceEmbedder model
        log(f"Loading Resemblyzer voice encoder...")
        voice_encoder = VoiceEncoder()
        log(f"Voice encoder loaded")

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

            # Process transcription and voice ID
            try:
                # Step 1: Speaker detection (if voice DB provided)
                speaker_labels = []
                new_speakers = {}

                if request.voice_db_embeddings is not None:
                    log(f"Running speaker detection...")
                    speaker_start = time.time()
                    try:
                        # Detect speaker changes using sliding window
                        speaker_segments = _detect_speaker_changes(
                            voice_encoder,
                            request.audio,
                            request.sample_rate,
                            window_duration=2.5,
                            stride=1.0,
                            similarity_threshold=0.75
                        )
                        log(f"Speaker detection took {time.time() - speaker_start:.2f}s")

                        # Match speakers against voice DB
                        match_start = time.time()
                        for seg in speaker_segments:
                            if seg['embedding'] is not None:
                                # Find matching voice
                                match = _find_matching_voice(seg['embedding'], request.voice_db_embeddings)

                                if match:
                                    voice_id, callsign, similarity = match
                                    label = callsign or f"Speaker {voice_id[:8]}"
                                    log(f"Matched voice at {seg['start']:.1f}-{seg['end']:.1f}s: {label} (similarity: {similarity:.2f})")
                                else:
                                    # New speaker - generate ID and store
                                    voice_id = str(uuid.uuid4())
                                    label = f"Speaker {voice_id[:8]}"
                                    new_speakers[voice_id] = {
                                        'embedding': seg['embedding'].tolist(),  # Convert to list for serialization
                                        'first_heard': time.time()
                                    }
                                    log(f"New speaker at {seg['start']:.1f}-{seg['end']:.1f}s: {label}")

                                speaker_labels.append({
                                    'start': seg['start'],
                                    'end': seg['end'],
                                    'label': label,
                                    'voice_id': voice_id
                                })

                        if speaker_labels:
                            unique_speakers = len(set(s['voice_id'] for s in speaker_labels))
                            unique_labels = ', '.join(set(s['label'] for s in speaker_labels))
                            log(f"Detected {unique_speakers} speakers: {unique_labels}")
                            log(f"Voice matching took {time.time() - match_start:.2f}s")

                    except Exception as e:
                        log(f"Speaker detection failed: {e}")
                        # Continue with transcription even if speaker detection fails

                # Step 2: Transcribe
                log(f"Transcribing...")
                log(f"About to call model.transcribe() with audio shape={request.audio.shape}")

                # DIAGNOSTIC: Verify model is still valid
                log(f"Model object type: {type(model)}")
                log(f"Audio memory flags: C_CONTIGUOUS={request.audio.flags['C_CONTIGUOUS']}, OWNDATA={request.audio.flags['OWNDATA']}")
                safe_flush()

                transcribe_start = time.time()
                try:
                    # DIAGNOSTIC: Force immediate evaluation by converting to list
                    # This avoids generator issues and gives immediate crash point
                    log(f"Calling model.transcribe()...")
                    safe_flush()

                    segments_gen, info = model.transcribe(
                        request.audio,
                        language="en",
                        beam_size=5,
                        temperature=0.0,  # Disable fallback (Windows stability)
                        vad_filter=False  # VAD already applied
                    )

                    log(f"model.transcribe() returned generator in {time.time() - transcribe_start:.2f}s")
                    log(f"Info: language={info.language}, language_probability={info.language_probability:.2f}")
                    safe_flush()

                    # DIAGNOSTIC: Consume generator with per-segment logging
                    log(f"Consuming transcription segments...")
                    segment_start = time.time()
                    texts = []
                    segment_count = 0
                    for seg in segments_gen:
                        segment_count += 1
                        log(f"Segment {segment_count}: [{seg.start:.2f}-{seg.end:.2f}] '{seg.text.strip()}'")
                        if seg.text.strip():
                            texts.append(seg.text.strip())
                        safe_flush()

                    log(f"Segment iteration complete: {segment_count} segments in {time.time() - segment_start:.2f}s")
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

                # Add speaker labels to text if detected
                if speaker_labels:
                    unique_labels = list(set(s['label'] for s in speaker_labels))
                    if len(unique_labels) == 1:
                        result_text = f"[{unique_labels[0]}] {result_text}"
                    else:
                        result_text = f"[{'/'.join(unique_labels)}] {result_text}"

                total_time = time.time() - processing_start
                log(f"Transcription complete in {total_time:.2f}s: {result_text}")

                # Send result with speaker info
                output_queue.put(TranscriptionResult(
                    request_id=request.request_id,
                    text=result_text,
                    success=True,
                    worker_id=worker_id,
                    speaker_labels=speaker_labels if speaker_labels else None,
                    new_speakers=new_speakers if new_speakers else None
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
                    error=str(e),
                    speaker_labels=None,
                    new_speakers=None
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

    log(f"Worker shutting down")


class SubprocessTranscriber:
    """
    Manages a pool of subprocesses for transcription to handle concurrent requests.

    The subprocess pool loads the Whisper model in each worker and processes
    transcription requests via queues.
    """

    def __init__(self, model_size: str = "small", compute_type: str = "float32", num_workers: int = 3):
        """
        Initialize subprocess transcriber pool.

        Args:
            model_size: Whisper model size
            compute_type: Compute type (float32 recommended for Windows)
            num_workers: Number of worker processes to spawn (default: 3)
        """
        self.model_size = model_size
        self.compute_type = compute_type
        self.num_workers = num_workers
        self.models_dir = _get_models_directory()

        # Shared IPC queues
        self.input_queue = mp.Queue(maxsize=50)  # Larger queue for pool
        self.output_queue = mp.Queue(maxsize=50)

        # Worker processes
        self.workers: List[mp.Process] = []
        self.workers_ready = 0
        self.is_ready = False
        self.request_counter = 0

        logger.info(f"SubprocessTranscriber pool initialized: model={model_size}, compute_type={compute_type}, workers={num_workers}")

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
                worker = mp.Process(
                    target=transcription_worker,
                    args=(i, self.input_queue, self.output_queue, self.model_size,
                          self.compute_type, self.models_dir),
                    daemon=False  # Not daemon so we can clean shutdown
                )
                worker.start()
                self.workers.append(worker)
                logger.info(f"Worker {i} started (PID: {worker.pid})")

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
                            logger.error(f"Worker {i} died during initialization")

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
        Submit audio for transcription with voice identification (non-blocking).

        Args:
            audio: Audio signal (mono, float32)
            sample_rate: Sample rate
            voice_db: Optional VoiceDatabase instance for speaker identification

        Returns:
            Request ID to match with results
        """
        if not self.is_ready or not self.is_alive():
            raise RuntimeError("Worker pool not ready")

        # Serialize voice DB for subprocess
        voice_db_embeddings = None
        if voice_db is not None:
            voice_db_embeddings = self._serialize_voice_db(voice_db)

        # Create request
        self.request_counter += 1
        request = TranscriptionRequest(
            audio=audio.copy(),  # Copy to avoid shared memory issues
            sample_rate=sample_rate,
            request_id=self.request_counter,
            voice_db_embeddings=voice_db_embeddings
        )

        # Send to pool (any available worker will pick it up)
        self.input_queue.put(request)
        logger.debug(f"Submitted transcription request {request.request_id} to pool")

        return request.request_id

    def _serialize_voice_db(self, voice_db) -> dict:
        """
        Serialize voice database for passing to subprocess.

        Args:
            voice_db: VoiceDatabase instance

        Returns:
            Dict of {voice_id: (embedding_list, callsign, metadata)}
        """
        serialized = {}
        try:
            # Get all operators from voice DB
            for operator in voice_db.get_all_operators():
                if operator and operator.embedding is not None:
                    # Convert embedding to list for serialization
                    embedding_list = operator.embedding.tolist() if hasattr(operator.embedding, 'tolist') else list(operator.embedding)
                    callsign = operator.callsign if hasattr(operator, 'callsign') else None
                    metadata = {}
                    if hasattr(operator, 'first_heard'):
                        metadata['first_heard'] = operator.first_heard.isoformat() if operator.first_heard else None
                    if hasattr(operator, 'last_heard'):
                        metadata['last_heard'] = operator.last_heard.isoformat() if operator.last_heard else None

                    serialized[operator.voice_id] = (embedding_list, callsign, metadata)

            logger.debug(f"Serialized {len(serialized)} voices for subprocess")
        except Exception as e:
            logger.error(f"Failed to serialize voice DB: {e}")

        return serialized if serialized else None

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
                if worker.is_alive():
                    worker.join(timeout=5.0)

                    # Force terminate if still alive
                    if worker.is_alive():
                        logger.warning(f"Worker {i} didn't stop gracefully, terminating...")
                        worker.terminate()
                        worker.join(timeout=2.0)

                    # Force kill if still alive
                    if worker.is_alive():
                        logger.error(f"Worker {i} still alive, killing...")
                        worker.kill()
                        worker.join(timeout=1.0)

            logger.info("All workers stopped")

            self.workers = []
            self.workers_ready = 0
            self.is_ready = False

        except Exception as e:
            logger.error(f"Error stopping worker pool: {e}")

    def is_alive(self) -> bool:
        """Check if any workers are alive."""
        if not self.workers:
            return False

        # Check how many workers are still alive
        alive_count = sum(1 for w in self.workers if w.is_alive())

        if alive_count == 0:
            logger.warning("All workers have died")
            return False

        if alive_count < self.workers_ready:
            logger.warning(f"Some workers died: {alive_count}/{self.workers_ready} alive")

        return alive_count > 0

    @property
    def process(self):
        """Backward compatibility - return first worker process."""
        return self.workers[0] if self.workers else None

    def __del__(self):
        """Cleanup on deletion."""
        self.stop()
