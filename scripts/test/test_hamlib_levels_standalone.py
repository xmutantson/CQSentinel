#!/usr/bin/env python3
"""
Standalone test script for hamlib RF control levels (IC-705, FT-710, etc.)

This is a self-contained script with no external dependencies (except Python stdlib).
Can be compiled to .exe with PyInstaller for testing on other machines.

Usage:
    python test_hamlib_levels_standalone.py
    OR
    pyinstaller --onefile test_hamlib_levels_standalone.py

Make sure rigctld is running before executing.
"""

import socket
import time
import sys
import subprocess
import os
import atexit
from typing import Optional


class RadioConnectionError(Exception):
    """Raised when radio connection fails"""
    pass


class HamlibTester:
    """Minimal hamlib controller for testing RF controls"""

    def __init__(self, host: str = "localhost", port: int = 4532):
        self.host = host
        self.port = port
        self.socket: Optional[socket.socket] = None
        self.model_id: Optional[int] = None

    def connect(self):
        """Connect to rigctld daemon"""
        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.settimeout(5.0)
            self.socket.connect((self.host, self.port))

            # Get model ID
            response = self._send_command("\\dump_state")
            lines = response.strip().split('\n')
            if len(lines) > 0:
                self.model_id = int(lines[0])

        except Exception as e:
            raise RadioConnectionError(f"Failed to connect to rigctld: {e}")

    def disconnect(self):
        """Disconnect from rigctld"""
        if self.socket:
            try:
                self.socket.close()
            except:
                pass
            self.socket = None

    def _send_command(self, command: str) -> str:
        """Send command to rigctld and return response"""
        if not self.socket:
            raise RadioConnectionError("Not connected to rigctld")

        try:
            # Send command
            cmd_bytes = (command + '\n').encode('utf-8')
            self.socket.sendall(cmd_bytes)

            # Read response
            response = b''
            while True:
                chunk = self.socket.recv(4096)
                if not chunk:
                    break
                response += chunk
                # Check for end of response
                if response.endswith(b'\n'):
                    break

            decoded = response.decode('utf-8', errors='ignore').strip()

            # Check for error
            if decoded.startswith('RPRT '):
                code = int(decoded.split()[1])
                if code != 0:
                    raise RadioConnectionError(f"Command '{command}' failed with code {code}")
                return ""

            return decoded

        except socket.timeout:
            raise RadioConnectionError(f"Command '{command}' timed out")
        except Exception as e:
            raise RadioConnectionError(f"Command '{command}' failed: {e}")

    def get_manufacturer(self) -> str:
        """Determine manufacturer from model ID"""
        if self.model_id is None:
            return 'unknown'

        if 3000 <= self.model_id < 5000:
            return 'icom'
        elif 1000 <= self.model_id < 2000:
            return 'yaesu'
        elif 2000 <= self.model_id < 3000:
            return 'kenwood'
        else:
            return 'unknown'


def start_rigctld(model_id: int, com_port: str, baud_rate: int) -> Optional[subprocess.Popen]:
    """Start rigctld daemon as subprocess"""

    # Find rigctld.exe (bundled with PyInstaller or in PATH)
    if getattr(sys, 'frozen', False):
        # Running as compiled exe
        base_path = sys._MEIPASS
        rigctld_path = os.path.join(base_path, 'rigctld.exe')
    else:
        # Running as script
        rigctld_path = 'rigctld.exe'

    if not os.path.exists(rigctld_path) and not getattr(sys, 'frozen', False):
        # Try to find in PATH
        rigctld_path = 'rigctld'

    cmd = [
        rigctld_path,
        '-m', str(model_id),
        '-r', com_port,
        '-s', str(baud_rate),
        '-t', '4532',  # TCP port
        '-vvvvv'  # Verbose for debugging
    ]

    print(f"Starting rigctld: {' '.join(cmd)}")

    try:
        # Start rigctld WITHOUT redirecting output (show in console for debugging)
        process = subprocess.Popen(
            cmd,
            creationflags=0 if sys.platform == 'win32' else 0  # Show console
        )

        # Give it time to start and listen on TCP port
        print("Waiting for rigctld to initialize...")
        for i in range(10):
            time.sleep(1)
            print(f"  Waiting... {i+1}/10")

            # Check if process died
            if process.poll() is not None:
                print(f"rigctld exited with code {process.returncode}")
                return None

            # Try to connect to see if it's ready
            try:
                test_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                test_sock.settimeout(0.5)
                test_sock.connect(('localhost', 4532))
                test_sock.close()
                print("✓ rigctld is ready and accepting connections")
                return process
            except:
                pass

        # After 10 seconds, if still not ready, warn but return process anyway
        print("⚠ rigctld process is running but not responding yet")
        print("  Will try to connect anyway...")
        return process

    except Exception as e:
        print(f"Failed to start rigctld: {e}")
        return None


