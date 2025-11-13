"""
Transcript display widget for real-time speech-to-text results
"""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QTextEdit, QPushButton,
    QHBoxLayout, QLabel
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont, QTextCursor
import logging

logger = logging.getLogger(__name__)


class TranscriptWidget(QWidget):
    """
    Widget for displaying real-time speech transcripts

    Shows transcribed text with timestamps and confidence scores.
    """

    # Signal emitted when transcript is cleared
    cleared = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)

        self.max_entries = 100  # Maximum number of transcript entries to keep

        self.init_ui()

    def init_ui(self):
        """Initialize user interface"""
        layout = QVBoxLayout(self)

        # Header
        header_layout = QHBoxLayout()

        header_label = QLabel("<b>Live Transcript</b>")
        header_layout.addWidget(header_label)

        header_layout.addStretch()

        # Clear button
        self.clear_btn = QPushButton("Clear")
        self.clear_btn.clicked.connect(self.clear_transcript)
        header_layout.addWidget(self.clear_btn)

        layout.addLayout(header_layout)

        # Transcript display
        self.transcript_text = QTextEdit()
        self.transcript_text.setReadOnly(True)
        self.transcript_text.setPlaceholderText(
            "Transcripts will appear here when audio is processed...\n"
            "\n"
            "To test:\n"
            "1. Connect radio and tune to a frequency\n"
            "2. Make sure audio is being received\n"
            "3. Click 'Process Audio' button"
        )

        # Font
        font = QFont("Courier New", 10)
        self.transcript_text.setFont(font)

        layout.addWidget(self.transcript_text)

        # Stats label
        self.stats_label = QLabel("Ready")
        self.stats_label.setStyleSheet("color: gray; font-size: 9pt;")
        layout.addWidget(self.stats_label)

    def add_transcript(
        self,
        text: str,
        frequency: float = None,
        timestamp: str = None,
        confidence: float = None
    ):
        """
        Add transcript entry

        Args:
            text: Transcribed text
            frequency: Radio frequency in Hz (optional)
            timestamp: Time string (optional)
            confidence: Confidence score 0-1 (optional)
        """
        if not text.strip():
            return

        # Format entry
        parts = []

        if timestamp:
            parts.append(f"[{timestamp}]")

        if frequency:
            parts.append(f"({frequency/1e6:.4f} MHz)")

        parts.append(text.strip())

        if confidence is not None:
            parts.append(f"(conf: {confidence:.2f})")

        entry = " ".join(parts)

        # Add to display
        self.transcript_text.append(entry)

        # Auto-scroll to bottom
        cursor = self.transcript_text.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        self.transcript_text.setTextCursor(cursor)

        # Update stats
        self._update_stats()

        logger.debug(f"Added transcript: {text[:50]}...")

    def add_multiple_transcripts(
        self,
        transcripts: list,
        frequency: float = None
    ):
        """
        Add multiple transcript segments

        Args:
            transcripts: List of transcript dicts with 'text', 'start', 'end'
            frequency: Radio frequency in Hz
        """
        from datetime import datetime

        timestamp = datetime.now().strftime("%H:%M:%S")

        for seg in transcripts:
            text = seg.get('text', '')
            confidence = seg.get('confidence', None)

            self.add_transcript(
                text=text,
                frequency=frequency,
                timestamp=timestamp,
                confidence=confidence
            )

    def clear_transcript(self):
        """Clear all transcripts"""
        self.transcript_text.clear()
        self.stats_label.setText("Ready")
        self.cleared.emit()
        logger.info("Transcript cleared")

    def _update_stats(self):
        """Update statistics label"""
        text = self.transcript_text.toPlainText()
        lines = len(text.split('\n')) if text else 0
        words = len(text.split()) if text else 0

        self.stats_label.setText(f"{lines} entries, {words} words")

    def get_transcript_text(self) -> str:
        """Get all transcript text"""
        return self.transcript_text.toPlainText()

    def save_to_file(self, filename: str):
        """
        Save transcript to file

        Args:
            filename: Output file path
        """
        try:
            with open(filename, 'w') as f:
                f.write(self.get_transcript_text())

            logger.info(f"Transcript saved to {filename}")

        except Exception as e:
            logger.error(f"Failed to save transcript: {e}")
