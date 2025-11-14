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
from typing import Optional
from pathlib import Path

logger = logging.getLogger(__name__)


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

    def start(self, timeout: float = 5.0) -> bool:
        """
        Start rigctld daemon

        Args:
            timeout: How long to wait for rigctld to start (seconds)

        Returns:
            True if rigctld is running (either already running or successfully started)
        """
        # Check if already running
        if self.is_running():
            logger.info("rigctld is already running")
            return True

        # Find rigctld executable (check both rigctld and rigctld.exe on Windows)
        rigctld_path = shutil.which("rigctld")
        if not rigctld_path and platform.system() == 'Windows':
            rigctld_path = shutil.which("rigctld.exe")

        if not rigctld_path:
            logger.error("rigctld not found in PATH.")
            logger.error("Please install Hamlib. On Windows, ensure Hamlib bin directory is in PATH.")
            logger.error("Download from: https://github.com/Hamlib/Hamlib/releases")
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

        # On Windows, add additional flags for stability
        if platform.system() == 'Windows':
            cmd.extend([
                "-vvvvv",  # Verbose logging for debugging
            ])

        logger.info(f"Starting rigctld: {' '.join(cmd)}")
        logger.info(f"Model ID: {self.model_id}, Serial Port: {self.serial_port}, Baud: {self.baud_rate}")

        try:
            # Start process
            # On Windows, use CREATE_NO_WINDOW to hide console
            if platform.system() == 'Windows':
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                startupinfo.wShowWindow = 0  # SW_HIDE

                self.process = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    startupinfo=startupinfo,
                    creationflags=subprocess.CREATE_NO_WINDOW,
                    text=True,
                    bufsize=1
                )
            else:
                self.process = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    bufsize=1
                )

            self._is_managed = True

            # Wait for rigctld to be ready
            start_time = time.time()
            last_check = start_time
            stderr_output = []

            while time.time() - start_time < timeout:
                # Check if process died
                if self.process.poll() is not None:
                    # Process terminated
                    stdout, stderr = self.process.communicate(timeout=1)
                    logger.error(f"rigctld process died with exit code {self.process.returncode}")
                    if stderr:
                        logger.error(f"rigctld stderr: {stderr}")
                        stderr_output.append(stderr)
                    if stdout:
                        logger.info(f"rigctld stdout: {stdout}")

                    # Provide specific error guidance
                    error_msg = stderr.lower() if stderr else ""
                    if "permission denied" in error_msg or "access is denied" in error_msg:
                        logger.error("Serial port access denied. Check that:")
                        logger.error("  1. No other program is using the radio")
                        logger.error("  2. You have permission to access the serial port")
                    elif "no such file" in error_msg or "cannot open" in error_msg:
                        logger.error(f"Serial port {self.serial_port} not found.")
                        logger.error("  Check Settings > Radio > Serial Port")
                    elif "rig_init" in error_msg:
                        logger.error("Failed to initialize radio. Check that:")
                        logger.error("  1. Radio model is correct")
                        logger.error("  2. Radio is powered on")
                        logger.error("  3. Serial cable is connected")

                    return False

                # Check if rigctld is listening
                if self.is_running():
                    logger.info(f"rigctld started successfully (PID: {self.process.pid})")
                    return True

                # Log stderr periodically (non-blocking read)
                if time.time() - last_check > 0.5:
                    try:
                        # Try to read any available stderr (non-blocking)
                        import select
                        if hasattr(select, 'select'):
                            readable, _, _ = select.select([self.process.stderr], [], [], 0)
                            if readable:
                                line = self.process.stderr.readline()
                                if line:
                                    logger.debug(f"rigctld: {line.strip()}")
                                    stderr_output.append(line)
                    except:
                        pass  # Non-blocking read not available

                    last_check = time.time()

                time.sleep(0.2)

            # Timeout - get any error output and kill process
            logger.error(f"rigctld failed to start within {timeout} seconds")

            # Try to get stderr output
            try:
                # Give it a moment to write error messages
                time.sleep(0.5)
                if self.process.poll() is None:
                    self.process.terminate()
                stdout, stderr = self.process.communicate(timeout=2)
                if stderr:
                    logger.error(f"rigctld error output: {stderr}")
                if stdout:
                    logger.info(f"rigctld output: {stdout}")
            except:
                pass

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
                self.process.terminate()
                self.process.wait(timeout=5.0)
                logger.info("rigctld stopped")
            except subprocess.TimeoutExpired:
                logger.warning("rigctld did not terminate, forcing kill")
                self.process.kill()
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
    Auto-detect radio serial port

    Returns:
        First available serial port, or None
    """
    try:
        import serial.tools.list_ports

        ports = list(serial.tools.list_ports.comports())
        if ports:
            # Prefer USB ports
            for port in ports:
                if 'USB' in port.description.upper():
                    logger.info(f"Auto-detected USB serial port: {port.device}")
                    return port.device

            # Fall back to first port
            logger.info(f"Auto-detected serial port: {ports[0].device}")
            return ports[0].device

    except ImportError:
        logger.warning("pyserial not installed, cannot auto-detect serial port")

    return None
