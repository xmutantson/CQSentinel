"""
Voice fingerprinting and speaker identification module.

This module provides:
- Voice embedding extraction using Resemblyzer
- Voice database for operator tracking
- Speaker matching and identification
"""

from cqsentinel.voice.embeddings import VoiceEmbedder, VoiceSegment
from cqsentinel.voice.database import VoiceDatabase, OperatorVoice

__all__ = [
    'VoiceEmbedder',
    'VoiceSegment',
    'VoiceDatabase',
    'OperatorVoice',
]
