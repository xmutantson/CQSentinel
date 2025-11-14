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

    def __init__(self, model_id: int, serial_port: str, baud_rate: int, port: int = 4532):
        """
        Initialize rigctld manager

        Args:
            model_id: Hamlib radio model ID (e.g., 3085 for IC-705)
            serial_port: Serial port device (e.g., "COM3" on Windows, "/dev/ttyUSB0" on Linux)
            baud_rate: Serial baud rate (e.g., 115200)
            port: rigctld TCP port (default 4532)
        """
        self.model_id = model_id
        self.serial_port = serial_port
        self.baud_rate = baud_rate
        self.port = port
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

        # Find rigctld executable
        rigctld_path = shutil.which("rigctld")
        if not rigctld_path:
            logger.error("rigctld not found in PATH. Please install Hamlib.")
            return False

        # Build command
        cmd = [
            rigctld_path,
            "-m", str(self.model_id),
            "-r", self.serial_port,
            "-s", str(self.baud_rate),
            "-t", str(self.port),
        ]

        # On Windows, add additional flags for stability
        if platform.system() == 'Windows':
            cmd.extend([
                "-vvvvv",  # Verbose logging for debugging
            ])

        logger.info(f"Starting rigctld: {' '.join(cmd)}")

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
                    creationflags=subprocess.CREATE_NO_WINDOW
                )
            else:
                self.process = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                )

            self._is_managed = True

            # Wait for rigctld to be ready
            start_time = time.time()
            while time.time() - start_time < timeout:
                if self.is_running():
                    logger.info(f"rigctld started successfully (PID: {self.process.pid})")
                    return True
                time.sleep(0.2)

            # Timeout - kill process
            logger.error("rigctld failed to start within timeout")
            self.stop()
            return False

        except Exception as e:
            logger.error(f"Failed to start rigctld: {e}")
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
