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
    """Request to transcribe audio with voice identification"""
    audio: np.ndarray
    sample_rate: int
    request_id: int
    # Voice ID data (serializable)
    voice_db_embeddings: Optional[dict] = None  # {voice_id: (embedding, callsign, metadata)}


@dataclass
class TranscriptionResult:
    """Result of transcription with speaker identification"""
    request_id: int
    text: str
    success: bool
    error: Optional[str] = None
    # Speaker identification results
    speaker_labels: Optional[list] = None  # List of {start, end, label, voice_id}
    new_speakers: Optional[dict] = None  # {voice_id: (embedding, metadata)} for new speakers detected


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
            print(f"[SUBPROCESS] Failed to compute embedding for window: {e}")
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


def transcription_worker(input_queue: mp.Queue, output_queue: mp.Queue, model_size: str, compute_type: str):
    """
    Worker process that loads Whisper model and VoiceEmbedder, processes transcription requests with voice ID.

    This runs in a separate process to avoid Windows threading issues with ctranslate2 and resemblyzer.

    Args:
        input_queue: Queue for receiving TranscriptionRequest objects
        output_queue: Queue for sending TranscriptionResult objects
        model_size: Whisper model size (tiny, base, small, medium, large)
        compute_type: Compute type (float32, float16, int8)
    """
    # Import inside subprocess to avoid loading in main process
    try:
        from faster_whisper import WhisperModel
        from resemblyzer import VoiceEncoder
        import uuid

        # Load Whisper model
        print(f"[SUBPROCESS] Loading Whisper {model_size} model (compute_type={compute_type})...")
        model = WhisperModel(
            model_size,
            device="cpu",
            compute_type=compute_type,
            download_root=None
        )
        print(f"[SUBPROCESS] Whisper model loaded")

        # Load VoiceEmbedder model
        print(f"[SUBPROCESS] Loading Resemblyzer voice encoder...")
        voice_encoder = VoiceEncoder()
        print(f"[SUBPROCESS] Voice encoder loaded")

        # Signal that we're ready
        output_queue.put(TranscriptionResult(
            request_id=-1,
            text="READY",
            success=True
        ))

    except Exception as e:
        print(f"[SUBPROCESS] Failed to load models: {e}")
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

            # Process transcription and voice ID
            try:
                # Step 1: Speaker detection (if voice DB provided)
                speaker_labels = []
                new_speakers = {}

                if request.voice_db_embeddings is not None:
                    print(f"[SUBPROCESS] Running speaker detection...")
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

                        # Match speakers against voice DB
                        for seg in speaker_segments:
                            if seg['embedding'] is not None:
                                # Find matching voice
                                match = _find_matching_voice(seg['embedding'], request.voice_db_embeddings)

                                if match:
                                    voice_id, callsign, similarity = match
                                    label = callsign or f"Speaker {voice_id[:8]}"
                                    print(f"[SUBPROCESS] Matched voice at {seg['start']:.1f}-{seg['end']:.1f}s: {label} (similarity: {similarity:.2f})")
                                else:
                                    # New speaker - generate ID and store
                                    voice_id = str(uuid.uuid4())
                                    label = f"Speaker {voice_id[:8]}"
                                    new_speakers[voice_id] = {
                                        'embedding': seg['embedding'].tolist(),  # Convert to list for serialization
                                        'first_heard': time.time()
                                    }
                                    print(f"[SUBPROCESS] New speaker at {seg['start']:.1f}-{seg['end']:.1f}s: {label}")

                                speaker_labels.append({
                                    'start': seg['start'],
                                    'end': seg['end'],
                                    'label': label,
                                    'voice_id': voice_id
                                })

                        if speaker_labels:
                            unique_speakers = len(set(s['voice_id'] for s in speaker_labels))
                            unique_labels = ', '.join(set(s['label'] for s in speaker_labels))
                            print(f"[SUBPROCESS] Detected {unique_speakers} speakers: {unique_labels}")

                    except Exception as e:
                        print(f"[SUBPROCESS] Speaker detection failed: {e}")
                        # Continue with transcription even if speaker detection fails

                # Step 2: Transcribe
                print(f"[SUBPROCESS] Transcribing...")
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

                # Add speaker labels to text if detected
                if speaker_labels:
                    unique_labels = list(set(s['label'] for s in speaker_labels))
                    if len(unique_labels) == 1:
                        result_text = f"[{unique_labels[0]}] {result_text}"
                    else:
                        result_text = f"[{'/'.join(unique_labels)}] {result_text}"

                print(f"[SUBPROCESS] Transcription complete: {result_text}")

                # Send result with speaker info
                output_queue.put(TranscriptionResult(
                    request_id=request.request_id,
                    text=result_text,
                    success=True,
                    speaker_labels=speaker_labels if speaker_labels else None,
                    new_speakers=new_speakers if new_speakers else None
                ))

            except Exception as e:
                print(f"[SUBPROCESS] Transcription failed: {e}")
                import traceback
                traceback.print_exc()
                output_queue.put(TranscriptionResult(
                    request_id=request.request_id,
                    text="",
                    success=False,
                    error=str(e),
                    speaker_labels=None,
                    new_speakers=None
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
        if not self.is_ready or not self.process or not self.process.is_alive():
            raise RuntimeError("Subprocess not ready")

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

        # Send to subprocess
        self.input_queue.put(request)
        logger.debug(f"Submitted transcription request {request.request_id}")

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
            for voice_id in voice_db.list_operators():
                operator = voice_db.get_operator(voice_id)
                if operator and operator.embedding is not None:
                    # Convert embedding to list for serialization
                    embedding_list = operator.embedding.tolist() if hasattr(operator.embedding, 'tolist') else list(operator.embedding)
                    callsign = operator.callsign if hasattr(operator, 'callsign') else None
                    metadata = operator.metadata if hasattr(operator, 'metadata') else {}

                    serialized[voice_id] = (embedding_list, callsign, metadata)

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
