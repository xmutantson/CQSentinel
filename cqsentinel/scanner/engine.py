"""
Band scanning engine.

Automated band sweeping with:
- Intelligent dwell times (early exit if no voice)
- SSB auto-centering when voice detected
- Full audio processing pipeline
- Voice fingerprinting and operator tracking
- Contest logic (callsign extraction, contestness scoring)
- Band map updates
- N3FJP dupe/multiplier checking
"""

import logging
import time
import threading
from typing import Optional, Callable, Dict, Any
from enum import Enum
from dataclasses import dataclass, field
from datetime import datetime

logger = logging.getLogger(__name__)


class ScanState(Enum):
    """Scanning state machine states."""
    IDLE = "idle"
    SCANNING = "scanning"
    VOICE_DETECTED = "voice_detected"
    CENTERING = "centering"
    LISTENING = "listening"
    PROCESSING = "processing"
    MOVING = "moving"
    PAUSED = "paused"
    ERROR = "error"


@dataclass
class ScanProgress:
    """Scan progress tracking."""
    state: ScanState = ScanState.IDLE
    current_frequency: float = 0.0  # Hz
    frequency_start: float = 0.0
    frequency_end: float = 0.0
    frequencies_scanned: int = 0
    total_frequencies: int = 0

    # Stations
    stations_detected: int = 0
    new_stations: int = 0
    worked_stations: int = 0
    multipliers: int = 0

    # Timing
    scan_start_time: Optional[datetime] = None
    elapsed_seconds: float = 0.0
    estimated_remaining_seconds: float = 0.0

    # Current station
    current_station_callsign: Optional[str] = None
    current_station_contestness: float = 0.0

    @property
    def progress_percent(self) -> float:
        """Calculate scan progress percentage."""
        if self.total_frequencies == 0:
            return 0.0
        return (self.frequencies_scanned / self.total_frequencies) * 100.0

    @property
    def scan_rate(self) -> float:
        """Frequencies scanned per minute."""
        if self.elapsed_seconds == 0:
            return 0.0
        return (self.frequencies_scanned / self.elapsed_seconds) * 60.0


