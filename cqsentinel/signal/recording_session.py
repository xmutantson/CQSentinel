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
        sample_rate: int = 16000,
        recording_duration: float = 90.0,  # 90 seconds
        detection_window: float = 2.0,  # 2 seconds for signal validation
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
            sample_rate: Audio sample rate
            recording_duration: How long to record (seconds)
            detection_window: Audio window for signal validation (seconds)
            on_state_change: Callback when session state changes
            on_result: Callback when session completes
            on_stuck: Callback(frequency_hz) when stuck on noise frequency
        """
        self.carrier_detector = carrier_detector
        self.transcript_analyzer = transcript_analyzer
        self.transcriber = transcriber
        self.vad = vad
        self.sample_rate = sample_rate
        self.recording_duration = recording_duration
        self.detection_window = detection_window

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

        # Frequency tracking (set by SignalScanner)
        self.current_frequency_hz = 0.0

        logger.info(
            f"RecordingSession initialized: {recording_duration}s recording, "
            f"{detection_window}s detection window, VAD={'enabled' if vad else 'disabled'}"
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
            # Signal lost
            self._set_state(SessionState.IDLE)
            self.carrier_detector.reset()
            self.vad_check_failures = 0  # Reset VAD failures
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
                else:
                    logger.debug(
                        f"VAD check failed ({self.vad_check_failures}/{self.max_vad_failures}), "
                        f"waiting for voice..."
                    )
            return None

        # Still validating...
        # TODO: Could auto-tune here based on tuning_correction_hz
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
