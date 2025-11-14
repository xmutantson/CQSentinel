"""
Radio control module for CQSentinel
"""

from cqsentinel.radio.hamlib_controller import HamlibController, RadioConnectionError
from cqsentinel.radio.rigctld_manager import RigctldManager, find_serial_port

# Phase 2 features (audio processing) - optional imports
# These require librosa, torch, and other heavy dependencies
try:
    from cqsentinel.radio.pitch import PitchDetector, PitchAnalysis
    from cqsentinel.radio.auto_tuner import SSBAutoTuner, CenteringResult
    _has_audio_processing = True
except ImportError:
    # Stub classes for when audio processing dependencies aren't available
    PitchDetector = None
    PitchAnalysis = None
    SSBAutoTuner = None
    CenteringResult = None
    _has_audio_processing = False

__all__ = [
    'HamlibController',
    'RadioConnectionError',
    'RigctldManager',
    'find_serial_port',
    'PitchDetector',
    'PitchAnalysis',
    'SSBAutoTuner',
    'CenteringResult',
]
