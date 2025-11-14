"""
Main Window for CQSentinel GUI

Provides the primary user interface with:
- Band selection
- Frequency display
- Audio level monitoring
- Radio control panel
- Status display
"""

import sys
import logging
from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QComboBox, QCheckBox,
    QGroupBox, QTextEdit, QProgressBar, QStatusBar,
    QMenuBar, QMenu, QMessageBox, QAction
)
from PyQt5.QtCore import Qt, QTimer, pyqtSignal, QThread
from PyQt5.QtGui import QFont

from cqsentinel.config import get_config, get_config_manager
from cqsentinel.radio import HamlibController, RadioConnectionError, RigctldManager, find_serial_port
from cqsentinel.audio import AudioCapture, list_audio_devices
from cqsentinel.gui.settings_dialog import SettingsDialog

logger = logging.getLogger(__name__)


class MainWindow(QMainWindow):
    """Main application window"""

    def __init__(self):
        super().__init__()

        self.config = get_config()
        self.radio: HamlibController = None
        self.rigctld_manager: RigctldManager = None
        self.audio: AudioCapture = None

        self.init_ui()
        self.setup_timers()

        logger.info("Main window initialized")

    def init_ui(self):
        """Initialize user interface"""
        self.setWindowTitle(f"CQSentinel v{self.get_version()} - SSB Contest Scanner")
        self.setGeometry(100, 100, 1200, 800)

        # Create menu bar
        self.create_menus()

        # Create central widget
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        # Main layout
        main_layout = QVBoxLayout(central_widget)

        # Top panel: Band selection and controls
        main_layout.addWidget(self.create_control_panel())

        # Middle panel: Radio status and frequency display
        main_layout.addWidget(self.create_radio_panel())

        # Bottom panel: Log/transcript display
        main_layout.addWidget(self.create_log_panel())

        # Status bar
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("Ready")

    def create_menus(self):
        """Create menu bar"""
        menubar = self.menuBar()

        # File menu
        file_menu = menubar.addMenu("&File")

        settings_action = QAction("&Settings", self)
        settings_action.triggered.connect(self.show_settings)
        file_menu.addAction(settings_action)

        file_menu.addSeparator()

        exit_action = QAction("E&xit", self)
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

        # Radio menu
        radio_menu = menubar.addMenu("&Radio")

        connect_action = QAction("&Connect", self)
        connect_action.triggered.connect(self.connect_radio)
        radio_menu.addAction(connect_action)

        disconnect_action = QAction("&Disconnect", self)
        disconnect_action.triggered.connect(self.disconnect_radio)
        radio_menu.addAction(disconnect_action)

        # Help menu
        help_menu = menubar.addMenu("&Help")

        about_action = QAction("&About", self)
        about_action.triggered.connect(self.show_about)
        help_menu.addAction(about_action)

    def create_control_panel(self) -> QGroupBox:
        """Create control panel with band selection"""
        group = QGroupBox("Control Panel")
        layout = QHBoxLayout()

        # Band selection
        layout.addWidget(QLabel("Bands:"))

        self.band_checkboxes = {}
        for band in ["160m", "80m", "40m", "20m", "15m", "10m"]:
            cb = QCheckBox(band)
            cb.setChecked(band in self.config.scan.enabled_bands)
            self.band_checkboxes[band] = cb
            layout.addWidget(cb)

        layout.addStretch()

        # Contest profile selector
        layout.addWidget(QLabel("Contest:"))
        self.contest_combo = QComboBox()
        self.contest_combo.addItems(["Field Day", "Winter Field Day", "CQWW", "CQWPX", "Salmon Run"])
        layout.addWidget(self.contest_combo)

        layout.addStretch()

        # Connect button
        self.connect_btn = QPushButton("Connect Radio")
        self.connect_btn.clicked.connect(self.connect_radio)
        layout.addWidget(self.connect_btn)

        # Start/Stop scanning
        self.scan_btn = QPushButton("Start Scan")
        self.scan_btn.clicked.connect(self.toggle_scan)
        self.scan_btn.setEnabled(False)
        layout.addWidget(self.scan_btn)

        group.setLayout(layout)
        return group

    def create_radio_panel(self) -> QGroupBox:
        """Create radio status panel"""
        group = QGroupBox("Radio Status")
        layout = QVBoxLayout()

        # Frequency display
        freq_layout = QHBoxLayout()
        freq_layout.addWidget(QLabel("Frequency:"))

        self.freq_label = QLabel("0.000 MHz")
        freq_font = QFont()
        freq_font.setPointSize(24)
        freq_font.setBold(True)
        self.freq_label.setFont(freq_font)
        freq_layout.addWidget(self.freq_label)

        freq_layout.addStretch()

        # Mode display
        freq_layout.addWidget(QLabel("Mode:"))
        self.mode_label = QLabel("USB")
        mode_font = QFont()
        mode_font.setPointSize(16)
        self.mode_label.setFont(mode_font)
        freq_layout.addWidget(self.mode_label)

        freq_layout.addStretch()

        # S-meter
        freq_layout.addWidget(QLabel("S-Meter:"))
        self.smeter_label = QLabel("S0")
        self.smeter_label.setFont(mode_font)
        freq_layout.addWidget(self.smeter_label)

        layout.addLayout(freq_layout)

        # Audio level meter
        audio_layout = QHBoxLayout()
        audio_layout.addWidget(QLabel("Audio Level:"))
        self.audio_meter = QProgressBar()
        self.audio_meter.setRange(0, 100)
        self.audio_meter.setValue(0)
        audio_layout.addWidget(self.audio_meter)
        layout.addLayout(audio_layout)

        group.setLayout(layout)
        return group

    def create_log_panel(self) -> QGroupBox:
        """Create log/transcript panel"""
        group = QGroupBox("Activity Log")
        layout = QVBoxLayout()

        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setMaximumHeight(200)
        layout.addWidget(self.log_text)

        group.setLayout(layout)
        return group

    def setup_timers(self):
        """Setup periodic update timers"""
        # Radio status update timer
        self.radio_timer = QTimer()
        self.radio_timer.timeout.connect(self.update_radio_status)
        # Will start when radio connects

    def connect_radio(self):
        """Connect to radio via Hamlib"""
        try:
            # Auto-start rigctld if configured
            if self.config.radio.auto_start_rigctld:
                self.log("Starting rigctld...")
                self.status_bar.showMessage("Starting rigctld...")

                # Get serial port (auto-detect if not configured)
                serial_port = self.config.radio.serial_port
                if not serial_port:
                    serial_port = find_serial_port()
                    if not serial_port:
                        raise RadioConnectionError(
                            "No serial port configured and auto-detection failed. "
                            "Please configure serial port in Settings."
                        )
                    self.log(f"Auto-detected serial port: {serial_port}")

                # Create and start rigctld manager
                self.rigctld_manager = RigctldManager(
                    model_id=self.config.radio.model_id,
                    serial_port=serial_port,
                    baud_rate=self.config.radio.baud_rate,
                    port=self.config.radio.rigctld_port
                )

                if not self.rigctld_manager.start():
                    raise RadioConnectionError(
                        "Failed to start rigctld. Check that:\n"
                        "1. Hamlib is installed\n"
                        "2. Radio is connected and powered on\n"
                        "3. Serial port is correct\n"
                        "4. No other program is using the radio"
                    )

                self.log("rigctld started successfully")

            self.log("Connecting to rigctld...")
            self.status_bar.showMessage("Connecting to radio...")

            # Create Hamlib controller
            self.radio = HamlibController(
                host=self.config.radio.rigctld_host,
                port=self.config.radio.rigctld_port
            )

            # Connect
            self.radio.connect()

            # Get initial status
            freq = self.radio.get_frequency()
            mode, bw = self.radio.get_mode()

            self.log(f"Connected to radio: {freq/1e6:.3f} MHz, {mode}")
            self.status_bar.showMessage("Radio connected")

            # Update UI
            self.connect_btn.setText("Disconnect Radio")
            self.connect_btn.clicked.disconnect()
            self.connect_btn.clicked.connect(self.disconnect_radio)
            self.scan_btn.setEnabled(True)

            # Start update timer
            self.radio_timer.start(1000)  # Update every 1 second

        except RadioConnectionError as e:
            self.log(f"Failed to connect: {e}")
            self.status_bar.showMessage("Connection failed")
            QMessageBox.critical(self, "Connection Error", str(e))

            # Clean up rigctld if we started it
            if self.rigctld_manager:
                self.rigctld_manager.stop()
                self.rigctld_manager = None

    def disconnect_radio(self):
        """Disconnect from radio"""
        if self.radio:
            self.radio.disconnect()
            self.radio = None

            self.log("Disconnected from radio")
            self.status_bar.showMessage("Radio disconnected")

            # Update UI
            self.connect_btn.setText("Connect Radio")
            self.connect_btn.clicked.disconnect()
            self.connect_btn.clicked.connect(self.connect_radio)
            self.scan_btn.setEnabled(False)

            # Stop timer
            self.radio_timer.stop()

            # Reset displays
            self.freq_label.setText("0.000 MHz")
            self.mode_label.setText("--")
            self.smeter_label.setText("S0")

        # Stop rigctld if we started it
        if self.rigctld_manager:
            self.log("Stopping rigctld...")
            self.rigctld_manager.stop()
            self.rigctld_manager = None

    def toggle_scan(self):
        """Start or stop scanning"""
        # TODO: Implement scanning logic
        if self.scan_btn.text() == "Start Scan":
            self.log("Starting scan...")
            self.scan_btn.setText("Stop Scan")
            # TODO: Start scanner
        else:
            self.log("Stopping scan...")
            self.scan_btn.setText("Start Scan")
            # TODO: Stop scanner

    def update_radio_status(self):
        """Update radio status display"""
        if not self.radio or not self.radio.is_connected:
            return

        try:
            # Get frequency
            freq = self.radio.get_frequency()
            self.freq_label.setText(f"{freq/1e6:.4f} MHz")

            # Get mode (less frequently to reduce load)
            if hasattr(self, '_mode_update_counter'):
                self._mode_update_counter += 1
            else:
                self._mode_update_counter = 0

            if self._mode_update_counter % 5 == 0:  # Every 5 seconds
                mode, bw = self.radio.get_mode()
                self.mode_label.setText(mode)

            # Get S-meter
            strength = self.radio.get_strength()
            if strength >= 0:
                if strength <= 9:
                    self.smeter_label.setText(f"S{strength}")
                else:
                    self.smeter_label.setText(f"S9+{strength-9}")

        except RadioConnectionError:
            self.log("Lost connection to radio")
            self.disconnect_radio()

    def log(self, message: str):
        """Add message to log panel"""
        self.log_text.append(message)
        logger.info(message)

    def show_settings(self):
        """Show settings dialog"""
        dialog = SettingsDialog(self)
        if dialog.exec():
            # Settings were saved, reload config
            self.config = get_config()
            self.log("Settings updated")
            logger.info("Settings updated by user")

    def show_about(self):
        """Show about dialog"""
        about_text = f"""
        <h2>CQSentinel v{self.get_version()}</h2>
        <p><b>SSB Contest Band Scanner with AI Voice Recognition</b></p>
        <p>The first practical implementation of an "SSB Skimmer" for ham radio contesting.</p>
        <p>Built with Python, PyQt5, Hamlib, and modern AI technologies.</p>
        <p><a href="https://github.com/xmutantson/CQSentinel">GitHub Repository</a></p>
        """
        QMessageBox.about(self, "About CQSentinel", about_text)

    def get_version(self) -> str:
        """Get application version"""
        try:
            from .. import __version__
            return __version__
        except:
            return "0.1.0"

    def closeEvent(self, event):
        """Handle window close event"""
        # Disconnect radio
        if self.radio:
            self.disconnect_radio()

        # Stop audio
        if self.audio:
            self.audio.stop_stream()

        # Save configuration
        try:
            get_config_manager().save()
        except:
            pass

        event.accept()
