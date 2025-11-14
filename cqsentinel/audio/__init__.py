"""
Audio processing module for CQSentinel

Uses lazy imports for heavy dependencies (torch-based modules)
to improve startup time.
"""

# Import lightweight modules immediately
from cqsentinel.audio.capture import AudioCapture, list_audio_devices

# Lazy imports for heavy modules (contains torch/ML dependencies)
# These will only be loaded when actually instantiated
__all__ = [
    'AudioCapture',
    'list_audio_devices',
    'AudioDenoiser',
    'VoiceActivityDetector'
]


def __getattr__(name):
    """Lazy import heavy modules only when accessed"""
    if name == 'AudioDenoiser':
        from cqsentinel.audio.denoiser import AudioDenoiser
        return AudioDenoiser
    elif name == 'VoiceActivityDetector':
        from cqsentinel.audio.vad import VoiceActivityDetector
        return VoiceActivityDetector
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
