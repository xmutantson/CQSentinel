"""
Scan profiles for different bands and operating scenarios.

Pre-configured scan profiles for common bands and contests.
"""

import logging
from dataclasses import dataclass
from typing import Dict, List, Tuple

logger = logging.getLogger(__name__)


@dataclass
class BandProfile:
    """
    Band scan profile.

    Defines frequency range, step size, and scan parameters for a band.
    """
    name: str
    band_name: str  # "160m", "80m", "40m", "20m", "15m", "10m"
    freq_start: float  # Hz
    freq_end: float  # Hz
    step_size: int = 1000  # Hz
    mode: str = "SSB"

    # Scan timing
    dwell_with_voice: float = 60.0  # seconds
    dwell_without_voice: float = 3.0  # seconds
    quick_check_duration: float = 2.0  # seconds

    # Contest parameters
    min_contestness_score: float = 40.0

    @property
    def frequency_range_mhz(self) -> Tuple[float, float]:
        """Get frequency range in MHz."""
        return (self.freq_start / 1e6, self.freq_end / 1e6)

    @property
    def total_steps(self) -> int:
        """Calculate total scan steps."""
        return int((self.freq_end - self.freq_start) / self.step_size)

    @property
    def estimated_scan_time_minutes(self) -> float:
        """
        Estimate scan time assuming average dwell.

        This is a rough estimate assuming 50% have voice.
        """
        avg_dwell = (self.dwell_with_voice + self.dwell_without_voice) / 2
        total_time_sec = self.total_steps * avg_dwell
        return total_time_sec / 60.0


# Pre-defined band profiles for US band plan (SSB portions)

BAND_160M = BandProfile(
    name="160m SSB",
    band_name="160m",
    freq_start=1.800e6,
    freq_end=2.000e6,
    step_size=1000,
    dwell_with_voice=60.0,
    dwell_without_voice=3.0
)

BAND_80M = BandProfile(
    name="80m SSB",
    band_name="80m",
    freq_start=3.600e6,  # LSB portion
    freq_end=4.000e6,
    step_size=1000,
    dwell_with_voice=60.0,
    dwell_without_voice=3.0
)

BAND_40M = BandProfile(
    name="40m SSB",
    band_name="40m",
    freq_start=7.125e6,  # Phone portion
    freq_end=7.300e6,
    step_size=1000,
    dwell_with_voice=60.0,
    dwell_without_voice=3.0
)

BAND_20M = BandProfile(
    name="20m SSB",
    band_name="20m",
    freq_start=14.150e6,  # Phone portion
    freq_end=14.350e6,
    step_size=1000,
    dwell_with_voice=60.0,
    dwell_without_voice=3.0
)

BAND_15M = BandProfile(
    name="15m SSB",
    band_name="15m",
    freq_start=21.200e6,  # Phone portion
    freq_end=21.450e6,
    step_size=1000,
    dwell_with_voice=60.0,
    dwell_without_voice=3.0
)

BAND_10M = BandProfile(
    name="10m SSB",
    band_name="10m",
    freq_start=28.300e6,  # Phone portion
    freq_end=29.700e6,
    step_size=1000,
    dwell_with_voice=60.0,
    dwell_without_voice=3.0
)

# VHF Bands
BAND_6M = BandProfile(
    name="6m",
    band_name="6m",
    freq_start=50.0e6,   # Full 6m band
    freq_end=54.0e6,
    step_size=12500,     # 12.5kHz steps for FM (standard channel spacing)
    mode="FM",
    dwell_with_voice=60.0,
    dwell_without_voice=3.0
)

BAND_2M = BandProfile(
    name="2m",
    band_name="2m",
    freq_start=144.0e6,  # Full 2m band
    freq_end=148.0e6,
    step_size=12500,     # 12.5kHz steps for FM (standard channel spacing)
    mode="FM",
    dwell_with_voice=60.0,
    dwell_without_voice=3.0
)

# UHF Band
BAND_70CM = BandProfile(
    name="70cm",
    band_name="70cm",
    freq_start=420.0e6,  # Full 70cm band
    freq_end=450.0e6,
    step_size=12500,     # 12.5kHz steps for FM (standard channel spacing)
    mode="FM",
    dwell_with_voice=60.0,
    dwell_without_voice=3.0
)

# Field Day focused (most active bands)
FIELD_DAY_20M = BandProfile(
    name="Field Day 20m",
    band_name="20m",
    freq_start=14.225e6,  # FD preferred range
    freq_end=14.300e6,
    step_size=500,  # Finer steps for busy band
    dwell_with_voice=45.0,  # Shorter dwell for fast scan
    dwell_without_voice=2.0,
    min_contestness_score=60.0  # Higher threshold
)

FIELD_DAY_40M = BandProfile(
    name="Field Day 40m",
    band_name="40m",
    freq_start=7.225e6,
    freq_end=7.300e6,
    step_size=500,
    dwell_with_voice=45.0,
    dwell_without_voice=2.0,
    min_contestness_score=60.0
)

