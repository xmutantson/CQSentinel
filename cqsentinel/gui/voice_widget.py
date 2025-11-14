"""
Voice database display widget.

Shows tracked operators with voice fingerprints, worked status, and metadata.
"""

import logging
from typing import Optional
from datetime import datetime

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTableWidget, QTableWidgetItem,
    QLabel, QPushButton, QHeaderView, QMessageBox
)
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QColor

from cqsentinel.voice.database import VoiceDatabase, OperatorVoice

logger = logging.getLogger(__name__)


class VoiceWidget(QWidget):
    """
    Widget for displaying voice database and operator tracking.

    Shows:
    - List of detected operators
    - Voice fingerprint information
    - Worked status
    - Callsigns and exchanges
    - Frequencies heard
    """

    # Signals
    operator_selected = pyqtSignal(str)  # voice_id
    reset_requested = pyqtSignal()
    mark_worked_requested = pyqtSignal(str)  # voice_id

    def __init__(self, voice_db: Optional[VoiceDatabase] = None, parent=None):
        """
        Initialize voice widget.

        Args:
            voice_db: VoiceDatabase instance (optional)
            parent: Parent widget
        """
        super().__init__(parent)

        self.voice_db = voice_db or VoiceDatabase()

        self._init_ui()
        self._update_display()

        logger.info("VoiceWidget initialized")

    def _init_ui(self):
        """Initialize user interface."""
        layout = QVBoxLayout()

        # Header with stats
        header_layout = QHBoxLayout()

        self.stats_label = QLabel("Operators: 0 | Worked: 0 | Age: 0.0 days")
        self.stats_label.setStyleSheet("font-weight: bold;")
        header_layout.addWidget(self.stats_label)

        header_layout.addStretch()

        # Reset button
        self.reset_button = QPushButton("Reset Database")
        self.reset_button.clicked.connect(self._on_reset_clicked)
        header_layout.addWidget(self.reset_button)

        layout.addLayout(header_layout)

        # Operator table
        self.table = QTableWidget()
        self.table.setColumnCount(8)
        self.table.setHorizontalHeaderLabels([
            "Callsign",
            "Worked",
            "Exchange",
            "First Heard",
            "Last Heard",
            "Frequencies",
            "Airtime (s)",
            "Confidence"
        ])

        # Configure table
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.setAlternatingRowColors(True)
        self.table.setSortingEnabled(True)

        # Set column widths
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)  # Callsign
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)  # Worked
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)  # Exchange
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)  # First
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)  # Last
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)  # Freqs
        header.setSectionResizeMode(6, QHeaderView.ResizeMode.ResizeToContents)  # Airtime
        header.setSectionResizeMode(7, QHeaderView.ResizeMode.ResizeToContents)  # Confidence

        # Connect signals
        self.table.itemSelectionChanged.connect(self._on_selection_changed)
        self.table.itemDoubleClicked.connect(self._on_item_double_clicked)

        layout.addWidget(self.table)

        # Action buttons
        button_layout = QHBoxLayout()

        self.mark_worked_button = QPushButton("Mark Worked")
        self.mark_worked_button.clicked.connect(self._on_mark_worked)
        self.mark_worked_button.setEnabled(False)
        button_layout.addWidget(self.mark_worked_button)

        button_layout.addStretch()

        self.refresh_button = QPushButton("Refresh")
        self.refresh_button.clicked.connect(self._update_display)
        button_layout.addWidget(self.refresh_button)

        layout.addLayout(button_layout)

        self.setLayout(layout)

    def set_database(self, voice_db: VoiceDatabase):
        """
        Set the voice database to display.

        Args:
            voice_db: VoiceDatabase instance
        """
        self.voice_db = voice_db
        self._update_display()

    def _update_display(self):
        """Update the operator display."""
        if not self.voice_db:
            return

        # Update stats
        stats = self.voice_db.get_statistics()
        self.stats_label.setText(
            f"Operators: {stats['total_operators']} | "
            f"Worked: {stats['worked_operators']} | "
            f"Age: {stats['age_days']:.1f} days"
        )

        # Warn if database is old
        if stats['age_days'] > 5:
            self.stats_label.setStyleSheet(
                "font-weight: bold; color: orange;"
            )
        else:
            self.stats_label.setStyleSheet("font-weight: bold;")

        # Update table
        operators = self.voice_db.get_all_operators()
        self.table.setRowCount(len(operators))

        for row, operator in enumerate(operators):
            # Callsign
            callsign_item = QTableWidgetItem(operator.callsign or "Unknown")
            callsign_item.setData(Qt.ItemDataRole.UserRole, operator.voice_id)
            self.table.setItem(row, 0, callsign_item)

            # Worked status
            worked_item = QTableWidgetItem("✓" if operator.worked else "")
            worked_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            if operator.worked:
                worked_item.setBackground(QColor(144, 238, 144))  # Light green
            self.table.setItem(row, 1, worked_item)

            # Exchange
            exchange_item = QTableWidgetItem(operator.exchange or "")
            self.table.setItem(row, 2, exchange_item)

            # First heard
            first_item = QTableWidgetItem(
                operator.first_heard.strftime("%H:%M:%S")
            )
            self.table.setItem(row, 3, first_item)

            # Last heard
            last_item = QTableWidgetItem(
                operator.last_heard.strftime("%H:%M:%S")
            )
            self.table.setItem(row, 4, last_item)

            # Frequencies
            freq_count = operator.frequency_count
            freq_item = QTableWidgetItem(str(freq_count))
            freq_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(row, 5, freq_item)

            # Airtime
            airtime_item = QTableWidgetItem(f"{operator.total_airtime_seconds:.1f}")
            airtime_item.setTextAlignment(Qt.AlignmentFlag.AlignRight)
            self.table.setItem(row, 6, airtime_item)

            # Confidence (based on number of samples)
            confidence = min(100, len(operator.embedding_samples) * 20)
            confidence_item = QTableWidgetItem(f"{confidence}%")
            confidence_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

            # Color code confidence
            if confidence >= 80:
                confidence_item.setBackground(QColor(144, 238, 144))  # Light green
            elif confidence >= 60:
                confidence_item.setBackground(QColor(255, 255, 224))  # Light yellow
            else:
                confidence_item.setBackground(QColor(255, 182, 193))  # Light red

            self.table.setItem(row, 7, confidence_item)

        logger.debug(f"Updated voice widget display ({len(operators)} operators)")

    def _on_selection_changed(self):
        """Handle selection change in table."""
        selected_rows = self.table.selectionModel().selectedRows()

        if selected_rows:
            self.mark_worked_button.setEnabled(True)
            row = selected_rows[0].row()
            voice_id = self.table.item(row, 0).data(Qt.ItemDataRole.UserRole)
            self.operator_selected.emit(voice_id)
        else:
            self.mark_worked_button.setEnabled(False)

    def _on_item_double_clicked(self, item):
        """Handle double-click on operator."""
        row = item.row()
        voice_id = self.table.item(row, 0).data(Qt.ItemDataRole.UserRole)
        operator = self.voice_db.get_operator(voice_id)

        if operator:
            self._show_operator_details(operator)

    def _show_operator_details(self, operator: OperatorVoice):
        """
        Show detailed operator information.

        Args:
            operator: OperatorVoice instance
        """
        details = f"""
Operator: {operator.callsign or 'Unknown'}
Voice ID: {operator.voice_id}

Exchange: {operator.exchange or 'N/A'}
Worked: {'Yes' if operator.worked else 'No'}

First Heard: {operator.first_heard.strftime('%Y-%m-%d %H:%M:%S')}
Last Heard: {operator.last_heard.strftime('%Y-%m-%d %H:%M:%S')}
Total Airtime: {operator.total_airtime_seconds:.1f} seconds

Frequencies Heard: {operator.frequency_count}
Unique Frequencies: {', '.join(f'{f/1e6:.3f} MHz' for f in set(operator.frequencies_heard[:5]))}

Voice Samples: {len(operator.embedding_samples)}
Contestness Score: {operator.contestness_score:.1f}
Run Station: {'Yes' if operator.is_run_station else 'No'}
        """.strip()

        QMessageBox.information(self, "Operator Details", details)

    def _on_mark_worked(self):
        """Mark selected operator as worked."""
        selected_rows = self.table.selectionModel().selectedRows()

        if not selected_rows:
            return

        row = selected_rows[0].row()
        voice_id = self.table.item(row, 0).data(Qt.ItemDataRole.UserRole)
        operator = self.voice_db.get_operator(voice_id)

        if operator and not operator.worked:
            self.voice_db.mark_worked(voice_id)
            self._update_display()
            self.mark_worked_requested.emit(voice_id)

            logger.info(f"Marked operator {operator.callsign or voice_id} as worked")

    def _on_reset_clicked(self):
        """Handle reset button click."""
        reply = QMessageBox.question(
            self,
            "Reset Database",
            "Reset voice database and clear all tracked operators?\n\n"
            "This will clear worked status and operator history.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )

        if reply == QMessageBox.StandardButton.Yes:
            self.voice_db.clear()
            self._update_display()
            self.reset_requested.emit()

            logger.info("Voice database reset")

    def add_operator(self, operator: OperatorVoice):
        """
        Add or update operator in display.

        Args:
            operator: OperatorVoice instance
        """
        self._update_display()

    def highlight_operator(self, voice_id: str):
        """
        Highlight an operator in the table.

        Args:
            voice_id: Operator's voice ID
        """
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 0)
            if item and item.data(Qt.ItemDataRole.UserRole) == voice_id:
                self.table.selectRow(row)
                self.table.scrollToItem(item)
                break

    def get_selected_operator(self) -> Optional[str]:
        """
        Get selected operator's voice ID.

        Returns:
            Voice ID or None if no selection
        """
        selected_rows = self.table.selectionModel().selectedRows()

        if selected_rows:
            row = selected_rows[0].row()
            return self.table.item(row, 0).data(Qt.ItemDataRole.UserRole)

        return None
