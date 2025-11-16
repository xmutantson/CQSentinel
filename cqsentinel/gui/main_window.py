"""
Main Window for CQSentinel GUI

Provides the primary user interface with:
- Band selection
- Frequency display
- Audio level monitoring
- Radio control panel
- Status display
"""

import sys
import logging
import logging.handlers
import queue
import threading
import time
import numpy as np
from typing import Optional
from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QComboBox, QCheckBox,
    QGroupBox, QTextEdit, QProgressBar, QStatusBar,
    QMenuBar, QMenu, QMessageBox, QAction, QScrollArea
)
from PyQt5.QtCore import Qt, QTimer, pyqtSignal, QThread, QObject
from PyQt5.QtGui import QFont

from cqsentinel.config import get_config, get_config_manager
from cqsentinel.radio import HamlibController, RadioConnectionError, RigctldManager, find_serial_port, SSBAutoTuner
from cqsentinel.audio import (
    AudioCapture, list_audio_devices, list_audio_output_devices,
    AudioBroadcaster, AudioMonitor, AudioLevelMeter,
    AudioStage, AudioChunk, AudioBuffer
)
from cqsentinel.audio.pipeline import AudioPipeline
from cqsentinel.audio.denoiser import AudioDenoiser
from cqsentinel.audio.vad import VoiceActivityDetector
from cqsentinel.speech.transcription import SpeechTranscriber
from cqsentinel.speech.subprocess_transcriber import SubprocessTranscriber
from cqsentinel.contest import CallsignExtractor, BehaviorAnalyzer
from cqsentinel.bandmap.station import BandMapState
from cqsentinel.bandmap.widget import BandMapWidget
from cqsentinel.bandmap.detail_panel import StationDetailPanel
from cqsentinel.gui.settings_dialog import SettingsDialog
from cqsentinel.scanner.profiles import BAND_PROFILES
from cqsentinel.scanner.engine import BandScanner, ScanProgress

logger = logging.getLogger(__name__)


class ScanThread(QThread):
    """Background thread for band scanning (Phase 1)"""
    log_signal = pyqtSignal(str)
    freq_update_signal = pyqtSignal(int)  # Emit frequency in Hz for display update

    def __init__(self, radio, bands, step_hz=1000, dwell_sec=2.0):
        super().__init__()
        self.radio = radio
        self.bands = bands
        self.step_hz = step_hz
        self.dwell_sec = dwell_sec
        self.running = True

    def run(self):
        """Scan loop"""
        import time
        import traceback
        try:
            for band_name in self.bands:
                if not self.running:
                    break

                if band_name not in BAND_PROFILES:
                    try:
                        self.log_signal.emit(f"Unknown band: {band_name}")
                    except Exception as e:
                        logger.error(f"Signal emit failed: {e}")
                    continue

                profile = BAND_PROFILES[band_name]
                try:
                    self.log_signal.emit(f"Scanning {profile.name}: {profile.freq_start/1e6:.3f}-{profile.freq_end/1e6:.3f} MHz")
                except Exception as e:
                    logger.error(f"Signal emit failed: {e}")

                # Set SSB mode: LSB for 40m and below (10 MHz), USB for above 40m
                ssb_mode = "LSB" if profile.freq_start <= 10_000_000 else "USB"
                try:
                    self.radio.set_mode(ssb_mode, 2400)
                    logger.debug(f"Set mode to {ssb_mode} for {band_name}")
                except Exception as e:
                    logger.warning(f"Failed to set mode to {ssb_mode}: {e}")

                freq = profile.freq_start
                while freq <= profile.freq_end and self.running:
                    try:
                        # Tune radio
                        self.radio.set_frequency(int(freq))

                        # Update frequency display (prevents race condition with status timer)
                        try:
                            self.freq_update_signal.emit(int(freq))
                        except Exception as e:
                            logger.error(f"Frequency display update failed: {e}")

                        # Emit frequency update to log
                        try:
                            self.log_signal.emit(f"  {freq/1e6:.4f} MHz")
                        except Exception as e:
                            logger.error(f"Signal emit failed for freq {freq}: {e}")

                        # Dwell
                        time.sleep(self.dwell_sec)

                        # Next frequency
                        freq += self.step_hz

                    except RadioConnectionError as e:
                        error_msg = f"Radio connection lost at {freq/1e6:.3f} MHz: {e}"
                        logger.error(error_msg)
                        try:
                            self.log_signal.emit(error_msg)
                        except:
                            pass
                        return  # Exit scan completely on connection loss
                    except Exception as e:
                        error_msg = f"Error at {freq/1e6:.3f} MHz: {e}\n{traceback.format_exc()}"
                        logger.error(error_msg)
                        try:
                            self.log_signal.emit(f"Error at {freq/1e6:.3f} MHz: {e}")
                        except:
                            pass
                        break

                if not self.running:
                    break

            try:
                self.log_signal.emit("Scan complete")
            except Exception as e:
                logger.error(f"Signal emit failed for scan complete: {e}")
        except Exception as e:
            error_msg = f"Scan thread crashed: {e}\n{traceback.format_exc()}"
            logger.error(error_msg)
            try:
                self.log_signal.emit(f"Scan error: {e}")
            except:
                pass

    def stop(self):
        """Stop scanning"""
        self.running = False


