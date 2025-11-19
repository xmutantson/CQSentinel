"""
Recording Session Manager

Coordinates the signal detection -> recording -> transcription -> analysis pipeline.
Records 90 seconds of contiguous audio once a valid signal is detected and centered.
"""

import numpy as np
import logging
import time
from typing import Optional, Callable
from dataclasses import dataclass
from enum import Enum

from .carrier_detector import CarrierDetector, SignalState, SignalInfo
from .transcript_analyzer import TranscriptAnalyzer, ContestAnalysis

logger = logging.getLogger(__name__)


class SessionState(Enum):
    """Recording session states"""
    IDLE = "idle"  # Waiting for signal
    DETECTING = "detecting"  # Signal detected, validating
    RECORDING = "recording"  # Recording 90s of audio
    TRANSCRIBING = "transcribing"  # Waiting for transcription
    ANALYZING = "analyzing"  # Analyzing transcript
    COMPLETE = "complete"  # Session finished


@dataclass
class SessionResult:
    """Results from a recording session"""
    session_id: int
    frequency_hz: float = 0.0
    duration_seconds: float = 0.0
    transcript: str = ""
    analysis: Optional[ContestAnalysis] = None
    signal_info: Optional[SignalInfo] = None
    success: bool = False
    error: Optional[str] = None


