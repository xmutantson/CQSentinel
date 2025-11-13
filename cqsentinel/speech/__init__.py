"""
Speech processing module for CQSentinel
Handles transcription, phonetics, and callsign extraction
"""

from .transcription import SpeechTranscriber, TranscriptSegment

__all__ = ['SpeechTranscriber', 'TranscriptSegment']