class TranscriptionWorker(QObject):
    """
    Worker object for background transcription using proper Qt threading pattern.

    This avoids Qt threading violations that occur when using Python's threading.Thread
    with PyQt5 signals in PyInstaller frozen apps.
    """
    # Signals (thread-safe)
    transcription_ready = pyqtSignal(float, str, object)  # freq_mhz, text, callsign
    transcription_complete = pyqtSignal()
    error_occurred = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self._audio = None
        self._sample_rate = None
        self._transcriber = None
        self._voice_embedder = None
        self._voice_db = None
        self._log_queue = None  # For thread-safe logging
        self._transcriber_lock = None  # Lock for shared transcriber

    def set_parameters(self, audio, sample_rate, transcriber, voice_embedder, voice_db, log_queue=None, transcriber_lock=None):
        """Set transcription parameters (call from main thread before starting)"""
        self._audio = audio
        self._sample_rate = sample_rate
        self._transcriber = transcriber
        self._voice_embedder = voice_embedder
        self._voice_db = voice_db
        self._log_queue = log_queue  # Queue for thread-safe logging
        self._transcriber_lock = transcriber_lock  # Lock for shared transcriber

    def transcribe(self):
        """Perform transcription (runs in worker thread)"""
        # DIAGNOSTIC: Print to console immediately (before any imports)
        print("[WORKER] transcribe() called - worker thread started")
        try:
            import time
            import logging
            import sys
            import io
            import os
            from logging.handlers import QueueHandler

            print("[WORKER] Imports complete, configuring logging...")

            # Configure thread-safe logging using QueueHandler
            # This prevents Qt threading violations in PyInstaller frozen builds
            if self._log_queue is not None:
                try:
                    # Create QueueHandler for this worker thread
                    queue_handler = QueueHandler(self._log_queue)
                    print("[WORKER] Created QueueHandler")

                    # Get all relevant loggers that may be used in worker thread
                    # External libraries
                    fw_logger = logging.getLogger('faster_whisper')
                    httpx_logger = logging.getLogger('httpx')
                    # CQSentinel modules used by worker
                    worker_logger = logging.getLogger(__name__)
                    speech_logger = logging.getLogger('cqsentinel.speech.transcription')
                    voice_embed_logger = logging.getLogger('cqsentinel.voice.embeddings')
                    voice_db_logger = logging.getLogger('cqsentinel.voice.database')
                    # Root logger (catches everything not caught by specific loggers)
                    root_logger = logging.getLogger()
                    print("[WORKER] Got all loggers")

                    # Redirect Python warnings to logging (they might be escaping)
                    import warnings
                    logging.captureWarnings(True)
                    warnings_logger = logging.getLogger('py.warnings')
                    print("[WORKER] Configured warnings capture")

                    # Save original handlers and propagate settings
                    saved_state = []
                    for log in [worker_logger, fw_logger, httpx_logger, speech_logger, voice_embed_logger, voice_db_logger, root_logger, warnings_logger]:
                        saved_state.append((log, log.handlers[:], log.propagate))
                        log.handlers.clear()
                        log.addHandler(queue_handler)
                        # CRITICAL: Disable propagation to prevent records from reaching parent loggers
                        # Parent loggers may have Qt-unsafe handlers that cause threading violations
                        log.propagate = False
                    print("[WORKER] Logger handlers configured")

                    print("[WORKER] Logger setup complete, about to redirect stdout/stderr...")
                except Exception as e:
                    print(f"[WORKER] EXCEPTION during logger setup: {e}")
                    import traceback
                    traceback.print_exc()
                    raise

                # DIAGNOSTIC: Test if os.pipe() works before we try to use it
                print("[WORKER] DIAGNOSTIC: Testing os.pipe() functionality...")
                pipe_test_passed = False
                try:
                    test_read_fd, test_write_fd = os.pipe()
                    print(f"[WORKER] DIAGNOSTIC: os.pipe() SUCCESS - created fds: read={test_read_fd}, write={test_write_fd}")
                    # Clean up test pipe
                    os.close(test_read_fd)
                    os.close(test_write_fd)
                    pipe_test_passed = True
                    print("[WORKER] DIAGNOSTIC: os.pipe() test PASSED")
                except Exception as e:
                    print(f"[WORKER] DIAGNOSTIC: os.pipe() FAILED with error: {e}")
                    import traceback
                    traceback.print_exc()
                    pipe_test_passed = False

                # DIAGNOSTIC: Check if we're in a frozen console build
                # In console mode (console=True in spec), C++ output safely goes to console
                # OS-level fd redirection is not needed and causes crashes in PyInstaller
                is_frozen = getattr(sys, 'frozen', False)
                print(f"[WORKER] DIAGNOSTIC: Frozen build: {is_frozen}")
                print(f"[WORKER] DIAGNOSTIC: sys.stderr type: {type(sys.stderr)}")
                if hasattr(sys.stderr, 'isatty'):
                    print(f"[WORKER] DIAGNOSTIC: sys.stderr.isatty(): {sys.stderr.isatty()}")

                # CRITICAL: Skip OS-level fd redirection in frozen console builds
                # The PyInstaller bootloader has already set up fds, and manipulating them causes crashes
                # In console mode, C++ output goes to the console which is safe
                skip_fd_redirect = is_frozen
                if skip_fd_redirect:
                    print("[WORKER] DIAGNOSTIC: Skipping OS-level fd redirection (frozen console build)")
                    print("[WORKER] DIAGNOSTIC: C++ output will appear in console (this is safe)")

                # CRITICAL: Redirect stdout/stderr to prevent direct writes from touching Qt
                # Libraries like tqdm, print() statements, or C++ code might write directly
                # In frozen builds, sys.stdout/stderr are Qt-wrapped and cause threading violations
                saved_stdout = sys.stdout
                saved_stderr = sys.stderr
                print(f"[WORKER] Saved stdout={saved_stdout}, stderr={saved_stderr}")
                sys.stdout = io.StringIO()  # Capture stdout (Python level)
                sys.stderr = io.StringIO()  # Capture stderr (Python level)
                # NOTE: print() no longer works after this point!

                # Variables for fd redirection (may not be used if skipped)
                saved_stdout_fd = None
                saved_stderr_fd = None
                stderr_tempfile = None
                stderr_reader_thread = None

                # Only redirect fds if not in frozen console build
                if not skip_fd_redirect:
                    # CRITICAL: Also redirect at OS level for C++ libraries (ctranslate2, PyTorch)
                    # C++ code writes directly to file descriptors 1/2, bypassing Python's sys.stdout/stderr
                    # SOLUTION: Use temporary file - reliable, cross-platform, captures all output

                    def tail_tempfile(filepath, log_func, stop_event):
                        """Background thread to tail temp file and forward C++ output to logging"""
                        try:
                            import time
                            with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
                                # Start at beginning of file
                                f.seek(0)
                                while not stop_event.is_set():
                                    line = f.readline()
                                    if line:
                                        line = line.rstrip('\n\r')
                                        if line.strip():
                                            log_func(f"[C++] {line}")
                                    else:
                                        # No data, sleep briefly
                                        time.sleep(0.01)

                                # Process any remaining lines after stop
                                for line in f:
                                    line = line.rstrip('\n\r')
                                    if line.strip():
                                        log_func(f"[C++] {line}")
                        except Exception as e:
                            # Tail thread failure is non-critical
                            pass

                    try:
                        logger.info("[WORKER] Setting up OS-level fd redirection...")
                        # Duplicate original file descriptors
                        saved_stdout_fd = os.dup(1)  # Duplicate stdout fd
                        saved_stderr_fd = os.dup(2)  # Duplicate stderr fd
                        logger.info(f"[WORKER] Saved original fds: stdout={saved_stdout_fd}, stderr={saved_stderr_fd}")

                        # Create temporary file for capturing C++ stderr
                        import tempfile
                        import threading
                        stderr_tempfile = tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.log')
                        stderr_tempfile.close()  # Close Python handle, we'll use fd directly
                        logger.info(f"[WORKER] Created temp file: {stderr_tempfile.name}")

                        # Open temp file for writing at OS level
                        stderr_fd = os.open(stderr_tempfile.name, os.O_WRONLY | os.O_APPEND)
                        logger.info(f"[WORKER] Opened temp file: fd={stderr_fd}")

                        # Redirect stderr to temp file (stdout to devnull, we don't expect stdout output)
                        os.dup2(stderr_fd, 2)  # Redirect stderr fd to temp file
                        os.close(stderr_fd)  # Close our copy, fd 2 still points to file

                        # Redirect stdout to devnull
                        devnull_fd = os.open(os.devnull, os.O_WRONLY)
                        os.dup2(devnull_fd, 1)
                        os.close(devnull_fd)
                        logger.info("[WORKER] Redirected stderr to tempfile, stdout to devnull")

                        # Start background thread to tail the temp file
                        from threading import Event
                        stop_tail = Event()
                        stderr_reader_thread = threading.Thread(
                            target=tail_tempfile,
                            args=(stderr_tempfile.name, logger.debug, stop_tail),
                            daemon=True
                        )
                        stderr_reader_thread.start()
                        logger.info("[WORKER] Started stderr tail thread")

                    except (OSError, AttributeError) as e:
                        # OS-level redirection failed (shouldn't happen, but fallback gracefully)
                        logger.error(f"[WORKER] ERROR: Failed to set up fd redirection: {e}")
                        import traceback
                        logger.error(traceback.format_exc())
                        pass

                try:
                    logger.info(f"Transcribing {len(self._audio)/self._sample_rate:.1f}s of speech...")

                    # DIAGNOSTIC: Check model states before loading
                    logger.info("[WORKER] Checking model states...")
                    if self._voice_embedder:
                        logger.info(f"[WORKER] VoiceEmbedder present, encoder loaded: {self._voice_embedder.encoder is not None}")
                    if self._transcriber:
                        logger.info(f"[WORKER] Transcriber present, model loaded: {self._transcriber.model is not None}")

                    # Identify speaker(s) using sliding window voice embeddings
                    speaker_labels = []
                    if self._voice_embedder and self._voice_db:
                        try:
                            logger.info("[WORKER] About to call detect_speaker_changes (may load Resemblyzer model)...")
                            # Detect speaker changes
                            speaker_segments = self._voice_embedder.detect_speaker_changes(
                                self._audio,
                                sample_rate=self._sample_rate,
                                window_duration=2.5,
                                stride=1.0,
                                similarity_threshold=0.75
                            )

                            # Map each speaker segment to voice ID
                            for seg in speaker_segments:
                                if seg['embedding'] is not None:
                                    match = self._voice_db.find_matching_voice(seg['embedding'])
                                    if match:
                                        voice_id, similarity = match
                                        operator = self._voice_db.get_operator(voice_id)
                                        label = operator.callsign or f"Speaker {voice_id[:8]}"
                                        logger.debug(f"Matched voice at {seg['start']:.1f}-{seg['end']:.1f}s: {label} (similarity: {similarity:.2f})")
                                    else:
                                        voice_id = self._voice_db.add_operator(seg['embedding'], metadata={'first_heard': time.time()})
                                        label = f"Speaker {voice_id[:8]}"
                                        logger.debug(f"New speaker at {seg['start']:.1f}-{seg['end']:.1f}s: {label}")

                                    speaker_labels.append({
                                        'start': seg['start'],
                                        'end': seg['end'],
                                        'label': label,
                                        'voice_id': voice_id
                                    })

                            unique_speakers = len(set(s['voice_id'] for s in speaker_labels))
                            if unique_speakers > 1:
                                logger.info(f"Detected {unique_speakers} different speakers in segment ({', '.join(set(s['label'] for s in speaker_labels))})")

                        except Exception as e:
                            logger.debug(f"Speaker detection failed: {e}")

                    # Transcribe (acquire lock because WhisperModel is NOT thread-safe)
                    # Multiple workers sharing the same transcriber would crash in C++ code
                    logger.info("[WORKER] About to transcribe with WhisperModel (may load model on first use)...")
                    if self._transcriber_lock is not None:
                        with self._transcriber_lock:
                            transcripts = self._transcriber.transcribe(
                                self._audio,
                                sample_rate=self._sample_rate,
                                vad_filter=False
                            )
                    else:
                        # No lock provided (shouldn't happen, but fallback)
                        transcripts = self._transcriber.transcribe(
                            self._audio,
                            sample_rate=self._sample_rate,
                            vad_filter=False
                        )

                    # Emit results
                    for transcript in transcripts:
                        if transcript.text.strip():
                            text = transcript.text
                            if speaker_labels:
                                unique_labels = list(set(s['label'] for s in speaker_labels))
                                if len(unique_labels) == 1:
                                    text = f"[{unique_labels[0]}] {text}"
                                else:
                                    text = f"[{'/'.join(unique_labels)}] {text}"

                            self.transcription_ready.emit(0.0, text, None)
                            logger.info(f"Transcribed: {text}")

                    self.transcription_complete.emit()
                finally:
                    # Stop stderr tail thread and clean up temp file
                    if stderr_reader_thread is not None and stderr_reader_thread.is_alive():
                        try:
                            logger.info("[WORKER] Stopping stderr tail thread...")
                            stop_tail.set()
                            stderr_reader_thread.join(timeout=2.0)  # Wait up to 2 seconds
                            if stderr_reader_thread.is_alive():
                                logger.warning("[WORKER] Tail thread did not stop in time")
                            else:
                                logger.info("[WORKER] Tail thread stopped")
                        except Exception as e:
                            logger.debug(f"[WORKER] Error stopping tail thread: {e}")

                    # Delete temporary file
                    if stderr_tempfile is not None:
                        try:
                            import os
                            if os.path.exists(stderr_tempfile.name):
                                os.unlink(stderr_tempfile.name)
                                logger.info(f"[WORKER] Deleted temp file: {stderr_tempfile.name}")
                        except Exception as e:
                            logger.debug(f"[WORKER] Error deleting temp file: {e}")

                    # Restore OS-level file descriptors
                    if saved_stderr_fd is not None:
                        try:
                            os.dup2(saved_stderr_fd, 2)  # Restore stderr fd
                            os.close(saved_stderr_fd)
                            logger.info("[WORKER] Restored stderr fd")
                        except (OSError, AttributeError) as e:
                            logger.debug(f"[WORKER] Error restoring stderr fd: {e}")
                    if saved_stdout_fd is not None:
                        try:
                            os.dup2(saved_stdout_fd, 1)  # Restore stdout fd
                            os.close(saved_stdout_fd)
                            logger.info("[WORKER] Restored stdout fd")
                        except (OSError, AttributeError) as e:
                            logger.debug(f"[WORKER] Error restoring stdout fd: {e}")

                    # Restore Python-level stdout/stderr
                    sys.stdout = saved_stdout
                    sys.stderr = saved_stderr

                    # Restore original handlers and propagate settings
                    for log, handlers, propagate in saved_state:
                        log.handlers.clear()
                        for h in handlers:
                            log.addHandler(h)
                        log.propagate = propagate
            else:
                # No log queue provided, use regular logging (may cause threading issues in frozen builds)
                logger.info(f"Transcribing {len(self._audio)/self._sample_rate:.1f}s of speech...")

                # Identify speaker(s) using sliding window voice embeddings
                speaker_labels = []
                if self._voice_embedder and self._voice_db:
                    try:
                        # Detect speaker changes
                        speaker_segments = self._voice_embedder.detect_speaker_changes(
                            self._audio,
                            sample_rate=self._sample_rate,
                            window_duration=2.5,
                            stride=1.0,
                            similarity_threshold=0.75
                        )

                        # Map each speaker segment to voice ID
                        for seg in speaker_segments:
                            if seg['embedding'] is not None:
                                match = self._voice_db.find_matching_voice(seg['embedding'])
                                if match:
                                    voice_id, similarity = match
                                    operator = self._voice_db.get_operator(voice_id)
                                    label = operator.callsign or f"Speaker {voice_id[:8]}"
                                    logger.debug(f"Matched voice at {seg['start']:.1f}-{seg['end']:.1f}s: {label} (similarity: {similarity:.2f})")
                                else:
                                    voice_id = self._voice_db.add_operator(seg['embedding'], metadata={'first_heard': time.time()})
                                    label = f"Speaker {voice_id[:8]}"
                                    logger.debug(f"New speaker at {seg['start']:.1f}-{seg['end']:.1f}s: {label}")

                                speaker_labels.append({
                                    'start': seg['start'],
                                    'end': seg['end'],
                                    'label': label,
                                    'voice_id': voice_id
                                })

                        unique_speakers = len(set(s['voice_id'] for s in speaker_labels))
                        if unique_speakers > 1:
                            logger.info(f"Detected {unique_speakers} different speakers in segment ({', '.join(set(s['label'] for s in speaker_labels))})")

                    except Exception as e:
                        logger.debug(f"Speaker detection failed: {e}")

                # Transcribe (acquire lock because WhisperModel is NOT thread-safe)
                if self._transcriber_lock is not None:
                    with self._transcriber_lock:
                        transcripts = self._transcriber.transcribe(
                            self._audio,
                            sample_rate=self._sample_rate,
                            vad_filter=False
                        )
                else:
                    # No lock provided (shouldn't happen, but fallback)
                    transcripts = self._transcriber.transcribe(
                        self._audio,
                        sample_rate=self._sample_rate,
                        vad_filter=False
                    )

                # Emit results
                for transcript in transcripts:
                    if transcript.text.strip():
                        text = transcript.text
                        if speaker_labels:
                            unique_labels = list(set(s['label'] for s in speaker_labels))
                            if len(unique_labels) == 1:
                                text = f"[{unique_labels[0]}] {text}"
                            else:
                                text = f"[{'/'.join(unique_labels)}] {text}"

                        self.transcription_ready.emit(0.0, text, None)
                        logger.info(f"Transcribed: {text}")

                self.transcription_complete.emit()

        except Exception as e:
            print(f"[WORKER] EXCEPTION in transcribe(): {e}")
            import traceback
            traceback.print_exc()
            logger.error(f"Transcription failed: {e}", exc_info=True)
            self.error_occurred.emit(str(e))
        finally:
            print("[WORKER] transcribe() finally block - emitting completion signal")
            self.transcription_complete.emit()


