"""
Noise Frequency Management Dialog.

Displays and manages frequencies marked as local noise,
allowing users to view, clear individual, or clear all markings.
"""

import logging
from typing import Optional

from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QMessageBox,
    QDialogButtonBox
)
from PyQt5.QtCore import Qt

from cqsentinel.bandmap.station import BandMapState

logger = logging.getLogger(__name__)


class NoiseFrequencyDialog(QDialog):
    """
    Dialog for viewing and managing noise frequency markings.

    Shows a table of frequencies marked as local noise with their
    occurrence counts, and allows clearing individual or all markings.
    """

    def __init__(self, band_map: BandMapState, parent=None):
        """
        Initialize noise frequency dialog.

        Args:
            band_map: BandMapState instance
            parent: Parent widget
        """
        super().__init__(parent)
        self.band_map = band_map
        self.init_ui()
        self.load_noise_frequencies()

    def init_ui(self):
        """Initialize user interface."""
        self.setWindowTitle(f"Noise Frequencies - {self.band_map.band or 'Unknown Band'}")
        self.setMinimumWidth(500)
        self.setMinimumHeight(400)

        layout = QVBoxLayout(self)

        # Header label
        header_label = QLabel(
            "Frequencies marked as local noise (skipped during scanning):"
        )
        header_label.setStyleSheet("font-weight: bold;")
        layout.addWidget(header_label)

        # Info label
        info_label = QLabel(
            "These frequencies are automatically skipped because no voice was detected\n"
            "after multiple attempts (likely local RFI from computers, power supplies, etc.)"
        )
        info_label.setStyleSheet("color: gray; font-size: 10px;")
        info_label.setWordWrap(True)
        layout.addWidget(info_label)

        # Table widget
        self.table = QTableWidget()
        self.table.setColumnCount(3)
        self.table.setHorizontalHeaderLabels(["Frequency (MHz)", "Occurrences", "Actions"])
        self.table.horizontalHeader().setStretchLastSection(False)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        layout.addWidget(self.table)

        # Button row
        button_layout = QHBoxLayout()

        self.clear_all_button = QPushButton("Clear All Markings")
        self.clear_all_button.clicked.connect(self.clear_all)
        button_layout.addWidget(self.clear_all_button)

        button_layout.addStretch()

        self.refresh_button = QPushButton("Refresh")
        self.refresh_button.clicked.connect(self.load_noise_frequencies)
        button_layout.addWidget(self.refresh_button)

        layout.addLayout(button_layout)

        # Dialog buttons
        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        button_box.rejected.connect(self.accept)
        layout.addWidget(button_box)

    def load_noise_frequencies(self):
        """Load noise frequencies into the table."""
        # Clear existing rows
        self.table.setRowCount(0)

        # Get noise frequencies sorted by frequency
        noise_freqs = sorted(self.band_map.noise_frequencies.items())

        if not noise_freqs:
            # Show "no noise frequencies" message
            self.table.setRowCount(1)
            no_data_item = QTableWidgetItem("No noise frequencies marked")
            no_data_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(0, 0, no_data_item)
            self.table.setSpan(0, 0, 1, 3)
            self.clear_all_button.setEnabled(False)
            return

        self.clear_all_button.setEnabled(True)

        # Populate table
        for freq_hz, count in noise_freqs:
            row = self.table.rowCount()
            self.table.insertRow(row)

            # Frequency column
            freq_mhz = freq_hz / 1e6
            freq_item = QTableWidgetItem(f"{freq_mhz:.3f}")
            freq_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            freq_item.setData(Qt.ItemDataRole.UserRole, freq_hz)  # Store Hz for clearing
            self.table.setItem(row, 0, freq_item)

            # Occurrences column
            count_item = QTableWidgetItem(str(count))
            count_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(row, 1, count_item)

            # Actions column - Clear button
            clear_button = QPushButton("Clear")
            clear_button.clicked.connect(lambda checked, f=freq_hz: self.clear_frequency(f))
            self.table.setCellWidget(row, 2, clear_button)

        logger.info(f"Loaded {len(noise_freqs)} noise frequencies into dialog")

    def clear_frequency(self, freq_hz: float):
        """
        Clear a single noise frequency marking.

        Args:
            freq_hz: Frequency in Hz to clear
        """
        freq_mhz = freq_hz / 1e6
        reply = QMessageBox.question(
            self,
            "Clear Noise Marking",
            f"Clear noise marking for {freq_mhz:.3f} MHz?\n\n"
            "This frequency will no longer be skipped during scanning.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )

        if reply == QMessageBox.StandardButton.Yes:
            self.band_map.clear_noise_frequency(freq_hz)
            logger.info(f"Cleared noise marking for {freq_mhz:.3f} MHz")
            self.load_noise_frequencies()

    def clear_all(self):
        """Clear all noise frequency markings."""
        noise_count = len(self.band_map.noise_frequencies)
        if noise_count == 0:
            return

        reply = QMessageBox.question(
            self,
            "Clear All Noise Markings",
            f"Clear all {noise_count} noise frequency markings?\n\n"
            "These frequencies will no longer be skipped during scanning.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )

        if reply == QMessageBox.StandardButton.Yes:
            self.band_map.clear_all_noise_frequencies()
            logger.info(f"Cleared {noise_count} noise frequency markings")
            self.load_noise_frequencies()
