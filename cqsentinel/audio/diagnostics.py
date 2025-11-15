"""
Audio subsystem diagnostics and self-test

Provides tools to test the audio pipeline end-to-end
"""

import numpy as np
import sounddevice as sd
import logging
import time
from typing import Optional

logger = logging.getLogger(__name__)


class AudioDiagnostics:
    """Audio subsystem diagnostic tests"""

    @staticmethod
    def list_all_devices():
        """List all audio input and output devices"""
        print("\n" + "=" * 70)
        print("AUDIO DEVICE INVENTORY")
        print("=" * 70)

        try:
            devices = sd.query_devices()
            default_in = sd.default.device[0]
            default_out = sd.default.device[1]

            print(f"\nDefault Input Device: {default_in}")
            print(f"Default Output Device: {default_out}")
            print(f"\nTotal Devices: {len(devices)}")
            print("\n" + "-" * 70)

            for idx, dev in enumerate(devices):
                device_type = []
                if dev['max_input_channels'] > 0:
                    device_type.append(f"INPUT ({dev['max_input_channels']} ch)")
                if dev['max_output_channels'] > 0:
                    device_type.append(f"OUTPUT ({dev['max_output_channels']} ch)")

                default_marker = ""
                if idx == default_in:
                    default_marker += " [DEFAULT INPUT]"
                if idx == default_out:
                    default_marker += " [DEFAULT OUTPUT]"

                print(f"[{idx:2d}] {dev['name']}")
                print(f"     Type: {', '.join(device_type)}{default_marker}")
                print(f"     Sample Rate: {dev['default_samplerate']} Hz")
                print()

        except Exception as e:
            print(f"ERROR listing devices: {e}")
            logger.error(f"Failed to list devices: {e}", exc_info=True)

    @staticmethod
    def test_input_capture(device: Optional[int] = None, duration: float = 2.0):
        """
        Test audio input capture

        Args:
            device: Device index (None for default)
            duration: Test duration in seconds

        Returns:
            True if test passed
        """
        print("\n" + "=" * 70)
        print("AUDIO INPUT CAPTURE TEST")
        print("=" * 70)

        device_info = "default" if device is None else f"device {device}"
        print(f"\nTesting {duration}s of audio capture from {device_info}...")

        try:
            # Record audio
            print("Recording... (make some noise!)")
            audio = sd.rec(
                int(duration * 16000),
                samplerate=16000,
                channels=1,
                dtype='float32',
                device=device
            )
            sd.wait()

            # Analyze
            if audio.ndim > 1:
                audio = audio.mean(axis=1)
            audio = audio.flatten()

            rms = np.sqrt(np.mean(audio**2))
            peak = np.max(np.abs(audio))
            samples = len(audio)

            print(f"\n[OK] Captured {samples} samples")
            print(f"     RMS Level: {rms:.6f} ({rms*100:.2f}%)")
            print(f"     Peak Level: {peak:.6f} ({peak*100:.2f}%)")

            if rms < 0.001:
                print("\n[WARNING] Very low audio level - check:")
                print("  - Is the correct input device selected?")
                print("  - Is the microphone/radio connected?")
                print("  - Is the input volume turned up?")
                return False
            else:
                print("\n[OK] Audio input working!")
                return True

        except Exception as e:
            print(f"\n[FAIL] Input capture failed: {e}")
            logger.error(f"Input capture test failed: {e}", exc_info=True)
            return False

    @staticmethod
    def test_output_playback(device: Optional[int] = None, duration: float = 1.0):
        """
        Test audio output playback

        Args:
            device: Device index (None for default)
            duration: Test duration in seconds

        Returns:
            True if test passed
        """
        print("\n" + "=" * 70)
        print("AUDIO OUTPUT PLAYBACK TEST")
        print("=" * 70)

        device_info = "default" if device is None else f"device {device}"
        print(f"\nTesting {duration}s tone playback to {device_info}...")
        print("You should hear a 440 Hz tone (musical note A)")

        try:
            # Generate a 440 Hz tone
            sample_rate = 16000
            t = np.linspace(0, duration, int(sample_rate * duration))
            tone = 0.3 * np.sin(2 * np.pi * 440 * t).astype('float32')

            # Play it
            print("Playing...")
            sd.play(tone, samplerate=sample_rate, device=device)
            sd.wait()

            print("\n[OK] Playback completed")
            print("     Did you hear the tone? (If not, check output device)")
            return True

        except Exception as e:
            print(f"\n[FAIL] Output playback failed: {e}")
            logger.error(f"Output playback test failed: {e}", exc_info=True)
            return False

    @staticmethod
    def test_streaming_callback(device: Optional[int] = None, duration: float = 3.0):
        """
        Test streaming audio with callback (mimics actual app usage)

        Args:
            device: Device index (None for default)
            duration: Test duration in seconds

        Returns:
            True if test passed
        """
        print("\n" + "=" * 70)
        print("AUDIO STREAMING CALLBACK TEST")
        print("=" * 70)

        device_info = "default" if device is None else f"device {device}"
        print(f"\nTesting {duration}s of streaming capture from {device_info}...")
        print("This tests the same code path used by the scanner")

        chunks_received = 0
        total_samples = 0
        max_rms = 0.0
        errors = []

        def callback(indata, frames, time_info, status):
            nonlocal chunks_received, total_samples, max_rms, errors

            if status:
                errors.append(str(status))

            try:
                chunks_received += 1
                total_samples += len(indata)

                # Calculate RMS
                if indata.ndim > 1:
                    audio = indata.mean(axis=1)
                else:
                    audio = indata.flatten()

                rms = np.sqrt(np.mean(audio**2))
                max_rms = max(max_rms, rms)

            except Exception as e:
                errors.append(f"Callback error: {e}")

        try:
            # Start stream
            print("Streaming... (make some noise!)")
            stream = sd.InputStream(
                device=device,
                channels=1,
                samplerate=16000,
                dtype='float32',
                callback=callback
            )

            stream.start()
            time.sleep(duration)
            stream.stop()
            stream.close()

            # Report results
            print(f"\n[OK] Streaming test completed")
            print(f"     Chunks received: {chunks_received}")
            print(f"     Total samples: {total_samples}")
            print(f"     Max RMS: {max_rms:.6f} ({max_rms*100:.2f}%)")

            if errors:
                print(f"\n[WARNING] {len(errors)} errors occurred:")
                for err in errors[:5]:  # Show first 5
                    print(f"     - {err}")

            if chunks_received == 0:
                print("\n[FAIL] No audio chunks received!")
                return False
            elif max_rms < 0.001:
                print("\n[WARNING] Very low audio level in stream")
                return False
            else:
                print("\n[OK] Audio streaming working!")
                return True

        except Exception as e:
            print(f"\n[FAIL] Streaming test failed: {e}")
            logger.error(f"Streaming test failed: {e}", exc_info=True)
            return False

    @staticmethod
    def run_full_diagnostic(input_device: Optional[int] = None,
                           output_device: Optional[int] = None):
        """
        Run complete audio diagnostic suite

        Args:
            input_device: Input device index (None for default)
            output_device: Output device index (None for default)
        """
        print("\n" + "=" * 70)
        print("CQSentinel AUDIO SUBSYSTEM DIAGNOSTIC")
        print("=" * 70)
        print()

        results = {}

        # Test 1: List devices
        AudioDiagnostics.list_all_devices()

        # Test 2: Input capture
        results['input_capture'] = AudioDiagnostics.test_input_capture(input_device)

        # Test 3: Output playback
        results['output_playback'] = AudioDiagnostics.test_output_playback(output_device)

        # Test 4: Streaming
        results['streaming'] = AudioDiagnostics.test_streaming_callback(input_device)

        # Summary
        print("\n" + "=" * 70)
        print("DIAGNOSTIC SUMMARY")
        print("=" * 70)

        all_passed = all(results.values())

        for test_name, passed in results.items():
            status = "[PASS]" if passed else "[FAIL]"
            print(f"{status} {test_name.replace('_', ' ').title()}")

        if all_passed:
            print("\n[OK] All tests passed! Audio subsystem is working.")
        else:
            print("\n[WARNING] Some tests failed. Check the output above for details.")

        print("=" * 70)
        print()

        return all_passed
