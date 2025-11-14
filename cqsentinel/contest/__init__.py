"""
Contest logic and callsign extraction.

This module provides:
- Phonetic alphabet parsing (NATO + creative)
- Callsign extraction from transcripts
- Contest behavior detection and scoring
- Station type classification
- Pre-configured contest profiles
"""

from cqsentinel.contest.phonetics import PhoneticParser, parse_callsign, parse_exchange
from cqsentinel.contest.callsign import CallsignExtractor, ExtractedCallsign, extract_callsigns, extract_best_callsign
from cqsentinel.contest.behavior import BehaviorAnalyzer, ContestnessAnalysis, StationType, analyze_contestness
from cqsentinel.contest.profiles import (
    ContestProfile,
    ExchangeField,
    MultiplierType,
    # Pre-configured profiles
    FIELD_DAY,
    WINTER_FIELD_DAY,
    CQ_WW_DX,
    CQ_WPX,
    SALMON_RUN,
    CONTEST_PROFILES,
    # Functions
    get_contest_profile,
    list_contest_profiles,
    detect_contest,
    parse_exchange_auto,
    # Constants
    ARRL_SECTIONS,
    CQ_ZONES,
    WA_COUNTIES,
)

__all__ = [
    # Phonetics
    'PhoneticParser',
    'parse_callsign',
    'parse_exchange',

    # Callsigns
    'CallsignExtractor',
    'ExtractedCallsign',
    'extract_callsigns',
    'extract_best_callsign',

    # Behavior
    'BehaviorAnalyzer',
    'ContestnessAnalysis',
    'StationType',
    'analyze_contestness',

    # Contest Profiles
    'ContestProfile',
    'ExchangeField',
    'MultiplierType',
    'FIELD_DAY',
    'WINTER_FIELD_DAY',
    'CQ_WW_DX',
    'CQ_WPX',
    'SALMON_RUN',
    'CONTEST_PROFILES',
    'get_contest_profile',
    'list_contest_profiles',
    'detect_contest',
    'parse_exchange_auto',
    'ARRL_SECTIONS',
    'CQ_ZONES',
    'WA_COUNTIES',
]
