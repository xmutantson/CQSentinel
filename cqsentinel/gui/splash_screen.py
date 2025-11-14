"""
Splash Screen for CQSentinel

Shows during application startup while heavy libraries are loading.
"""

from PyQt5.QtWidgets import QSplashScreen, QLabel, QVBoxLayout, QWidget, QProgressBar
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QPixmap, QPainter, QColor, QFont
from typing import Optional


class SplashScreen(QSplashScreen):
    """
    Custom splash screen with loading progress
    """

    def __init__(self):
        # Create a pixmap for the splash screen
        pixmap = QPixmap(600, 400)
        pixmap.fill(QColor(20, 40, 60))  # Dark blue background

        super().__init__(pixmap, Qt.WindowType.WindowStaysOnTopHint)

        # Draw content on pixmap
        self._draw_splash(pixmap)
        self.setPixmap(pixmap)

        # Show immediately
        self.show()

    def _draw_splash(self, pixmap: QPixmap):
        """Draw splash screen content"""
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Title
        title_font = QFont("Arial", 32, QFont.Weight.Bold)
        painter.setFont(title_font)
        painter.setPen(QColor(255, 255, 255))
        painter.drawText(pixmap.rect(), Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop,
                        "\n\nCQSentinel")

        # Subtitle
        subtitle_font = QFont("Arial", 14)
        painter.setFont(subtitle_font)
        painter.setPen(QColor(200, 200, 200))
        painter.drawText(pixmap.rect(), Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop,
                        "\n\n\n\n\nSSB Contest Band Scanner")

        # Version
        version_font = QFont("Arial", 10)
        painter.setFont(version_font)
        painter.setPen(QColor(150, 150, 150))
        painter.drawText(pixmap.rect(), Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignBottom,
                        "Version 0.1.0\n\n")

        # Loading message
        loading_font = QFont("Arial", 12)
        painter.setFont(loading_font)
        painter.setPen(QColor(100, 200, 255))
        painter.drawText(pixmap.rect(), Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter,
                        "\n\n\n\n\nLoading AI models and libraries...\nThis may take a few moments.")

        painter.end()

    def update_message(self, message: str):
        """
        Update loading message

        Args:
            message: New message to display
        """
        self.showMessage(
            message,
            Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignBottom,
            QColor(100, 200, 255)
        )

    def finish_loading(self, main_window):
        """
        Finish splash screen and show main window

        Args:
            main_window: Main window to show after splash
        """
        self.finish(main_window)
