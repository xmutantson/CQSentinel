#!/usr/bin/env python3
"""
Test script to check what hamlib reports for supported RF control levels.

This will help diagnose whether hamlib properly handles the IC-705
preamp/attenuator controls or if there's a hamlib bug.

Usage:
    python test_hamlib_levels.py

Make sure rigctld is running with your IC-705 before executing.
"""

import sys
from cqsentinel.radio.hamlib_controller import HamlibController

def main():
    print("=" * 70)
    print("Hamlib Supported Levels Test")
    print("=" * 70)
    print()

    # Connect to rigctld
    print("Connecting to rigctld (localhost:4532)...")
    radio = HamlibController(host="localhost", port=4532)

    try:
        radio.connect()
        print(f"✓ Connected to radio")
        print(f"  Model ID: {radio.model_id}")
        print(f"  Manufacturer: {radio._get_manufacturer_from_model_id()}")
        print()
    except Exception as e:
        print(f"✗ Failed to connect: {e}")
        print()
        print("Make sure rigctld is running:")
        print("  rigctld -m 3085 -r <port> -s <baud>")
        return 1

    try:
        # Query supported preamp levels
        print("=" * 70)
        print("PREAMP LEVELS")
        print("=" * 70)

        # IMPORTANT: Test what 'l PREAMP' actually returns first
        print("Testing raw hamlib commands to understand value format:")
        print()

        # Get current preamp value
        try:
            response = radio._send_command("l PREAMP")
            print(f"  Raw 'l PREAMP' response: '{response}'")
            print(f"  Type: {type(response)}, Value: {repr(response)}")
        except Exception as e:
            print(f"  'l PREAMP' failed: {e}")

        print()

        # Try the 'u' command (this might fail - u is for functions, not levels)
        print("Attempting 'u PREAMP' command (may not work):")
        preamp_levels = radio.get_supported_preamp_levels()
        if preamp_levels is not None:
            print(f"✓ 'u PREAMP' returned: {preamp_levels}")
            print()

            # Test reading current value
            current = radio.get_preamp()
            if current is not None:
                print(f"  Current preamp setting: {current}")

                # Try to match it with reported levels
                if current in preamp_levels:
                    print(f"  ✓ Current value ({current}) IS in supported list")
                else:
                    print(f"  ✗ WARNING: Current value ({current}) NOT in supported list!")
            print()

            # Try setting each supported level
            print("Testing each supported level:")
            for level in preamp_levels:
                print(f"  Setting preamp to {level}...", end=" ")
                if radio.set_preamp(level):
                    print("✓ SUCCESS")
                    # Verify it was set
                    import time
                    time.sleep(0.2)
                    verify = radio.get_preamp()
                    if verify == level:
                        print(f"    Verified: {verify} ✓")
                    else:
                        print(f"    WARNING: Set to {level} but read back {verify}")
                else:
                    print("✗ FAILED")

            # Restore to off
            print(f"  Restoring to off (0)...")
            radio.set_preamp(0)
        else:
            print("✗ Hamlib did not report supported preamp levels")
            print("  This may mean:")
            print("  - Preamp not supported on this radio")
            print("  - Hamlib version too old")
            print("  - Hamlib bug in IC-705 backend")

        print()

        # Query supported attenuator levels
        print("=" * 70)
        print("ATTENUATOR LEVELS")
        print("=" * 70)

        att_levels = radio.get_supported_attenuator_levels()
        if att_levels is not None:
            print(f"✓ Hamlib reports supported attenuator levels: {att_levels}")
            print()

            # Test reading current value
            current = radio.get_attenuator()
            if current is not None:
                print(f"  Current attenuator setting: {current}")

                # Try to match it with reported levels
                if current in att_levels:
                    print(f"  ✓ Current value ({current}) IS in supported list")
                else:
                    print(f"  ✗ WARNING: Current value ({current}) NOT in supported list!")
            print()

            # Try setting each supported level
            print("Testing each supported level:")
            for level in att_levels:
                print(f"  Setting attenuator to {level}...", end=" ")
                if radio.set_attenuator(level):
                    print("✓ SUCCESS")
                    # Verify it was set
                    import time
                    time.sleep(0.2)
                    verify = radio.get_attenuator()
                    if verify == level:
                        print(f"    Verified: {verify} ✓")
                    else:
                        print(f"    WARNING: Set to {level} but read back {verify}")
                else:
                    print("✗ FAILED")

            # Restore to off
            print(f"  Restoring to off (0)...")
            radio.set_attenuator(0)
        else:
            print("✗ Hamlib did not report supported attenuator levels")
            print("  This may mean:")
            print("  - Attenuator not supported on this radio")
            print("  - Hamlib version too old")
            print("  - Hamlib bug in IC-705 backend")

        print()
        print("=" * 70)
        print("CONCLUSION")
        print("=" * 70)

        if preamp_levels and att_levels:
            print("✓ Hamlib properly reports supported levels for this radio")
            print("  The UI dropdowns will now use these values")
        elif preamp_levels or att_levels:
            print("⚠ Hamlib reports some controls but not others")
            print("  Check if your radio/hamlib version fully supports these features")
        else:
            print("✗ Hamlib does not report any supported levels")
            print("  Possible issues:")
            print("  - Hamlib version too old (try upgrading)")
            print("  - IC-705 backend missing support (file hamlib bug)")
            print("  - Command 'u PREAMP' / 'u ATT' not supported in rigctld")

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