# Quick scan profiles (faster sweep)
QUICK_20M = BandProfile(
    name="Quick 20m",
    band_name="20m",
    freq_start=14.150e6,
    freq_end=14.350e6,
    step_size=2000,  # 2 kHz steps
    dwell_with_voice=30.0,  # Shorter dwell
    dwell_without_voice=2.0,
    quick_check_duration=1.5,
    min_contestness_score=50.0
)

# All available band profiles
BAND_PROFILES: Dict[str, BandProfile] = {
    "160m": BAND_160M,
    "80m": BAND_80M,
    "40m": BAND_40M,
    "20m": BAND_20M,
    "15m": BAND_15M,
    "10m": BAND_10M,
    "6m": BAND_6M,
    "2m": BAND_2M,
    "70cm": BAND_70CM,
    "field_day_20m": FIELD_DAY_20M,
    "field_day_40m": FIELD_DAY_40M,
    "quick_20m": QUICK_20M,
}


@dataclass
class MultiBandProfile:
    """
    Multi-band scan profile.

    Scans multiple bands in sequence.
    """
    name: str
    bands: List[str]  # Band profile names
    repeat: bool = False  # Continuously repeat scan

    def get_band_profiles(self) -> List[BandProfile]:
        """Get band profiles in scan order."""
        profiles = []
        for band_name in self.bands:
            if band_name in BAND_PROFILES:
                profiles.append(BAND_PROFILES[band_name])
            else:
                logger.warning(f"Unknown band profile: {band_name}")
        return profiles


# Pre-defined multi-band profiles

# HF contest bands (most common)
HF_CONTEST_BANDS = MultiBandProfile(
    name="HF Contest Bands",
    bands=["20m", "40m", "15m", "10m"],
    repeat=True
)

# Field Day favorites
FIELD_DAY_BANDS = MultiBandProfile(
    name="Field Day Bands",
    bands=["field_day_20m", "field_day_40m", "80m", "15m"],
    repeat=True
)

# All HF bands
ALL_HF_BANDS = MultiBandProfile(
    name="All HF Bands",
    bands=["160m", "80m", "40m", "20m", "15m", "10m"],
    repeat=True
)

# All bands including VHF/UHF
ALL_BANDS = MultiBandProfile(
    name="All Bands (HF/VHF/UHF)",
    bands=["160m", "80m", "40m", "20m", "15m", "10m", "6m", "2m", "70cm"],
    repeat=True
)

# VHF/UHF weak signal bands
VHF_UHF_BANDS = MultiBandProfile(
    name="VHF/UHF Weak Signal",
    bands=["6m", "2m", "70cm"],
    repeat=True
)

# Daytime bands
DAYTIME_BANDS = MultiBandProfile(
    name="Daytime Bands",
    bands=["20m", "15m", "10m"],
    repeat=True
)

# Nighttime bands
NIGHTTIME_BANDS = MultiBandProfile(
    name="Nighttime Bands",
    bands=["160m", "80m", "40m"],
    repeat=True
)

MULTI_BAND_PROFILES: Dict[str, MultiBandProfile] = {
    "hf_contest": HF_CONTEST_BANDS,
    "field_day": FIELD_DAY_BANDS,
    "all_hf": ALL_HF_BANDS,
    "all_bands": ALL_BANDS,
    "vhf_uhf": VHF_UHF_BANDS,
    "daytime": DAYTIME_BANDS,
    "nighttime": NIGHTTIME_BANDS,
}


def get_band_profile(band_name: str) -> BandProfile:
    """
    Get band profile by name.

    Args:
        band_name: Band profile name (e.g., "20m", "field_day_20m")

    Returns:
        BandProfile

    Raises:
        KeyError: If profile not found
    """
    if band_name not in BAND_PROFILES:
        raise KeyError(f"Unknown band profile: {band_name}")

    return BAND_PROFILES[band_name]


def get_multi_band_profile(profile_name: str) -> MultiBandProfile:
    """
    Get multi-band profile by name.

    Args:
        profile_name: Profile name (e.g., "hf_contest", "field_day")

    Returns:
        MultiBandProfile

    Raises:
        KeyError: If profile not found
    """
    if profile_name not in MULTI_BAND_PROFILES:
        raise KeyError(f"Unknown multi-band profile: {profile_name}")

    return MULTI_BAND_PROFILES[profile_name]


def list_band_profiles() -> List[str]:
    """Get list of available band profile names."""
    return list(BAND_PROFILES.keys())


def list_multi_band_profiles() -> List[str]:
    """Get list of available multi-band profile names."""
    return list(MULTI_BAND_PROFILES.keys())


def create_custom_profile(
    name: str,
    freq_start_mhz: float,
    freq_end_mhz: float,
    **kwargs
) -> BandProfile:
    """
    Create a custom band profile.

    Args:
        name: Profile name
        freq_start_mhz: Start frequency in MHz
        freq_end_mhz: End frequency in MHz
        **kwargs: Additional BandProfile parameters

    Returns:
        BandProfile

    Example:
        >>> profile = create_custom_profile(
        ...     "Custom 20m",
        ...     14.200,
        ...     14.300,
        ...     step_size=500
        ... )
    """
    return BandProfile(
        name=name,
        band_name=kwargs.get('band_name', 'custom'),
        freq_start=freq_start_mhz * 1e6,
        freq_end=freq_end_mhz * 1e6,
        **kwargs
    )
