"""
Voice fingerprinting and speaker identification module.

NOTE: Voice fingerprinting via Resemblyzer has been disabled as it is not
effective for SSB audio (300-3000 Hz bandwidth). See FUTURE_WORK_VOICE_ID.md
for plans to train a custom SSB voice identification model.

This module provides:
- Voice database for operator tracking (still available)
- Voice embedding extraction (disabled - Resemblyzer not installed)
"""

# Import database classes (still used for callsign tracking)
from cqsentinel.voice.database import VoiceDatabase, OperatorVoice

# VoiceEmbedder and VoiceSegment are deprecated and will fail if used
# since Resemblyzer is no longer installed. Import them only if available.
try:
    from cqsentinel.voice.embeddings import VoiceEmbedder, VoiceSegment
except ImportError:
    # Resemblyzer not installed - voice embedding not available
    VoiceEmbedder = None
    VoiceSegment = None

__all__ = [
    'VoiceEmbedder',  # Deprecated - will be None if Resemblyzer not installed
    'VoiceSegment',   # Deprecated - will be None if Resemblyzer not installed
    'VoiceDatabase',
    'OperatorVoice',
]
