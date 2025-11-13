#!/usr/bin/env python3
"""
Test SSB Auto-Centering

This script tests the auto-centering functionality with simulated or real audio.

Usage:
    # Test with simulated audio
    python scripts/test_auto_center.py --simulate

    # Test with real radio
    python scripts/test_auto_center.py --radio --freq 14.250

    # Test with audio file
    python scripts/test_auto_center.py --file recording.wav
"""

import sys
import argparse
import numpy as np
import logging
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from cqsentinel.radio import PitchDetector, SSBAutoTuner
from cqsentinel.audio import AudioCapture

logging.basicConfig(
    level=logging.INFO,
    format='%(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def generate_test_audio(f0: float = 120.0, duration: float = 3.0, sample_rate: int = 16000):
    """
    Generate synthetic speech-like audio at specific F0

    Args:
        f0: Fundamental frequency in Hz
        duration: Duration in seconds
        sample_rate: Sample rate

    Returns:
        Audio signal
    """
    t = np.linspace(0, duration, int(duration * sample_rate))

    # Generate harmonic series (simulating speech)
    audio = np.zeros_like(t)

    # Add harmonics at F0, 2*F0, 3*F0, etc.
    for harmonic in range(1, 10):
        amplitude = 1.0 / harmonic  # Decreasing amplitude
        audio += amplitude * np.sin(2 * np.pi * harmonic * f0 * t)

    # Add formants (resonances) to make it more speech-like
    # Formant 1: ~700 Hz
    # Formant 2: ~1220 Hz
    # Formant 3: ~2600 Hz

    from scipy import signal

    # Apply formant filters
    for formant_freq in [700, 1220, 2600]:
        b, a = signal.butter(2, formant_freq / (sample_rate / 2), btype='low')
        formant = signal.lfilter(b, a, np.random.randn(len(t)) * 0.1)
        audio += formant

    # Normalize
    audio = audio / np.max(np.abs(audio)) * 0.8

    # Add some silence (simulate pauses)
    silence_mask = np.sin(2 * np.pi * 0.5 * t) < 0
    audio[silence_mask] *= 0.1

    return audio.astype(np.float32)


def test_pitch_detector():
    """Test pitch detection with various F0 values"""
    print("=" * 60)
    print("Testing Pitch Detector")
    print("=" * 60)
    print()

    detector = PitchDetector(sample_rate=16000)

    # Test cases: (F0, description, expected_centered)
    test_cases = [
        (60, "Too low (tuned too low)", False),
        (120, "Normal male voice", True),
        (220, "Normal female voice", True),
        (450, "Too high (Donald Duck)", False),
        (90, "Low male voice", True),
        (350, "High female voice", True),
    ]

    for f0, description, expected_centered in test_cases:
        print(f"Test: {description} (F0={f0} Hz)")

        # Generate test audio
        audio = generate_test_audio(f0=f0)

        # Analyze
        analysis = detector.analyze_pitch(audio)

        print(f"  Measured F0: {analysis.median_f0:.1f} Hz")
        print(f"  Centered: {analysis.is_centered} (expected: {expected_centered})")
        print(f"  Confidence: {analysis.confidence:.2f}")
        print(f"  Voiced ratio: {analysis.voiced_ratio:.1%}")
        print(f"  Estimated offset: {analysis.estimated_offset_hz:+d} Hz")

        # Check result
        if analysis.is_centered == expected_centered:
            print("  ✓ PASS")
        else:
            print("  ✗ FAIL")

        print()


def test_auto_tuner_simulation():
    """Test auto-tuner with simulated off-frequency signal"""
    print("=" * 60)
    print("Testing Auto-Tuner (Simulation)")
    print("=" * 60)
    print()

    # Simulate signal that's 500 Hz off (F0 will appear shifted)
    # Real F0: 120 Hz, but due to 500 Hz offset, appears as different pitch

    class MockRadio:
        def __init__(self):
            self.frequency = 14_250_000  # 14.250 MHz
            self.offset = 500  # Hz (simulated tuning error)

        def set_frequency(self, freq):
            old_freq = self.frequency
            self.frequency = freq
            # Update simulated offset
            self.offset = self.offset - (freq - old_freq)
            print(f"    Radio: {old_freq/1e6:.4f} → {freq/1e6:.4f} MHz")

    radio = MockRadio()

    def capture_audio(duration=3.0):
        """Simulate audio capture with offset"""
        # F0 appears shifted based on current offset
        apparent_f0 = 120 + radio.offset * 0.3  # Simplified simulation
        audio = generate_test_audio(f0=apparent_f0, duration=duration)
        print(f"    Capturing audio... (apparent F0: {apparent_f0:.1f} Hz)")
        return audio

    # Create auto-tuner
    tuner = SSBAutoTuner(
        sample_rate=16000,
        max_iterations=3,
        tolerance_hz=50,
        sideband="USB"
    )

    # Run auto-centering
    print(f"Initial frequency: {radio.frequency/1e6:.4f} MHz")
    print(f"Initial offset: {radio.offset} Hz")
    print()

    result = tuner.auto_center(
        radio_controller=radio,
        audio_capture_func=capture_audio,
        initial_frequency=radio.frequency,
        capture_duration=3.0
    )

    print()
    print("Auto-centering result:")
    print(f"  Success: {result.success}")
    print(f"  Final frequency: {result.final_frequency/1e6:.4f} MHz")
    print(f"  Iterations: {result.iterations}")
    print(f"  Initial offset: {result.initial_offset:+d} Hz")
    print(f"  Final offset: {result.final_offset:+d} Hz")
    print(f"  Confidence: {result.confidence:.2f}")

    if result.success:
        print("  ✓ PASS - Signal centered")
    else:
        print("  ⚠ Could not center (may be normal for simulation)")


def test_with_real_audio(audio_file: str):
    """Test with real audio file"""
    print("=" * 60)
    print(f"Testing with audio file: {audio_file}")
    print("=" * 60)
    print()

    # Load audio
    import soundfile as sf

    try:
        audio, sample_rate = sf.read(audio_file)

        # Convert to mono if stereo
        if audio.ndim > 1:
            audio = audio.mean(axis=1)

        print(f"Loaded: {len(audio)} samples, {sample_rate} Hz")
        print()

        # Resample if needed
        if sample_rate != 16000:
            from scipy import signal
            audio = signal.resample(audio, int(len(audio) * 16000 / sample_rate))
            sample_rate = 16000
            print(f"Resampled to 16000 Hz")

        # Analyze
        detector = PitchDetector(sample_rate=sample_rate)
        analysis = detector.analyze_pitch(audio)

        print("Pitch Analysis:")
        print(f"  Median F0: {analysis.median_f0:.1f} Hz")
        print(f"  F0 range: [{analysis.f0_range[0]:.1f}, {analysis.f0_range[1]:.1f}] Hz")
        print(f"  Centered: {analysis.is_centered}")
        print(f"  Confidence: {analysis.confidence:.2f}")
        print(f"  Voiced ratio: {analysis.voiced_ratio:.1%}")
        print(f"  Estimated offset: {analysis.estimated_offset_hz:+d} Hz")

    except Exception as e:
        print(f"Error: {e}")


def main():
    parser = argparse.ArgumentParser(description='Test SSB Auto-Centering')
    parser.add_argument('--simulate', action='store_true',
                        help='Run simulation tests')
    parser.add_argument('--file', type=str,
                        help='Test with audio file')
    parser.add_argument('--all', action='store_true',
                        help='Run all tests')

    args = parser.parse_args()

    if args.all or (not args.simulate and not args.file):
        # Run all tests by default
        test_pitch_detector()
        print()
        test_auto_tuner_simulation()

    elif args.simulate:
        test_pitch_detector()
        print()
        test_auto_tuner_simulation()

    elif args.file:
        test_with_real_audio(args.file)

    print()
    print("=" * 60)
    print("Tests complete")
    print("=" * 60)


if __name__ == '__main__':
    main()