def stop_rigctld(process: subprocess.Popen):
    """Stop rigctld daemon"""
    if process and process.poll() is None:
        print("Stopping rigctld...")
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
        print("✓ rigctld stopped")


def main():
    print("=" * 70)
    print("Hamlib RF Controls Test - Standalone Version")
    print("=" * 70)
    print()
    print("This script tests preamp and attenuator control via hamlib.")
    print("It will help diagnose what values your radio expects.")
    print()

    # Get radio configuration from user
    print("Radio Configuration:")
    print()
    print("Common model IDs:")
    print("  IC-705:  3085")
    print("  FT-710:  1049")
    print("  IC-7300: 3073")
    print()

    try:
        model_id_str = input("Enter model ID [3085]: ").strip()
        model_id = int(model_id_str) if model_id_str else 3085

        com_port = input("Enter COM port [COM3]: ").strip()
        if not com_port:
            com_port = "COM3"

        baud_str = input("Enter baud rate [19200]: ").strip()
        baud_rate = int(baud_str) if baud_str else 19200

    except ValueError as e:
        print(f"Invalid input: {e}")
        input("\nPress Enter to exit...")
        return 1
    except KeyboardInterrupt:
        print("\nCancelled by user")
        return 1

    print()
    print(f"Configuration:")
    print(f"  Model ID:  {model_id}")
    print(f"  COM Port:  {com_port}")
    print(f"  Baud Rate: {baud_rate}")
    print()

    # Start rigctld
    rigctld_process = start_rigctld(model_id, com_port, baud_rate)
    if not rigctld_process:
        print()
        print("Failed to start rigctld. Make sure:")
        print("  1. rigctld.exe is in the same folder as this executable")
        print("  2. Your radio is connected to the specified COM port")
        print("  3. The radio is turned on")
        input("\nPress Enter to exit...")
        return 1

    # Register cleanup handler
    atexit.register(stop_rigctld, rigctld_process)

    # Connect to rigctld
    print()
    print("Connecting to rigctld (localhost:4532)...")
    tester = HamlibTester(host="localhost", port=4532)

    # Retry connection with backoff
    connected = False
    for attempt in range(5):
        try:
            tester.connect()
            print(f"✓ Connected to rigctld on attempt {attempt + 1}")
            print(f"  Model ID: {tester.model_id}")
            print(f"  Manufacturer: {tester.get_manufacturer()}")
            print()
            connected = True
            break
        except Exception as e:
            if attempt < 4:
                print(f"Connection attempt {attempt + 1}/5 failed, retrying...")
                time.sleep(2)
            else:
                print(f"✗ Failed to connect after {attempt + 1} attempts: {e}")
                print()
                print("Connection failed. This might mean:")
                print("  1. The radio is not responding on the COM port")
                print("  2. Wrong model ID, COM port, or baud rate")
                print("  3. Another program is using the COM port")
                print("  4. rigctld.exe had an error (check output above)")
                print()
                if rigctld_process:
                    stop_rigctld(rigctld_process)
                input("\nPress Enter to exit...")
                return 1

    if not connected:
        if rigctld_process:
            stop_rigctld(rigctld_process)
        input("\nPress Enter to exit...")
        return 1

    try:
        # Test PREAMP
        print("=" * 70)
        print("PREAMP TESTS")
        print("=" * 70)
        print()

        # Read current value
        print("1. Reading current preamp setting:")
        try:
            response = tester._send_command("l PREAMP")
            print(f"   ✓ Current value: {response}")
        except Exception as e:
            print(f"   ✗ Failed: {e}")
        print()

        # Try common values
        print("2. Testing common preamp values:")
        test_values = [0, 1, 2, 10, 20]
        working_values = []

        for value in test_values:
            print(f"   Testing L PREAMP {value}...", end=" ")
            try:
                tester._send_command(f"L PREAMP {value}")
                time.sleep(0.2)
                # Verify it was set
                verify = tester._send_command("l PREAMP")
                if verify == str(value):
                    print(f"✓ SUCCESS (verified: {verify})")
                    working_values.append(value)
                else:
                    print(f"⚠ Set but got back: {verify}")
                    working_values.append(value)
            except Exception as e:
                print(f"✗ FAILED ({e})")

        print()
        print(f"   Working preamp values: {working_values}")
        print()

        # Restore to off
        print("3. Restoring preamp to off (0)...")
        try:
            tester._send_command("L PREAMP 0")
            print("   ✓ Done")
        except:
            print("   ✗ Failed to restore")
        print()

        # Test ATTENUATOR
        print("=" * 70)
        print("ATTENUATOR TESTS")
        print("=" * 70)
        print()

        # Read current value
        print("1. Reading current attenuator setting:")
        try:
            response = tester._send_command("l ATT")
            print(f"   ✓ Current value: {response}")
        except Exception as e:
            print(f"   ✗ Failed: {e}")
        print()

        # Try common values
        print("2. Testing common attenuator values:")
        test_values = [0, 1, 2, 3, 6, 12, 18, 20]
        working_values = []

        for value in test_values:
            print(f"   Testing L ATT {value}...", end=" ")
            try:
                tester._send_command(f"L ATT {value}")
                time.sleep(0.2)
                # Verify it was set
                verify = tester._send_command("l ATT")
                if verify == str(value):
                    print(f"✓ SUCCESS (verified: {verify})")
                    working_values.append(value)
                else:
                    print(f"⚠ Set but got back: {verify}")
                    working_values.append(value)
            except Exception as e:
                print(f"✗ FAILED ({e})")

        print()
        print(f"   Working attenuator values: {working_values}")
        print()

        # Restore to off
        print("3. Restoring attenuator to off (0)...")
        try:
            tester._send_command("L ATT 0")
            print("   ✓ Done")
        except:
            print("   ✗ Failed to restore")
        print()

        # Test RF GAIN
        print("=" * 70)
        print("RF GAIN TEST")
        print("=" * 70)
        print()

        print("1. Reading current RF gain:")
        try:
            response = tester._send_command("l RFGAIN")
            gain = float(response)
            print(f"   ✓ Current value: {gain} (normalized 0.0-1.0)")
            print(f"   ✓ As percentage: {int(gain * 100)}%")
        except Exception as e:
            print(f"   ✗ Failed: {e}")
        print()

        print("2. Testing RF gain control:")
        test_gains = [0.5, 0.75, 1.0]
        for gain in test_gains:
            print(f"   Setting RF gain to {gain} ({int(gain*100)}%)...", end=" ")
            try:
                tester._send_command(f"L RFGAIN {gain}")
                time.sleep(0.2)
                verify = tester._send_command("l RFGAIN")
                verify_val = float(verify)
                if abs(verify_val - gain) < 0.01:
                    print(f"✓ SUCCESS (verified: {verify_val})")
                else:
                    print(f"⚠ Set but got back: {verify_val}")
            except Exception as e:
                print(f"✗ FAILED ({e})")
        print()

        # Restore to max
        print("3. Restoring RF gain to 100% (1.0)...")
        try:
            tester._send_command("L RFGAIN 1.0")
            print("   ✓ Done")
        except:
            print("   ✗ Failed to restore")
        print()

        # Summary
        print("=" * 70)
        print("SUMMARY")
        print("=" * 70)
        print()
        print("Based on the tests above, you should use these values in your UI:")
        print()

        manufacturer = tester.get_manufacturer()
        if manufacturer == 'icom':
            print("ICOM Radio Detected:")
            print("  Preamp values:     [0, 1, 2]")
            print("  Attenuator values: [0, 20] or similar")
        elif manufacturer == 'yaesu':
            print("YAESU Radio Detected:")
            print("  Preamp values:     [0, 10, 20] (likely)")
            print("  Attenuator values: [0, 6, 12, 18] (likely)")
        else:
            print(f"Unknown manufacturer (model ID: {tester.model_id})")
            print("  Check test results above for working values")

        print()

    except Exception as e:
        print(f"Error during test: {e}")
        import traceback
        traceback.print_exc()
        if rigctld_process:
            stop_rigctld(rigctld_process)
        input("\nPress Enter to exit...")
        return 1
    finally:
        tester.disconnect()
        print()
        print("Disconnected from rigctld")
        if rigctld_process:
            stop_rigctld(rigctld_process)

    print()
    input("Press Enter to exit...")
    return 0


if __name__ == "__main__":
    sys.exit(main())
