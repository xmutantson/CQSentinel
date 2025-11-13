"""
Contest logic and callsign extraction.

This module provides:
- Phonetic alphabet parsing (NATO + creative)
- Callsign extraction from transcripts
- Contest behavior detection and scoring
- Station type classification
"""

from .phonetics import PhoneticParser, parse_callsign, parse_exchange
from .callsign import CallsignExtractor, ExtractedCallsign, extract_callsigns, extract_best_callsign
from .behavior import BehaviorAnalyzer, ContestnessAnalysis, StationType, analyze_contestness

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
]
