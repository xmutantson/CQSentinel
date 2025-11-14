"""
Band map visualization widget.

Displays stations on a frequency spectrum with color-coded markers,
signal strength indicators, and click-to-tune functionality.
"""

import logging
from typing import Optional, List

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QFrame
)
from PyQt5.QtCore import Qt, pyqtSignal, QPoint, QRect
from PyQt5.QtGui import QPainter, QColor, QPen, QFont, QBrush, QPainterPath

from cqsentinel.bandmap.station import BandMapStation, BandMapState, StationStatus

logger = logging.getLogger(__name__)


# Color scheme for station status
STATUS_COLORS = {
    StationStatus.NEW: QColor(0, 255, 0),  # Green
    StationStatus.MULTIPLIER: QColor(255, 215, 0),  # Gold
    StationStatus.WORKED: QColor(255, 0, 0),  # Red
    StationStatus.UNCLEAR: QColor(128, 128, 128),  # Gray
}


class BandMapWidget(QWidget):
    """
    Band map visualization widget.

    Displays stations as markers on a frequency spectrum with:
    - Color-coded status (new/worked/multiplier)
    - Signal strength indicators
    - Callsign labels
    - Click-to-tune functionality

    Signals:
        station_clicked: Emitted when user clicks a station (frequency_hz)
        station_selected: Emitted when station is selected for details (BandMapStation)
    """

    # Signals
    station_clicked = pyqtSignal(float)  # frequency_hz
    station_selected = pyqtSignal(object)  # BandMapStation

    def __init__(self, band_map_state: Optional[BandMapState] = None, parent=None):
        """
        Initialize band map widget.

        Args:
            band_map_state: BandMapState instance
            parent: Parent widget
        """
        super().__init__(parent)

        self.band_map = band_map_state or BandMapState()
        self.selected_station: Optional[BandMapStation] = None

        # Display settings
        self.freq_min = 14.000e6  # 14.000 MHz
        self.freq_max = 14.350e6  # 14.350 MHz
        self.marker_size = 20
        self.show_callsigns = True
        self.show_signal_strength = True

        self._init_ui()

        logger.info("BandMapWidget initialized")

    def _init_ui(self):
        """Initialize user interface."""
        layout = QVBoxLayout()

        # Header
        header_layout = QHBoxLayout()

        self.band_label = QLabel(f"Band: {self.band_map.band or 'Unknown'}")
        self.band_label.setStyleSheet("font-weight: bold;")
        header_layout.addWidget(self.band_label)

        header_layout.addStretch()

        self.stats_label = QLabel("Stations: 0 | New: 0 | Worked: 0")
        header_layout.addWidget(self.stats_label)

        layout.addLayout(header_layout)

        # Canvas for drawing
        self.setMinimumHeight(400)
        self.setMouseTracking(True)

        layout.addStretch()
        self.setLayout(layout)

        # Update display
        self.update_display()

    def set_band_map(self, band_map_state: BandMapState):
        """
        Set the band map state to display.

        Args:
            band_map_state: BandMapState instance
        """
        self.band_map = band_map_state
        self.band_label.setText(f"Band: {band_map_state.band or 'Unknown'}")
        self.update_display()

    def set_frequency_range(self, freq_min_hz: float, freq_max_hz: float):
        """
        Set the frequency range to display.

        Args:
            freq_min_hz: Minimum frequency in Hz
            freq_max_hz: Maximum frequency in Hz
        """
        self.freq_min = freq_min_hz
        self.freq_max = freq_max_hz
        self.update()

    def update_display(self):
        """Update the display with current band map data."""
        # Update statistics
        stats = self.band_map.get_statistics()
        self.stats_label.setText(
            f"Stations: {stats['total_stations']} | "
            f"New: {stats['new_stations']} | "
            f"Worked: {stats['worked_stations']}"
        )

        # Trigger repaint
        self.update()

    def paintEvent(self, event):
        """
        Paint the band map.

        Args:
            event: Paint event
        """
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Get widget dimensions
        width = self.width()
        height = self.height()

        # Draw background
        painter.fillRect(0, 0, width, height, QColor(20, 20, 30))

        # Draw frequency grid
        self._draw_frequency_grid(painter, width, height)

        # Draw stations
        self._draw_stations(painter, width, height)

        painter.end()

    def _draw_frequency_grid(self, painter: QPainter, width: int, height: int):
        """
        Draw frequency grid lines and labels.

        Args:
            painter: QPainter instance
            width: Widget width
            height: Widget height
        """
        # Grid settings
        pen = QPen(QColor(60, 60, 80), 1)
        painter.setPen(pen)

        font = QFont("Monospace", 9)
        painter.setFont(font)

        # Calculate frequency step (e.g., every 50 kHz)
        freq_range = self.freq_max - self.freq_min
        step = 50e3  # 50 kHz
        if freq_range > 1e6:
            step = 100e3  # 100 kHz for wider ranges

        # Draw vertical grid lines
        freq = self.freq_min
        while freq <= self.freq_max:
            x = self._freq_to_x(freq, width)

            # Draw grid line
            painter.drawLine(x, 0, x, height)

            # Draw frequency label
            freq_mhz = freq / 1e6
            label = f"{freq_mhz:.3f}"
            painter.setPen(QColor(150, 150, 150))
            painter.drawText(x - 30, height - 5, label)
            painter.setPen(pen)

            freq += step

    def _draw_stations(self, painter: QPainter, width: int, height: int):
        """
        Draw station markers.

        Args:
            painter: QPainter instance
            width: Widget width
            height: Widget height
        """
        for station in self.band_map.stations:
            self._draw_station_marker(painter, station, width, height)

    def _draw_station_marker(
        self,
        painter: QPainter,
        station: BandMapStation,
        width: int,
        height: int
    ):
        """
        Draw a single station marker.

        Args:
            painter: QPainter instance
            station: BandMapStation to draw
            width: Widget width
            height: Widget height
        """
        # Calculate position
        x = self._freq_to_x(station.frequency, width)
        y = height // 2  # Center vertically

        # Adjust y based on contestness (higher score = higher on display)
        if station.contestness_score > 0:
            offset = (station.contestness_score / 100.0) * (height * 0.3)
            y = int(height * 0.7 - offset)

        # Get status color
        color = STATUS_COLORS.get(station.status, STATUS_COLORS[StationStatus.UNCLEAR])

        # Highlight if selected
        if station == self.selected_station:
            pen = QPen(QColor(255, 255, 255), 3)
            painter.setPen(pen)
            painter.drawEllipse(x - self.marker_size//2 - 3, y - self.marker_size//2 - 3,
                              self.marker_size + 6, self.marker_size + 6)

        # Draw marker circle
        painter.setBrush(QBrush(color))
        painter.setPen(QPen(color.darker(), 2))
        painter.drawEllipse(x - self.marker_size//2, y - self.marker_size//2,
                           self.marker_size, self.marker_size)

        # Draw callsign label
        if self.show_callsigns and station.callsign:
            painter.setPen(QColor(255, 255, 255))
            font = QFont("Monospace", 8, QFont.Weight.Bold)
            painter.setFont(font)

            # Draw callsign above marker
            text_x = x - 20
            text_y = y - self.marker_size
            painter.drawText(text_x, text_y, station.callsign)

            # Draw status below
            font.setBold(False)
            font.setPointSize(7)
            painter.setFont(font)
            painter.setPen(color)
            status_text = station.display_status
            painter.drawText(text_x, y + self.marker_size + 12, status_text)

        # Draw signal strength indicator
        if self.show_signal_strength and station.signal_strength is not None:
            self._draw_signal_indicator(painter, x, y, station.signal_strength)

    def _draw_signal_indicator(
        self,
        painter: QPainter,
        x: int,
        y: int,
        signal_strength: float
    ):
        """
        Draw signal strength indicator bars.

        Args:
            painter: QPainter instance
            x: X position
            y: Y position
            signal_strength: Signal strength (0-9+)
        """
        # Draw small bars indicating signal strength
        bar_width = 2
        bar_spacing = 3
        max_bars = 9

        # Normalize signal strength to number of bars
        num_bars = min(int(signal_strength), max_bars)

        for i in range(num_bars):
            bar_height = 3 + i * 2
            bar_x = x + self.marker_size//2 + 5 + i * bar_spacing
            bar_y = y + self.marker_size//2 - bar_height

            # Color: green for strong, yellow for medium, red for weak
            if i < 3:
                color = QColor(255, 0, 0)  # Red
            elif i < 6:
                color = QColor(255, 255, 0)  # Yellow
            else:
                color = QColor(0, 255, 0)  # Green

            painter.fillRect(bar_x, bar_y, bar_width, bar_height, color)

    def _freq_to_x(self, frequency: float, width: int) -> int:
        """
        Convert frequency to x-coordinate.

        Args:
            frequency: Frequency in Hz
            width: Widget width

        Returns:
            X-coordinate in pixels
        """
        margin = 50
        freq_range = self.freq_max - self.freq_min
        ratio = (frequency - self.freq_min) / freq_range
        return int(margin + ratio * (width - 2 * margin))

    def _x_to_freq(self, x: int, width: int) -> float:
        """
        Convert x-coordinate to frequency.

        Args:
            x: X-coordinate in pixels
            width: Widget width

        Returns:
            Frequency in Hz
        """
        margin = 50
        ratio = (x - margin) / (width - 2 * margin)
        return self.freq_min + ratio * (self.freq_max - self.freq_min)

    def mousePressEvent(self, event):
        """
        Handle mouse press events for click-to-tune.

        Args:
            event: Mouse event
        """
        if event.button() == Qt.MouseButton.LeftButton:
            # Find station near click position
            station = self._find_station_at_position(event.pos())

            if station:
                # Select station
                self.selected_station = station
                self.station_selected.emit(station)
                self.update()

                # Emit click signal for tuning
                self.station_clicked.emit(station.frequency)

                logger.info(f"Station clicked: {station.callsign} at {station.frequency_mhz:.3f} MHz")

    def _find_station_at_position(self, pos: QPoint) -> Optional[BandMapStation]:
        """
        Find station at mouse position.

        Args:
            pos: Mouse position

        Returns:
            BandMapStation or None
        """
        click_x = pos.x()
        click_y = pos.y()

        width = self.width()
        height = self.height()

        # Check each station
        for station in self.band_map.stations:
            x = self._freq_to_x(station.frequency, width)
            y = height // 2

            if station.contestness_score > 0:
                offset = (station.contestness_score / 100.0) * (height * 0.3)
                y = int(height * 0.7 - offset)

            # Check if click is within marker bounds
            distance = ((click_x - x) ** 2 + (click_y - y) ** 2) ** 0.5
            if distance <= self.marker_size:
                return station

        return None

    def add_station(self, station: BandMapStation):
        """
        Add a station to the band map.

        Args:
            station: BandMapStation to add
        """
        # This is typically handled by BandMapState, but provided for convenience
        self.band_map.add_or_update_station(
            frequency=station.frequency,
            callsign=station.callsign,
            status=station.status,
            contestness_score=station.contestness_score,
            signal_strength=station.signal_strength
        )
        self.update_display()

    def clear_stations(self):
        """Clear all stations from the band map."""
        self.band_map.clear()
        self.selected_station = None
        self.update_display()

    def toggle_callsigns(self):
        """Toggle callsign label display."""
        self.show_callsigns = not self.show_callsigns
        self.update()

    def toggle_signal_strength(self):
        """Toggle signal strength indicator display."""
        self.show_signal_strength = not self.show_signal_strength
        self.update()
