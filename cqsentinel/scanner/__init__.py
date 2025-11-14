"""
Band scanning engine.

Automated band sweeping with intelligent dwell times,
SSB auto-centering, and full integration with all
CQSentinel components.
"""

from cqsentinel.scanner.engine import BandScanner, ScanState, ScanProgress
from cqsentinel.scanner.profiles import (
    BandProfile,
    MultiBandProfile,
    BAND_PROFILES,
    MULTI_BAND_PROFILES,
    get_band_profile,
    get_multi_band_profile,
    list_band_profiles,
    list_multi_band_profiles,
    create_custom_profile,
    # Pre-defined profiles
    BAND_20M,
    BAND_40M,
    BAND_80M,
    FIELD_DAY_20M,
    FIELD_DAY_40M,
    HF_CONTEST_BANDS,
    FIELD_DAY_BANDS,
)

__all__ = [
    'BandScanner',
    'ScanState',
    'ScanProgress',
    'BandProfile',
    'MultiBandProfile',
    'BAND_PROFILES',
    'MULTI_BAND_PROFILES',
    'get_band_profile',
    'get_multi_band_profile',
    'list_band_profiles',
    'list_multi_band_profiles',
    'create_custom_profile',
    'BAND_20M',
    'BAND_40M',
    'BAND_80M',
    'FIELD_DAY_20M',
    'FIELD_DAY_40M',
    'HF_CONTEST_BANDS',
    'FIELD_DAY_BANDS',
]
