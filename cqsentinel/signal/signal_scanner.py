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
import time
from typing import Dict, Optional, Callable
from datetime import datetime

from ..signal.carrier_detector import CarrierDetector
from ..signal.transcript_analyzer import TranscriptAnalyzer
from ..signal.recording_session import RecordingSession, SessionResult, SessionState
from ..bandmap.station import BandMapState, BandMapStation, StationStatus, ActivityType
from ..scanner.profiles import BAND_PROFILES

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


class SignalScanner:
    """
    Manages the complete signal detection → transcription → band map pipeline.

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
        band_maps: Optional[Dict[str, BandMapState]] = None,
        sample_rate: int = 16000,
        on_station_added: Optional[Callable] = None,
        on_session_state_change: Optional[Callable] = None,
    ):
        """
        Initialize signal scanner.

        Args:
            radio: Radio control interface (for frequency and S-meter)
            transcriber: SubprocessTranscriber instance
            pitch_detector: PitchDetector instance (for centering)
            band_maps: Dictionary of band name -> BandMapState
            sample_rate: Audio sample rate
            on_station_added: Callback when station is added to band map
            on_session_state_change: Callback when recording session state changes
        """
        self.radio = radio
        self.transcriber = transcriber
        self.sample_rate = sample_rate
        self.band_maps = band_maps or {}

        # Callbacks
        self.on_station_added = on_station_added
        self.on_session_state_change = on_session_state_change

        # Initialize components
        self.carrier_detector = CarrierDetector(
            radio=radio,
            pitch_detector=pitch_detector,
            sample_rate=sample_rate
        )

        self.transcript_analyzer = TranscriptAnalyzer()

        self.recording_session = RecordingSession(
            carrier_detector=self.carrier_detector,
            transcript_analyzer=self.transcript_analyzer,
            transcriber=transcriber,
            sample_rate=sample_rate,
            recording_duration=90.0,  # 90 second recordings
            on_state_change=self._on_session_state_change,
            on_result=self._on_session_result
        )

        # Statistics
        self.sessions_completed = 0
        self.stations_discovered = 0
        self.contests_detected = 0

        # Current state
        self.current_frequency = 0.0
        self.is_active = False

        logger.info("SignalScanner initialized")

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
            except Exception as e:
                logger.debug(f"Failed to get frequency from radio: {e}")

        # Process audio through recording session
        self.recording_session.process_audio(audio)

    def _on_session_state_change(self, old_state: SessionState, new_state: SessionState):
        """Handle session state changes."""
        logger.debug(f"Session state: {old_state.value} → {new_state.value}")

        if self.on_session_state_change:
            self.on_session_state_change(old_state, new_state)

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
                # Not contest activity
                logger.info(
                    f"Non-contest activity on {frequency/1e6:.3f} MHz "
                    f"(confidence={result.analysis.confidence:.2f})"
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