class BandScanner:
    """
    Automated band scanning engine.

    Integrates all CQSentinel components for intelligent band sweeping:
    - Radio control for frequency tuning
    - Audio capture and processing
    - SSB auto-centering
    - Voice fingerprinting
    - Contest logic
    - Band map updates
    - N3FJP integration

    Usage:
        scanner = BandScanner(
            radio_controller=radio,
            audio_capture=audio_cap,
            audio_pipeline=pipeline,
            auto_tuner=tuner,
            voice_database=voice_db,
            callsign_extractor=cs_extractor,
            behavior_analyzer=behavior,
            band_map=band_map,
            n3fjp_client=n3fjp,
            multiplier_tracker=mult_tracker
        )

        # Start scanning
        scanner.start_scan(
            freq_start=14000000,
            freq_end=14350000,
            step_size=1000
        )

        # Monitor progress
        while scanner.is_scanning():
            progress = scanner.get_progress()
            print(f"Progress: {progress.progress_percent:.1f}%")
            time.sleep(1)
    """

    def __init__(
        self,
        radio_controller,
        audio_capture,
        audio_pipeline,
        auto_tuner,
        voice_database=None,  # Voice fingerprinting disabled, parameter kept for compatibility
        callsign_extractor=None,
        behavior_analyzer=None,
        band_map=None,
        n3fjp_client=None,
        multiplier_tracker=None,
        # Scan parameters
        step_size_hz: int = 1000,
        scan_speed_steps_per_sec: float = 1.0,
        dwell_with_voice_sec: float = 60.0,
        dwell_without_voice_sec: float = 3.0,
        quick_check_duration: float = 2.0,
        min_contestness_score: float = 40.0,
        # Callbacks
        on_station_detected: Optional[Callable] = None,
        on_progress_update: Optional[Callable] = None
    ):
        """
        Initialize band scanner.

        Args:
            radio_controller: HamlibController instance
            audio_capture: AudioCapture instance
            audio_pipeline: AudioPipeline instance
            auto_tuner: SSBAutoTuner instance
            voice_database: VoiceDatabase instance
            callsign_extractor: CallsignExtractor instance
            behavior_analyzer: BehaviorAnalyzer instance
            band_map: BandMapState instance
            n3fjp_client: N3FJPClient instance (optional)
            multiplier_tracker: MultiplierTracker instance (optional)
            step_size_hz: Frequency step in Hz (default: 1 kHz)
            scan_speed_steps_per_sec: Scan rate (0.2 to 5.0 steps/sec)
            dwell_with_voice_sec: Dwell time when voice detected
            dwell_without_voice_sec: Dwell time when no voice
            quick_check_duration: Quick voice check duration
            min_contestness_score: Minimum contestness to process
            on_station_detected: Callback when station detected
            on_progress_update: Callback for progress updates
        """
        # Components
        self.radio = radio_controller
        self.audio_cap = audio_capture
        self.pipeline = audio_pipeline
        self.tuner = auto_tuner
        self.voice_db = voice_database
        self.callsign_ext = callsign_extractor
        self.behavior = behavior_analyzer
        self.band_map = band_map
        self.n3fjp = n3fjp_client
        self.mult_tracker = multiplier_tracker

        # Parameters
        self.step_size_hz = step_size_hz
        self.scan_speed = scan_speed_steps_per_sec
        self.dwell_with_voice = dwell_with_voice_sec
        self.dwell_without_voice = dwell_without_voice_sec
        self.quick_check_duration = quick_check_duration
        self.min_contestness = min_contestness_score

        # Calculate delay between steps based on scan speed
        self.step_delay = 1.0 / max(0.2, min(5.0, scan_speed_steps_per_sec))

        # Callbacks
        self.on_station_detected = on_station_detected
        self.on_progress_update = on_progress_update

        # State
        self.progress = ScanProgress()
        self._scan_thread: Optional[threading.Thread] = None
        self._stop_requested = False
        self._pause_requested = False
        self._lock = threading.Lock()

        logger.info(f"BandScanner initialized (scan_speed={scan_speed_steps_per_sec} steps/sec, delay={self.step_delay:.2f}s)")

    def start_scan(
        self,
        freq_start: float,
        freq_end: float,
        step_size: Optional[int] = None
    ):
        """
        Start band scan.

        Args:
            freq_start: Start frequency in Hz
            freq_end: End frequency in Hz
            step_size: Frequency step in Hz (optional)
        """
        with self._lock:
            if self.is_scanning():
                logger.warning("Scan already in progress")
                return

            # Set mode based on band:
            # VHF/UHF (above 30 MHz) = FM
            # HF LSB for 40m and below (<=10 MHz)
            # HF USB for above 40m
            if freq_start >= 30_000_000:
                radio_mode = "FM"
                bandwidth = 12000  # FM bandwidth
            elif freq_start <= 10_000_000:
                radio_mode = "LSB"
                bandwidth = 2400
            else:
                radio_mode = "USB"
                bandwidth = 2400

            try:
                self.radio.set_mode(radio_mode, bandwidth)
                logger.info(f"Set mode to {radio_mode} for {freq_start/1e6:.3f} MHz")
                time.sleep(0.5)  # Give radio time to switch modes
            except Exception as e:
                logger.warning(f"Failed to set mode to {radio_mode}: {e}")

            # Initialize progress
            self.progress = ScanProgress(
                state=ScanState.SCANNING,
                frequency_start=freq_start,
                frequency_end=freq_end,
                current_frequency=freq_start,
                scan_start_time=datetime.now()
            )

            if step_size:
                self.step_size_hz = step_size

            # Calculate total frequencies
            freq_range = freq_end - freq_start
            self.progress.total_frequencies = int(freq_range / self.step_size_hz)

            # Start scan thread
            self._stop_requested = False
            self._pause_requested = False
            self._scan_thread = threading.Thread(
                target=self._scan_loop,
                args=(freq_start, freq_end),
                daemon=True
            )
            self._scan_thread.start()

            logger.info(
                f"Started scan: {freq_start/1e6:.3f}-{freq_end/1e6:.3f} MHz, "
                f"step={self.step_size_hz} Hz, mode={radio_mode}, "
                f"speed={self.scan_speed} steps/sec"
            )

    def stop_scan(self):
        """Stop scanning."""
        with self._lock:
            self._stop_requested = True
            logger.info("Stop requested")

    def pause_scan(self):
        """Pause scanning."""
        with self._lock:
            self._pause_requested = True
            self.progress.state = ScanState.PAUSED
            logger.info("Pause requested")

    def resume_scan(self):
        """Resume scanning."""
        with self._lock:
            self._pause_requested = False
            self.progress.state = ScanState.SCANNING
            logger.info("Scan resumed")

    def is_scanning(self) -> bool:
        """Check if scan is active."""
        return (
            self._scan_thread is not None and
            self._scan_thread.is_alive() and
            not self._stop_requested
        )

    def get_progress(self) -> ScanProgress:
        """Get current scan progress."""
        with self._lock:
            # Update elapsed time
            if self.progress.scan_start_time:
                elapsed = (datetime.now() - self.progress.scan_start_time).total_seconds()
                self.progress.elapsed_seconds = elapsed

                # Estimate remaining time
                if self.progress.frequencies_scanned > 0:
                    time_per_freq = elapsed / self.progress.frequencies_scanned
                    remaining_freqs = self.progress.total_frequencies - self.progress.frequencies_scanned
                    self.progress.estimated_remaining_seconds = time_per_freq * remaining_freqs

            return self.progress

    def _scan_loop(self, freq_start: float, freq_end: float):
        """Main scan loop (runs in thread)."""
        try:
            freq = freq_start

            while freq <= freq_end and not self._stop_requested:
                # Handle pause
                while self._pause_requested and not self._stop_requested:
                    time.sleep(0.1)

                if self._stop_requested:
                    break

                # Process frequency
                self._process_frequency(freq)

                # Move to next frequency
                freq += self.step_size_hz

                with self._lock:
                    self.progress.current_frequency = freq
                    self.progress.frequencies_scanned += 1

                # Progress callback
                if self.on_progress_update:
                    try:
                        self.on_progress_update(self.get_progress())
                    except Exception as e:
                        logger.error(f"Progress callback error: {e}")

            # Scan complete
            with self._lock:
                self.progress.state = ScanState.IDLE

            logger.info("Scan complete")

        except Exception as e:
            logger.error(f"Scan error: {e}", exc_info=True)
            with self._lock:
                self.progress.state = ScanState.ERROR

    def _process_frequency(self, frequency: float):
        """
        Process a single frequency.

        Args:
            frequency: Frequency in Hz
        """
        try:
            # Tune radio
            self.progress.state = ScanState.MOVING
            self.radio.set_frequency(int(frequency))
            time.sleep(0.1)  # Settling time

            # Quick voice check
            self.progress.state = ScanState.VOICE_DETECTED
            quick_audio = self.audio_cap.record(self.quick_check_duration)
            quick_result = self.pipeline.process_quick(quick_audio)

            if not quick_result['has_speech']:
                # No voice, move on after scan speed delay
                logger.debug(f"{frequency/1e6:.3f} MHz: No voice")
                time.sleep(self.step_delay)
                return

            logger.info(f"{frequency/1e6:.3f} MHz: Voice detected!")

            # Voice detected - auto-center
            self.progress.state = ScanState.CENTERING
            center_result = self.tuner.auto_center(
                self.radio,
                self.audio_cap.record,
                frequency,
                capture_duration=3.0
            )

            if center_result.success:
                centered_freq = center_result.final_frequency
                logger.info(
                    f"Centered: {centered_freq/1e6:.3f} MHz "
                    f"({center_result.iterations} iterations)"
                )
            else:
                centered_freq = frequency
                logger.warning(f"Centering failed, using {frequency/1e6:.3f} MHz")

            # Capture full sample
            self.progress.state = ScanState.LISTENING
            full_audio = self.audio_cap.record(self.dwell_with_voice)

            # Process audio
            self.progress.state = ScanState.PROCESSING
            result = self.pipeline.process(full_audio)

            # Extract callsigns
            full_transcript = ' '.join(seg.text for seg in result.transcripts)
            callsigns = self.callsign_ext.get_unique_callsigns(full_transcript)

            # Analyze behavior
            voice_seg_dicts = [
                {
                    'speaker_id': i,
                    'start_time': seg.start_time,
                    'end_time': seg.end_time
                }
                for i, seg in enumerate(result.voice_segments)
            ]

            behavior_result = self.behavior.analyze(
                full_transcript,
                result.duration,
                voice_seg_dicts
            )

            # Skip if low contestness
            if behavior_result.score < self.min_contestness:
                logger.debug(
                    f"{centered_freq/1e6:.3f} MHz: Low contestness "
                    f"({behavior_result.score:.0f}), skipping"
                )
                return

            # Process station
            self._process_station(
                frequency=centered_freq,
                callsigns=callsigns,
                behavior=behavior_result,
                voice_segments=result.voice_segments,
                transcripts=result.transcripts
            )

        except Exception as e:
            logger.error(f"Error processing {frequency/1e6:.3f} MHz: {e}")

    def _process_station(
        self,
        frequency: float,
        callsigns: list,
        behavior,
        voice_segments,
        transcripts
    ):
        """
        Process detected station.

        Args:
            frequency: Station frequency
            callsigns: Extracted callsigns
            behavior: Behavior analysis result
            voice_segments: Voice fingerprints
            transcripts: Transcript segments
        """
        # Get best callsign
        callsign = callsigns[0] if callsigns else None

        logger.info(
            f"Station: {frequency/1e6:.3f} MHz, "
            f"Call: {callsign or 'Unknown'}, "
            f"Contestness: {behavior.score:.0f}"
        )

        # Update progress
        with self._lock:
            self.progress.stations_detected += 1
            self.progress.current_station_callsign = callsign
            self.progress.current_station_contestness = behavior.score

        # Check voice database (if available)
        voice_id = None
        if self.voice_db and voice_segments:
            for seg in voice_segments:
                match = self.voice_db.find_matching_voice(seg.embedding)
                if match:
                    voice_id, similarity = match
                    operator = self.voice_db.get_operator(voice_id)

                    if operator.worked:
                        logger.info(f"Already worked via voice: {operator.callsign}")
                        with self._lock:
                            self.progress.worked_stations += 1
                        # Skip this station
                        return

                    break

        # Check N3FJP dupe
        is_dupe = False
        is_mult = False

        if callsign and self.n3fjp:
            try:
                is_dupe = self.n3fjp.check_dupe(callsign)

                if self.mult_tracker:
                    call_info = self.n3fjp.get_call_info(callsign)
                    is_mult = self.mult_tracker.is_new_multiplier(callsign, call_info)
            except Exception as e:
                logger.error(f"N3FJP error: {e}")

        # Determine status
        from ..bandmap import StationStatus, ActivityType

        if is_dupe:
            status = StationStatus.WORKED
            with self._lock:
                self.progress.worked_stations += 1
        elif is_mult:
            status = StationStatus.MULTIPLIER
            with self._lock:
                self.progress.multipliers += 1
        else:
            status = StationStatus.NEW
            with self._lock:
                self.progress.new_stations += 1

        # Add to band map
        station = self.band_map.add_or_update_station(
            frequency=frequency,
            callsign=callsign,
            voice_id=voice_id,
            status=status,
            worked=is_dupe,
            is_multiplier=is_mult,
            contestness_score=behavior.score,
            activity_type=ActivityType.RUN_STATION if behavior.is_run_station else ActivityType.UNCLEAR,
            is_run_station=behavior.is_run_station
        )

        # Add transcripts
        if transcripts:
            for seg in transcripts[:3]:  # Last 3
                station.add_transcript(seg.text)

        # Update voice database (if available)
        if self.voice_db and callsign and voice_segments:
            for seg in voice_segments:
                self.voice_db.add_or_update(
                    seg.embedding,
                    metadata={
                        'callsign': callsign,
                        'frequency': frequency,
                        'contestness_score': behavior.score,
                        'is_run_station': behavior.is_run_station
                    }
                )

        # Station detected callback
        if self.on_station_detected:
            try:
                self.on_station_detected(station)
            except Exception as e:
                logger.error(f"Station callback error: {e}")

        logger.info(
            f"Added station: {callsign or 'Unknown'} - "
            f"{status.value.upper()}"
            f"{' (MULT!)' if is_mult else ''}"
        )
