"""
Station detail panel widget.

Displays detailed information about a selected station including
frequency, callsign, status, activity analysis, and transcripts.
"""

import logging
from typing import Optional

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QGroupBox, QTextEdit, QGridLayout
)
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QFont

from .station import BandMapStation, StationStatus, ActivityType

logger = logging.getLogger(__name__)


class StationDetailPanel(QWidget):
    """
    Station detail panel widget.

    Shows comprehensive information about a selected station:
    - Frequency and callsign
    - Status (new/worked/multiplier)
    - Signal quality
    - Contest activity analysis
    - Exchange information
    - Recent transcripts

    Signals:
        tune_requested: Emitted when user clicks "Tune To" button (frequency_hz)
        mark_worked_requested: Emitted when user clicks "Mark Worked" (station)
        ignore_requested: Emitted when user clicks "Ignore" (station)
    """

    # Signals
    tune_requested = pyqtSignal(float)  # frequency_hz
    mark_worked_requested = pyqtSignal(object)  # BandMapStation
    ignore_requested = pyqtSignal(object)  # BandMapStation

    def __init__(self, parent=None):
        """
        Initialize station detail panel.

        Args:
            parent: Parent widget
        """
        super().__init__(parent)

        self.current_station: Optional[BandMapStation] = None

        self._init_ui()

        logger.info("StationDetailPanel initialized")

    def _init_ui(self):
        """Initialize user interface."""
        layout = QVBoxLayout()

        # Header
        header_label = QLabel("Station Detail")
        header_label.setStyleSheet("font-weight: bold; font-size: 14px;")
        layout.addWidget(header_label)

        # Main info group
        main_group = QGroupBox("Station Information")
        main_layout = QGridLayout()

        # Frequency
        main_layout.addWidget(QLabel("Frequency:"), 0, 0)
        self.freq_label = QLabel("---")
        self.freq_label.setStyleSheet("font-weight: bold;")
        main_layout.addWidget(self.freq_label, 0, 1)

        # Callsign
        main_layout.addWidget(QLabel("Callsign:"), 1, 0)
        self.callsign_label = QLabel("---")
        self.callsign_label.setStyleSheet("font-weight: bold; font-size: 16px;")
        main_layout.addWidget(self.callsign_label, 1, 1)

        # Status
        main_layout.addWidget(QLabel("Status:"), 2, 0)
        self.status_label = QLabel("---")
        main_layout.addWidget(self.status_label, 2, 1)

        # Signal strength
        main_layout.addWidget(QLabel("Signal:"), 3, 0)
        self.signal_label = QLabel("---")
        main_layout.addWidget(self.signal_label, 3, 1)

        main_group.setLayout(main_layout)
        layout.addWidget(main_group)

        # Contest info group
        contest_group = QGroupBox("Contest Activity")
        contest_layout = QGridLayout()

        # Contestness score
        contest_layout.addWidget(QLabel("Contestness:"), 0, 0)
        self.contestness_label = QLabel("---")
        contest_layout.addWidget(self.contestness_label, 0, 1)

        # Activity type
        contest_layout.addWidget(QLabel("Type:"), 1, 0)
        self.activity_label = QLabel("---")
        contest_layout.addWidget(self.activity_label, 1, 1)

        # Exchange
        contest_layout.addWidget(QLabel("Exchange:"), 2, 0)
        self.exchange_label = QLabel("---")
        contest_layout.addWidget(self.exchange_label, 2, 1)

        # Estimated rate
        contest_layout.addWidget(QLabel("Est. Rate:"), 3, 0)
        self.rate_label = QLabel("---")
        contest_layout.addWidget(self.rate_label, 3, 1)

        contest_group.setLayout(contest_layout)
        layout.addWidget(contest_group)

        # Last heard group
        heard_group = QGroupBox("Activity")
        heard_layout = QGridLayout()

        heard_layout.addWidget(QLabel("First Heard:"), 0, 0)
        self.first_heard_label = QLabel("---")
        heard_layout.addWidget(self.first_heard_label, 0, 1)

        heard_layout.addWidget(QLabel("Last Heard:"), 1, 0)
        self.last_heard_label = QLabel("---")
        heard_layout.addWidget(self.last_heard_label, 1, 1)

        heard_layout.addWidget(QLabel("Age:"), 2, 0)
        self.age_label = QLabel("---")
        heard_layout.addWidget(self.age_label, 2, 1)

        heard_group.setLayout(heard_layout)
        layout.addWidget(heard_group)

        # Transcripts
        transcript_group = QGroupBox("Recent Transcripts")
        transcript_layout = QVBoxLayout()

        self.transcript_text = QTextEdit()
        self.transcript_text.setReadOnly(True)
        self.transcript_text.setMaximumHeight(100)
        self.transcript_text.setFont(QFont("Monospace", 9))
        transcript_layout.addWidget(self.transcript_text)

        transcript_group.setLayout(transcript_layout)
        layout.addWidget(transcript_group)

        # Action buttons
        button_layout = QHBoxLayout()

        self.tune_button = QPushButton("Tune To")
        self.tune_button.clicked.connect(self._on_tune_clicked)
        self.tune_button.setEnabled(False)
        button_layout.addWidget(self.tune_button)

        self.mark_worked_button = QPushButton("Mark Worked")
        self.mark_worked_button.clicked.connect(self._on_mark_worked_clicked)
        self.mark_worked_button.setEnabled(False)
        button_layout.addWidget(self.mark_worked_button)

        self.ignore_button = QPushButton("Ignore")
        self.ignore_button.clicked.connect(self._on_ignore_clicked)
        self.ignore_button.setEnabled(False)
        button_layout.addWidget(self.ignore_button)

        layout.addLayout(button_layout)

        layout.addStretch()
        self.setLayout(layout)

        # Show empty state
        self._show_empty_state()

    def set_station(self, station: Optional[BandMapStation]):
        """
        Set the station to display.

        Args:
            station: BandMapStation to display (or None for empty)
        """
        self.current_station = station

        if station is None:
            self._show_empty_state()
        else:
            self._show_station_details(station)

    def _show_empty_state(self):
        """Show empty state when no station is selected."""
        self.freq_label.setText("---")
        self.callsign_label.setText("---")
        self.status_label.setText("---")
        self.signal_label.setText("---")
        self.contestness_label.setText("---")
        self.activity_label.setText("---")
        self.exchange_label.setText("---")
        self.rate_label.setText("---")
        self.first_heard_label.setText("---")
        self.last_heard_label.setText("---")
        self.age_label.setText("---")
        self.transcript_text.setPlainText("No station selected")

        # Disable buttons
        self.tune_button.setEnabled(False)
        self.mark_worked_button.setEnabled(False)
        self.ignore_button.setEnabled(False)

    def _show_station_details(self, station: BandMapStation):
        """
        Show details for a station.

        Args:
            station: BandMapStation to display
        """
        # Frequency
        self.freq_label.setText(f"{station.frequency_mhz:.3f} MHz ({station.band})")

        # Callsign
        callsign_text = station.display_callsign
        self.callsign_label.setText(callsign_text)

        # Status with color
        status_text = station.display_status
        if station.is_multiplier:
            self.status_label.setText(status_text)
            self.status_label.setStyleSheet("color: gold; font-weight: bold;")
        elif station.worked:
            self.status_label.setText(status_text)
            self.status_label.setStyleSheet("color: red;")
        elif station.status == StationStatus.NEW:
            self.status_label.setText(status_text)
            self.status_label.setStyleSheet("color: green; font-weight: bold;")
        else:
            self.status_label.setText(status_text)
            self.status_label.setStyleSheet("color: gray;")

        # Signal strength
        if station.signal_strength is not None:
            signal_text = f"S{int(station.signal_strength)}"
            if station.snr is not None:
                signal_text += f" (SNR: {station.snr:.1f} dB)"
            self.signal_label.setText(signal_text)
        else:
            self.signal_label.setText("Unknown")

        # Contestness score
        score = station.contestness_score
        score_text = f"{score:.0f}/100"
        if score > 80:
            score_text += " (Very High)"
            self.contestness_label.setStyleSheet("color: green; font-weight: bold;")
        elif score > 60:
            score_text += " (High)"
            self.contestness_label.setStyleSheet("color: lightgreen;")
        elif score > 40:
            score_text += " (Medium)"
            self.contestness_label.setStyleSheet("color: yellow;")
        else:
            score_text += " (Low)"
            self.contestness_label.setStyleSheet("color: orange;")
        self.contestness_label.setText(score_text)

        # Activity type
        activity_text = station.activity_type.value.replace("_", " ").title()
        if station.is_run_station:
            activity_text += " (RUN)"
            self.activity_label.setStyleSheet("font-weight: bold;")
        else:
            self.activity_label.setStyleSheet("")
        self.activity_label.setText(activity_text)

        # Exchange
        if station.exchange:
            self.exchange_label.setText(station.exchange)
        else:
            self.exchange_label.setText("Not captured")

        # Estimated rate
        if station.estimated_qso_rate > 0:
            self.rate_label.setText(f"{station.estimated_qso_rate:.0f} QSOs/hour")
        else:
            self.rate_label.setText("Unknown")

        # Timestamps
        self.first_heard_label.setText(station.first_heard.strftime("%H:%M:%S"))
        self.last_heard_label.setText(station.last_heard.strftime("%H:%M:%S"))

        # Age
        age_text = f"{station.age_minutes:.1f} minutes ago"
        if station.is_stale:
            self.age_label.setText(age_text + " (stale)")
            self.age_label.setStyleSheet("color: orange;")
        elif station.is_recent:
            self.age_label.setText(age_text + " (recent)")
            self.age_label.setStyleSheet("color: green;")
        else:
            self.age_label.setText(age_text)
            self.age_label.setStyleSheet("")

        # Transcripts
        if station.transcripts:
            transcript_text = "\n\n".join(station.transcripts[-3:])  # Last 3
            self.transcript_text.setPlainText(transcript_text)
        else:
            self.transcript_text.setPlainText("No transcripts available")

        # Enable buttons
        self.tune_button.setEnabled(True)
        self.mark_worked_button.setEnabled(not station.worked)
        self.ignore_button.setEnabled(True)

    def _on_tune_clicked(self):
        """Handle "Tune To" button click."""
        if self.current_station:
            self.tune_requested.emit(self.current_station.frequency)
            logger.info(f"Tune requested to {self.current_station.frequency_mhz:.3f} MHz")

    def _on_mark_worked_clicked(self):
        """Handle "Mark Worked" button click."""
        if self.current_station:
            self.mark_worked_requested.emit(self.current_station)
            logger.info(f"Mark worked: {self.current_station.callsign}")

    def _on_ignore_clicked(self):
        """Handle "Ignore" button click."""
        if self.current_station:
            self.ignore_requested.emit(self.current_station)
            logger.info(f"Ignore: {self.current_station.callsign}")

    def refresh(self):
        """Refresh the display with current station data."""
        if self.current_station:
            self._show_station_details(self.current_station)
