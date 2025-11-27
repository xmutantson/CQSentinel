#!/usr/bin/env python3
"""
Test script for RF gain, preamp, and attenuator controls

Demonstrates the new hamlib control methods for:
- RF gain adjustment
- Preamp on/off
- Attenuator settings

Usage:
    python test_rf_controls.py

Make sure rigctld is running before executing this script.
"""

import sys
import time
from cqsentinel.radio.hamlib_controller import HamlibController

def main():
    print("=" * 60)
    print("CQSentinel RF Controls Test")
    print("=" * 60)
    print()

    # Connect to rigctld (default: localhost:4532)
    print("Connecting to rigctld...")
    radio = HamlibController(host="localhost", port=4532)

    try:
        radio.connect()
        print(f"✓ Connected to radio")
        print()
    except Exception as e:
        print(f"✗ Failed to connect: {e}")
        print()
        print("Make sure rigctld is running:")
        print("  rigctld -m <model_id> -r <port> -s <baud>")
        return 1

    try:
        # Get current frequency and mode
        freq = radio.get_frequency()
        mode, bw = radio.get_mode()
        print(f"Current frequency: {freq/1e6:.3f} MHz")
        print(f"Current mode: {mode} (BW: {bw} Hz)")
        print()

        # Test RF Gain
        print("=" * 60)
        print("RF GAIN CONTROL")
        print("=" * 60)

        current_rf_gain = radio.get_rf_gain()
        if current_rf_gain is not None:
            print(f"✓ Current RF gain: {current_rf_gain}")
            print()

            # Example: Set to 50% gain (0.5 normalized)
            print("Testing: Setting RF gain to 0.5 (50%)...")
            if radio.set_rf_gain(0.5):
                print("✓ RF gain set to 0.5")
                time.sleep(0.5)
                new_gain = radio.get_rf_gain()
                print(f"  Verified: {new_gain}")
            else:
                print("✗ Failed to set RF gain")

            # Restore original
            print(f"Restoring RF gain to {current_rf_gain}...")
            radio.set_rf_gain(current_rf_gain)
        else:
            print("✗ RF gain control not supported on this radio")

        print()

        # Test Preamp
        print("=" * 60)
        print("PREAMP CONTROL")
        print("=" * 60)

        current_preamp = radio.get_preamp()
        if current_preamp is not None:
            print(f"✓ Current preamp: {current_preamp} dB")
            print()

            # Example: Turn on 10dB preamp
            print("Testing: Setting preamp to 10 dB...")
            if radio.set_preamp(10):
                print("✓ Preamp set to 10 dB")
                time.sleep(0.5)
                new_preamp = radio.get_preamp()
                print(f"  Verified: {new_preamp} dB")
            else:
                print("✗ Failed to set preamp")

            # Turn off
            print("Testing: Turning off preamp (0)...")
            if radio.set_preamp(0):
                print("✓ Preamp turned off")
                time.sleep(0.5)
                new_preamp = radio.get_preamp()
                print(f"  Verified: {new_preamp} dB")
            else:
                print("✗ Failed to turn off preamp")

            # Restore original
            print(f"Restoring preamp to {current_preamp} dB...")
            radio.set_preamp(current_preamp)
        else:
            print("✗ Preamp control not supported on this radio")

        print()

        # Test Attenuator
        print("=" * 60)
        print("ATTENUATOR CONTROL")
        print("=" * 60)

        current_att = radio.get_attenuator()
        if current_att is not None:
            print(f"✓ Current attenuator: {current_att} dB")
            print()

            # Example: Set 12dB attenuation
            print("Testing: Setting attenuator to 12 dB...")
            if radio.set_attenuator(12):
                print("✓ Attenuator set to 12 dB")
                time.sleep(0.5)
                new_att = radio.get_attenuator()
                print(f"  Verified: {new_att} dB")
            else:
                print("✗ Failed to set attenuator")

            # Turn off
            print("Testing: Turning off attenuator (0)...")
            if radio.set_attenuator(0):
                print("✓ Attenuator turned off")
                time.sleep(0.5)
                new_att = radio.get_attenuator()
                print(f"  Verified: {new_att} dB")
            else:
                print("✗ Failed to turn off attenuator")

            # Restore original
            print(f"Restoring attenuator to {current_att} dB...")
            radio.set_attenuator(current_att)
        else:
            print("✗ Attenuator control not supported on this radio")

        print()
        print("=" * 60)
        print("Test complete!")
        print("=" * 60)

    except Exception as e:
        print(f"Error during test: {e}")
        import traceback
        traceback.print_exc()
        return 1
    finally:
        radio.disconnect()
        print()
        print("Disconnected from radio")

    return 0


if __name__ == "__main__":
    sys.exit(main())
