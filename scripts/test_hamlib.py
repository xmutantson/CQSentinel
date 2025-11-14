#!/usr/bin/env python3
"""
Standalone Hamlib rigctld test script

Tests rigctld connection with various configurations to diagnose radio issues.

Usage:
    python scripts/test_hamlib.py
    python scripts/test_hamlib.py --model 3073 --address 94
    python scripts/test_hamlib.py --model 3085  # IC-705 default
"""

import argparse
import subprocess
import socket
import time
import sys
from pathlib import Path


def check_port(port=4532, timeout=1.0):
    """Check if rigctld is listening on port"""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        result = sock.connect_ex(("localhost", port))
        sock.close()
        return result == 0
    except:
        return False


def test_rigctld(model_id, serial_port, baud_rate=115200, civ_address=None, timeout=15.0):
    """
    Test rigctld with given configuration

    Args:
        model_id: Hamlib model ID (e.g., 3085 for IC-705, 3073 for IC-7300)
        serial_port: Serial port (e.g., COM4)
        baud_rate: Baud rate (default 115200)
        civ_address: CI-V address in hex (e.g., "94"), None for default
        timeout: How long to wait for startup
    """
    # Find rigctld
    rigctld_path = None

    # Check bundled version (if running from dist)
    bundled_path = Path('dist/CQSentinel/_internal/hamlib/bin/rigctld.exe')
    if bundled_path.exists():
        rigctld_path = str(bundled_path)

    # Check external directory
    if not rigctld_path:
        external_path = Path('external/hamlib/bin/rigctld.exe')
        if external_path.exists():
            rigctld_path = str(external_path)

    # Check PATH
    if not rigctld_path:
        import shutil
        rigctld_path = shutil.which("rigctld")
        if not rigctld_path:
            rigctld_path = shutil.which("rigctld.exe")

    if not rigctld_path:
        print("❌ ERROR: rigctld not found!")
        print("\nSearched in:")
        print("  - dist/CQSentinel/_internal/hamlib/bin/rigctld.exe")
        print("  - external/hamlib/bin/rigctld.exe")
        print("  - PATH")
        print("\nTo download Hamlib:")
        print("  python scripts/download_hamlib.py")
        return False

    print(f"✓ Found rigctld: {rigctld_path}")
    print()

    # Build command
    cmd = [
        rigctld_path,
        "-m", str(model_id),
        "-r", serial_port,
        "-s", str(baud_rate),
        "-t", "4532",
        "-vvvvv",  # Maximum verbosity
        "--set-conf", "auto_power_on=0",  # Skip power status check (separate arg)
    ]

    # Add CI-V address if specified
    if civ_address:
        civ_decimal = int(civ_address, 16)
        cmd.extend(["-c", str(civ_decimal)])
        print(f"CI-V Address: 0x{civ_address} ({civ_decimal})")

    print("=" * 70)
    print("Test Configuration:")
    print("=" * 70)
    print(f"Model ID:    {model_id}")
    print(f"Serial Port: {serial_port}")
    print(f"Baud Rate:   {baud_rate}")
    print(f"TCP Port:    4532")
    print()
    print("Command:")
    print(" ".join(cmd))
    print("=" * 70)
    print()

    # Start rigctld
    print("Starting rigctld...")
    print()

    try:
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1
        )

        print(f"Process started (PID: {process.pid})")
        print()
        print("Waiting for rigctld to initialize...")
        print("(Press Ctrl+C to stop)")
        print()

        start_time = time.time()
        port_available = False

        # Monitor for timeout seconds
        while time.time() - start_time < timeout:
            # Check if process died
            if process.poll() is not None:
                stdout, stderr = process.communicate(timeout=1)
                print()
                print("=" * 70)
                print("❌ rigctld process exited!")
                print("=" * 70)
                print(f"Exit code: {process.returncode}")
                print()

                if stderr:
                    print("STDERR OUTPUT:")
                    print("-" * 70)
                    print(stderr)
                    print("-" * 70)

                if stdout:
                    print()
                    print("STDOUT OUTPUT:")
                    print("-" * 70)
                    print(stdout)
                    print("-" * 70)

                return False

            # Check if port is available
            if not port_available and check_port(4532):
                port_available = True
                elapsed = time.time() - start_time
                print()
                print("=" * 70)
                print(f"✓ SUCCESS! rigctld is listening on port 4532")
                print("=" * 70)
                print(f"Startup time: {elapsed:.1f} seconds")
                print()
                print("You can now connect to rigctld with:")
                print("  telnet localhost 4532")
                print("  (or use any Hamlib-compatible software)")
                print()
                print("Press Ctrl+C to stop rigctld...")

                # Keep running until user stops
                try:
                    process.wait()
                except KeyboardInterrupt:
                    print()
                    print("Stopping rigctld...")
                    process.terminate()
                    try:
                        process.wait(timeout=3)
                    except subprocess.TimeoutExpired:
                        process.kill()
                    print("✓ Stopped")

                return True

            time.sleep(0.5)

        # Timeout reached
        print()
        print("=" * 70)
        print(f"⚠ TIMEOUT: rigctld did not start within {timeout} seconds")
        print("=" * 70)
        print()

        # Check port one last time
        if check_port(4532):
            print("✓ Port 4532 IS listening (despite initialization errors)")
            print()
            print("This means rigctld started but had errors during radio initialization.")
            print("The radio might still be usable - try connecting anyway.")
        else:
            print("✗ Port 4532 is NOT listening")
            print()
            print("rigctld failed to start the TCP server.")

        print()
        print("Getting error output...")

        # Get stderr output
        try:
            # Process should still be running
            import select
            if hasattr(select, 'select'):
                # Try non-blocking read
                readable, _, _ = select.select([process.stderr], [], [], 1)
                if readable:
                    stderr_lines = []
                    for _ in range(100):  # Read up to 100 lines
                        line = process.stderr.readline()
                        if not line:
                            break
                        stderr_lines.append(line)

                    if stderr_lines:
                        print()
                        print("STDERR OUTPUT (last errors):")
                        print("-" * 70)
                        print("".join(stderr_lines[-50:]))  # Last 50 lines
                        print("-" * 70)
        except:
            pass

        # Stop process
        print()
        print("Stopping rigctld...")
        process.terminate()
        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            process.kill()

        return False

    except KeyboardInterrupt:
        print()
        print("Interrupted by user")
        if process:
            process.terminate()
        return False
    except Exception as e:
        print(f"❌ ERROR: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(
        description="Test Hamlib rigctld connection",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Test IC-705 at default address (A4h)
  python scripts/test_hamlib.py --model 3085 --port COM4

  # Test IC-705 at custom address 94h
  python scripts/test_hamlib.py --model 3085 --port COM4 --address 94

  # Test IC-7300 at default address (94h)
  python scripts/test_hamlib.py --model 3073 --port COM4

Common Model IDs:
  3085 - Icom IC-705
  3073 - Icom IC-7300
  3078 - Icom IC-7610
  3068 - Icom IC-9100
  3070 - Icom IC-7100
        """
    )

    parser.add_argument("-m", "--model", type=int, default=3085,
                        help="Hamlib model ID (default: 3085 for IC-705)")
    parser.add_argument("-p", "--port", type=str, default="COM4",
                        help="Serial port (default: COM4)")
    parser.add_argument("-b", "--baud", type=int, default=115200,
                        help="Baud rate (default: 115200)")
    parser.add_argument("-a", "--address", type=str, default=None,
                        help="CI-V address in hex (e.g., 94), empty for default")
    parser.add_argument("-t", "--timeout", type=float, default=15.0,
                        help="Startup timeout in seconds (default: 15)")

    args = parser.parse_args()

    print()
    print("=" * 70)
    print("Hamlib rigctld Test Script")
    print("=" * 70)
    print()

    success = test_rigctld(
        model_id=args.model,
        serial_port=args.port,
        baud_rate=args.baud,
        civ_address=args.address,
        timeout=args.timeout
    )

    print()
    print("=" * 70)
    if success:
        print("✓ Test completed successfully")
    else:
        print("✗ Test failed")
    print("=" * 70)
    print()

    return 0 if success else 1


if __name__ == '__main__':
    sys.exit(main())
