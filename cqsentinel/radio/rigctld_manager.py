"""
rigctld Process Manager

Handles automatic starting and stopping of the rigctld daemon process.
Supports both Windows and Linux platforms.
"""

import subprocess
import time
import logging
import socket
import shutil
import platform
import sys
from typing import Optional
from pathlib import Path

logger = logging.getLogger(__name__)


def get_bundled_rigctld_path() -> Optional[str]:
    """
    Get path to bundled rigctld executable

    Returns:
        Path to rigctld.exe if bundled, None otherwise
    """
    # Check if running as PyInstaller bundle
    if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
        # Running in PyInstaller bundle
        bundle_dir = Path(sys._MEIPASS)
        rigctld_path = bundle_dir / 'hamlib' / 'bin' / 'rigctld.exe'

        if rigctld_path.exists():
            logger.info(f"Found bundled rigctld at: {rigctld_path}")
            return str(rigctld_path)

    # Also check next to executable (onedir mode)
    if getattr(sys, 'frozen', False):
        exe_dir = Path(sys.executable).parent
        rigctld_path = exe_dir / 'hamlib' / 'bin' / 'rigctld.exe'

        if rigctld_path.exists():
            logger.info(f"Found bundled rigctld at: {rigctld_path}")
            return str(rigctld_path)

    return None