class MainWindow(QMainWindow):
    """Main application window"""

    # Signals for thread-safe GUI updates
    station_detected_signal = pyqtSignal(object)  # Station object
    progress_update_signal = pyqtSignal(object)  # ScanProgress object
    transcription_signal = pyqtSignal(float, str, str)  # freq_mhz, transcription, callsign
    audio_levels_signal = pyqtSignal(float, float)  # rms_level, peak_level
    voice_detection_signal = pyqtSignal(bool, float)  # has_speech, speech_ratio
    log_signal = pyqtSignal(str)  # Log messages (thread-safe)
    scan_finished_signal = pyqtSignal()  # Scan finished (thread-safe)

    def __init__(self):
        super().__init__()

        self.config = get_config()

        # Phase 1: Radio control
        self.radio: HamlibController = None
        self.rigctld_manager: RigctldManager = None

        # Phase 2-8: Advanced features (initialized on-demand)
        self.audio: AudioCapture = None
        self.audio_pipeline: AudioPipeline = None
        self.auto_tuner: SSBAutoTuner = None
        self.transcriber: SpeechTranscriber = None
        self.subprocess_transcriber: SubprocessTranscriber = None  # Subprocess-based transcription for Windows
        self.callsign_extractor: CallsignExtractor = None
        self.behavior_analyzer: BehaviorAnalyzer = None
        self.band_map: BandMapState = None

        # Scanning
        self.scan_thread: ScanThread = None
        self.band_scanner: BandScanner = None
        self.use_full_scanner = False  # Enable when Phase 2+ components ready
        self.scan_queue = []  # Queue of bands to scan
        self.current_scan_band = None  # Current band being scanned
        self.enabled_bands_for_scan = []  # Bands that were enabled when scan started (for continuous loop)

        # Audio monitoring (new broadcaster pattern)
        self.audio_broadcaster = AudioBroadcaster()
        self.audio_level_meter = AudioLevelMeter()
        self.audio_monitor = AudioMonitor()  # For diagnostic playback
        self.audio_buffer = AudioBuffer(buffer_duration=1.0, sample_rate=self.config.audio.sample_rate)  # Buffer for VAD

        # Speech ratio smoothing (exponential moving average)
        self._speech_ratio_smoothed = 0.0
        self._speech_ratio_alpha = 0.3  # Smoothing factor (0.3 = 30% new, 70% old)

        # Transcription buffering (accumulate audio during speech, transcribe on pauses)
        self._transcription_buffer = []  # List of denoised audio chunks
        self._is_speaking = False  # Track if currently speaking
        self._silence_buffers = 0  # Count consecutive silent buffers
        self._min_transcription_duration = 2.0  # Minimum 2 seconds before transcribing
        self._max_silence_buffers = 2  # Transcribe after 2 consecutive silent buffers (2 seconds of silence)
        self._max_transcription_duration = 15.0  # Maximum 15 seconds before forcing transcription
        self._transcription_start_time = None  # When we started accumulating audio

        # Transcription queue management (prevent backup during long contests)
        self._active_transcriptions = 0  # Counter for in-flight transcriptions
        self._max_concurrent_transcriptions = 5  # Maximum parallel transcriptions (match num_workers)
        self._transcription_lock = threading.Lock()  # Protect counter
        self._transcriber_lock = threading.Lock()  # Protect shared transcriber (WhisperModel is NOT thread-safe)

        # Thread-safe logging with QueueHandler/QueueListener pattern
        # This prevents Qt threading violations when worker threads log to stdout/stderr
        self._log_queue = queue.Queue()

        # Get handlers from root logger to use in QueueListener
        root_logger = logging.getLogger()
        handlers = root_logger.handlers if root_logger.handlers else []

        # Create QueueListener to process log records from worker threads
        # The listener runs in a separate thread and forwards records to the actual handlers
        self._queue_listener = logging.handlers.QueueListener(
            self._log_queue,
            *handlers,
            respect_handler_level=True
        )

        # Start the queue listener
        self._queue_listener.start()
        logger.debug("QueueListener started for thread-safe logging")

        # Band map visualization (always available)
        self.band_map_widgets = {}  # Dictionary of BandMapWidget instances per band
        self.band_maps = {}  # Dictionary of BandMapState instances per band
        self.station_detail_panel: StationDetailPanel = None

        # Initialize audio capture for level meter (basic monitoring, always available)
        try:
            # Get configured audio device index
            audio_device_index = self._get_audio_device_index()
            self.audio = AudioCapture(device=audio_device_index, sample_rate=self.config.audio.sample_rate)
            self.start_audio_monitoring()
            if audio_device_index is not None:
                logger.info(f"Basic audio monitoring initialized with device index {audio_device_index}")
            else:
                logger.info("Basic audio monitoring initialized with default device")
        except Exception as e:
            logger.warning(f"Could not initialize audio capture: {e}")
            # Not critical - app can still function

        self.init_ui()
        self.setup_timers()

        # Connect signals for thread-safe GUI updates from scanner callbacks
        self.station_detected_signal.connect(self._handle_station_detected)
        self.progress_update_signal.connect(self._handle_progress_update)
        self.transcription_signal.connect(self._handle_transcription)
        self.audio_levels_signal.connect(self._handle_audio_levels)
        self.voice_detection_signal.connect(self._handle_voice_detection)
        self.log_signal.connect(self._handle_log)  # Thread-safe logging
        self.scan_finished_signal.connect(self.on_scan_finished)  # Thread-safe scan completion

        # Register audio consumers with broadcaster
        self.audio_broadcaster.register_consumer(self.audio_level_meter.process_chunk)
        self.audio_broadcaster.register_consumer(self.audio_monitor.process_chunk)

        logger.info("Main window initialized")

        # Set initial band visibility based on checkbox state
        # Use QTimer to ensure UI is fully rendered before calculating heights
        from PyQt5.QtCore import QTimer
        QTimer.singleShot(100, self.update_band_visibility)

        # Initialize advanced features automatically after UI is ready
        QTimer.singleShot(500, self.init_advanced_features)

    def init_advanced_features(self):
        """Initialize Phase 2-8 advanced features (audio processing, AI models, etc.)"""
        try:
            self.log("Initializing advanced features...")

            # Audio capture (already initialized for level meter, reuse it)
            if not self.audio:
                self.log("  Initializing audio capture...")
                audio_device_index = self._get_audio_device_index()
                self.audio = AudioCapture(device=audio_device_index, sample_rate=self.config.audio.sample_rate)
                self.start_audio_monitoring()
            else:
                self.log("  Audio capture already active (for level meter)")

            # Audio pipeline (denoiser + VAD)
            if not self.audio_pipeline:
                self.log("  Initializing audio pipeline...")
                self.audio_pipeline = AudioPipeline(
                    sample_rate=self.config.audio.sample_rate,
                    denoise_level=self.config.audio.noise_reduction_level,
                    vad_threshold=self.config.audio.vad_sensitivity,
                    whisper_model=self.config.audio.whisper_model_size,
                    enable_voice_id=True
                )

            # SSB Auto-tuner
            if not self.auto_tuner:
                self.log("  Initializing SSB auto-tuner...")
                self.auto_tuner = SSBAutoTuner()

            # Speech transcriber - using subprocess approach for Windows compatibility
            # The subprocess isolates faster-whisper/ctranslate2 to avoid Windows threading crashes
            if not self.subprocess_transcriber:
                self.log("  Starting transcription subprocess (may download AI model)...")
                model_size = self.config.audio.whisper_model_size if hasattr(self.config.audio, 'whisper_model_size') else "small"
                self.subprocess_transcriber = SubprocessTranscriber(
                    model_size=model_size,
                    compute_type="float32",  # Use float32 for stability on Windows
                    num_workers=5  # Multiple workers for parallel transcription (openai-whisper is safe)
                )

                # Start subprocess and wait for model loading
                if self.subprocess_transcriber.start():
                    self.log("  Transcription subprocess ready")
                else:
                    self.log("  ERROR: Failed to start transcription subprocess")
                    logger.error("Failed to start transcription subprocess")

            # Keep old transcriber for backward compatibility (not used with subprocess approach)
            if not self.transcriber:
                self.log("  Initializing speech transcriber (may download AI model)...")
                self.transcriber = SpeechTranscriber()

            # Contest logic
            if not self.callsign_extractor:
                self.log("  Initializing callsign extractor...")
                self.callsign_extractor = CallsignExtractor()

            if not self.behavior_analyzer:
                self.log("  Initializing behavior analyzer...")
                self.behavior_analyzer = BehaviorAnalyzer()

            # Band map - now using per-band band maps
            # The band_maps dictionary is already created in init_ui
            self.log("  Band maps initialized for all bands")

            self.use_full_scanner = True
            self.log("[OK] Advanced features initialized successfully!")
            self.log("  Full scanner with audio processing, AI transcription, and voice ID enabled.")
            logger.info("Advanced features initialized: audio pipeline, transcription, voice ID, contest logic")

        except Exception as e:
            self.log(f"ERROR initializing advanced features: {e}")
            logger.error(f"Failed to initialize advanced features: {e}", exc_info=True)
            self.log("[WARNING] Using basic scanner mode (advanced features unavailable)")
            self.use_full_scanner = False

    def _get_audio_device_index(self) -> Optional[int]:
        """
        Get the audio device index from the configured device name.

        Returns:
            Device index (int) if found, None for default device
        """
        device_name = self.config.radio.audio_device_name

        # If no device configured or empty string, use default
        if not device_name:
            logger.info("Using default audio input device")
            return None

        # Try to find device by name
        try:
            devices = list_audio_devices()
            for device in devices:
                if device.name == device_name:
                    logger.info(f"Found audio device '{device_name}' at index {device.index}")
                    return device.index

            # Device not found - warn and use default
            logger.warning(f"Configured audio device '{device_name}' not found, using default")
            return None
        except Exception as e:
            logger.error(f"Error finding audio device: {e}")
            return None

    def start_audio_monitoring(self):
        """Start audio stream with broadcaster pattern for multiple consumers"""
        if not self.audio:
            return

        # Check if already recording
        if hasattr(self.audio, '_recording') and self.audio._recording:
            logger.debug("Audio monitoring already active")
            return

        try:
            import time

            # Diagnostics counters
            callback_count = [0]  # Use list to allow modification in nested function
            buffers_processed = [0]
            speech_detected_count = [0]
            denoised_chunks_created = [0]

            def audio_callback(audio_chunk):
                """
                Process audio chunks with proper buffering.

                Small chunks (64ms) come from sounddevice. We:
                1. Broadcast raw audio immediately (for real-time monitoring)
                2. Buffer chunks into larger segments (1s) for VAD
                3. Process buffered segments to detect speech
                4. Broadcast denoised audio when speech detected
                """
                try:
                    callback_count[0] += 1

                    # === STEP 1: Broadcast RAW audio immediately for real-time monitoring ===
                    raw_chunk = AudioChunk(
                        stage=AudioStage.RAW,
                        data=audio_chunk,
                        sample_rate=self.audio.sample_rate,
                        timestamp=time.time()
                    )
                    self.audio_broadcaster.broadcast(raw_chunk)

                    # Update level meter
                    rms, peak = self.audio_level_meter.get_levels()
                    self.audio_levels_signal.emit(rms, peak)

                    # === STEP 2: Buffer audio for VAD (if pipeline available) ===
                    if self.audio_pipeline:
                        # Add chunk to buffer
                        buffered_audio = self.audio_buffer.add_chunk(audio_chunk)

                        # Process when buffer is full (returns None otherwise)
                        if buffered_audio is not None:
                            buffers_processed[0] += 1

                            try:
                                # Process buffered audio through VAD
                                result = self.audio_pipeline.process_quick(
                                    buffered_audio,
                                    check_voice_only=True
                                )
                                has_speech = result.get('has_speech', False)
                                speech_ratio = result.get('speech_ratio', 0.0)

                                # Apply smoothing to speech ratio (exponential moving average)
                                self._speech_ratio_smoothed = (
                                    self._speech_ratio_alpha * speech_ratio +
                                    (1 - self._speech_ratio_alpha) * self._speech_ratio_smoothed
                                )

                                # Emit signal for voice detection (thread-safe) with smoothed ratio
                                self.voice_detection_signal.emit(has_speech, self._speech_ratio_smoothed)

                                # === STEP 3: Create denoised audio ===
                                # Always denoise when we have speech, regardless of transcription
                                if has_speech:
                                    speech_detected_count[0] += 1

                                    try:
                                        # Denoise the buffered audio
                                        denoised = self.audio_pipeline.denoiser.denoise(buffered_audio)

                                        # Broadcast denoised audio for real-time monitoring
                                        denoised_chunk = AudioChunk(
                                            stage=AudioStage.DENOISED,
                                            data=denoised,
                                            sample_rate=self.audio.sample_rate,
                                            timestamp=time.time(),
                                            metadata={
                                                'has_speech': True,
                                                'speech_ratio': speech_ratio,
                                                'buffer_duration': result.get('duration', 1.0)
                                            }
                                        )
                                        self.audio_broadcaster.broadcast(denoised_chunk)
                                        denoised_chunks_created[0] += 1

                                        # Log first few denoised chunks
                                        if denoised_chunks_created[0] <= 3:
                                            logger.info(
                                                f"DIAGNOSTIC: Created denoised chunk #{denoised_chunks_created[0]} "
                                                f"(speech_ratio: {speech_ratio:.2%}, buffer: {result.get('duration', 1.0):.2f}s)"
                                            )

                                        # === STEP 4: Accumulate audio for transcription ===
                                        # Track when we started speaking
                                        if not self._is_speaking:
                                            self._transcription_start_time = time.time()

                                        # Add denoised audio to transcription buffer
                                        self._transcription_buffer.append(denoised)
                                        self._is_speaking = True
                                        self._silence_buffers = 0

                                        # Check if we've been accumulating for too long (15s max)
                                        if self._transcription_start_time is not None:
                                            elapsed = time.time() - self._transcription_start_time
                                            total_duration = len(self._transcription_buffer)  # seconds (1 buffer = 1 second)

                                            if elapsed >= self._max_transcription_duration and total_duration >= self._min_transcription_duration:
                                                # Force transcription due to timeout
                                                logger.info(f"Forcing transcription after {elapsed:.1f}s (max {self._max_transcription_duration}s)")

                                                # Check if we're falling behind
                                                can_transcribe = False
                                                with self._transcription_lock:
                                                    if self._active_transcriptions >= self._max_concurrent_transcriptions:
                                                        logger.warning(
                                                            f"Skipping transcription (timeout) - already {self._active_transcriptions} in progress. "
                                                            f"Falling behind! Consider faster Whisper model."
                                                        )
                                                        # Don't clear buffer - keep accumulating
                                                    else:
                                                        self._active_transcriptions += 1
                                                        can_transcribe = True
                                                        logger.debug(f"Starting transcription ({self._active_transcriptions}/{self._max_concurrent_transcriptions} active)")

                                                if can_transcribe:
                                                    # Concatenate all buffered audio
                                                    full_audio = np.concatenate(self._transcription_buffer)

                                                    # Start transcription using proper QThread pattern
                                                    # (avoids Qt threading violations in PyInstaller frozen builds)
                                                    self._start_transcription_worker(full_audio)

                                                    # Clear buffer and reset state (but keep speaking=True since we might still be talking)
                                                    self._transcription_buffer.clear()
                                                    self._transcription_start_time = time.time()  # Restart timer for next chunk
                                                    self._silence_buffers = 0

                                    except Exception as e:
                                        logger.error(f"Denoising failed: {e}", exc_info=True)

                                else:
                                    # No speech detected
                                    if self._is_speaking:
                                        # We were speaking, now silence - count it
                                        self._silence_buffers += 1

                                        # If we've had enough silence, transcribe accumulated audio
                                        if self._silence_buffers >= self._max_silence_buffers:
                                            # Check if we have enough audio to transcribe
                                            total_duration = len(self._transcription_buffer)  # seconds (1 buffer = 1 second)

                                            if total_duration >= self._min_transcription_duration:
                                                # Check if we're falling behind
                                                can_transcribe = False
                                                with self._transcription_lock:
                                                    if self._active_transcriptions >= self._max_concurrent_transcriptions:
                                                        logger.warning(
                                                            f"Skipping transcription (pause) - already {self._active_transcriptions} in progress. "
                                                            f"Falling behind! Consider faster Whisper model."
                                                        )
                                                    else:
                                                        self._active_transcriptions += 1
                                                        can_transcribe = True
                                                        logger.debug(f"Starting transcription ({self._active_transcriptions}/{self._max_concurrent_transcriptions} active)")

                                                if can_transcribe:
                                                    # Concatenate all buffered audio
                                                    full_audio = np.concatenate(self._transcription_buffer)

                                                    # Start transcription using proper QThread pattern
                                                    # (avoids Qt threading violations in PyInstaller frozen builds)
                                                    self._start_transcription_worker(full_audio)

                                                    # Clear buffer and reset state
                                                    self._transcription_buffer.clear()
                                                    self._is_speaking = False
                                                    self._silence_buffers = 0
                                                    self._transcription_start_time = None

                                # Periodic diagnostics every 10 buffers
                                if buffers_processed[0] % 10 == 0:
                                    logger.debug(
                                        f"Audio buffer diagnostics: "
                                        f"callbacks={callback_count[0]}, "
                                        f"buffers={buffers_processed[0]}, "
                                        f"speech_detected={speech_detected_count[0]}, "
                                        f"denoised_created={denoised_chunks_created[0]}"
                                    )

                            except Exception as e:
                                logger.error(f"Buffered audio processing failed: {e}", exc_info=True)

                except Exception as e:
                    logger.error(f"Audio callback error: {e}", exc_info=True)

            self.audio.start_stream(audio_callback)
            logger.info("Audio monitoring started with buffering (1.0s buffers for VAD)")
        except Exception as e:
            logger.warning(f"Failed to start audio monitoring: {e}")

    def _start_transcription_worker(self, audio_data):
        """
        Start transcription using subprocess approach (Windows-compatible).

        This completely isolates faster-whisper/ctranslate2 in a separate process
        to avoid Windows threading crashes with C++ libraries.
        """
        # Use subprocess transcriber if available, fallback to threading approach
        # Add diagnostic logging to track subprocess state
        subprocess_available = False
        if self.subprocess_transcriber:
            is_alive = self.subprocess_transcriber.is_alive()
            logger.info(f"Subprocess transcriber check: exists=True, is_alive={is_alive}")
            if is_alive:
                subprocess_available = True
            else:
                # Log additional diagnostics
                proc = self.subprocess_transcriber.process
                if proc:
                    logger.warning(f"Subprocess not alive: pid={proc.pid}, exitcode={proc.exitcode}")
                else:
                    logger.warning("Subprocess process object is None")
        else:
            logger.info("Subprocess transcriber check: exists=False")

        if subprocess_available:
            # Submit audio to subprocess for transcription (non-blocking)
            try:
                request_id = self.subprocess_transcriber.transcribe_async(
                    audio=audio_data,
                    sample_rate=self.audio.sample_rate
                )
                logger.debug(f"Submitted transcription request {request_id} to subprocess")

                # Track pending requests (for cleanup and monitoring)
                if not hasattr(self, '_pending_transcription_requests'):
                    self._pending_transcription_requests = []
                self._pending_transcription_requests.append(request_id)

                # NOTE: Counter is already incremented before this function is called
                # (see lines 981/1022 in audio callback). Don't double-increment!
                logger.debug(f"Transcription submitted ({self._active_transcriptions}/{self._max_concurrent_transcriptions} active)")

            except Exception as e:
                logger.error(f"Failed to submit transcription to subprocess: {e}", exc_info=True)
                # CRITICAL: Decrement counter since we failed to submit
                # Counter was incremented BEFORE calling this function
                with self._transcription_lock:
                    self._active_transcriptions = max(0, self._active_transcriptions - 1)
                    logger.warning(f"Reverted counter after failed submission ({self._active_transcriptions}/{self._max_concurrent_transcriptions} active)")

        else:
            # Fallback: Use QThread worker approach (may crash on Windows)
            logger.warning("Subprocess transcriber not available, falling back to QThread (may crash on Windows)")

            # Create worker and thread
            worker = TranscriptionWorker()
            thread = QThread()

            # Move worker to thread
            worker.moveToThread(thread)

            # Connect signals
            worker.transcription_ready.connect(self._handle_transcription)
            worker.transcription_complete.connect(thread.quit)
            worker.transcription_complete.connect(lambda: self._on_transcription_finished(thread, worker))
            worker.error_occurred.connect(lambda err: logger.error(f"Transcription worker error: {err}"))

            # Set worker parameters (including log queue for thread-safe logging)
            worker.set_parameters(
                audio=audio_data.copy(),
                sample_rate=self.audio.sample_rate,
                transcriber=self.audio_pipeline.transcriber,
                voice_embedder=None,  # Voice fingerprinting removed
                voice_db=None,  # Voice fingerprinting removed
                log_queue=self._log_queue,  # Thread-safe logging
                transcriber_lock=self._transcriber_lock  # Protect shared transcriber
            )

            # Start worker when thread starts
            thread.started.connect(worker.transcribe)

            # Keep reference to prevent garbage collection
            if not hasattr(self, '_transcription_threads'):
                self._transcription_threads = []
            self._transcription_threads.append((thread, worker))

            # Start thread
            thread.start()

            logger.debug(f"Started transcription worker in QThread")

    def _poll_transcription_results(self):
        """
        Poll subprocess for transcription results (called by QTimer).

        This method is called periodically (every 100ms) to check if any
        transcription results are available from the subprocess.
        """
        if not self.subprocess_transcriber:
            return

        # Check worker health and respawn if needed
        alive_count = self.subprocess_transcriber.get_alive_count()
        if alive_count == 0:
            # All workers dead - this is critical
            logger.error("All transcription workers have died! Attempting respawn...")
            respawned = self.subprocess_transcriber.respawn_dead_workers()
            if respawned == 0:
                logger.error("Failed to respawn any workers")
            else:
                logger.info(f"Respawned {respawned} workers")

            # Reset active transcriptions counter since pending requests are lost
            with self._transcription_lock:
                if self._active_transcriptions > 0:
                    logger.warning(f"Resetting active transcription counter from {self._active_transcriptions} to 0 (workers died)")
                    self._active_transcriptions = 0

            # Clear pending request list
            if hasattr(self, '_pending_transcription_requests'):
                if self._pending_transcription_requests:
                    logger.warning(f"Clearing {len(self._pending_transcription_requests)} pending transcription requests (workers died)")
                    self._pending_transcription_requests.clear()

            # Clear input queue to prevent overload
            self.subprocess_transcriber.clear_input_queue()
            return

        elif alive_count < self.subprocess_transcriber.num_workers:
            # Some workers dead - try to respawn (will respect cooldown)
            if not hasattr(self, '_last_respawn_warning_time'):
                self._last_respawn_warning_time = 0.0
            if not hasattr(self, '_last_known_alive_count'):
                self._last_known_alive_count = self.subprocess_transcriber.num_workers

            # Detect newly dead workers and adjust counter for lost requests
            if alive_count < self._last_known_alive_count:
                dead_count = self._last_known_alive_count - alive_count
                with self._transcription_lock:
                    # Assume each dead worker had at most 1 in-flight request
                    old_count = self._active_transcriptions
                    self._active_transcriptions = max(0, self._active_transcriptions - dead_count)
                    if old_count != self._active_transcriptions:
                        logger.warning(f"Adjusted active transcription count from {old_count} to {self._active_transcriptions} (workers died)")
                self._last_known_alive_count = alive_count

            current_time = time.time()
            # Only warn once per 10 seconds to avoid spam
            if current_time - self._last_respawn_warning_time > 10.0:
                logger.warning(f"Worker pool degraded: {alive_count}/{self.subprocess_transcriber.num_workers} workers alive")
                self._last_respawn_warning_time = current_time

            # Attempt respawn (respawn_dead_workers has internal cooldown)
            respawned = self.subprocess_transcriber.respawn_dead_workers()
            if respawned > 0:
                logger.info(f"Successfully respawned {respawned} workers")
                # Update last known count to include respawned workers
                self._last_known_alive_count = self.subprocess_transcriber.get_alive_count()

        # Check for queue overload recovery
        with self._transcription_lock:
            # If we think we have max transcriptions active but workers are dying/slow
            # and we're stuck in "falling behind" state, recover
            if self._active_transcriptions >= self._max_concurrent_transcriptions:
                # Check if the queue has been stale for too long
                if not hasattr(self, '_queue_stale_time'):
                    self._queue_stale_time = time.time()
                else:
                    stale_duration = time.time() - self._queue_stale_time
                    if stale_duration > 30.0:  # 30 seconds of being "full" with no results
                        logger.warning(f"Queue appears stale for {stale_duration:.1f}s, attempting recovery...")
                        # Reset counter based on actual pending requests if known
                        old_count = self._active_transcriptions
                        if hasattr(self, '_pending_transcription_requests'):
                            # Use actual pending count (most accurate)
                            pending_count = len(self._pending_transcription_requests)
                            self._active_transcriptions = min(pending_count, alive_count)
                            logger.warning(f"Reset active count from {old_count} to {self._active_transcriptions} (pending={pending_count}, alive={alive_count})")
                        else:
                            # Fallback: reset to 0 to allow new transcriptions
                            self._active_transcriptions = 0
                            logger.warning(f"Reset active transcription count from {old_count} to 0 (forced recovery)")
                        self._queue_stale_time = time.time()
            else:
                # Reset stale timer when not at max capacity
                self._queue_stale_time = time.time()

        if not self.subprocess_transcriber.is_alive():
            return

        # Poll for results (non-blocking, timeout=0)
        try:
            result = self.subprocess_transcriber.get_result(timeout=0)
            if result is not None:
                # Got a result!
                logger.debug(f"Received transcription result for request {result.request_id}")

                if result.success:
                    # Emit transcription signal (thread-safe)
                    if result.text.strip():
                        # Emit with frequency=0.0 (no frequency info in subprocess mode)
                        # Callsign is already embedded in the text by subprocess
                        self.transcription_signal.emit(0.0, result.text.strip(), None)
                        logger.info(f"Transcribed: {result.text.strip()}")
                else:
                    # Transcription failed
                    logger.error(f"Transcription failed: {result.error}")

                # Remove from pending requests
                if hasattr(self, '_pending_transcription_requests'):
                    if result.request_id in self._pending_transcription_requests:
                        self._pending_transcription_requests.remove(result.request_id)

                # Decrement active count
                with self._transcription_lock:
                    self._active_transcriptions = max(0, self._active_transcriptions - 1)
                    logger.debug(f"Transcription complete ({self._active_transcriptions}/{self._max_concurrent_transcriptions} active)")

        except Exception as e:
            logger.debug(f"Error polling transcription results: {e}")

    def _on_transcription_finished(self, thread, worker):
        """Clean up after transcription completes"""
        # Decrement active count
        with self._transcription_lock:
            self._active_transcriptions -= 1
            logger.debug(f"Transcription complete ({self._active_transcriptions}/{self._max_concurrent_transcriptions} active)")

        # Clean up thread and worker
        thread.quit()
        thread.wait()

        # Remove from active list
        if hasattr(self, '_transcription_threads'):
            self._transcription_threads = [(t, w) for t, w in self._transcription_threads
                                          if t != thread]

    def init_ui(self):
        """Initialize user interface"""
        self.setWindowTitle(f"CQSentinel v{self.get_version()} - SSB Contest Scanner")
        self.setGeometry(100, 100, 1200, 800)

        # Create menu bar
        self.create_menus()

        # Create central widget
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        # Main layout
        main_layout = QVBoxLayout(central_widget)

        # Top panel: Band selection and controls
        main_layout.addWidget(self.create_control_panel())

        # Radio status panel
        main_layout.addWidget(self.create_radio_panel())

        # Main content area: 2 columns
        content_layout = QHBoxLayout()

        # LEFT COLUMN: Band maps + Activity log
        left_column = QVBoxLayout()

        # Stacked band maps
        bandmaps_container = QWidget()
        bandmaps_layout = QVBoxLayout(bandmaps_container)
        bandmaps_layout.setContentsMargins(0, 0, 0, 0)

        # Create band map widgets for all bands (ordered from highest to lowest frequency)
        for band_name in ["10m", "15m", "20m", "40m", "80m", "160m"]:
            if band_name in BAND_PROFILES:
                profile = BAND_PROFILES[band_name]

                # Create band map state for this band
                band_map_state = BandMapState(band=band_name)
                self.band_maps[band_name] = band_map_state

                # Create band map widget
                band_map_widget = BandMapWidget(band_map_state)
                band_map_widget.set_frequency_range(profile.freq_start, profile.freq_end)
                band_map_widget.station_clicked.connect(self.on_station_clicked)
                band_map_widget.station_selected.connect(self.on_station_selected)

                # Store reference
                self.band_map_widgets[band_name] = band_map_widget

                # Add to layout
                bandmaps_layout.addWidget(band_map_widget)

        # Make scrollable
        self.bandmaps_scroll_area = QScrollArea()
        self.bandmaps_scroll_area.setWidget(bandmaps_container)
        self.bandmaps_scroll_area.setWidgetResizable(True)
        self.bandmaps_scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        left_column.addWidget(self.bandmaps_scroll_area, stretch=6)

        # Activity log (below band maps, same width)
        left_column.addWidget(self.create_log_panel(), stretch=2)

        # RIGHT COLUMN: Station detail + Pipeline status
        right_column = QVBoxLayout()

        # Station detail panel (top right)
        self.station_detail_panel = StationDetailPanel()
        self.station_detail_panel.tune_requested.connect(self.on_station_clicked)
        self.station_detail_panel.mark_worked_requested.connect(self.on_mark_station_worked)
        right_column.addWidget(self.station_detail_panel, stretch=3)

        # Pipeline status panel (bottom right)
        right_column.addWidget(self.create_pipeline_status_panel(), stretch=5)

        # Add columns to content layout
        content_layout.addLayout(left_column, stretch=17)
        content_layout.addLayout(right_column, stretch=3)

        main_layout.addLayout(content_layout)

        # Status bar
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("Ready")

    def create_menus(self):
        """Create menu bar"""
        menubar = self.menuBar()

        # File menu
        file_menu = menubar.addMenu("&File")

        settings_action = QAction("&Settings", self)
        settings_action.triggered.connect(self.show_settings)
        file_menu.addAction(settings_action)

        file_menu.addSeparator()

        exit_action = QAction("E&xit", self)
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

        # Radio menu
        radio_menu = menubar.addMenu("&Radio")

        connect_action = QAction("&Connect", self)
        connect_action.triggered.connect(self.connect_radio)
        radio_menu.addAction(connect_action)

        disconnect_action = QAction("&Disconnect", self)
        disconnect_action.triggered.connect(self.disconnect_radio)
        radio_menu.addAction(disconnect_action)

        # Scanner menu
        scanner_menu = menubar.addMenu("&Scanner")

        enable_advanced_action = QAction("Enable &Advanced Features", self)
        enable_advanced_action.setToolTip("Initialize AI models, audio processing, and voice recognition")
        enable_advanced_action.triggered.connect(self.init_advanced_features)
        scanner_menu.addAction(enable_advanced_action)

        # Tools menu
        tools_menu = menubar.addMenu("&Tools")

        audio_diag_action = QAction("&Audio Diagnostics", self)
        audio_diag_action.setToolTip("Run audio subsystem self-test")
        audio_diag_action.triggered.connect(self.run_audio_diagnostics)
        tools_menu.addAction(audio_diag_action)

        # Help menu
        help_menu = menubar.addMenu("&Help")

        about_action = QAction("&About", self)
        about_action.triggered.connect(self.show_about)
        help_menu.addAction(about_action)

    def create_control_panel(self) -> QGroupBox:
        """Create control panel with band selection"""
        group = QGroupBox("Control Panel")
        layout = QHBoxLayout()

        # Band selection (ordered from highest to lowest frequency)
        layout.addWidget(QLabel("Bands:"))

        self.band_checkboxes = {}
        for band in ["10m", "15m", "20m", "40m", "80m", "160m"]:
            cb = QCheckBox(band)
            cb.setChecked(band in self.config.scan.enabled_bands)
            cb.stateChanged.connect(self.on_band_selection_changed)
            self.band_checkboxes[band] = cb
            layout.addWidget(cb)

        layout.addStretch()

        # Contest profile selector
        layout.addWidget(QLabel("Contest:"))
        self.contest_combo = QComboBox()
        self.contest_combo.addItems(["Field Day", "Winter Field Day", "CQWW", "CQWPX", "Salmon Run"])
        # Map display names to profile IDs
        self.contest_profile_map = {
            "Field Day": "FD",
            "Winter Field Day": "WFD",
            "CQWW": "CQWW",
            "CQWPX": "CQWPX",
            "Salmon Run": "WASR"
        }
        # Set current contest profile
        current_profile = self.config.contest.active_profile
        for display_name, profile_id in self.contest_profile_map.items():
            if profile_id == current_profile:
                self.contest_combo.setCurrentText(display_name)
                break
        self.contest_combo.currentTextChanged.connect(self.on_contest_changed)
        layout.addWidget(self.contest_combo)

        # N3FJP checkbox and status
        self.n3fjp_checkbox = QCheckBox("N3FJP")
        self.n3fjp_checkbox.setChecked(self.config.contest.n3fjp_enabled)
        self.n3fjp_checkbox.setToolTip("Enable N3FJP integration for dupe checking")
        self.n3fjp_checkbox.stateChanged.connect(self.on_n3fjp_toggled)
        layout.addWidget(self.n3fjp_checkbox)

        self.n3fjp_status_label = QLabel("●")
        self.n3fjp_status_label.setStyleSheet("color: gray;")
        self.n3fjp_status_label.setToolTip("N3FJP connection status")
        layout.addWidget(self.n3fjp_status_label)

        layout.addStretch()

        # Connect button
        self.connect_btn = QPushButton("Connect Radio")
        self.connect_btn.clicked.connect(self.connect_radio)
        layout.addWidget(self.connect_btn)

        # Start/Stop scanning
        self.scan_btn = QPushButton("Start Scan")
        self.scan_btn.clicked.connect(self.toggle_scan)
        self.scan_btn.setEnabled(False)
        layout.addWidget(self.scan_btn)

        group.setLayout(layout)
        return group

    def create_radio_panel(self) -> QGroupBox:
        """Create radio status panel"""
        group = QGroupBox("Radio Status")
        layout = QVBoxLayout()

        # Frequency display (large, centered)
        freq_layout = QHBoxLayout()
        freq_layout.addWidget(QLabel("Frequency:"))

        self.freq_label = QLabel("0.000 MHz")
        freq_font = QFont()
        freq_font.setPointSize(24)
        freq_font.setBold(True)
        self.freq_label.setFont(freq_font)
        self.freq_label.setMinimumWidth(250)  # Prevent label from resizing
        freq_layout.addWidget(self.freq_label)
        freq_layout.addStretch()
        layout.addLayout(freq_layout)

        # Mode and S-meter display (separate row)
        status_layout = QHBoxLayout()

        # Mode display
        status_layout.addWidget(QLabel("Mode:"))
        self.mode_label = QLabel("USB")
        mode_font = QFont()
        mode_font.setPointSize(16)
        self.mode_label.setFont(mode_font)
        self.mode_label.setMinimumWidth(80)  # Fixed width
        status_layout.addWidget(self.mode_label)

        status_layout.addStretch()

        # S-meter
        status_layout.addWidget(QLabel("S-Meter:"))
        self.smeter_label = QLabel("S0")
        self.smeter_label.setFont(mode_font)
        self.smeter_label.setMinimumWidth(80)  # Fixed width
        status_layout.addWidget(self.smeter_label)

        layout.addLayout(status_layout)

        # Audio level meter
        audio_layout = QHBoxLayout()
        audio_layout.addWidget(QLabel("Audio Level:"))
        self.audio_meter = QProgressBar()
        self.audio_meter.setRange(0, 100)
        self.audio_meter.setValue(0)
        audio_layout.addWidget(self.audio_meter)
        layout.addLayout(audio_layout)

        group.setLayout(layout)
        return group

    def create_log_panel(self) -> QGroupBox:
        """Create log/transcript panel"""
        group = QGroupBox("Activity Log")
        layout = QVBoxLayout()

        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        layout.addWidget(self.log_text)

        group.setLayout(layout)
        return group

    def create_pipeline_status_panel(self) -> QGroupBox:
        """Create realtime pipeline status panel"""
        group = QGroupBox("Pipeline Status")
        layout = QVBoxLayout()

        # Voice detection status
        status_layout = QHBoxLayout()
        status_layout.addWidget(QLabel("Voice Detected:"))
        self.voice_detected_label = QLabel("●")
        self.voice_detected_label.setStyleSheet("color: gray; font-size: 20px;")
        status_layout.addWidget(self.voice_detected_label)
        status_layout.addStretch()
        layout.addLayout(status_layout)

        # Audio level for voice
        voice_level_layout = QHBoxLayout()
        voice_level_layout.addWidget(QLabel("Speech Ratio:"))
        self.speech_ratio_bar = QProgressBar()
        self.speech_ratio_bar.setRange(0, 100)
        self.speech_ratio_bar.setValue(0)
        self.speech_ratio_bar.setFormat("%p%")
        voice_level_layout.addWidget(self.speech_ratio_bar)
        layout.addLayout(voice_level_layout)

        # Audio monitor diagnostic controls
        monitor_group = QGroupBox("Audio Diagnostic Monitor")
        monitor_layout = QVBoxLayout()

        # Output device selector
        output_device_layout = QHBoxLayout()
        output_device_layout.addWidget(QLabel("Output Device:"))
        self.output_device_combo = QComboBox()
        self.output_device_combo.setToolTip("Select audio output device for monitoring")

        # Populate output devices
        try:
            output_devices = list_audio_output_devices()
            self.output_device_combo.addItem("Default", None)
            for device in output_devices:
                device_name = f"{device.name} {'(Default)' if device.is_default else ''}"
                self.output_device_combo.addItem(device_name, device.index)
        except Exception as e:
            logger.warning(f"Could not list output devices: {e}")
            self.output_device_combo.addItem("Default", None)

        self.output_device_combo.currentIndexChanged.connect(self._on_output_device_changed)
        output_device_layout.addWidget(self.output_device_combo)
        monitor_layout.addLayout(output_device_layout)

        monitor_btn_layout = QHBoxLayout()
        monitor_btn_layout.addWidget(QLabel("Listen to:"))

        self.monitor_off_btn = QPushButton("Off")
        self.monitor_off_btn.setCheckable(True)
        self.monitor_off_btn.setChecked(True)
        self.monitor_off_btn.clicked.connect(lambda: self.set_audio_monitor(None))
        monitor_btn_layout.addWidget(self.monitor_off_btn)

        self.monitor_raw_btn = QPushButton("Raw Input")
        self.monitor_raw_btn.setCheckable(True)
        self.monitor_raw_btn.setToolTip("Listen to raw audio from radio")
        self.monitor_raw_btn.clicked.connect(lambda: self.set_audio_monitor(AudioStage.RAW))
        monitor_btn_layout.addWidget(self.monitor_raw_btn)

        self.monitor_denoised_btn = QPushButton("Denoised")
        self.monitor_denoised_btn.setCheckable(True)
        self.monitor_denoised_btn.setToolTip("Listen to audio after noise reduction")
        self.monitor_denoised_btn.clicked.connect(lambda: self.set_audio_monitor(AudioStage.DENOISED))
        monitor_btn_layout.addWidget(self.monitor_denoised_btn)

        monitor_btn_layout.addStretch()
        monitor_layout.addLayout(monitor_btn_layout)

        monitor_group.setLayout(monitor_layout)
        layout.addWidget(monitor_group)

        # Transcription display
        layout.addWidget(QLabel("Recent Transcriptions:"))
        self.transcription_text = QTextEdit()
        self.transcription_text.setReadOnly(True)
        self.transcription_text.setFont(QFont("Monospace", 9))
        self.transcription_text.setPlaceholderText("Transcriptions will appear here when voice is detected...")
        layout.addWidget(self.transcription_text)

        # Scanning status
        scan_status_layout = QHBoxLayout()
        scan_status_layout.addWidget(QLabel("Scan Status:"))
        self.scan_status_label = QLabel("Idle")
        self.scan_status_label.setStyleSheet("color: gray;")
        scan_status_layout.addWidget(self.scan_status_label)
        scan_status_layout.addStretch()
        layout.addLayout(scan_status_layout)

        group.setLayout(layout)
        return group

    def set_audio_monitor(self, stage: Optional[AudioStage]):
        """
        Enable/disable audio monitoring at a specific stage.

        Args:
            stage: AudioStage to monitor, or None to disable
        """
        # Update button states
        self.monitor_off_btn.setChecked(stage is None)
        self.monitor_raw_btn.setChecked(stage == AudioStage.RAW)
        self.monitor_denoised_btn.setChecked(stage == AudioStage.DENOISED)

        # Stop any existing monitoring
        self.audio_monitor.stop_monitoring()

        # Start monitoring if stage is specified
        if stage is not None:
            self.audio_monitor.start_monitoring(stage, volume=0.7)
            self.log(f"Audio monitor: listening to {stage.value} audio")
        else:
            self.log("Audio monitor: off")

    def _on_output_device_changed(self, index: int):
        """Handle output device selection change"""
        device_index = self.output_device_combo.itemData(index)
        device_name = self.output_device_combo.currentText()

        # Update audio monitor output device
        self.audio_monitor.output_device = device_index
        logger.info(f"Audio output device changed to: {device_name} (index={device_index})")
        self.log(f"Audio output: {device_name}")

        # If currently monitoring, restart with new device
        if self.audio_monitor.is_monitoring:
            current_stage = self.audio_monitor.monitoring_stage
            self.audio_monitor.stop_monitoring()
            self.audio_monitor.start_monitoring(current_stage, volume=0.7)

    def setup_timers(self):
        """Setup periodic update timers"""
        # Radio status update timer
        self.radio_timer = QTimer()
        self.radio_timer.timeout.connect(self.update_radio_status)
        # Will start when radio connects

        # Subprocess transcription result polling timer
        # Polls every 100ms for results from transcription subprocess
        self.transcription_poll_timer = QTimer()
        self.transcription_poll_timer.timeout.connect(self._poll_transcription_results)
        self.transcription_poll_timer.start(100)  # Poll every 100ms
        logger.debug("Transcription result polling timer started (100ms interval)")

    def connect_radio(self):
        """Connect to radio via Hamlib"""
        try:
            # Auto-start rigctld if configured
            if self.config.radio.auto_start_rigctld:
                self.log("Starting rigctld...")
                self.status_bar.showMessage("Starting rigctld...")

                # Log current config for debugging
                logger.info(f"Radio config:")
                logger.info(f"  Model: {self.config.radio.model} (ID: {self.config.radio.model_id})")
                logger.info(f"  CI-V address: '{self.config.radio.civ_address}'")
                logger.info(f"  Serial port (saved): '{self.config.radio.serial_port}'")
                logger.info(f"  Baud rate: {self.config.radio.baud_rate}")

                # Get serial port (auto-detect if not configured)
                serial_port = self.config.radio.serial_port
                if not serial_port:
                    self.log("No serial port configured, auto-detecting...")
                    serial_port = find_serial_port()
                    if not serial_port:
                        raise RadioConnectionError(
                            "No serial port configured and auto-detection failed. "
                            "Please configure serial port in Settings."
                        )
                    self.log(f"Auto-detected serial port: {serial_port}")
                else:
                    self.log(f"Using saved serial port: {serial_port}")

                # Create and start rigctld manager
                self.rigctld_manager = RigctldManager(
                    model_id=self.config.radio.model_id,
                    serial_port=serial_port,
                    baud_rate=self.config.radio.baud_rate,
                    port=self.config.radio.rigctld_port,
                    civ_address=self.config.radio.civ_address
                )

                if not self.rigctld_manager.start():
                    raise RadioConnectionError(
                        "Failed to start rigctld. Check that:\n"
                        "1. Hamlib is installed\n"
                        "2. Radio is connected and powered on\n"
                        "3. Serial port is correct\n"
                        "4. No other program is using the radio"
                    )

                self.log("rigctld started successfully")

            self.log("Connecting to rigctld...")
            self.status_bar.showMessage("Connecting to radio...")

            # Create Hamlib controller
            self.radio = HamlibController(
                host=self.config.radio.rigctld_host,
                port=self.config.radio.rigctld_port
            )

            # Connect
            self.radio.connect()

            # Get initial status
            freq = self.radio.get_frequency()
            mode, bw = self.radio.get_mode()

            self.log(f"Connected to radio: {freq/1e6:.3f} MHz, {mode}")
            self.status_bar.showMessage("Radio connected")

            # Update UI
            self.connect_btn.setText("Disconnect Radio")
            self.connect_btn.clicked.disconnect()
            self.connect_btn.clicked.connect(self.disconnect_radio)
            self.scan_btn.setEnabled(True)

            # Start update timer
            self.radio_timer.start(1000)  # Update every 1 second

        except RadioConnectionError as e:
            self.log(f"Failed to connect: {e}")
            self.status_bar.showMessage("Connection failed")
            QMessageBox.critical(self, "Connection Error", str(e))

            # Clean up rigctld if we started it
            if self.rigctld_manager:
                self.rigctld_manager.stop()
                self.rigctld_manager = None

    def disconnect_radio(self):
        """Disconnect from radio"""
        if self.radio:
            self.radio.disconnect()
            self.radio = None

            self.log("Disconnected from radio")
            self.status_bar.showMessage("Radio disconnected")

            # Update UI
            self.connect_btn.setText("Connect Radio")
            self.connect_btn.clicked.disconnect()
            self.connect_btn.clicked.connect(self.connect_radio)
            self.scan_btn.setEnabled(False)

            # Stop timer
            self.radio_timer.stop()

            # Reset displays
            self.freq_label.setText("0.000 MHz")
            self.mode_label.setText("--")
            self.smeter_label.setText("S0")

        # Stop rigctld if we started it
        if self.rigctld_manager:
            self.log("Stopping rigctld...")
            self.rigctld_manager.stop()
            self.rigctld_manager = None

    def toggle_scan(self):
        """Start or stop scanning"""
        if self.scan_btn.text() == "Start Scan":
            # Check if radio is connected
            if not self.radio or not self.radio.is_connected:
                self.log("ERROR: Radio not connected. Please connect radio first.")
                QMessageBox.warning(self, "Radio Not Connected",
                    "Please connect to the radio before starting scan.")
                return

            # Get enabled bands
            enabled_bands = [band for band, cb in self.band_checkboxes.items() if cb.isChecked()]
            if not enabled_bands:
                self.log("ERROR: No bands selected. Please select at least one band.")
                QMessageBox.warning(self, "No Bands Selected",
                    "Please select at least one band to scan.")
                return

            # Start scanner
            self.log(f"Starting scan on bands: {', '.join(enabled_bands)}")
            self.update_scan_status("Starting scan...", "yellow")

            if self.use_full_scanner and self.audio_pipeline:
                # Use full-featured BandScanner with all Phase 2-8 features
                self.log("Using FULL SCANNER with AI features:")
                self.log("  [OK] Audio processing (noise reduction + voice detection)")
                self.log("  [OK] Speech transcription (Whisper AI)")
                self.log("  [OK] Voice fingerprinting (speaker identification)")
                self.log("  [OK] SSB auto-centering")
                self.log("  [OK] Contest logic (callsign extraction)")

                # Initialize BandScanner with transcription callback
                def on_station_detected_callback(station):
                    # Emit signal for thread-safe GUI update
                    self.station_detected_signal.emit(station)

                def on_progress_update_callback(prog):
                    # Emit signal for thread-safe GUI update
                    self.progress_update_signal.emit(prog)

                self.band_scanner = BandScanner(
                    radio_controller=self.radio,
                    audio_capture=self.audio,
                    audio_pipeline=self.audio_pipeline,
                    auto_tuner=self.auto_tuner,
                    voice_database=None,  # Voice fingerprinting removed
                    callsign_extractor=self.callsign_extractor,
                    behavior_analyzer=self.behavior_analyzer,
                    band_map=self.band_map,
                    on_station_detected=on_station_detected_callback,
                    on_progress_update=on_progress_update_callback
                )

                # Save enabled bands for continuous loop
                self.enabled_bands_for_scan = enabled_bands.copy()

                # Queue up all bands to scan (from lowest freq to highest)
                self.scan_queue = []
                # Reverse the enabled_bands list to scan from lowest to highest freq
                # (since band names go from high freq to low freq: 10m has higher freq than 160m)
                for band_name in reversed(enabled_bands):
                    if band_name in BAND_PROFILES:
                        profile = BAND_PROFILES[band_name]
                        self.log(f"  Queued: {profile.name}: {profile.freq_start/1e6:.3f}-{profile.freq_end/1e6:.3f} MHz")
                        self.scan_queue.append({
                            'band_name': band_name,
                            'profile': profile
                        })

                # Start scanning first band (lowest frequency)
                if self.scan_queue:
                    self._start_next_band_scan()
            else:
                # Use simple Phase 1 scanner (frequency stepping only)
                self.log("Using BASIC SCANNER (frequency stepping only)")
                self.log("  Enable advanced features via Scanner menu for AI capabilities")

                self.scan_thread = ScanThread(
                    radio=self.radio,
                    bands=enabled_bands,
                    step_hz=self.config.scan.step_size_hz,
                    dwell_sec=2.0  # Phase 1: 2 second dwell per frequency
                )
                self.scan_thread.log_signal.connect(self.log)
                self.scan_thread.freq_update_signal.connect(self.update_freq_display)
                self.scan_thread.finished.connect(self.on_scan_finished)
                self.scan_thread.start()

            self.scan_btn.setText("Stop Scan")
            self.connect_btn.setEnabled(False)
            for cb in self.band_checkboxes.values():
                cb.setEnabled(False)
        else:
            # Stop scanner
            self.log("Stopping scan...")
            self.update_scan_status("Stopping...", "yellow")

            # Clear scan state
            self.scan_queue = []
            self.enabled_bands_for_scan = []
            self.current_scan_band = None

            if self.band_scanner:
                self.band_scanner.stop_scan()
                self.band_scanner = None
            if self.scan_thread:
                self.scan_thread.stop()
                self.scan_thread.wait(3000)  # Wait up to 3 seconds

            self.update_scan_status("Idle", "gray")
            self.scan_btn.setText("Start Scan")
            self.connect_btn.setEnabled(True)
            for cb in self.band_checkboxes.values():
                cb.setEnabled(True)

    def on_scan_finished(self):
        """Called when scan completes"""
        self.log("Scan finished")
        self.update_scan_status("Scan complete", "green")
        self.scan_btn.setText("Start Scan")
        self.connect_btn.setEnabled(True)
        for cb in self.band_checkboxes.values():
            cb.setEnabled(True)
        self.scan_thread = None

    def update_radio_status(self):
        """Update radio status display"""
        if not self.radio or not self.radio.is_connected:
            return

        try:
            # Get frequency
            freq = self.radio.get_frequency()
            self.freq_label.setText(f"{freq/1e6:.4f} MHz")

            # Update tuning indicators on all band maps
            self._update_tuning_indicators(freq)

            # Get mode (less frequently to reduce load)
            if hasattr(self, '_mode_update_counter'):
                self._mode_update_counter += 1
            else:
                self._mode_update_counter = 0

            if self._mode_update_counter % 5 == 0:  # Every 5 seconds
                mode, bw = self.radio.get_mode()
                self.mode_label.setText(mode)

            # Get S-meter
            strength = self.radio.get_strength()
            if strength >= 0:
                if strength <= 9:
                    self.smeter_label.setText(f"S{strength}")
                else:
                    self.smeter_label.setText(f"S9+{strength-9}")

        except RadioConnectionError:
            self.log("Lost connection to radio")
            self.disconnect_radio()

    def _handle_audio_levels(self, rms_level: float, peak_level: float):
        """Handle audio levels signal (thread-safe GUI update)"""
        try:
            # Update audio meter with RMS level
            audio_level_percent = int(rms_level * 100)
            self.audio_meter.setValue(audio_level_percent)
        except Exception as e:
            logger.error(f"Error handling audio levels: {e}", exc_info=True)

    def _handle_voice_detection(self, has_speech: bool, speech_ratio: float):
        """Handle voice detection signal (thread-safe GUI update)"""
        try:
            if has_speech:
                self.voice_detected_label.setStyleSheet("color: green; font-size: 20px;")
                self.speech_ratio_bar.setValue(int(speech_ratio * 100))
            else:
                self.voice_detected_label.setStyleSheet("color: gray; font-size: 20px;")
                self.speech_ratio_bar.setValue(0)
        except Exception as e:
            logger.error(f"Error handling voice detection: {e}", exc_info=True)

    def log(self, message: str):
        """Add message to log panel (thread-safe via signal)"""
        # Emit signal instead of directly manipulating widgets
        # This allows log() to be called from any thread
        self.log_signal.emit(message)
        logger.info(message)

    def _handle_log(self, message: str):
        """Handle log message on main thread (slot for log_signal)"""
        # Check if user has scrolled up (not at bottom)
        scrollbar = self.log_text.verticalScrollBar()
        at_bottom = scrollbar.value() >= (scrollbar.maximum() - 10)  # Within 10 pixels of bottom

        # Add message to text widget (safe on main thread)
        self.log_text.append(message)

        # Auto-scroll only if user was at bottom (hasn't scrolled up to read)
        if at_bottom:
            scrollbar.setValue(scrollbar.maximum())

    def update_freq_display(self, freq_hz: int):
        """Update frequency display from scan thread (prevents race condition)"""
        self.freq_label.setText(f"{freq_hz/1e6:.4f} MHz")
        # Update tuning indicators
        self._update_tuning_indicators(freq_hz)

    def _update_tuning_indicators(self, freq_hz: float):
        """
        Update tuning indicator on all band map widgets.

        Args:
            freq_hz: Current radio frequency in Hz
        """
        # Update tuning indicator for each band
        for band_name, band_widget in self.band_map_widgets.items():
            # Check if frequency falls within this band's range
            if band_name in BAND_PROFILES:
                profile = BAND_PROFILES[band_name]
                if profile.freq_start <= freq_hz <= profile.freq_end:
                    # Frequency is in this band - show indicator
                    band_widget.set_tuning_frequency(freq_hz)
                else:
                    # Frequency is not in this band - hide indicator
                    band_widget.set_tuning_frequency(None)
            else:
                band_widget.set_tuning_frequency(None)

    def _handle_station_detected(self, station):
        """Handle station detected signal (thread-safe GUI update)"""
        try:
            self.log(f"STATION on {self.current_scan_band}: {station.callsign if hasattr(station, 'callsign') else station}")
            # If station has transcripts, display them
            if hasattr(station, 'transcripts') and station.transcripts:
                for transcript in station.transcripts[-3:]:  # Last 3
                    freq_mhz = station.frequency_mhz if hasattr(station, 'frequency_mhz') else 0.0
                    callsign = station.callsign if hasattr(station, 'callsign') else None
                    self._handle_transcription(freq_mhz, transcript, callsign)
        except Exception as e:
            logger.error(f"Error handling station detected: {e}", exc_info=True)

    def _handle_progress_update(self, prog):
        """Handle progress update signal (thread-safe GUI update)"""
        try:
            status_text = f"Scanning {self.current_scan_band}: {prog.progress_percent:.1f}% ({prog.current_frequency/1e6:.3f} MHz)"
            self.update_scan_status(status_text, "green")
            if int(prog.progress_percent) % 10 == 0 and prog.progress_percent > 0:  # Log every 10%
                self.log(f"{self.current_scan_band}: {prog.progress_percent:.1f}%")
        except Exception as e:
            logger.error(f"Error handling progress update: {e}", exc_info=True)

    def _handle_transcription(self, frequency_mhz: float, transcription: str, callsign: str = None):
        """Handle transcription signal (thread-safe GUI update)"""
        try:
            from datetime import datetime
            timestamp = datetime.now().strftime("%H:%M:%S")

            # Format transcription entry
            if callsign:
                entry = f"[{timestamp}] {frequency_mhz:.3f} MHz - {callsign}: {transcription}"
            else:
                entry = f"[{timestamp}] {frequency_mhz:.3f} MHz: {transcription}"

            # Check if at bottom for auto-scroll
            scrollbar = self.transcription_text.verticalScrollBar()
            at_bottom = scrollbar.value() >= (scrollbar.maximum() - 10)

            # Add to transcription display
            self.transcription_text.append(entry)

            # Auto-scroll if at bottom
            if at_bottom:
                scrollbar.setValue(scrollbar.maximum())

            # Also add to activity log
            if callsign:
                self.log(f"TRANSCRIPTION [{callsign}]: {transcription}")
            else:
                self.log(f"TRANSCRIPTION: {transcription}")
        except Exception as e:
            logger.error(f"Error handling transcription: {e}", exc_info=True)

    def update_scan_status(self, status: str, color: str = "gray"):
        """
        Update the scan status label.

        Args:
            status: Status text
            color: Color name (gray, green, yellow, red, etc.)
        """
        self.scan_status_label.setText(status)
        self.scan_status_label.setStyleSheet(f"color: {color};")

    def on_station_clicked(self, frequency_hz: float):
        """Handle band map station click - tune radio to frequency"""
        if self.radio and self.radio.is_connected:
            try:
                self.radio.set_frequency(int(frequency_hz))
                self.log(f"Tuned to station at {frequency_hz/1e6:.3f} MHz")
            except Exception as e:
                self.log(f"Failed to tune to {frequency_hz/1e6:.3f} MHz: {e}")
        else:
            self.log("Radio not connected - cannot tune to station")

    def on_contest_changed(self, display_name: str):
        """Handle contest profile selection change"""
        if display_name in self.contest_profile_map:
            profile_id = self.contest_profile_map[display_name]
            self.config.contest.active_profile = profile_id
            self.log(f"Contest profile changed to: {display_name} ({profile_id})")
            logger.info(f"Contest profile changed to {profile_id}")

    def on_station_selected(self, station):
        """Handle station selection - update detail panel"""
        if self.station_detail_panel:
            self.station_detail_panel.set_station(station)
            logger.debug(f"Station selected: {station.callsign if station else 'None'}")

    def on_mark_station_worked(self, station):
        """Handle mark station as worked request from detail panel"""
        if station:
            from cqsentinel.bandmap.station import StationStatus
            station.worked = True
            station.status = StationStatus.WORKED
            self.log(f"Marked {station.callsign} as worked")
            # Update all band map displays
            for band_map_widget in self.band_map_widgets.values():
                band_map_widget.update_display()
            # Refresh detail panel
            if self.station_detail_panel:
                self.station_detail_panel.set_station(station)

    def on_n3fjp_toggled(self, state):
        """Handle N3FJP checkbox toggle"""
        enabled = (state == Qt.CheckState.Checked.value) if hasattr(Qt.CheckState, 'Checked') else (state == 2)
        self.config.contest.n3fjp_enabled = enabled

        if enabled:
            self.log("N3FJP integration enabled")
            self.n3fjp_status_label.setStyleSheet("color: orange;")
            self.n3fjp_status_label.setToolTip("N3FJP: Connecting...")
            # Attempt to connect to N3FJP
            self._connect_n3fjp()
        else:
            self.log("N3FJP integration disabled")
            self.n3fjp_status_label.setStyleSheet("color: gray;")
            self.n3fjp_status_label.setToolTip("N3FJP: Disabled")
            # Disconnect if connected
            if hasattr(self, 'n3fjp_client') and self.n3fjp_client:
                try:
                    self.n3fjp_client.disconnect()
                except:
                    pass
                self.n3fjp_client = None

    def on_band_selection_changed(self):
        """Handle band checkbox state changes - show/hide bands and adjust heights"""
        self.update_band_visibility()

    def update_band_visibility(self):
        """Update which band displays are visible and adjust their heights to fit viewport"""
        # Get list of enabled bands
        enabled_bands = [band for band, cb in self.band_checkboxes.items() if cb.isChecked()]
        num_visible = len(enabled_bands)

        if num_visible == 0:
            # Hide all if none selected
            for band_widget in self.band_map_widgets.values():
                band_widget.setVisible(False)
            return

        # Show/hide bands based on checkbox state
        for band_name, band_widget in self.band_map_widgets.items():
            should_be_visible = band_name in enabled_bands
            band_widget.setVisible(should_be_visible)

        # Calculate height for each visible band to fit in viewport
        # Get available height from scroll area
        available_height = self.bandmaps_scroll_area.viewport().height()

        # Reserve some space for margins/spacing (10px per band)
        spacing_total = num_visible * 10
        usable_height = max(100, available_height - spacing_total)

        # Divide equally among visible bands
        height_per_band = usable_height // num_visible if num_visible > 0 else 150

        # Ensure reasonable min/max bounds
        height_per_band = max(80, min(height_per_band, 250))

        # Apply heights to all visible bands
        for band_name in enabled_bands:
            if band_name in self.band_map_widgets:
                widget = self.band_map_widgets[band_name]
                widget.setMinimumHeight(height_per_band)
                widget.setMaximumHeight(height_per_band)

        logger.info(f"Updated band visibility: {num_visible} bands visible, {height_per_band}px each")

    def _check_voice_db_age(self):
        """Check voice database age and warn if stale.

        NOTE: Voice fingerprinting has been disabled. This method is kept for
        backward compatibility but does nothing.
        """
        # Voice fingerprinting disabled - no voice database to check
        pass

    def _connect_n3fjp(self):
        """Connect to N3FJP logging software"""
        try:
            from cqsentinel.n3fjp import N3FJPClient

            self.log(f"Connecting to N3FJP at {self.config.contest.n3fjp_host}:{self.config.contest.n3fjp_port}...")

            self.n3fjp_client = N3FJPClient(
                host=self.config.contest.n3fjp_host,
                port=self.config.contest.n3fjp_port
            )

            if self.n3fjp_client.connect():
                self.log("[OK] Connected to N3FJP successfully")
                self.n3fjp_status_label.setStyleSheet("color: green;")
                self.n3fjp_status_label.setToolTip("N3FJP: Connected")
            else:
                raise Exception("Connection failed")

        except Exception as e:
            self.log(f"[FAIL] Failed to connect to N3FJP: {e}")
            self.log("  Make sure N3FJP is running with network server enabled")
            self.n3fjp_status_label.setStyleSheet("color: red;")
            self.n3fjp_status_label.setToolTip(f"N3FJP: Failed - {e}")
            self.n3fjp_client = None

    def _start_next_band_scan(self):
        """Start scanning the next band in the queue (with continuous loop)"""
        if not self.scan_queue:
            # Queue is empty - rebuild it for continuous loop
            self.log("All bands scanned - restarting from lowest band...")

            # Rebuild scan queue from enabled bands (reverse order: lowest freq first)
            for band_name in reversed(self.enabled_bands_for_scan):
                if band_name in BAND_PROFILES:
                    profile = BAND_PROFILES[band_name]
                    self.scan_queue.append({
                        'band_name': band_name,
                        'profile': profile
                    })

            # If still empty (user stopped scan), exit
            if not self.scan_queue:
                self.log("Scan stopped")
                self.scan_finished_signal.emit()  # Thread-safe signal instead of direct call
                return

        # Get next band from queue
        band_info = self.scan_queue.pop(0)
        self.current_scan_band = band_info['band_name']
        profile = band_info['profile']

        self.log(f"Starting scan: {profile.name} ({profile.freq_start/1e6:.3f}-{profile.freq_end/1e6:.3f} MHz)")

        # Get the band map for this specific band
        current_band_map = self.band_maps.get(self.current_scan_band)

        # Create callbacks with transcription support (using signals for thread safety)
        def on_station_detected_callback(station):
            # Emit signal for thread-safe GUI update
            self.station_detected_signal.emit(station)

        def on_progress_update_callback(prog):
            # Emit signal for thread-safe GUI update
            self.progress_update_signal.emit(prog)

        # Reinitialize BandScanner with the correct band map
        self.band_scanner = BandScanner(
            radio_controller=self.radio,
            audio_capture=self.audio,
            audio_pipeline=self.audio_pipeline,
            auto_tuner=self.auto_tuner,
            voice_database=None,  # Voice fingerprinting removed
            callsign_extractor=self.callsign_extractor,
            behavior_analyzer=self.behavior_analyzer,
            band_map=current_band_map,
            on_station_detected=on_station_detected_callback,
            on_progress_update=on_progress_update_callback
        )

        # Start scan for this band
        self.band_scanner.start_scan(
            freq_start=profile.freq_start,
            freq_end=profile.freq_end,
            step_size=self.config.scan.step_size_hz
        )

        # Monitor scan completion in background
        import threading
        import time
        def monitor_scan():
            while self.band_scanner and self.band_scanner.is_scanning():
                time.sleep(1)

            # Scan finished, start next band (continuous loop will rebuild queue if empty)
            self.log(f"Band {self.current_scan_band} complete")
            self._start_next_band_scan()

        monitor_thread = threading.Thread(target=monitor_scan, daemon=True)
        monitor_thread.start()

    def show_settings(self):
        """Show settings dialog"""
        dialog = SettingsDialog(self)
        if dialog.exec():
            # Settings were saved, reload config
            self.config = get_config()
            self.log("Settings updated")
            logger.info("Settings updated by user")

    def run_audio_diagnostics(self):
        """Run audio subsystem diagnostic tests"""
        from cqsentinel.audio.diagnostics import AudioDiagnostics

        # Show message
        QMessageBox.information(
            self,
            "Audio Diagnostics",
            "The audio diagnostic tests will now run in the console window.\n\n"
            "Check the console for detailed results.\n\n"
            "Make sure to make noise during input tests!"
        )

        # Run diagnostics (output goes to console)
        try:
            input_dev = self.audio.device if self.audio else None
            output_dev = self.audio_monitor.output_device if self.audio_monitor else None

            self.log("Running audio diagnostics... (check console)")
            logger.info("Starting audio diagnostics")

            # Run in background thread so UI doesn't freeze
            import threading
            def run_diag():
                try:
                    result = AudioDiagnostics.run_full_diagnostic(input_dev, output_dev)
                    if result:
                        self.log("[OK] Audio diagnostics passed - check console for details")
                    else:
                        self.log("[WARNING] Audio diagnostics found issues - check console")
                except Exception as e:
                    logger.error(f"Diagnostic error: {e}", exc_info=True)
                    self.log(f"[ERROR] Diagnostic failed: {e}")

            threading.Thread(target=run_diag, daemon=True).start()

        except Exception as e:
            logger.error(f"Failed to run diagnostics: {e}", exc_info=True)
            QMessageBox.critical(self, "Error", f"Failed to run diagnostics:\n{e}")

    def show_about(self):
        """Show about dialog"""
        about_text = f"""
        <h2>CQSentinel v{self.get_version()}</h2>
        <p><b>SSB Contest Band Scanner with AI Voice Recognition</b></p>
        <p>The first practical implementation of an "SSB Skimmer" for ham radio contesting.</p>
        <p>Built with Python, PyQt5, Hamlib, and modern AI technologies.</p>
        <p><a href="https://github.com/xmutantson/CQSentinel">GitHub Repository</a></p>
        """
        QMessageBox.about(self, "About CQSentinel", about_text)

    def get_version(self) -> str:
        """Get application version"""
        try:
            from .. import __version__
            return __version__
        except:
            return "0.1.0"

    def closeEvent(self, event):
        """Handle window close event"""
        # Stop transcription polling timer FIRST to prevent warning spam during shutdown
        if hasattr(self, 'transcription_poll_timer'):
            logger.debug("Stopping transcription poll timer")
            self.transcription_poll_timer.stop()

        # Disconnect radio
        if self.radio:
            self.disconnect_radio()

        # Stop audio
        if self.audio:
            self.audio.stop_stream()

        # Save configuration
        try:
            get_config_manager().save()
        except:
            pass

        # Stop transcription subprocess
        if hasattr(self, 'subprocess_transcriber') and self.subprocess_transcriber:
            logger.debug("Stopping transcription subprocess")
            self.subprocess_transcriber.stop()

        # Stop QueueListener for thread-safe logging
        if hasattr(self, '_queue_listener'):
            logger.debug("Stopping QueueListener")
            self._queue_listener.stop()

        event.accept()
