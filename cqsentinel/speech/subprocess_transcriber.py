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


def _wav_to_mel_spectrogram_torchaudio(wav, sampling_rate=16000,
                                        mel_window_length=25, mel_window_step=10,
                                        mel_n_channels=40):
    """
    Mel spectrogram using torchaudio (PyTorch native - NO NUMBA).

    This replaces librosa.feature.melspectrogram() which uses numba and crashes
    on Windows subprocesses. torchaudio is already a dependency and uses pure
    PyTorch operations.

    Parameters match Resemblyzer's defaults:
    - sampling_rate: 16000 Hz
    - mel_window_length: 25 ms
    - mel_window_step: 10 ms (hop)
    - mel_n_channels: 40 mel bands
    """
    import torch
    import torchaudio.transforms as T

    # Convert to torch tensor if needed
    if isinstance(wav, np.ndarray):
        wav_tensor = torch.from_numpy(wav).float()
    else:
        wav_tensor = wav

    # Ensure 1D
    if wav_tensor.dim() > 1:
        wav_tensor = wav_tensor.squeeze()

    # Calculate parameters in samples
    n_fft = int(sampling_rate * mel_window_length / 1000)
    hop_length = int(sampling_rate * mel_window_step / 1000)

    # Create MelSpectrogram transform (no numba involved!)
    mel_transform = T.MelSpectrogram(
        sample_rate=sampling_rate,
        n_fft=n_fft,
        hop_length=hop_length,
        n_mels=mel_n_channels,
        norm='slaney',  # Match librosa's default normalization
        mel_scale='htk'  # Match librosa's mel scale
    )

    # Compute mel spectrogram
    mel_spec = mel_transform(wav_tensor)

    # Convert to log scale (like librosa)
    mel_spec = torch.log10(torch.clamp(mel_spec, min=1e-10))

    # Convert back to numpy and transpose to match librosa output (time x freq)
    return mel_spec.numpy().T.astype(np.float32)


def _detect_speaker_changes(voice_encoder, audio: np.ndarray, sample_rate: int,
                           window_duration: float = 2.5, stride: float = 1.0,
                           similarity_threshold: float = 0.85) -> list:
    """
    Detect speaker changes in audio using sliding window embeddings.

    Args:
        voice_encoder: Resemblyzer VoiceEncoder instance
        audio: Audio signal (mono, float32)
        sample_rate: Sample rate
        window_duration: Window duration in seconds
        stride: Stride in seconds
        similarity_threshold: Similarity threshold for same speaker (0.85 for SSB audio)

    Returns:
        List of speaker segments with embeddings
    """
    segments = []
    window_samples = int(window_duration * sample_rate)
    stride_samples = int(stride * sample_rate)

    # Validate audio before processing
    if len(audio) < window_samples:
        # Audio too short for speaker detection
        return segments

    # Check for problematic audio (silence, extreme values)
    audio_rms = np.sqrt(np.mean(audio ** 2))
    if audio_rms < 0.001:  # Nearly silent
        return segments

    # CRITICAL: Preprocess audio using scipy (NOT librosa - it uses numba which crashes)
    # Resample to 16kHz (Resemblyzer's expected rate) and normalize volume
    preprocessed_audio = audio
    try:
        from scipy import signal as scipy_signal

        # Resample to 16kHz if needed
        if sample_rate != 16000:
            num_samples = int(len(audio) * 16000 / sample_rate)
            preprocessed_audio = scipy_signal.resample(audio, num_samples)
            if sys.stdout is not None:
                try:
                    print(f"[WORKER] Resampled audio (scipy): {sample_rate}Hz -> 16000Hz ({len(audio)} -> {len(preprocessed_audio)} samples)")
                except Exception:
                    pass
            sample_rate = 16000
            window_samples = int(window_duration * sample_rate)
            stride_samples = int(stride * sample_rate)

        # Normalize volume (simple RMS normalization to -23 dBFS)
        # -23 dBFS matches Resemblyzer's default and provides good speech clarity
        # This AMPLIFIES quiet/weak signals, not reduces them
        rms = np.sqrt(np.mean(preprocessed_audio ** 2))
        if rms > 1e-10:
            target_rms = 10 ** (-23 / 20.0)  # -23 dBFS (Resemblyzer default)
            preprocessed_audio = preprocessed_audio * (target_rms / rms)
            preprocessed_audio = np.clip(preprocessed_audio, -1.0, 1.0)

        if sys.stdout is not None:
            try:
                print(f"[WORKER] Preprocessed audio (scipy): normalized to -23 dBFS")
            except Exception:
                pass

    except Exception as e:
        if sys.stdout is not None:
            try:
                print(f"[WORKER] scipy preprocessing failed: {e}, using raw audio")
            except Exception:
                pass

    current_speaker_idx = 0
    prev_embedding = None
    current_segment_start = 0.0
    failed_windows = 0
    max_failed_windows = 3  # Give up if too many failures

    for start_sample in range(0, len(preprocessed_audio) - window_samples + 1, stride_samples):
        end_sample = start_sample + window_samples
        window = preprocessed_audio[start_sample:end_sample]

        # After preprocess_wav, audio is already at 16kHz, but double-check
        if sample_rate != 16000:
            # Simple resampling
            from scipy import signal
            window = signal.resample(window, int(len(window) * 16000 / sample_rate))

        try:
            # Validate window before passing to Resemblyzer
            if not np.isfinite(window).all():
                failed_windows += 1
                continue

            # Ensure window is contiguous float32
            window = np.ascontiguousarray(window, dtype=np.float32)

            # Check window has enough energy (avoid silent windows that crash encoder)
            window_rms = np.sqrt(np.mean(window ** 2))
            if window_rms < 0.0001:
                continue  # Skip silent windows

            embedding = voice_encoder.embed_utterance(window)

            # Validate embedding
            if embedding is None or not np.isfinite(embedding).all():
                failed_windows += 1
                if failed_windows >= max_failed_windows:
                    if sys.stdout is not None:
                        try:
                            print(f"[WORKER] Too many embedding failures, aborting speaker detection")
                        except Exception:
                            pass
                    break
                continue

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
            failed_windows = 0  # Reset failure counter on success

        except Exception as e:
            # Skip this window if embedding fails
            failed_windows += 1
            if sys.stdout is not None:
                try:
                    print(f"[WORKER] Failed to compute embedding for window: {e}")
                except Exception:
                    pass

            if failed_windows >= max_failed_windows:
                if sys.stdout is not None:
                    try:
                        print(f"[WORKER] Too many embedding failures ({failed_windows}), aborting speaker detection")
                    except Exception:
                        pass
                break
            continue

    # Add final segment
    if prev_embedding is not None:
        segments.append({
            'start': current_segment_start,
            'end': len(preprocessed_audio) / sample_rate,
            'speaker_idx': current_speaker_idx,
            'embedding': prev_embedding
        })

    return segments


