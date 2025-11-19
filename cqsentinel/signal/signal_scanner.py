"""
Signal Scanner - Orchestrates the complete signal detection to band map pipeline.

Coordinates:
1. Signal detection (CarrierDetector)
2. Audio recording (RecordingSession)
3. Transcription (SubprocessTranscriber)
4. Analysis (TranscriptAnalyzer)
5. Band map updates (BandMapState)
"""

import logging
import re
import time
from typing import Dict, Optional, Callable
from datetime import datetime

from ..signal.carrier_detector import CarrierDetector
from ..signal.transcript_analyzer import TranscriptAnalyzer
from ..signal.recording_session import RecordingSession, SessionResult, SessionState
from ..bandmap.station import BandMapState, BandMapStation, StationStatus, ActivityType
from ..scanner.profiles import BAND_PROFILES
from ..radio.auto_tuner import SSBAutoTuner
from ..radio.fm_tuner import FMAutoTuner
from ..radio.pitch import PitchDetector

logger = logging.getLogger(__name__)


def frequency_to_band(frequency_hz: float) -> Optional[str]:
    """
    Determine which band a frequency belongs to.

    Args:
        frequency_hz: Frequency in Hz

    Returns:
        Band name (e.g., "20m", "6m") or None if outside all bands
    """
    for band_name, profile in BAND_PROFILES.items():
        # Skip special profiles (field_day_, quick_, etc.)
        if "_" in band_name:
            continue
        if profile.freq_start <= frequency_hz <= profile.freq_end:
            return band_name
    return None


def count_unique_words(text: str, min_word_length: int = 3) -> int:
    """
    Count unique English words in a transcript.

    Used to validate that a transcript contains real speech
    (not just noise or carrier artifacts).

    Args:
        text: Transcript text
        min_word_length: Minimum word length to count (default 3)

    Returns:
        Number of unique words of minimum length
    """
    if not text:
        return 0

    # Extract words (alphanumeric sequences)
    words = re.findall(r'\b[a-zA-Z]+\b', text.lower())

    # Filter by length and get unique
    unique_words = set(w for w in words if len(w) >= min_word_length)

    return len(unique_words)