class RigctldManager:
    """
    Manages rigctld daemon process

    Automatically starts/stops rigctld when needed.
    """

    def __init__(self, model_id: int, serial_port: str, baud_rate: int, port: int = 4532, civ_address: str = ""):
        """
        Initialize rigctld manager

        Args:
            model_id: Hamlib radio model ID (e.g., 3085 for IC-705)
            serial_port: Serial port device (e.g., "COM3" on Windows, "/dev/ttyUSB0" on Linux)
            baud_rate: Serial baud rate (e.g., 115200)
            port: rigctld TCP port (default 4532)
            civ_address: CI-V address for Icom radios in hex (e.g., "94" for 0x94), empty for default
        """
        self.model_id = model_id
        self.serial_port = serial_port
        self.baud_rate = baud_rate
        self.port = port
        self.civ_address = civ_address
        self.process: Optional[subprocess.Popen] = None
        self._is_managed = False  # True if we started the process

    def is_running(self) -> bool:
        """
        Check if rigctld is already running (by trying to connect)

        Returns:
            True if rigctld is reachable
        """
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(1.0)
            sock.connect(("localhost", self.port))
            sock.close()
            return True
        except (socket.error, ConnectionRefusedError):
            return False

    def start(self, timeout: float = 30.0) -> bool:
        """
        Start rigctld daemon

        Args:
            timeout: How long to wait for rigctld to start (seconds, default 30)

        Returns:
            True if rigctld is running (either already running or successfully started)

        Note:
            Some radios (like IC-705) may take 20+ seconds to start due to
            initialization errors that are eventually ignored.
        """
        # Check if already running
        if self.is_running():
            logger.info("rigctld is already running")
            return True

        # Find rigctld executable
        # 1. Check for bundled version first (PyInstaller bundle)
        rigctld_path = get_bundled_rigctld_path()

        # 2. Fall back to PATH if not bundled
        if not rigctld_path:
            rigctld_path = shutil.which("rigctld")
            if not rigctld_path and platform.system() == 'Windows':
                rigctld_path = shutil.which("rigctld.exe")

        # 3. Give up if still not found
        if not rigctld_path:
            logger.error("rigctld not found.")
            logger.error("Hamlib is bundled with CQSentinel but rigctld.exe was not found.")
            logger.error("Please reinstall CQSentinel or install Hamlib manually:")
            logger.error("  Download from: https://github.com/Hamlib/Hamlib/releases")
            return False

        logger.info(f"Found rigctld at: {rigctld_path}")

        # Build command
        cmd = [
            rigctld_path,
            "-m", str(self.model_id),
            "-r", self.serial_port,
            "-s", str(self.baud_rate),
            "-t", str(self.port),
        ]

        # Add CI-V address if specified (for Icom radios)
        if self.civ_address:
            try:
                # Convert hex string to decimal for rigctld -c parameter
                civ_decimal = int(self.civ_address, 16)
                cmd.extend(["-c", str(civ_decimal)])
                logger.info(f"Using CI-V address: 0x{self.civ_address} ({civ_decimal})")
            except ValueError:
                logger.warning(f"Invalid CI-V address '{self.civ_address}', using default")

        # Disable auto power-on check to avoid initialization errors
        # Some Icom radios (like IC-705) reject the power status command
        cmd.extend([
            "--set-conf", "auto_power_on=0",
        ])

        # On Windows, add additional flags for stability
        if platform.system() == 'Windows':
            cmd.extend([
                "-vvvvv",  # Verbose logging for debugging
            ])

        logger.info(f"Starting rigctld: {' '.join(cmd)}")
        logger.info(f"Model ID: {self.model_id}, Serial Port: {self.serial_port}, Baud: {self.baud_rate}")

        try:
            # Start process
            # Don't capture stdout/stderr to prevent pipe blocking on Windows
            # rigctld with -vvvvv generates massive output that fills pipe buffers
            # On Windows, use CREATE_NO_WINDOW to hide console
            if platform.system() == 'Windows':
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                startupinfo.wShowWindow = 0  # SW_HIDE

                self.process = subprocess.Popen(
                    cmd,
                    startupinfo=startupinfo,
                    creationflags=subprocess.CREATE_NO_WINDOW,
                )
            else:
                self.process = subprocess.Popen(cmd)

            self._is_managed = True

            # Wait for rigctld to be ready
            start_time = time.time()

            while time.time() - start_time < timeout:
                # Check if process died
                if self.process.poll() is not None:
                    # Process terminated
                    logger.error(f"rigctld process died with exit code {self.process.returncode}")
                    logger.error("Common causes:")
                    logger.error("  1. Serial port access denied (check no other program is using the radio)")
                    logger.error("  2. Serial port not found (check Settings > Radio > Serial Port)")
                    logger.error("  3. Radio model incorrect or radio powered off")
                    logger.error("  4. Serial cable not connected")
                    return False

                # Check if rigctld is listening
                if self.is_running():
                    elapsed = time.time() - start_time
                    logger.info(f"rigctld started successfully in {elapsed:.1f}s (PID: {self.process.pid})")
                    return True

                time.sleep(0.2)

            # Timeout - but check one more time if port is available
            # rigctld might be listening despite protocol errors
            if self.is_running():
                logger.warning(f"rigctld started with errors but is listening on port {self.port}")
                return True

            logger.error(f"rigctld failed to start within {timeout} seconds")
            logger.error("The process may still be initializing. Check:")
            logger.error("  1. Radio is powered on and connected")
            logger.error("  2. Serial port settings are correct")
            logger.error("  3. No other program is using the radio")

            self.stop()
            return False

        except FileNotFoundError as e:
            logger.error(f"rigctld executable not found: {e}")
            logger.error("Install Hamlib and ensure it's in your PATH")
            return False
        except Exception as e:
            logger.error(f"Failed to start rigctld: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return False

    def stop(self):
        """Stop rigctld daemon if we started it"""
        if self.process and self._is_managed:
            logger.info("Stopping rigctld...")
            try:
                # On Windows, terminate the entire process tree
                if platform.system() == 'Windows':
                    try:
                        # Try to kill process tree on Windows using taskkill
                        subprocess.run(
                            ['taskkill', '/F', '/T', '/PID', str(self.process.pid)],
                            capture_output=True,
                            timeout=5
                        )
                        logger.info("rigctld process tree terminated (Windows)")
                    except Exception as e:
                        logger.warning(f"taskkill failed, using terminate: {e}")
                        self.process.terminate()
                else:
                    # On Unix, terminate normally
                    self.process.terminate()

                # Wait for process to exit
                self.process.wait(timeout=5.0)
                logger.info("rigctld stopped")

            except subprocess.TimeoutExpired:
                logger.warning("rigctld did not terminate, forcing kill")
                try:
                    self.process.kill()
                    self.process.wait(timeout=2.0)
                except Exception as e:
                    logger.error(f"Force kill failed: {e}")
            except Exception as e:
                logger.error(f"Error stopping rigctld: {e}")

            self.process = None
            self._is_managed = False

    def restart(self, timeout: float = 5.0) -> bool:
        """
        Restart rigctld daemon

        Args:
            timeout: How long to wait for rigctld to start

        Returns:
            True if successfully restarted
        """
        self.stop()
        time.sleep(1.0)  # Give system time to release port
        return self.start(timeout)

    def get_status(self) -> dict:
        """
        Get rigctld status information

        Returns:
            Dictionary with status info
        """
        return {
            'running': self.is_running(),
            'managed': self._is_managed,
            'pid': self.process.pid if self.process else None,
            'model_id': self.model_id,
            'serial_port': self.serial_port,
            'baud_rate': self.baud_rate,
            'port': self.port,
            'civ_address': self.civ_address,
        }

    def __enter__(self):
        """Context manager entry"""
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit"""
        self.stop()

    def __repr__(self):
        status = "running" if self.is_running() else "stopped"
        managed = " (managed)" if self._is_managed else ""
        return f"<RigctldManager model={self.model_id} port={self.port} {status}{managed}>"


def find_serial_port() -> Optional[str]:
    """
    Auto-detect radio serial port (CI-V for Icom IC-705)

    For IC-705 over USB, there are two ports:
    - CI-V port (Device A) - for radio control
    - GPS port - NOT for radio control

    Returns:
        Best serial port for radio control, or None
    """
    try:
        import serial.tools.list_ports

        ports = list(serial.tools.list_ports.comports())
        if not ports:
            logger.warning("No serial ports found")
            return None

        # Log all available ports for debugging
        logger.info(f"Found {len(ports)} serial port(s):")
        for port in ports:
            logger.info(f"  {port.device}: {port.description} (hwid: {port.hwid})")

        # Priority 1: Prefer ports with "CI-V" or "Device A" in description
        for port in ports:
            desc_upper = port.description.upper()
            if 'CI-V' in desc_upper or 'DEVICE A' in desc_upper:
                logger.info(f"Auto-detected CI-V port: {port.device} ({port.description})")
                return port.device

        # Priority 2: Skip GPS ports (for IC-705 and similar radios)
        non_gps_ports = []
        for port in ports:
            desc_upper = port.description.upper()
            if 'GPS' not in desc_upper and 'GNSS' not in desc_upper:
                non_gps_ports.append(port)

        # Priority 3: Prefer USB ports (excluding GPS)
        for port in non_gps_ports:
            if 'USB' in port.description.upper():
                logger.info(f"Auto-detected USB serial port: {port.device} ({port.description})")
                return port.device

        # Priority 4: Use first non-GPS port
        if non_gps_ports:
            logger.info(f"Auto-detected serial port: {non_gps_ports[0].device} ({non_gps_ports[0].description})")
            return non_gps_ports[0].device

        # Priority 5: Fall back to first port (even if GPS)
        logger.warning(f"Only GPS port available, using anyway: {ports[0].device}")
        return ports[0].device

    except ImportError:
        logger.warning("pyserial not installed, cannot auto-detect serial port")

    return None
