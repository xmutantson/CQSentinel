"""
Band map visualization widget.

Displays stations on a frequency spectrum with color-coded markers,
signal strength indicators, and click-to-tune functionality.
"""

import logging
from typing import Optional, List

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QFrame, QMenu, QAction
)
from PyQt5.QtCore import Qt, pyqtSignal, QPoint, QRect
from PyQt5.QtGui import QPainter, QColor, QPen, QFont, QBrush, QPainterPath

from cqsentinel.bandmap.station import BandMapStation, BandMapState, StationStatus, ActivityType

logger = logging.getLogger(__name__)


# Color scheme for station status
STATUS_COLORS = {
    StationStatus.NEW: QColor(0, 255, 0),  # Green
    StationStatus.MULTIPLIER: QColor(255, 215, 0),  # Gold
    StationStatus.WORKED: QColor(255, 0, 0),  # Red
    StationStatus.UNCLEAR: QColor(128, 128, 128),  # Gray
}

# Color for ragchew activity type (cyan/teal to distinguish from contest activity)
RAGCHEW_COLOR = QColor(0, 200, 200)  # Cyan/teal for ragchew stations


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
    station_cleared = pyqtSignal(object)  # BandMapStation - emitted when user clears a station

    def __init__(self, band_map_state: Optional[BandMapState] = None, parent=None):
        """
        Initialize band map widget.

        Args:
            band_map_state: BandMapState instance
            parent: Parent widget
        """
        super().__init__(parent)

        self.band_map = band_map_state if band_map_state is not None else BandMapState()
        self.selected_station: Optional[BandMapStation] = None

        # Display settings
        self.freq_min = 14.000e6  # 14.000 MHz
        self.freq_max = 14.350e6  # 14.350 MHz
        self.marker_size = 20
        self.show_callsigns = True
        self.show_signal_strength = True

        # Zoom settings
        self.zoom_level = 1.0  # 1.0 = show entire band, higher = zoomed in
        self.zoom_center_freq = None  # Center frequency when zoomed (None = center of band)
        self.min_zoom = 1.0
        self.max_zoom = 10.0

        # Drag/pan settings for zoomed view
        self.is_dragging = False
        self.drag_start_pos = None
        self.drag_start_center_freq = None

        # Current tuning indicator
        self.current_tuning_freq = None  # Current radio frequency (for scanning indicator)

        self._init_ui()

        logger.info("BandMapWidget initialized")

    def _init_ui(self):
        """Initialize user interface."""
        layout = QVBoxLayout()

        # Header
        header_layout = QHBoxLayout()

        # Band label hidden - frequency marks provide sufficient context
        self.band_label = QLabel(f"Band: {self.band_map.band or 'Unknown'}")
        self.band_label.setStyleSheet("font-weight: bold;")
        self.band_label.setVisible(False)  # Hide - frequency marks are enough
        header_layout.addWidget(self.band_label)

        header_layout.addStretch()

        self.stats_label = QLabel("Stations: 0 | New: 0 | Worked: 0")
        header_layout.addWidget(self.stats_label)

        # Zoom controls
        from PyQt5.QtWidgets import QSlider
        from PyQt5.QtCore import Qt
        header_layout.addWidget(QLabel("Zoom:"))
        self.zoom_slider = QSlider(Qt.Orientation.Horizontal)
        self.zoom_slider.setMinimum(int(self.min_zoom * 10))
        self.zoom_slider.setMaximum(int(self.max_zoom * 10))
        self.zoom_slider.setValue(int(self.zoom_level * 10))
        self.zoom_slider.setMaximumWidth(100)
        self.zoom_slider.setToolTip("Zoom level: 1x = entire band, 10x = maximum zoom")
        self.zoom_slider.valueChanged.connect(self.on_zoom_changed)
        header_layout.addWidget(self.zoom_slider)

        self.zoom_label = QLabel("1.0x")
        header_layout.addWidget(self.zoom_label)

        layout.addLayout(header_layout)

        # Add stretch to push header to top, rest is canvas for drawing
        layout.addStretch()

        # Reduced height to fit 6 bands on screen without scrolling (600-900px total)
        self.setMinimumHeight(100)
        self.setMaximumHeight(150)
        self.setMouseTracking(True)

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
        # Reset zoom when changing frequency range
        self.zoom_level = 1.0
        self.zoom_center_freq = None
        if hasattr(self, 'zoom_slider'):
            self.zoom_slider.setValue(int(self.zoom_level * 10))
        self.update()

    def on_zoom_changed(self, value):
        """Handle zoom slider changes"""
        self.zoom_level = value / 10.0
        self.zoom_label.setText(f"{self.zoom_level:.1f}x")

        # If first time zooming, center on middle of band
        if self.zoom_center_freq is None:
            self.zoom_center_freq = (self.freq_min + self.freq_max) / 2

        # Redraw with new zoom level
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

        # Draw tuning indicator (if set)
        self._draw_tuning_indicator(painter, width, height)

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

        # Get visible frequency range based on zoom
        freq_min_visible, freq_max_visible = self.get_visible_freq_range()
        freq_range = freq_max_visible - freq_min_visible

        # Calculate frequency step (e.g., every 50 kHz)
        step = 50e3  # 50 kHz
        if freq_range > 1e6:
            step = 100e3  # 100 kHz for wider ranges
        elif freq_range < 100e3 and self.zoom_level > 3:
            step = 10e3  # 10 kHz for high zoom

        # Calculate label spacing - determine how often to draw labels based on pixel space
        # Measure typical label width (e.g., "144.500")
        sample_label = f"{freq_min_visible / 1e6:.3f}"
        label_width = painter.fontMetrics().horizontalAdvance(sample_label)
        min_label_spacing = label_width + 20  # Add padding between labels

        # Calculate pixels per step
        pixels_per_step = (step / freq_range) * width

        # Determine label interval (draw label every N grid lines)
        if pixels_per_step < min_label_spacing:
            label_interval = int(min_label_spacing / pixels_per_step) + 1
        else:
            label_interval = 1

        # Draw vertical grid lines for visible range
        freq = freq_min_visible - (freq_min_visible % step)  # Start at step boundary
        grid_index = 0
        while freq <= freq_max_visible:
            x = self._freq_to_x(freq, width)

            # Draw grid line
            painter.drawLine(x, 0, x, height)

            # Draw frequency label only at intervals to avoid overlap
            if grid_index % label_interval == 0:
                freq_mhz = freq / 1e6
                label = f"{freq_mhz:.3f}"
                text_width = painter.fontMetrics().horizontalAdvance(label)
                painter.setPen(QColor(255, 255, 255))  # White text for better visibility
                painter.drawText(x - text_width // 2, height - 5, label)
                painter.setPen(pen)

            freq += step
            grid_index += 1

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

        # Get status color - use ragchew color if activity type is RAGCHEW
        if station.activity_type == ActivityType.RAGCHEW:
            color = RAGCHEW_COLOR
        else:
            color = STATUS_COLORS.get(station.status, STATUS_COLORS[StationStatus.UNCLEAR])

        # Highlight if selected
        if station == self.selected_station:
            pen = QPen(QColor(255, 255, 255), 3)
            painter.setPen(pen)
            painter.drawEllipse(x - self.marker_size//2 - 3, y - self.marker_size//2 - 3,
                              self.marker_size + 6, self.marker_size + 6)

        # Draw marker - use square for ragchews, circle for contests
        painter.setBrush(QBrush(color))
        painter.setPen(QPen(color.darker(), 2))
        if station.activity_type == ActivityType.RAGCHEW:
            # Square marker for ragchews
            painter.drawRect(x - self.marker_size//2, y - self.marker_size//2,
                            self.marker_size, self.marker_size)
        else:
            # Circle marker for contests
            painter.drawEllipse(x - self.marker_size//2, y - self.marker_size//2,
                               self.marker_size, self.marker_size)

        # Draw callsign label (or "RAGCHEW" for ragchew stations)
        if self.show_callsigns:
            painter.setPen(QColor(255, 255, 255))
            font = QFont("Monospace", 8, QFont.Weight.Bold)
            painter.setFont(font)

            # Draw callsign or activity type above marker
            text_x = x - 20
            text_y = y - self.marker_size
            if station.callsign:
                painter.drawText(text_x, text_y, station.callsign)
            elif station.activity_type == ActivityType.RAGCHEW:
                painter.setPen(RAGCHEW_COLOR)  # Use cyan for ragchew label
                painter.drawText(text_x - 10, text_y, "RAGCHEW")

            # Draw status below
            font.setBold(False)
            font.setPointSize(7)
            painter.setFont(font)
            painter.setPen(QColor(255, 255, 255))  # White text for better visibility
            if station.callsign:
                status_text = station.display_status
                painter.drawText(text_x, y + self.marker_size + 12, status_text)
            elif station.activity_type == ActivityType.RAGCHEW:
                # Show frequency for ragchews
                freq_text = f"{station.frequency / 1e6:.3f}"
                painter.drawText(text_x, y + self.marker_size + 12, freq_text)

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

    def get_visible_freq_range(self):
        """
        Get the visible frequency range based on zoom level.

        Returns:
            Tuple of (freq_min_visible, freq_max_visible) in Hz
        """
        if self.zoom_level <= 1.0:
            # No zoom - show entire band
            return (self.freq_min, self.freq_max)

        # Calculate visible range based on zoom
        total_range = self.freq_max - self.freq_min
        visible_range = total_range / self.zoom_level

        # Center on zoom_center_freq (or middle of band if not set)
        center = self.zoom_center_freq if self.zoom_center_freq else (self.freq_min + self.freq_max) / 2

        # Calculate visible min/max
        freq_min_visible = center - visible_range / 2
        freq_max_visible = center + visible_range / 2

        # Clamp to actual band limits
        freq_min_visible = max(self.freq_min, freq_min_visible)
        freq_max_visible = min(self.freq_max, freq_max_visible)

        return (freq_min_visible, freq_max_visible)

    def _freq_to_x(self, frequency: float, width: int) -> int:
        """
        Convert frequency to x-coordinate (accounting for zoom).

        Args:
            frequency: Frequency in Hz
            width: Widget width

        Returns:
            X-coordinate in pixels
        """
        margin = 50
        freq_min_visible, freq_max_visible = self.get_visible_freq_range()
        freq_range = freq_max_visible - freq_min_visible
        ratio = (frequency - freq_min_visible) / freq_range
        return int(margin + ratio * (width - 2 * margin))

    def _x_to_freq(self, x: int, width: int) -> float:
        """
        Convert x-coordinate to frequency (accounting for zoom).

        Args:
            x: X-coordinate in pixels
            width: Widget width

        Returns:
            Frequency in Hz
        """
        margin = 50
        ratio = (x - margin) / (width - 2 * margin)
        freq_min_visible, freq_max_visible = self.get_visible_freq_range()
        return freq_min_visible + ratio * (freq_max_visible - freq_min_visible)

    def mousePressEvent(self, event):
        """
        Handle mouse press events for click-to-tune and drag panning.

        Args:
            event: Mouse event
        """
        if event.button() == Qt.MouseButton.LeftButton:
            # Start drag tracking for panning (when zoomed)
            self.is_dragging = True
            self.drag_start_pos = event.pos()
            if self.zoom_center_freq is None:
                self.zoom_center_freq = (self.freq_min + self.freq_max) / 2
            self.drag_start_center_freq = self.zoom_center_freq

    def mouseMoveEvent(self, event):
        """
        Handle mouse move events for drag panning.

        Args:
            event: Mouse event
        """
        if self.is_dragging and self.drag_start_pos is not None:
            # Calculate drag delta in pixels
            delta_x = event.pos().x() - self.drag_start_pos.x()

            # Convert pixel delta to frequency delta
            # Negative because dragging right should move view left (show lower freqs)
            width = self.width()
            freq_min_visible, freq_max_visible = self.get_visible_freq_range()
            visible_range = freq_max_visible - freq_min_visible
            freq_delta = -(delta_x / width) * visible_range

            # Update center frequency
            self.zoom_center_freq = self.drag_start_center_freq + freq_delta

            # Clamp to band limits
            total_range = self.freq_max - self.freq_min
            visible_range_half = total_range / (2 * self.zoom_level)
            self.zoom_center_freq = max(
                self.freq_min + visible_range_half,
                min(self.freq_max - visible_range_half, self.zoom_center_freq)
            )

            # Redraw
            self.update()

    def mouseReleaseEvent(self, event):
        """
        Handle mouse release events for click-to-tune.

        Args:
            event: Mouse event
        """
        if event.button() == Qt.MouseButton.LeftButton:
            # Check if this was a click (not a drag)
            if self.drag_start_pos is not None:
                drag_distance = (event.pos() - self.drag_start_pos).manhattanLength()

                # If drag distance is small, treat as a click
                if drag_distance < 5:
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

            # End drag
            self.is_dragging = False
            self.drag_start_pos = None
            self.drag_start_center_freq = None

    def contextMenuEvent(self, event):
        """
        Handle right-click context menu.

        Args:
            event: Context menu event
        """
        # Find station at click position
        station = self._find_station_at_position(event.pos())

        if station:
            # Show context menu for station
            menu = QMenu(self)

            # Add station info as header
            station_info = f"{station.callsign} @ {station.frequency_mhz:.3f} MHz"
            header_action = QAction(station_info, self)
            header_action.setEnabled(False)
            font = header_action.font()
            font.setBold(True)
            header_action.setFont(font)
            menu.addAction(header_action)

            menu.addSeparator()

            # Clear this station
            clear_action = QAction("Clear this station", self)
            clear_action.triggered.connect(lambda: self._clear_station(station))
            menu.addAction(clear_action)

            # Mark as worked (if not already)
            if station.status != StationStatus.WORKED:
                mark_worked_action = QAction("Mark as worked", self)
                mark_worked_action.triggered.connect(lambda: self._mark_station_worked(station))
                menu.addAction(mark_worked_action)

            # Tune to station
            tune_action = QAction("Tune to this frequency", self)
            tune_action.triggered.connect(lambda: self.station_clicked.emit(station.frequency))
            menu.addAction(tune_action)

            menu.exec_(event.globalPos())
        else:
            # Show general context menu
            menu = QMenu(self)

            # Clear all stations
            clear_all_action = QAction("Clear all stations", self)
            clear_all_action.triggered.connect(self._clear_all_stations)
            menu.addAction(clear_all_action)

            menu.addSeparator()

            # Toggle callsign labels
            toggle_callsigns_action = QAction("Toggle callsign labels", self)
            toggle_callsigns_action.triggered.connect(self.toggle_callsigns)
            menu.addAction(toggle_callsigns_action)

            # Toggle signal strength
            toggle_signal_action = QAction("Toggle signal strength", self)
            toggle_signal_action.triggered.connect(self.toggle_signal_strength)
            menu.addAction(toggle_signal_action)

            menu.exec_(event.globalPos())

    def _clear_station(self, station: BandMapStation):
        """
        Clear a single station from the band map.

        Args:
            station: Station to clear
        """
        logger.info(f"Clearing station: {station.callsign} at {station.frequency_mhz:.3f} MHz")

        # Remove from band map
        if station in self.band_map.stations:
            self.band_map.stations.remove(station)

        # Clear selection if this was selected
        if self.selected_station == station:
            self.selected_station = None

        # Emit signal
        self.station_cleared.emit(station)

        # Update display
        self.update_display()

    def _clear_all_stations(self):
        """Clear all stations from the band map."""
        logger.info("Clearing all stations from band map")
        self.clear_stations()

    def _mark_station_worked(self, station: BandMapStation):
        """
        Mark a station as worked.

        Args:
            station: Station to mark as worked
        """
        logger.info(f"Marking station as worked: {station.callsign}")
        station.worked = True
        station.status = StationStatus.WORKED
        self.update_display()

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

    def set_tuning_frequency(self, frequency_hz: Optional[float]):
        """
        Set the current tuning frequency to display an indicator line.

        Args:
            frequency_hz: Current radio frequency in Hz (None to hide indicator)
        """
        self.current_tuning_freq = frequency_hz
        self.update()

    def _draw_tuning_indicator(self, painter: QPainter, width: int, height: int):
        """
        Draw a vertical line indicating the current tuning frequency.

        Args:
            painter: QPainter instance
            width: Widget width
            height: Widget height
        """
        if self.current_tuning_freq is None:
            return

        # Check if frequency is within visible range
        freq_min_visible, freq_max_visible = self.get_visible_freq_range()
        if self.current_tuning_freq < freq_min_visible or self.current_tuning_freq > freq_max_visible:
            return

        # Calculate x position
        x = self._freq_to_x(self.current_tuning_freq, width)

        # Draw bright indicator line
        pen = QPen(QColor(255, 255, 0), 2)  # Yellow, 2px wide
        pen.setStyle(Qt.PenStyle.DashLine)
        painter.setPen(pen)
        painter.drawLine(x, 0, x, height)

        # Draw label at top with triangle pinned to the line
        painter.setPen(QColor(255, 255, 0))
        font = QFont("Monospace", 8, QFont.Weight.Bold)
        painter.setFont(font)
        freq_mhz = self.current_tuning_freq / 1e6
        freq_text = f"{freq_mhz:.4f}"

        # Measure text width
        text_width = painter.fontMetrics().horizontalAdvance(freq_text)
        triangle_width = painter.fontMetrics().horizontalAdvance("▼")

        # Check if we're too close to edges - flip triangle if needed
        margin = 10  # Minimum margin from edge
        space_on_right = width - x
        space_on_left = x

        if space_on_right < text_width + triangle_width + margin:
            # Near right edge - put text on left, triangle points down but text is left of it
            triangle_x = x - triangle_width // 2  # Center triangle on line
            text_x = triangle_x - text_width - 4  # Text to the left
            painter.drawText(text_x, 15, freq_text)
            painter.drawText(triangle_x, 15, "▼")
        elif space_on_left < margin:
            # Near left edge - put text on right
            triangle_x = x - triangle_width // 2  # Center triangle on line
            text_x = triangle_x + triangle_width + 4  # Text to the right
            painter.drawText(triangle_x, 15, "▼")
            painter.drawText(text_x, 15, freq_text)
        else:
            # Normal case - triangle centered on line, text to the right
            triangle_x = x - triangle_width // 2  # Center triangle on line
            text_x = triangle_x + triangle_width + 4  # Text to the right
            painter.drawText(triangle_x, 15, "▼")
            painter.drawText(text_x, 15, freq_text)