def _find_matching_voice(embedding: np.ndarray, voice_db_embeddings: dict,
                         similarity_threshold: float = 0.85) -> Optional[Tuple[str, str, float]]:
    """
    Find matching voice in database.

    Args:
        embedding: Voice embedding to match
        voice_db_embeddings: Dict of {voice_id: (embedding_list, callsign, metadata)}
        similarity_threshold: Minimum similarity threshold (0.85 for SSB audio)

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

    # CRITICAL: Disable numba JIT to prevent crashes on Windows subprocess
    # librosa uses numba internally, and numba JIT crashes on Windows PyInstaller builds
    # We'll monkey-patch Resemblyzer to use torchaudio instead, so librosa won't be called
    os.environ['NUMBA_DISABLE_JIT'] = '1'
    os.environ['NUMBA_THREADING_LAYER'] = 'safe'
    os.environ['NUMBA_NUM_THREADS'] = '1'
    log(f"Numba JIT disabled (NUMBA_DISABLE_JIT={os.environ.get('NUMBA_DISABLE_JIT')})")

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
        from resemblyzer import VoiceEncoder
        import uuid

        # CRITICAL: Monkey-patch Resemblyzer to use torchaudio instead of librosa
        # This avoids librosa's numba dependency that crashes on Windows subprocesses
        # torchaudio is already a dependency and uses pure PyTorch (no numba)
        try:
            import resemblyzer.audio
            original_mel = resemblyzer.audio.wav_to_mel_spectrogram
            resemblyzer.audio.wav_to_mel_spectrogram = _wav_to_mel_spectrogram_torchaudio
            log(f"Patched Resemblyzer to use torchaudio MelSpectrogram (avoiding numba/librosa)")
        except Exception as patch_err:
            log(f"Warning: Could not patch Resemblyzer: {patch_err}")

        # Load Whisper model using openai-whisper (PyTorch backend - more stable)
        log(f"Loading Whisper {model_size} model (using openai-whisper for stability)...")
        log(f"Models directory: {models_dir}")
        log(f"TORCH_HOME: {os.environ['TORCH_HOME']}")

        # openai-whisper downloads models to ~/.cache/whisper by default
        # Set download_root to our models directory
        whisper_cache = os.path.join(models_dir, 'whisper')
        os.makedirs(whisper_cache, exist_ok=True)
        log(f"Whisper cache directory: {whisper_cache}")

        model = whisper.load_model(
            model_size,
            device="cpu",
            download_root=whisper_cache
        )
        log(f"Whisper model loaded (openai-whisper, PyTorch backend)")

        # Test model with silence to verify it works
        log(f"Testing model with 1-second silence...")
        test_audio = np.zeros(16000, dtype=np.float32)
        try:
            # openai-whisper expects audio as float32 numpy array at 16kHz
            test_result = model.transcribe(test_audio, language="en", fp16=False)
            log(f"Model test PASSED: transcribed silence successfully")
        except Exception as test_e:
            log(f"Model test FAILED: {test_e}")
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
                # Step 1: Speaker detection (ALWAYS run to build voice fingerprints)
                speaker_labels = []
                new_speakers = {}

                # Always run speaker detection to build voice database
                # Even if DB is empty, we need to fingerprint new speakers
                num_known_voices = len(request.voice_db_embeddings) if request.voice_db_embeddings else 0
                log(f"Running speaker detection (known voices: {num_known_voices})...")
                speaker_start = time.time()
                try:
                    # Detect speaker changes using sliding window
                    speaker_segments = _detect_speaker_changes(
                        voice_encoder,
                        request.audio,
                        request.sample_rate,
                        window_duration=2.5,
                        stride=1.0,
                        similarity_threshold=0.85  # Higher threshold for SSB audio (limited bandwidth)
                    )
                    log(f"Speaker detection took {time.time() - speaker_start:.2f}s, found {len(speaker_segments)} segments")

                    # Match speakers against voice DB (or create new entries if DB is empty)
                    match_start = time.time()
                    for seg in speaker_segments:
                        if seg['embedding'] is not None:
                            # Try to find matching voice in DB
                            match = None
                            if request.voice_db_embeddings and len(request.voice_db_embeddings) > 0:
                                match = _find_matching_voice(seg['embedding'], request.voice_db_embeddings)

                            # Also check against new speakers discovered in this request
                            # This handles the case where same speaker appears in multiple segments
                            if not match and new_speakers:
                                local_match = _find_matching_voice(seg['embedding'], new_speakers, similarity_threshold=0.85)
                                if local_match:
                                    voice_id, _, similarity = local_match
                                    label = f"Speaker {voice_id[:8]}"
                                    log(f"Matched to local speaker at {seg['start']:.1f}-{seg['end']:.1f}s: {label} (similarity: {similarity:.2f})")
                                    match = (voice_id, None, similarity)  # Treat as match

                            if match:
                                voice_id, callsign, similarity = match
                                label = callsign or f"Speaker {voice_id[:8]}"
                                log(f"Matched voice at {seg['start']:.1f}-{seg['end']:.1f}s: {label} (similarity: {similarity:.2f})")
                            else:
                                # New speaker - generate ID and store fingerprint
                                # Store in tuple format (embedding_list, callsign, metadata) to match voice_db_embeddings
                                voice_id = str(uuid.uuid4())
                                label = f"Speaker {voice_id[:8]}"
                                new_speakers[voice_id] = (
                                    seg['embedding'].tolist(),  # Convert to list for serialization
                                    None,  # No callsign yet
                                    {'first_heard': time.time()}
                                )
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
                    elif len(speaker_segments) == 0:
                        log(f"No speaker segments detected (audio too short or silent)")

                except Exception as e:
                    log(f"Speaker detection failed: {e}")
                    import traceback
                    if sys.stderr is not None:
                        try:
                            traceback.print_exc()
                        except Exception:
                            pass
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
                    log(f"Calling model.transcribe()...")
                    safe_flush()

                    # openai-whisper API (returns dict with 'text' and 'segments')
                    result = model.transcribe(
                        request.audio,
                        language="en",
                        fp16=False,  # Use float32 on CPU
                        verbose=False  # Don't print progress
                    )

                    log(f"model.transcribe() completed in {time.time() - transcribe_start:.2f}s")
                    log(f"Detected language: {result.get('language', 'unknown')}")
                    safe_flush()

                    # Extract text from result
                    texts = []
                    if 'segments' in result:
                        segment_count = len(result['segments'])
                        log(f"Processing {segment_count} segments...")
                        for i, seg in enumerate(result['segments']):
                            seg_text = seg.get('text', '').strip()
                            log(f"Segment {i+1}: [{seg.get('start', 0):.2f}-{seg.get('end', 0):.2f}] '{seg_text}'")
                            if seg_text:
                                texts.append(seg_text)
                            safe_flush()
                    else:
                        # Fallback to full text if no segments
                        full_text = result.get('text', '').strip()
                        if full_text:
                            texts.append(full_text)

                    log(f"Transcription complete: {len(texts)} text segments")
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
                worker_id = self._worker_id_counter
                self._worker_id_counter += 1
                worker = mp.Process(
                    target=transcription_worker,
                    args=(worker_id, self.input_queue, self.output_queue, self.model_size,
                          self.compute_type, self.models_dir),
                    daemon=False  # Not daemon so we can clean shutdown
                )
                worker.start()
                self.workers.append(worker)
                self.worker_ids.append(worker_id)
                logger.info(f"Worker {worker_id} started (PID: {worker.pid})")

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

        # Return empty dict (not None) to enable speaker detection even with no existing voices
        return serialized

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
                        args=(new_worker_id, self.input_queue, self.output_queue, self.model_size,
                              self.compute_type, self.models_dir),
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