class SignalScanner:
    """
    Manages the complete signal detection -> transcription -> band map pipeline.

    This is the main orchestrator that:
    1. Monitors radio frequency and audio
    2. Detects and validates signals
    3. Records 90 seconds of audio
    4. Transcribes and analyzes
    5. Updates band maps with discovered stations
    """

    def __init__(
        self,
        radio=None,
        transcriber=None,
        pitch_detector=None,
        vad=None,  # VoiceActivityDetector for speech validation
        band_maps: Optional[Dict[str, BandMapState]] = None,
        sample_rate: int = 16000,
        noise_skip_threshold: int = 3,  # Mark as noise after N stuck occurrences
        auto_center_enabled: bool = True,  # Enable auto-centering
        on_station_added: Optional[Callable] = None,
        on_session_state_change: Optional[Callable] = None,
    ):
        """
        Initialize signal scanner.

        Args:
            radio: Radio control interface (for frequency and S-meter)
            transcriber: SubprocessTranscriber instance
            pitch_detector: PitchDetector instance (for centering)
            vad: VoiceActivityDetector for validating speech before recording
            band_maps: Dictionary of band name -> BandMapState
            sample_rate: Audio sample rate
            noise_skip_threshold: Mark frequency as noise after N stuck occurrences (0=disabled)
            auto_center_enabled: Enable automatic signal centering
            on_station_added: Callback when station is added to band map
            on_session_state_change: Callback when recording session state changes
        """
        self.radio = radio
        self.transcriber = transcriber
        self.vad = vad
        self.sample_rate = sample_rate
        self.band_maps = band_maps or {}
        self.noise_skip_threshold = noise_skip_threshold
        self.auto_center_enabled = auto_center_enabled

        # Callbacks
        self.on_station_added = on_station_added
        self.on_session_state_change = on_session_state_change

        # Initialize pitch detector if not provided
        if pitch_detector is None and auto_center_enabled:
            logger.info("Creating PitchDetector for auto-centering")
            # Try to get CREPE setting from config
            try:
                from ..config import get_config
                config = get_config()
                use_crepe = config.audio.use_crepe_pitch
            except:
                use_crepe = False
            pitch_detector = PitchDetector(sample_rate=sample_rate, use_crepe=use_crepe)

        # Initialize components
        self.carrier_detector = CarrierDetector(
            radio=radio,
            pitch_detector=pitch_detector,
            sample_rate=sample_rate
        )

        self.transcript_analyzer = TranscriptAnalyzer()

        # Create auto-tuners for different modes
        ssb_auto_tuner = None
        fm_auto_tuner = None

        if auto_center_enabled and radio:
            # SSB auto-tuner (USB/LSB)
            if pitch_detector:
                logger.info("Creating SSBAutoTuner for USB/LSB auto-centering")
                # Try to get CREPE setting from config
                try:
                    from ..config import get_config
                    config = get_config()
                    use_crepe = config.audio.use_crepe_pitch
                except:
                    use_crepe = False

                ssb_auto_tuner = SSBAutoTuner(
                    sample_rate=sample_rate,
                    max_iterations=3,
                    tolerance_hz=50,
                    sideband="USB",  # Will be set dynamically
                    use_crepe=use_crepe
                )

            # FM auto-tuner
            logger.info("Creating FMAutoTuner for FM auto-centering")
            # Try to get FM settings from config
            try:
                from ..config import get_config
                config = get_config()
                scan_range = config.scan.fm_scan_range_hz
                scan_step = config.scan.fm_scan_step_hz
                power_threshold = config.scan.fm_power_threshold_db
            except:
                scan_range = 10000
                scan_step = 100
                power_threshold = -80.0

            fm_auto_tuner = FMAutoTuner(
                sample_rate=sample_rate,
                scan_range_hz=scan_range,
                scan_step_hz=scan_step,
                power_threshold_db=power_threshold
            )

        self.recording_session = RecordingSession(
            carrier_detector=self.carrier_detector,
            transcript_analyzer=self.transcript_analyzer,
            transcriber=transcriber,
            vad=vad,  # Pass VAD for speech validation
            radio=radio,  # Pass radio for auto-centering
            auto_tuner=ssb_auto_tuner,  # SSB auto-tuner
            fm_tuner=fm_auto_tuner,  # FM auto-tuner
            sample_rate=sample_rate,
            recording_duration=90.0,  # 90 second recordings
            auto_center_enabled=auto_center_enabled,
            on_state_change=self._on_session_state_change,
            on_result=self._on_session_result,
            on_stuck=self._on_stuck  # Handle stuck events for noise tracking
        )

        # Statistics
        self.sessions_completed = 0
        self.stations_discovered = 0
        self.contests_detected = 0

        # Current state
        self.current_frequency = 0.0
        self.is_active = False

        logger.info(f"SignalScanner initialized (noise_skip_threshold={noise_skip_threshold})")

    def start(self):
        """Start the signal scanner."""
        self.is_active = True
        logger.info("SignalScanner started")

    def stop(self):
        """Stop the signal scanner."""
        self.is_active = False
        self.recording_session.cancel()
        logger.info("SignalScanner stopped")

    def process_audio(self, audio):
        """
        Process incoming audio samples.

        This should be called continuously with audio chunks from the radio.

        Args:
            audio: Audio samples (float32 numpy array)
        """
        if not self.is_active:
            return

        # Update current frequency from radio
        if self.radio:
            try:
                freq = self.radio.get_frequency()
                if freq and freq > 0:
                    self.current_frequency = freq
                    # Pass frequency to recording session for transcription tracking
                    self.recording_session.current_frequency_hz = freq
            except Exception as e:
                logger.debug(f"Failed to get frequency from radio: {e}")

        # Process audio through recording session
        self.recording_session.process_audio(audio)

    def _on_session_state_change(self, old_state: SessionState, new_state: SessionState):
        """Handle session state changes."""
        logger.debug(f"Session state: {old_state.value} -> {new_state.value}")

        if self.on_session_state_change:
            self.on_session_state_change(old_state, new_state)

    def _on_stuck(self, frequency_hz: float):
        """
        Handle stuck event (signal detected but no voice after VAD validation).

        This marks the frequency as a potential local noise source.

        Args:
            frequency_hz: Frequency where we got stuck
        """
        if self.noise_skip_threshold <= 0:
            return  # Feature disabled

        # Determine which band this frequency belongs to
        band_name = frequency_to_band(frequency_hz)
        if not band_name:
            logger.debug(f"Stuck frequency {frequency_hz/1e6:.3f} MHz not in any known band")
            return

        # Get the band map for this band
        if band_name not in self.band_maps:
            logger.debug(f"No band map for {band_name} to track stuck frequency")
            return

        band_map = self.band_maps[band_name]

        # Mark noise occurrence
        count = band_map.mark_noise_occurrence(frequency_hz)

        # Log if threshold reached
        if count >= self.noise_skip_threshold:
            logger.warning(
                f"Frequency {frequency_hz/1e6:.3f} MHz marked as LOCAL NOISE "
                f"({count} occurrences, threshold={self.noise_skip_threshold}) - "
                f"will skip during scanning"
            )
        else:
            logger.info(
                f"Noise occurrence at {frequency_hz/1e6:.3f} MHz "
                f"({count}/{self.noise_skip_threshold})"
            )

    def _on_session_result(self, result: SessionResult):
        """
        Handle completed recording session.

        This is where the magic happens - we take the transcription analysis
        and add the station to the appropriate band map.
        """
        self.sessions_completed += 1

        # Get the frequency this recording was made at
        frequency = self.current_frequency
        if frequency <= 0:
            logger.warning("No valid frequency for session result, cannot add to band map")
            return

        # Determine which band this frequency belongs to
        band_name = frequency_to_band(frequency)
        if not band_name:
            logger.warning(f"Frequency {frequency/1e6:.3f} MHz not in any known band")
            return

        # Get the band map for this band
        if band_name not in self.band_maps:
            logger.warning(f"No band map for {band_name}")
            return

        band_map = self.band_maps[band_name]

        # Log the session result
        logger.info(
            f"Session {result.session_id} complete on {band_name} "
            f"({frequency/1e6:.3f} MHz): "
            f"transcript={len(result.transcript)} chars"
        )

        if result.analysis:
            logger.info(
                f"Analysis: is_contest={result.analysis.is_contest}, "
                f"callsign={result.analysis.running_station_callsign}, "
                f"confidence={result.analysis.confidence:.2f}, "
                f"type={result.analysis.contest_type}"
            )

            # Add or update station in band map
            if result.analysis.is_contest and result.analysis.running_station_callsign:
                station = self._add_station_to_bandmap(
                    band_map=band_map,
                    frequency=frequency,
                    result=result
                )

                self.stations_discovered += 1
                self.contests_detected += 1

                logger.info(
                    f"[DISCOVERED] {result.analysis.running_station_callsign} "
                    f"running contest on {frequency/1e6:.3f} MHz ({band_name})"
                )

                # Trigger callback
                if self.on_station_added and station:
                    self.on_station_added(station, band_name, result)

            elif result.analysis.is_contest:
                # Contest detected but no callsign extracted
                logger.info(
                    f"Contest activity detected on {frequency/1e6:.3f} MHz "
                    f"but callsign not extracted"
                )

                # Still add to band map as unknown station
                station = band_map.add_or_update_station(
                    frequency=frequency,
                    callsign=None,
                    contestness_score=result.analysis.confidence * 100,
                    activity_type=ActivityType.CONTEST,
                    is_run_station=True,
                    status=StationStatus.NEW
                )
                station.add_transcript(result.transcript)

            else:
                # Not contest activity - check if it's a valid ragchew
                unique_words = count_unique_words(result.transcript)
                min_unique_words = 10  # Require at least 10 unique words for valid speech

                logger.info(
                    f"Non-contest activity on {frequency/1e6:.3f} MHz "
                    f"(confidence={result.analysis.confidence:.2f}, "
                    f"unique_words={unique_words})"
                )

                if unique_words >= min_unique_words:
                    # Add as ragchew - valid speech but not a contest
                    station = band_map.add_or_update_station(
                        frequency=frequency,
                        callsign=None,  # No callsign extracted for ragchews
                        contestness_score=result.analysis.confidence * 100,
                        activity_type=ActivityType.RAGCHEW,
                        is_run_station=False,
                        status=StationStatus.NEW
                    )
                    station.add_transcript(result.transcript)

                    logger.info(
                        f"[RAGCHEW] Added ragchew activity on {frequency/1e6:.3f} MHz "
                        f"({band_name}) - {unique_words} unique words"
                    )

                    # Trigger callback
                    if self.on_station_added and station:
                        self.on_station_added(station, band_name, result)
                else:
                    logger.info(
                        f"Skipping signal on {frequency/1e6:.3f} MHz - "
                        f"insufficient speech content ({unique_words} unique words < {min_unique_words})"
                    )

    def _add_station_to_bandmap(
        self,
        band_map: BandMapState,
        frequency: float,
        result: SessionResult
    ) -> BandMapStation:
        """
        Add discovered station to the band map.

        Args:
            band_map: BandMapState instance
            frequency: Frequency in Hz
            result: SessionResult from recording session

        Returns:
            BandMapStation instance
        """
        analysis = result.analysis

        # Create or update station
        station = band_map.add_or_update_station(
            frequency=frequency,
            callsign=analysis.running_station_callsign,
            contestness_score=analysis.confidence * 100,  # Convert to 0-100 scale
            activity_type=ActivityType.CONTEST,
            is_run_station=True,
            status=StationStatus.NEW
        )

        # Add transcript to station history
        station.add_transcript(result.transcript)

        # Update signal info if available
        if result.signal_info:
            station.signal_strength = result.signal_info.s_meter

        # Update other metadata
        station.mode = "SSB"
        station.estimated_qso_rate = self._estimate_qso_rate(result.transcript)

        return station

    def _estimate_qso_rate(self, transcript: str) -> float:
        """
        Estimate QSO rate from transcript.

        Counts exchanges and estimates QSOs per hour.

        Args:
            transcript: Full transcript text

        Returns:
            Estimated QSOs per hour
        """
        # Count occurrences of common exchange markers
        exchange_markers = [
            "five nine", "59", "five seven", "57",
            "thanks", "thank you", "73", "qsl", "roger"
        ]

        text_lower = transcript.lower()
        exchange_count = sum(
            text_lower.count(marker) for marker in exchange_markers
        )

        # Estimate: if we see N exchanges in 90 seconds,
        # extrapolate to per hour (90s = 1.5 minutes)
        # Each QSO has ~2-3 exchanges (caller + runner)
        qsos_in_90s = exchange_count / 2.5
        qsos_per_hour = qsos_in_90s * 40  # 90s × 40 = 3600s = 1 hour

        return round(qsos_per_hour, 1)

    def get_statistics(self) -> dict:
        """
        Get scanner statistics.

        Returns:
            Dictionary with scanner statistics
        """
        return {
            "sessions_completed": self.sessions_completed,
            "stations_discovered": self.stations_discovered,
            "contests_detected": self.contests_detected,
            "current_frequency": self.current_frequency,
            "is_active": self.is_active,
            "session_state": self.recording_session.state.value,
            "recording_progress": self.recording_session.get_recording_progress()
        }

    def get_session_state(self) -> SessionState:
        """Get current recording session state."""
        return self.recording_session.state

    def is_recording(self) -> bool:
        """Check if currently recording."""
        return self.recording_session.state == SessionState.RECORDING

    def get_recording_progress(self) -> float:
        """Get recording progress (0.0 to 1.0)."""
        return self.recording_session.get_recording_progress()
