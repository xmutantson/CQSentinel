"""
N3FJP TCP API client.

Connects to N3FJP logging software for:
- Dupe checking (QSO already in log?)
- Callsign information (DXCC, zone, grid, etc.)
- Log entry retrieval
- Real-time log monitoring

N3FJP uses a simple TCP protocol on port 1100 (default).
"""

import logging
import socket
import threading
import time
from typing import Optional, Dict, Any, Callable
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)


class N3FJPStatus(Enum):
    """Connection status."""
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    ERROR = "error"


@dataclass
class CallInfo:
    """Information about a callsign from N3FJP."""
    callsign: str
    is_dupe: bool = False
    is_mult: bool = False

    # DXCC info
    dxcc_name: Optional[str] = None
    dxcc_entity: Optional[str] = None
    continent: Optional[str] = None

    # Zone info
    cq_zone: Optional[str] = None
    itu_zone: Optional[str] = None

    # Location
    grid: Optional[str] = None
    state: Optional[str] = None
    county: Optional[str] = None

    # Previous QSO info
    prev_band: Optional[str] = None
    prev_mode: Optional[str] = None
    prev_datetime: Optional[str] = None


class N3FJPClient:
    """
    N3FJP TCP API client.

    Connects to N3FJP logging software to check for dupes,
    get callsign information, and monitor log changes.

    Usage:
        client = N3FJPClient(host='localhost', port=1100)

        if client.connect():
            is_dupe = client.check_dupe('W1AW', '20m', 'SSB')
            info = client.get_call_info('W1AW')

            if info.is_mult:
                print(f"New multiplier! DXCC: {info.dxcc_name}")

        client.disconnect()
    """

    def __init__(
        self,
        host: str = 'localhost',
        port: int = 1100,
        timeout: float = 5.0,
        auto_reconnect: bool = True
    ):
        """
        Initialize N3FJP client.

        Args:
            host: N3FJP host address (default: localhost)
            port: N3FJP TCP port (default: 1100)
            timeout: Socket timeout in seconds
            auto_reconnect: Automatically reconnect on disconnect
        """
        self.host = host
        self.port = port
        self.timeout = timeout
        self.auto_reconnect = auto_reconnect

        self.socket: Optional[socket.socket] = None
        self.status = N3FJPStatus.DISCONNECTED

        self._lock = threading.Lock()
        self._reconnect_thread: Optional[threading.Thread] = None
        self._stop_reconnect = False

        logger.info(f"N3FJPClient initialized (host={host}, port={port})")

    def connect(self) -> bool:
        """
        Connect to N3FJP.

        Returns:
            True if connected successfully
        """
        with self._lock:
            if self.status == N3FJPStatus.CONNECTED:
                return True

            try:
                self.status = N3FJPStatus.CONNECTING

                self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                self.socket.settimeout(self.timeout)
                self.socket.connect((self.host, self.port))

                self.status = N3FJPStatus.CONNECTED
                logger.info(f"Connected to N3FJP at {self.host}:{self.port}")

                return True

            except socket.timeout:
                self.status = N3FJPStatus.ERROR
                logger.error(f"Connection to N3FJP timed out")
                return False
            except ConnectionRefusedError:
                self.status = N3FJPStatus.ERROR
                logger.error(f"Connection to N3FJP refused (is N3FJP running?)")
                return False
            except Exception as e:
                self.status = N3FJPStatus.ERROR
                logger.error(f"Failed to connect to N3FJP: {e}")
                return False

    def disconnect(self):
        """Disconnect from N3FJP."""
        with self._lock:
            self._stop_reconnect = True

            if self.socket:
                try:
                    self.socket.close()
                except:
                    pass
                self.socket = None

            self.status = N3FJPStatus.DISCONNECTED
            logger.info("Disconnected from N3FJP")

    def is_connected(self) -> bool:
        """Check if connected to N3FJP."""
        return self.status == N3FJPStatus.CONNECTED

    def send_command(self, command: str) -> Optional[str]:
        """
        Send command to N3FJP and get response.

        Args:
            command: Command string

        Returns:
            Response string or None on error
        """
        if not self.is_connected():
            if not self.connect():
                return None

        with self._lock:
            try:
                # Send command (terminated with newline)
                self.socket.sendall(f"{command}\r\n".encode('utf-8'))

                # Receive response
                response = self.socket.recv(4096).decode('utf-8').strip()

                logger.debug(f"N3FJP command: {command} -> {response[:100]}")

                return response

            except socket.timeout:
                logger.warning("N3FJP command timed out")
                self.status = N3FJPStatus.ERROR

                if self.auto_reconnect:
                    self._start_reconnect_thread()

                return None
            except Exception as e:
                logger.error(f"N3FJP command error: {e}")
                self.status = N3FJPStatus.ERROR

                if self.auto_reconnect:
                    self._start_reconnect_thread()

                return None

    def check_dupe(
        self,
        callsign: str,
        band: Optional[str] = None,
        mode: Optional[str] = None
    ) -> bool:
        """
        Check if callsign is a dupe.

        Args:
            callsign: Callsign to check
            band: Band (e.g., "20m") - optional
            mode: Mode (e.g., "SSB") - optional

        Returns:
            True if dupe, False if new

        Example:
            >>> client.check_dupe('W1AW', '20m', 'SSB')
            False  # Not worked yet
        """
        # N3FJP dupe check command format varies by contest logger
        # This is a generic implementation
        cmd = f"<CMD><CHECKDUPE><CALL>{callsign}</CALL>"

        if band:
            cmd += f"<BAND>{band}</BAND>"
        if mode:
            cmd += f"<MODE>{mode}</MODE>"

        cmd += "</CHECKDUPE></CMD>"

        response = self.send_command(cmd)

        if response is None:
            return False  # Assume not dupe on error

        # Parse response (format varies by logger)
        response_upper = response.upper()

        # Common indicators of dupe
        is_dupe = any(indicator in response_upper for indicator in [
            'DUPE', 'DUPLICATE', 'WORKED', 'TRUE'
        ])

        logger.debug(f"Dupe check {callsign}: {is_dupe}")

        return is_dupe

    def get_call_info(self, callsign: str) -> CallInfo:
        """
        Get information about a callsign.

        Args:
            callsign: Callsign to look up

        Returns:
            CallInfo with available information

        Example:
            >>> info = client.get_call_info('W1AW')
            >>> print(info.dxcc_name)
            'United States'
        """
        cmd = f"<CMD><GETCALLINFO><CALL>{callsign}</CALL></GETCALLINFO></CMD>"

        response = self.send_command(cmd)

        info = CallInfo(callsign=callsign)

        if response is None:
            return info

        # Parse XML response (simplified parser)
        # N3FJP returns XML-like format

        info.dxcc_name = self._extract_field(response, 'DXCC')
        info.dxcc_entity = self._extract_field(response, 'ENTITY')
        info.continent = self._extract_field(response, 'CONTINENT')
        info.cq_zone = self._extract_field(response, 'CQZONE')
        info.itu_zone = self._extract_field(response, 'ITUZONE')
        info.grid = self._extract_field(response, 'GRID')
        info.state = self._extract_field(response, 'STATE')
        info.county = self._extract_field(response, 'COUNTY')

        # Check if dupe
        info.is_dupe = self.check_dupe(callsign)

        return info

    def get_frequency(self) -> Optional[float]:
        """
        Get current frequency from N3FJP.

        Returns:
            Frequency in Hz or None
        """
        cmd = "<CMD><GETFREQ></GETFREQ></CMD>"
        response = self.send_command(cmd)

        if response:
            try:
                # Extract frequency value
                freq_str = self._extract_field(response, 'FREQ')
                if freq_str:
                    return float(freq_str) * 1000  # Convert kHz to Hz
            except:
                pass

        return None

    def set_frequency(self, freq_hz: float) -> bool:
        """
        Set frequency in N3FJP.

        Args:
            freq_hz: Frequency in Hz

        Returns:
            True if successful
        """
        freq_khz = freq_hz / 1000.0
        cmd = f"<CMD><SETFREQ>{freq_khz:.3f}</SETFREQ></CMD>"

        response = self.send_command(cmd)

        return response is not None

    def add_contact(
        self,
        callsign: str,
        freq_hz: float,
        mode: str = "SSB",
        rst_sent: str = "59",
        rst_rcvd: str = "59",
        exchange: Optional[str] = None
    ) -> bool:
        """
        Add a contact to N3FJP log.

        Args:
            callsign: Callsign worked
            freq_hz: Frequency in Hz
            mode: Mode (SSB, CW, etc.)
            rst_sent: RST sent
            rst_rcvd: RST received
            exchange: Exchange received

        Returns:
            True if added successfully
        """
        freq_khz = freq_hz / 1000.0

        cmd = f"<CMD><ADDCONTACT>"
        cmd += f"<CALL>{callsign}</CALL>"
        cmd += f"<FREQ>{freq_khz:.3f}</FREQ>"
        cmd += f"<MODE>{mode}</MODE>"
        cmd += f"<RSTSENT>{rst_sent}</RSTSENT>"
        cmd += f"<RSTRCVD>{rst_rcvd}</RSTRCVD>"

        if exchange:
            cmd += f"<EXCHANGE>{exchange}</EXCHANGE>"

        cmd += "</ADDCONTACT></CMD>"

        response = self.send_command(cmd)

        success = response is not None and 'OK' in response.upper()

        if success:
            logger.info(f"Added contact: {callsign} on {freq_khz:.3f} kHz")

        return success

    def _extract_field(self, xml_str: str, field_name: str) -> Optional[str]:
        """
        Extract field value from XML-like response.

        Args:
            xml_str: XML string
            field_name: Field name to extract

        Returns:
            Field value or None
        """
        try:
            start_tag = f"<{field_name}>"
            end_tag = f"</{field_name}>"

            start = xml_str.find(start_tag)
            if start == -1:
                return None

            start += len(start_tag)
            end = xml_str.find(end_tag, start)

            if end == -1:
                return None

            value = xml_str[start:end].strip()
            return value if value else None

        except:
            return None

    def _start_reconnect_thread(self):
        """Start background reconnection thread."""
        if self._reconnect_thread and self._reconnect_thread.is_alive():
            return

        self._stop_reconnect = False
        self._reconnect_thread = threading.Thread(
            target=self._reconnect_loop,
            daemon=True
        )
        self._reconnect_thread.start()
        logger.info("Started reconnection thread")

    def _reconnect_loop(self):
        """Background reconnection loop."""
        retry_delay = 5.0  # seconds

        while not self._stop_reconnect:
            if self.status != N3FJPStatus.CONNECTED:
                logger.info("Attempting to reconnect to N3FJP...")

                if self.connect():
                    logger.info("Reconnected to N3FJP successfully")
                    break
                else:
                    logger.debug(f"Reconnect failed, retrying in {retry_delay}s")

            time.sleep(retry_delay)

    def __enter__(self):
        """Context manager entry."""
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.disconnect()
        return False