class RecordingSession:
    """
    Manages a single 90-second recording session.

    Flow:
    1. Wait for CarrierDetector to reach CENTERED state
    2. Start recording 90 seconds of contiguous audio
    3. Submit to transcription (Whisper)
    4. Analyze transcript for contest detection and callsign extraction
    5. Return results
    """

    def __init__(
        self,
        carrier_detector: CarrierDetector,
        transcript_analyzer: TranscriptAnalyzer,
        transcriber=None,  # SubprocessTranscriber
        vad=None,  # VoiceActivityDetector for validation
        radio=None,  # Radio controller for auto-centering
        auto_tuner=None,  # SSBAutoTuner for USB/LSB
        fm_tuner=None,  # FMAutoTuner for FM
        sample_rate: int = 16000,
        recording_duration: float = 90.0,  # 90 seconds
        detection_window: float = 2.0,  # 2 seconds for signal validation
        auto_center_enabled: bool = True,  # Enable auto-centering
        on_state_change: Optional[Callable] = None,
        on_result: Optional[Callable] = None,
        on_stuck: Optional[Callable] = None,  # Called when stuck on noise
    ):
        """
        Initialize recording session manager.

        Args:
            carrier_detector: CarrierDetector instance
            transcript_analyzer: TranscriptAnalyzer instance
            transcriber: SubprocessTranscriber instance
            vad: VoiceActivityDetector for validating speech before recording
            radio: Radio controller for auto-centering
            auto_tuner: SSBAutoTuner for USB/LSB auto-centering
            fm_tuner: FMAutoTuner for FM auto-centering
            sample_rate: Audio sample rate
            recording_duration: How long to record (seconds)
            detection_window: Audio window for signal validation (seconds)
            auto_center_enabled: Enable automatic signal centering
            on_state_change: Callback when session state changes
            on_result: Callback when session completes
            on_stuck: Callback(frequency_hz) when stuck on noise frequency
        """
        self.carrier_detector = carrier_detector
        self.transcript_analyzer = transcript_analyzer
        self.transcriber = transcriber
        self.vad = vad
        self.radio = radio
        self.auto_tuner = auto_tuner
        self.fm_tuner = fm_tuner
        self.sample_rate = sample_rate
        self.recording_duration = recording_duration
        self.detection_window = detection_window
        self.auto_center_enabled = auto_center_enabled

        # Callbacks
        self.on_state_change = on_state_change
        self.on_result = on_result
        self.on_stuck = on_stuck

        # Session state
        self.state = SessionState.IDLE
        self.session_id = 0
        self.current_result = None

        # Recording buffer
        self.recording_samples = int(recording_duration * sample_rate)
        self.recording_buffer = np.zeros(self.recording_samples, dtype=np.float32)
        self.recording_position = 0
        self.recording_start_time = 0.0

        # Detection buffer (for validating signal)
        self.detection_samples = int(detection_window * sample_rate)
        self.detection_buffer = np.zeros(self.detection_samples, dtype=np.float32)
        self.detection_position = 0

        # Transcription tracking
        self.pending_transcription_id = None

        # VAD validation tracking
        self.vad_check_failures = 0
        self.max_vad_failures = 3  # Skip after 3 consecutive VAD failures

        # Auto-centering tracking
        self.centering_attempted = False
        self.centering_in_progress = False  # Prevent signal loss during centering from causing loops

        # Frequency tracking (set by SignalScanner)
        self.current_frequency_hz = 0.0

        logger.info(
            f"RecordingSession initialized: {recording_duration}s recording, "
            f"{detection_window}s detection window, VAD={'enabled' if vad else 'disabled'}, "
            f"auto_center={'enabled' if auto_center_enabled else 'disabled'}"
        )

    def _set_state(self, new_state: SessionState):
        """Update session state and trigger callback."""
        old_state = self.state
        self.state = new_state

        if old_state != new_state:
            logger.info(f"Session state: {old_state.value} -> {new_state.value}")
            if self.on_state_change:
                self.on_state_change(old_state, new_state)

    def process_audio(self, audio: np.ndarray) -> Optional[SessionResult]:
        """
        Process incoming audio samples.

        This should be called continuously with audio chunks.
        Returns SessionResult when a session completes.

        Args:
            audio: Audio samples (float32)

        Returns:
            SessionResult if session just completed, None otherwise
        """
        # Update detection buffer (rolling window)
        self._update_detection_buffer(audio)

        # Handle current state
        if self.state == SessionState.IDLE:
            return self._handle_idle()

        elif self.state == SessionState.DETECTING:
            return self._handle_detecting()

        elif self.state == SessionState.RECORDING:
            return self._handle_recording(audio)

        elif self.state == SessionState.TRANSCRIBING:
            return self._handle_transcribing()

        elif self.state == SessionState.ANALYZING:
            return self._handle_analyzing()

        elif self.state == SessionState.COMPLETE:
            # Reset for next session
            result = self.current_result
            self._reset_session()
            return result

        return None

    def _update_detection_buffer(self, audio: np.ndarray):
        """Update rolling detection buffer."""
        samples_to_add = len(audio)

        if samples_to_add >= self.detection_samples:
            # New audio is longer than buffer, take last chunk
            self.detection_buffer = audio[-self.detection_samples:].copy()
            self.detection_position = self.detection_samples
        else:
            # Shift buffer and add new samples
            shift = self.detection_samples - samples_to_add
            self.detection_buffer[:shift] = self.detection_buffer[samples_to_add:]
            self.detection_buffer[shift:] = audio
            self.detection_position = min(
                self.detection_position + samples_to_add, self.detection_samples
            )

    def _handle_idle(self) -> Optional[SessionResult]:
        """IDLE state: Wait for signal detection."""
        # Check if we have enough detection audio
        if self.detection_position < self.detection_samples:
            return None

        # Update carrier detector state
        signal_state = self.carrier_detector.update_state(self.detection_buffer)

        if signal_state in (SignalState.SIGNAL_DETECTED, SignalState.VOICE_PRESENT):
            self._set_state(SessionState.DETECTING)
            logger.info("Signal detected, entering DETECTING state")

        return None

    def _handle_detecting(self) -> Optional[SessionResult]:
        """DETECTING state: Validate signal and check centering."""
        signal_state = self.carrier_detector.update_state(self.detection_buffer)

        if signal_state == SignalState.IDLE:
            # Signal lost - but don't reset if we're in the middle of auto-centering
            # (FM auto-centering switches to CW mode which may cause temporary signal loss)
            if not self.centering_in_progress:
                self._set_state(SessionState.IDLE)
                self.carrier_detector.reset()
                self.vad_check_failures = 0  # Reset VAD failures
                self.centering_attempted = False  # Reset centering for next signal
            else:
                logger.debug("[AUTO-CENTER] Signal lost during auto-centering, ignoring (expected during mode switch)")
            return None

        if signal_state == SignalState.CENTERED:
            # Signal is centered, but validate with VAD before recording
            if self._validate_vad():
                # VAD confirms voice, start recording!
                self._start_recording()
            else:
                # VAD says no voice (likely FM carrier or noise)
                self.vad_check_failures += 1
                if self.vad_check_failures >= self.max_vad_failures:
                    logger.warning(
                        f"No voice detected after {self.max_vad_failures} VAD checks, "
                        f"skipping this signal (likely carrier/noise at {self.current_frequency_hz/1e6:.3f} MHz)"
                    )

                    # Report stuck event for noise tracking
                    if self.on_stuck and self.current_frequency_hz > 0:
                        self.on_stuck(self.current_frequency_hz)

                    # Reset and move on
                    self._set_state(SessionState.IDLE)
                    self.carrier_detector.reset()
                    self.vad_check_failures = 0
                    self.centering_attempted = False  # Reset centering for next signal
                    self.centering_in_progress = False  # Reset centering progress
                else:
                    logger.debug(
                        f"VAD check failed ({self.vad_check_failures}/{self.max_vad_failures}), "
                        f"waiting for voice..."
                    )
            return None

        # For FM mode: auto-center immediately on SIGNAL_DETECTED (skip voice check)
        # For SSB mode: wait for VOICE_PRESENT (speech band energy check)
        should_auto_center = False
        if signal_state == SignalState.SIGNAL_DETECTED:
            # Check if this is FM mode
            if self.radio:
                try:
                    mode, _ = self.radio.get_mode()
                    mode = mode.upper()
                    if mode == "FM":
                        # FM detected - auto-center immediately without voice check
                        logger.debug("FM mode: auto-centering on signal detection (skipping voice energy check)")
                        should_auto_center = True
                except Exception as e:
                    logger.debug(f"Could not get radio mode: {e}")

        # Auto-center if voice present (SSB) or signal detected (FM)
        if signal_state == SignalState.VOICE_PRESENT or should_auto_center:
            if self.auto_center_enabled and not self.centering_attempted:
                if signal_state == SignalState.VOICE_PRESENT:
                    logger.info("Voice detected, attempting auto-centering...")
                self._attempt_auto_center()
            else:
                # Just log tuning suggestion (SSB only)
                if signal_state == SignalState.VOICE_PRESENT:
                    tuning_suggestion = self.carrier_detector.get_tuning_suggestion()
                    if abs(tuning_suggestion) > 0:
                        logger.debug(f"Tuning suggestion: {tuning_suggestion:+.0f} Hz")

        return None

    def _validate_vad(self) -> bool:
        """
        Validate speech presence using Silero VAD.

        Returns:
            True if voice detected, False if carrier/noise only
        """
        if self.vad is None:
            # No VAD available, skip validation
            return True

        try:
            # Use VAD to check for actual speech in detection buffer
            has_speech = self.vad.has_speech(self.detection_buffer, min_duration=0.3)
            if has_speech:
                # Double-check with speech ratio
                speech_ratio = self.vad.get_speech_ratio(self.detection_buffer)
                if speech_ratio >= 0.1:  # At least 10% speech
                    logger.info(f"VAD confirmed voice: speech_ratio={speech_ratio:.2f}")
                    return True
                else:
                    logger.debug(f"VAD speech ratio too low: {speech_ratio:.2f}")
                    return False
            else:
                logger.debug("VAD detected no speech (likely carrier/noise)")
                return False
        except Exception as e:
            logger.warning(f"VAD validation error: {e}, proceeding without validation")
            return True  # Fail-open if VAD errors

    def _attempt_auto_center(self):
        """Attempt to auto-center signal using mode-specific algorithm."""
        logger.info("[AUTO-CENTER] ========== AUTO-CENTERING STARTED ==========")

        if not self.radio:
            logger.warning("[AUTO-CENTER] No radio controller available for auto-centering")
            self.centering_attempted = True
            return

        # Set flag to prevent signal loss from resetting state during mode switches
        self.centering_in_progress = True
        logger.debug("[AUTO-CENTER] Set centering_in_progress=True to prevent state reset during mode switch")

        try:
            # Get current mode
            logger.debug("[AUTO-CENTER] Querying radio mode...")
            mode, bandwidth = self.radio.get_mode()
            mode = mode.upper()
            logger.info(
                f"[AUTO-CENTER] Mode={mode}, Bandwidth={bandwidth}, "
                f"Frequency={self.current_frequency_hz/1e6:.4f} MHz"
            )

            if mode in ["USB", "LSB"]:
                # SSB auto-centering using pitch detection
                logger.info(f"[AUTO-CENTER] Using SSB pitch-based centering for {mode}")

                if self.auto_tuner:
                    logger.debug(f"[AUTO-CENTER] SSBAutoTuner available, setting sideband to {mode}")
                    self.auto_tuner.set_sideband(mode)

                    logger.info(f"[AUTO-CENTER] Starting SSB auto-centering...")
                    result = self.auto_tuner.auto_center(
                        radio_controller=self.radio,
                        audio_capture_func=self._capture_audio_for_centering,
                        initial_frequency=int(self.current_frequency_hz),
                        capture_duration=2.0  # 2 seconds per iteration
                    )

                    if result.success:
                        logger.info(
                            f"[AUTO-CENTER] ✓ SSB auto-centered: {result.final_frequency/1e6:.4f} MHz "
                            f"(offset: {result.final_offset:+d} Hz, {result.iterations} iterations)"
                        )
                        # Update our frequency tracking
                        self.current_frequency_hz = float(result.final_frequency)
                    else:
                        logger.warning(
                            f"[AUTO-CENTER] ✗ SSB auto-centering failed after {result.iterations} iterations, "
                            f"final offset: {result.final_offset:+d} Hz"
                        )
                else:
                    logger.warning("[AUTO-CENTER] No SSBAutoTuner available for SSB centering")

            elif mode == "FM":
                # FM auto-centering using power-based edge detection
                logger.info("[AUTO-CENTER] Using FM power-based edge detection")

                if self.fm_tuner:
                    logger.info("[AUTO-CENTER] FMAutoTuner available, starting edge detection...")
                    logger.info("[AUTO-CENTER] FM centering will switch to CW mode temporarily for edge scanning")

                    result = self.fm_tuner.auto_center(
                        radio_controller=self.radio,
                        audio_capture_func=self._capture_audio_for_centering,
                        initial_frequency=int(self.current_frequency_hz)
                    )

                    if result.success:
                        logger.info(
                            f"[AUTO-CENTER] ✓ FM auto-centered: {result.final_frequency/1e6:.4f} MHz "
                            f"(BW: {result.bandwidth_hz/1000:.1f} kHz, "
                            f"edges: {result.signal_start_hz/1e6:.4f} - {result.signal_end_hz/1e6:.4f} MHz)"
                        )
                        # Update our frequency tracking
                        self.current_frequency_hz = float(result.final_frequency)
                        # For FM, force carrier_detector to CENTERED state (no pitch-based detection needed)
                        logger.debug("[AUTO-CENTER] FM centered, forcing CarrierDetector to CENTERED state")
                        self.carrier_detector.state = SignalState.CENTERED
                    else:
                        logger.warning("[AUTO-CENTER] ✗ FM auto-centering failed to detect signal edges")
                else:
                    logger.warning("[AUTO-CENTER] No FMAutoTuner available for FM centering")
                    logger.debug(f"[AUTO-CENTER] self.fm_tuner = {self.fm_tuner}")

            else:
                logger.warning(f"[AUTO-CENTER] Auto-centering not supported for mode {mode}")

        except Exception as e:
            logger.error(f"[AUTO-CENTER] ✗ Exception during auto-centering: {e}", exc_info=True)

        finally:
            self.centering_in_progress = False
            self.centering_attempted = True
            logger.info("[AUTO-CENTER] ========== AUTO-CENTERING COMPLETE ==========")
            logger.debug(f"[AUTO-CENTER] Set centering_in_progress=False, centering_attempted=True")

    def _capture_audio_for_centering(self, duration: float = 2.0) -> np.ndarray:
        """
        Capture audio for auto-centering purposes.

        This is a helper method passed to auto-tuners that need to capture
        fresh audio samples during the centering process.

        Args:
            duration: Duration to capture in seconds

        Returns:
            Audio samples (float32)
        """
        # Import here to avoid circular dependency
        import sounddevice as sd

        try:
            samples = int(duration * self.sample_rate)
            logger.debug(f"Capturing {duration}s of audio for centering ({samples} samples)")

            # Capture audio directly from sounddevice
            audio = sd.rec(samples, samplerate=self.sample_rate, channels=1, dtype='float32')
            sd.wait()  # Wait for recording to complete

            return audio.flatten()

        except Exception as e:
            logger.error(f"Audio capture failed: {e}")
            # Return silence on error
            return np.zeros(int(duration * self.sample_rate), dtype=np.float32)

    def _start_recording(self):
        """Begin 90-second recording."""
        self.session_id += 1
        self.recording_position = 0
        self.recording_start_time = time.time()
        self.recording_buffer.fill(0)

        self.current_result = SessionResult(
            session_id=self.session_id,
            frequency_hz=self.current_frequency_hz,  # Save frequency for this recording
            signal_info=self.carrier_detector.last_signal_info
        )

        self._set_state(SessionState.RECORDING)
        logger.info(
            f"Started recording session {self.session_id} "
            f"at {self.current_frequency_hz/1e6:.3f} MHz ({self.recording_duration}s)"
        )

    def _handle_recording(self, audio: np.ndarray) -> Optional[SessionResult]:
        """RECORDING state: Capture 90 seconds of audio."""
        samples_to_add = len(audio)
        space_left = self.recording_samples - self.recording_position

        if samples_to_add >= space_left:
            # Recording complete!
            self.recording_buffer[self.recording_position:] = audio[:space_left]
            self.recording_position = self.recording_samples

            duration = time.time() - self.recording_start_time
            self.current_result.duration_seconds = duration
            logger.info(f"Recording complete: {duration:.1f}s captured")

            # Submit for transcription
            self._submit_transcription()
            return None
        else:
            # Add to buffer
            self.recording_buffer[self.recording_position:self.recording_position + samples_to_add] = audio
            self.recording_position += samples_to_add

            # Log progress periodically
            progress = self.recording_position / self.recording_samples * 100
            if int(progress) % 10 == 0 and int(progress) > 0:
                elapsed = time.time() - self.recording_start_time
                logger.debug(f"Recording progress: {progress:.0f}% ({elapsed:.1f}s)")

        return None

    def _submit_transcription(self):
        """Submit recorded audio for transcription."""
        if not self.transcriber:
            logger.error("No transcriber available")
            self.current_result.success = False
            self.current_result.error = "No transcriber available"
            self._set_state(SessionState.COMPLETE)
            return

        try:
            self.pending_transcription_id = self.transcriber.transcribe_async(
                audio=self.recording_buffer.copy(),
                sample_rate=self.sample_rate,
                frequency_hz=self.current_frequency_hz  # Pass frequency for tracking
            )
            logger.info(
                f"Submitted {self.recording_duration}s audio for transcription "
                f"(request_id={self.pending_transcription_id}, frequency={self.current_frequency_hz/1e6:.3f} MHz)"
            )
            self._set_state(SessionState.TRANSCRIBING)

        except Exception as e:
            logger.error(f"Failed to submit transcription: {e}")
            self.current_result.success = False
            self.current_result.error = str(e)
            self._set_state(SessionState.COMPLETE)

    def _handle_transcribing(self) -> Optional[SessionResult]:
        """TRANSCRIBING state: Wait for transcription result."""
        if not self.transcriber:
            self._set_state(SessionState.COMPLETE)
            return None

        # Check for result (non-blocking)
        try:
            result = self.transcriber.get_result(timeout=0)
            if result is not None and result.request_id == self.pending_transcription_id:
                if result.success:
                    self.current_result.transcript = result.text
                    logger.info(f"Transcription received: {len(result.text)} chars")
                    self._set_state(SessionState.ANALYZING)
                else:
                    self.current_result.success = False
                    self.current_result.error = result.error
                    self._set_state(SessionState.COMPLETE)
        except Exception as e:
            logger.debug(f"Error checking transcription result: {e}")

        return None

    def _handle_analyzing(self) -> Optional[SessionResult]:
        """ANALYZING state: Analyze transcript for contest/callsign."""
        try:
            analysis = self.transcript_analyzer.analyze_contest(
                self.current_result.transcript
            )
            self.current_result.analysis = analysis
            self.current_result.success = True

            logger.info(
                f"Analysis complete: is_contest={analysis.is_contest}, "
                f"callsign={analysis.running_station_callsign}, "
                f"confidence={analysis.confidence:.2f}"
            )

            # Trigger result callback
            if self.on_result:
                self.on_result(self.current_result)

            self._set_state(SessionState.COMPLETE)

        except Exception as e:
            logger.error(f"Analysis failed: {e}")
            self.current_result.success = False
            self.current_result.error = str(e)
            self._set_state(SessionState.COMPLETE)

        return None

    def _reset_session(self):
        """Reset session state for next recording."""
        self.state = SessionState.IDLE
        self.current_result = None
        self.recording_position = 0
        self.pending_transcription_id = None
        self.centering_attempted = False  # Reset for next signal
        self.centering_in_progress = False  # Reset centering progress
        self.carrier_detector.reset()
        logger.debug("Session reset, ready for next signal")

    def cancel(self):
        """Cancel current session."""
        logger.info(f"Cancelling session (was in {self.state.value} state)")
        self._reset_session()

    def get_recording_progress(self) -> float:
        """Get recording progress (0.0 to 1.0)."""
        if self.state != SessionState.RECORDING:
            return 0.0
        return self.recording_position / self.recording_samples

    def is_active(self) -> bool:
        """Check if session is actively processing (not idle)."""
        return self.state != SessionState.IDLE
