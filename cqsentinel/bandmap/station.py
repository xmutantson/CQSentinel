"""
Band map station data models.

Represents stations detected on the band with their metadata,
status, and activity information.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, List
from enum import Enum

logger = logging.getLogger(__name__)


class StationStatus(Enum):
    """Station work status."""
    NEW = "new"  # Not worked yet
    WORKED = "worked"  # Already worked (dupe)
    MULTIPLIER = "multiplier"  # New multiplier
    UNCLEAR = "unclear"  # Status unknown


class ActivityType(Enum):
    """Station activity type."""
    RUN_STATION = "run_station"
    SEARCH_POUNCE = "search_pounce"
    RAGCHEW = "ragchew"
    UNCLEAR = "unclear"


@dataclass
class BandMapStation:
    """
    Represents a station on the band map.

    Contains all metadata about a detected station including
    frequency, callsign, status, and activity analysis.
    """
    # Core identification
    frequency: float  # Hz
    callsign: Optional[str] = None
    voice_id: Optional[str] = None  # UUID from voice database

    # Status
    status: StationStatus = StationStatus.UNCLEAR
    worked: bool = False
    is_multiplier: bool = False

    # Signal quality
    signal_strength: Optional[float] = None  # S-meter reading (0-9+)
    snr: Optional[float] = None  # Signal-to-noise ratio

    # Activity analysis
    contestness_score: float = 0.0  # 0-100
    activity_type: ActivityType = ActivityType.UNCLEAR
    is_run_station: bool = False

    # Contest data
    exchange: Optional[str] = None  # e.g., "2A WWA", "Zone 7"
    section: Optional[str] = None
    zone: Optional[str] = None
    grid: Optional[str] = None

    # Timestamps
    first_heard: datetime = field(default_factory=datetime.now)
    last_heard: datetime = field(default_factory=datetime.now)
    last_updated: datetime = field(default_factory=datetime.now)

    # Transcripts
    transcripts: List[str] = field(default_factory=list)
    last_transcript: Optional[str] = None

    # Metadata
    mode: str = "SSB"
    band: Optional[str] = None  # "20m", "40m", etc.
    estimated_qso_rate: float = 0.0  # QSOs per hour

    def __post_init__(self):
        """Calculate derived fields."""
        if self.band is None and self.frequency:
            self.band = self._frequency_to_band(self.frequency)

    @property
    def age_seconds(self) -> float:
        """Time since last heard in seconds."""
        return (datetime.now() - self.last_heard).total_seconds()

    @property
    def age_minutes(self) -> float:
        """Time since last heard in minutes."""
        return self.age_seconds / 60.0

    @property
    def frequency_mhz(self) -> float:
        """Frequency in MHz."""
        return self.frequency / 1e6

    @property
    def is_stale(self) -> bool:
        """Check if station data is stale (>10 minutes old)."""
        return self.age_minutes > 10.0

    @property
    def is_recent(self) -> bool:
        """Check if station was heard recently (<2 minutes)."""
        return self.age_minutes < 2.0

    @property
    def display_status(self) -> str:
        """Get human-readable status."""
        if self.is_multiplier:
            return "MULT"
        elif self.worked:
            return "DUPE"
        elif self.status == StationStatus.NEW:
            return "NEW"
        else:
            return "?"

    @property
    def display_callsign(self) -> str:
        """Get display callsign (or Unknown if not identified)."""
        return self.callsign or "Unknown"

    def update_timestamp(self):
        """Update last heard/updated timestamps."""
        now = datetime.now()
        self.last_heard = now
        self.last_updated = now

    def add_transcript(self, text: str, max_transcripts: int = 10):
        """
        Add a transcript to the station's history.

        Args:
            text: Transcript text
            max_transcripts: Maximum transcripts to keep
        """
        self.transcripts.append(text)
        self.last_transcript = text

        # Keep only recent transcripts
        if len(self.transcripts) > max_transcripts:
            self.transcripts = self.transcripts[-max_transcripts:]

        self.update_timestamp()

    def update_from_analysis(
        self,
        contestness_score: Optional[float] = None,
        activity_type: Optional[ActivityType] = None,
        is_run_station: Optional[bool] = None,
        callsign: Optional[str] = None,
        exchange: Optional[str] = None
    ):
        """
        Update station data from contest analysis.

        Args:
            contestness_score: Contestness score (0-100)
            activity_type: Activity type classification
            is_run_station: Whether this is a run station
            callsign: Callsign (if extracted)
            exchange: Exchange information
        """
        if contestness_score is not None:
            self.contestness_score = contestness_score

        if activity_type is not None:
            self.activity_type = activity_type

        if is_run_station is not None:
            self.is_run_station = is_run_station

        if callsign is not None:
            self.callsign = callsign

        if exchange is not None:
            self.exchange = exchange

        self.update_timestamp()

    def _frequency_to_band(self, freq_hz: float) -> str:
        """
        Convert frequency to band name.

        Args:
            freq_hz: Frequency in Hz

        Returns:
            Band name (e.g., "20m")
        """
        freq_mhz = freq_hz / 1e6

        # Ham band ranges (SSB portions)
        if 1.8 <= freq_mhz < 2.0:
            return "160m"
        elif 3.5 <= freq_mhz < 4.0:
            return "80m"
        elif 7.0 <= freq_mhz < 7.3:
            return "40m"
        elif 14.0 <= freq_mhz < 14.35:
            return "20m"
        elif 21.0 <= freq_mhz < 21.45:
            return "15m"
        elif 28.0 <= freq_mhz < 29.7:
            return "10m"
        else:
            return "Unknown"

    def matches_frequency(self, freq_hz: float, tolerance_hz: float = 1000) -> bool:
        """
        Check if this station matches a frequency within tolerance.

        Args:
            freq_hz: Frequency to check
            tolerance_hz: Tolerance in Hz (default: 1 kHz)

        Returns:
            True if frequency matches
        """
        return abs(self.frequency - freq_hz) <= tolerance_hz

    def __repr__(self) -> str:
        """String representation."""
        return (
            f"BandMapStation({self.frequency_mhz:.3f} MHz, "
            f"{self.display_callsign}, {self.display_status})"
        )


class BandMapState:
    """
    Manages the state of the band map.

    Maintains a collection of stations detected on the band,
    handles updates, and provides filtering/sorting capabilities.
    """

    def __init__(self, band: Optional[str] = None):
        """
        Initialize band map state.

        Args:
            band: Band name (e.g., "20m")
        """
        self.band = band
        self.stations: List[BandMapStation] = []
        self.created_at = datetime.now()
        self.last_scan: Optional[datetime] = None

        # Local noise tracking - frequencies with persistent non-voice signals
        # Dict[int, int] mapping frequency (Hz) to stuck occurrence count
        self.noise_frequencies: dict[int, int] = {}

        logger.info(f"BandMapState initialized (band: {band})")

    def add_or_update_station(
        self,
        frequency: float,
        **kwargs
    ) -> BandMapStation:
        """
        Add a new station or update existing one.

        Args:
            frequency: Station frequency in Hz
            **kwargs: Additional station parameters

        Returns:
            BandMapStation instance (new or updated)
        """
        # Look for existing station at this frequency
        existing = self.find_station_by_frequency(frequency, tolerance_hz=1000)

        if existing:
            # Update existing station
            for key, value in kwargs.items():
                if hasattr(existing, key) and value is not None:
                    setattr(existing, key, value)
            existing.update_timestamp()
            logger.debug(f"Updated station at {existing.frequency_mhz:.3f} MHz")
            return existing
        else:
            # Create new station
            station = BandMapStation(frequency=frequency, **kwargs)
            self.stations.append(station)
            logger.info(f"Added new station at {station.frequency_mhz:.3f} MHz")
            return station

    def find_station_by_frequency(
        self,
        frequency: float,
        tolerance_hz: float = 1000
    ) -> Optional[BandMapStation]:
        """
        Find station by frequency.

        Args:
            frequency: Frequency in Hz
            tolerance_hz: Tolerance in Hz

        Returns:
            BandMapStation or None
        """
        for station in self.stations:
            if station.matches_frequency(frequency, tolerance_hz):
                return station
        return None

    def find_station_by_callsign(self, callsign: str) -> Optional[BandMapStation]:
        """
        Find station by callsign.

        Args:
            callsign: Callsign to search for

        Returns:
            BandMapStation or None
        """
        callsign_upper = callsign.upper()
        for station in self.stations:
            if station.callsign and station.callsign.upper() == callsign_upper:
                return station
        return None

    def get_stations_sorted(
        self,
        sort_by: str = "frequency",
        reverse: bool = False
    ) -> List[BandMapStation]:
        """
        Get stations sorted by specified field.

        Args:
            sort_by: Field to sort by ('frequency', 'contestness_score', 'last_heard')
            reverse: Reverse sort order

        Returns:
            Sorted list of stations
        """
        if sort_by == "frequency":
            return sorted(self.stations, key=lambda s: s.frequency, reverse=reverse)
        elif sort_by == "contestness_score":
            return sorted(self.stations, key=lambda s: s.contestness_score, reverse=reverse)
        elif sort_by == "last_heard":
            return sorted(self.stations, key=lambda s: s.last_heard, reverse=reverse)
        else:
            return self.stations.copy()

    def get_new_stations(self) -> List[BandMapStation]:
        """Get list of unworked stations."""
        return [s for s in self.stations if s.status == StationStatus.NEW and not s.worked]

    def get_multipliers(self) -> List[BandMapStation]:
        """Get list of new multiplier stations."""
        return [s for s in self.stations if s.is_multiplier and not s.worked]

    def get_worked_stations(self) -> List[BandMapStation]:
        """Get list of worked stations."""
        return [s for s in self.stations if s.worked]

    def get_recent_stations(self, max_age_minutes: float = 5.0) -> List[BandMapStation]:
        """
        Get stations heard recently.

        Args:
            max_age_minutes: Maximum age in minutes

        Returns:
            List of recent stations
        """
        return [s for s in self.stations if s.age_minutes <= max_age_minutes]

    def remove_stale_stations(self, max_age_minutes: float = 15.0) -> int:
        """
        Remove stations that haven't been heard recently.

        Args:
            max_age_minutes: Maximum age before removal

        Returns:
            Number of stations removed
        """
        before_count = len(self.stations)
        self.stations = [s for s in self.stations if s.age_minutes <= max_age_minutes]
        removed = before_count - len(self.stations)

        if removed > 0:
            logger.info(f"Removed {removed} stale stations")

        return removed

    def clear(self):
        """Clear all stations from the band map."""
        count = len(self.stations)
        self.stations.clear()
        logger.info(f"Cleared band map ({count} stations removed)")

    def update_scan_time(self):
        """Update the last scan timestamp."""
        self.last_scan = datetime.now()

    def get_statistics(self) -> dict:
        """
        Get band map statistics.

        Returns:
            Dictionary with statistics
        """
        return {
            'total_stations': len(self.stations),
            'new_stations': len(self.get_new_stations()),
            'multipliers': len(self.get_multipliers()),
            'worked_stations': len(self.get_worked_stations()),
            'recent_stations': len(self.get_recent_stations()),
            'noise_frequencies': len(self.noise_frequencies),
            'last_scan': self.last_scan,
            'band': self.band,
        }

    def mark_noise_occurrence(self, frequency: float, tolerance_hz: float = 500) -> int:
        """
        Mark a noise occurrence at a frequency.

        Args:
            frequency: Frequency in Hz where noise was detected
            tolerance_hz: Group frequencies within this tolerance

        Returns:
            Current occurrence count for this frequency
        """
        # Round frequency to nearest kHz for grouping
        freq_key = int(round(frequency / 1000) * 1000)

        # Increment occurrence count
        if freq_key not in self.noise_frequencies:
            self.noise_frequencies[freq_key] = 0

        self.noise_frequencies[freq_key] += 1
        count = self.noise_frequencies[freq_key]

        logger.debug(
            f"Noise occurrence at {freq_key/1e6:.3f} MHz (count: {count})"
        )

        return count

    def is_noise_frequency(
        self,
        frequency: float,
        threshold: int,
        tolerance_hz: float = 500
    ) -> bool:
        """
        Check if a frequency is marked as noise.

        Args:
            frequency: Frequency in Hz to check
            threshold: Minimum occurrence count to consider as noise (0=disabled)
            tolerance_hz: Check frequencies within this tolerance

        Returns:
            True if frequency should be skipped as noise
        """
        if threshold <= 0:
            return False  # Feature disabled

        # Round frequency to nearest kHz for lookup
        freq_key = int(round(frequency / 1000) * 1000)

        # Check if this frequency has enough occurrences
        count = self.noise_frequencies.get(freq_key, 0)
        return count >= threshold

    def get_noise_frequencies(self, threshold: int = 0) -> List[float]:
        """
        Get list of frequencies marked as noise.

        Args:
            threshold: Minimum occurrence count (0=all)

        Returns:
            List of frequencies in Hz
        """
        if threshold <= 0:
            return list(self.noise_frequencies.keys())
        else:
            return [
                freq for freq, count in self.noise_frequencies.items()
                if count >= threshold
            ]

    def clear_noise_frequency(self, frequency: float):
        """
        Clear noise marking for a specific frequency.

        Args:
            frequency: Frequency in Hz to clear
        """
        freq_key = int(round(frequency / 1000) * 1000)
        if freq_key in self.noise_frequencies:
            del self.noise_frequencies[freq_key]
            logger.info(f"Cleared noise marking for {freq_key/1e6:.3f} MHz")

    def clear_all_noise_frequencies(self):
        """Clear all noise frequency markings."""
        count = len(self.noise_frequencies)
        self.noise_frequencies.clear()
        if count > 0:
            logger.info(f"Cleared {count} noise frequency markings")

    def __len__(self) -> int:
        """Return number of stations."""
        return len(self.stations)

    def __repr__(self) -> str:
        """String representation."""
        stats = self.get_statistics()
        return (
            f"BandMapState({stats['total_stations']} stations, "
            f"{stats['new_stations']} new, {stats['worked_stations']} worked)"
        )
