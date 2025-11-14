"""
Hamlib CAT Controller

Provides interface to control amateur radios via Hamlib's rigctld daemon.
Supports 200+ radio models including Icom IC-705.
"""

import socket
import time
import logging
from typing import Optional, Tuple
from enum import Enum

logger = logging.getLogger(__name__)


class RadioMode(Enum):
    """Radio operating modes"""
    USB = "USB"
    LSB = "LSB"
    CW = "CW"
    AM = "AM"
    FM = "FM"


class RadioConnectionError(Exception):
    """Raised when radio connection fails"""
    pass


class HamlibController:
    """
    Interface to Hamlib rigctld for CAT control

    Communicates with rigctld daemon via TCP socket.
    rigctld must be running separately, e.g.:
        rigctld -m 3085 -r /dev/ttyUSB0 -s 115200

    where 3085 is the model number for IC-705
    """

    def __init__(self, host: str = "localhost", port: int = 4532):
        """
        Initialize Hamlib controller

        Args:
            host: rigctld server hostname
            port: rigctld server port (default 4532)
        """
        self.host = host
        self.port = port
        self.sock: Optional[socket.socket] = None
        self._connected = False
        self._last_frequency = 0
        self._last_mode = None

    def connect(self, timeout: float = 5.0) -> bool:
        """
        Connect to rigctld daemon

        Args:
            timeout: Connection timeout in seconds

        Returns:
            True if connected successfully

        Raises:
            RadioConnectionError: If connection fails
        """
        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.sock.settimeout(timeout)
            self.sock.connect((self.host, self.port))
            self._connected = True

            # Test connection with get_freq
            freq = self.get_frequency()
            logger.info(f"Connected to rigctld at {self.host}:{self.port}, current frequency: {freq/1e6:.3f} MHz")
            return True

        except socket.error as e:
            self._connected = False
            raise RadioConnectionError(f"Failed to connect to rigctld at {self.host}:{self.port}: {e}")

    def disconnect(self):
        """Close connection to rigctld"""
        if self.sock:
            try:
                self.sock.close()
            except:
                pass
            self.sock = None
        self._connected = False
        logger.info("Disconnected from rigctld")

    def _send_command(self, command: str) -> str:
        """
        Send command to rigctld and get response

        Args:
            command: Hamlib command string

        Returns:
            Response from rigctld

        Raises:
            RadioConnectionError: If not connected or command fails
        """
        if not self._connected or not self.sock:
            raise RadioConnectionError("Not connected to rigctld")

        try:
            # Send command
            self.sock.sendall(f"{command}\n".encode())

            # Read response
            response = b""
            while True:
                chunk = self.sock.recv(1024)
                if not chunk:
                    break
                response += chunk
                if b"\n" in response:
                    break

            result = response.decode('utf-8').strip()

            # Check for errors
            if result.startswith("RPRT"):
                code = result.split()[1] if len(result.split()) > 1 else "unknown"
                if code != "0":
                    raise RadioConnectionError(f"Command '{command}' failed with code {code}")
                return ""

            return result

        except socket.error as e:
            self._connected = False
            raise RadioConnectionError(f"Communication error: {e}")

    def get_frequency(self) -> int:
        """
        Get current VFO frequency

        Returns:
            Frequency in Hz
        """
        response = self._send_command("f")

        # Handle empty response (can happen with concurrent requests or rigctld errors)
        if not response or response.strip() == "":
            # Return last known frequency if available
            if self._last_frequency:
                logger.warning("Empty frequency response from rigctld, using cached value")
                return self._last_frequency
            else:
                raise RadioConnectionError("rigctld returned empty frequency and no cached value available")

        try:
            freq = int(response)
            self._last_frequency = freq
            return freq
        except ValueError as e:
            logger.error(f"Invalid frequency response from rigctld: '{response}'")
            # Try to return last known frequency
            if self._last_frequency:
                logger.warning("Using cached frequency after parse error")
                return self._last_frequency
            else:
                raise RadioConnectionError(f"Invalid frequency format: '{response}'")

    def set_frequency(self, freq_hz: int) -> bool:
        """
        Set VFO frequency

        Args:
            freq_hz: Frequency in Hz

        Returns:
            True if successful
        """
        try:
            self._send_command(f"F {freq_hz}")
            self._last_frequency = freq_hz
            logger.debug(f"Set frequency to {freq_hz/1e6:.6f} MHz")
            return True
        except RadioConnectionError as e:
            logger.error(f"Failed to set frequency: {e}")
            return False

    def get_mode(self) -> Tuple[str, int]:
        """
        Get current operating mode and bandwidth

        Returns:
            Tuple of (mode, bandwidth_hz)
        """
        response = self._send_command("m")
        lines = response.strip().split('\n')

        mode = lines[0] if len(lines) > 0 else "USB"
        bandwidth = int(lines[1]) if len(lines) > 1 else 2400

        self._last_mode = mode
        return mode, bandwidth

    def set_mode(self, mode: str, bandwidth: int = 2400) -> bool:
        """
        Set operating mode and bandwidth

        Args:
            mode: Mode string (USB, LSB, CW, AM, FM)
            bandwidth: Bandwidth in Hz

        Returns:
            True if successful
        """
        try:
            self._send_command(f"M {mode} {bandwidth}")
            self._last_mode = mode
            logger.debug(f"Set mode to {mode}, bandwidth {bandwidth} Hz")
            return True
        except RadioConnectionError as e:
            logger.error(f"Failed to set mode: {e}")
            return False

    def get_strength(self) -> int:
        """
        Get signal strength (S-meter)

        Returns:
            Signal strength (0-9 for S0-S9, 10+ for S9+10, etc.)
            Returns -1 on error
        """
        try:
            response = self._send_command("l STRENGTH")
            # Hamlib returns strength in dB (usually negative)
            # Convert to S-units: S9 = 0dB, S8 = -6dB, S7 = -12dB, etc.
            # Each S-unit is 6dB
            db_value = int(float(response))

            if db_value >= 0:
                # S9 or above: S9+XdB
                return 9 + (db_value // 10)  # S9+10dB, S9+20dB, etc.
            else:
                # Below S9: Calculate S-unit
                s_unit = 9 + (db_value // 6)
                return max(0, s_unit)  # Clamp to S0 minimum

        except (ValueError, RadioConnectionError) as e:
            logger.debug(f"Failed to get signal strength: {e}")
            return -1

    def get_ptt(self) -> bool:
        """
        Get PTT (transmit) status

        Returns:
            True if transmitting, False if receiving
        """
        try:
            response = self._send_command("t")
            return response == "1"
        except RadioConnectionError:
            return False

    def set_ptt(self, transmit: bool) -> bool:
        """
        Set PTT (transmit) state

        Args:
            transmit: True to transmit, False to receive

        Returns:
            True if successful

        Note: CQSentinel is receive-only, this is for completeness
        """
        try:
            self._send_command(f"T {1 if transmit else 0}")
            return True
        except RadioConnectionError as e:
            logger.error(f"Failed to set PTT: {e}")
            return False

    def get_vfo(self) -> str:
        """
        Get current VFO

        Returns:
            VFO name (e.g., "VFOA", "VFOB")
        """
        try:
            response = self._send_command("v")
            return response
        except RadioConnectionError:
            return "VFOA"

    @property
    def is_connected(self) -> bool:
        """Check if connected to rigctld"""
        return self._connected

    @property
    def last_frequency(self) -> int:
        """Get last known frequency (cached)"""
        return self._last_frequency

    @property
    def last_mode(self) -> Optional[str]:
        """Get last known mode (cached)"""
        return self._last_mode

    def __enter__(self):
        """Context manager entry"""
        if not self._connected:
            self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit"""
        self.disconnect()

    def __repr__(self):
        status = "connected" if self._connected else "disconnected"
        return f"<HamlibController {self.host}:{self.port} ({status})>"
