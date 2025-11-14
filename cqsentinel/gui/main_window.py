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
import numpy as np
from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QComboBox, QCheckBox,
    QGroupBox, QTextEdit, QProgressBar, QStatusBar,
    QMenuBar, QMenu, QMessageBox, QAction
)
from PyQt5.QtCore import Qt, QTimer, pyqtSignal, QThread
from PyQt5.QtGui import QFont

from cqsentinel.config import get_config, get_config_manager
from cqsentinel.radio import HamlibController, RadioConnectionError, RigctldManager, find_serial_port, SSBAutoTuner
from cqsentinel.audio import AudioCapture, list_audio_devices
from cqsentinel.audio.pipeline import AudioPipeline
from cqsentinel.audio.denoiser import AudioDenoiser
from cqsentinel.audio.vad import VoiceActivityDetector
from cqsentinel.speech.transcription import SpeechTranscriber
from cqsentinel.voice import VoiceDatabase, VoiceEmbedder
from cqsentinel.contest import CallsignExtractor, BehaviorAnalyzer
from cqsentinel.bandmap.station import BandMapState
from cqsentinel.gui.settings_dialog import SettingsDialog
from cqsentinel.scanner.profiles import BAND_PROFILES
from cqsentinel.scanner.engine import BandScanner, ScanProgress

logger = logging.getLogger(__name__)


class ScanThread(QThread):
    """Background thread for band scanning (Phase 1)"""
    log_signal = pyqtSignal(str)
    freq_update_signal = pyqtSignal(int)  # Emit frequency in Hz for display update

    def __init__(self, radio, bands, step_hz=1000, dwell_sec=2.0):
        super().__init__()
        self.radio = radio
        self.bands = bands
        self.step_hz = step_hz
        self.dwell_sec = dwell_sec
        self.running = True

    def run(self):
        """Scan loop"""
        import time
        import traceback
        try:
            for band_name in self.bands:
                if not self.running:
                    break

                if band_name not in BAND_PROFILES:
                    try:
                        self.log_signal.emit(f"Unknown band: {band_name}")
                    except Exception as e:
                        logger.error(f"Signal emit failed: {e}")
                    continue

                profile = BAND_PROFILES[band_name]
                try:
                    self.log_signal.emit(f"Scanning {profile.name}: {profile.freq_start/1e6:.3f}-{profile.freq_end/1e6:.3f} MHz")
                except Exception as e:
                    logger.error(f"Signal emit failed: {e}")

                # Set SSB mode: LSB for 40m and below (10 MHz), USB for above 40m
                ssb_mode = "LSB" if profile.freq_start <= 10_000_000 else "USB"
                try:
                    self.radio.set_mode(ssb_mode, 2400)
                    logger.debug(f"Set mode to {ssb_mode} for {band_name}")
                except Exception as e:
                    logger.warning(f"Failed to set mode to {ssb_mode}: {e}")

                freq = profile.freq_start
                while freq <= profile.freq_end and self.running:
                    try:
                        # Tune radio
                        self.radio.set_frequency(int(freq))

                        # Update frequency display (prevents race condition with status timer)
                        try:
                            self.freq_update_signal.emit(int(freq))
                        except Exception as e:
                            logger.error(f"Frequency display update failed: {e}")

                        # Emit frequency update to log
                        try:
                            self.log_signal.emit(f"  {freq/1e6:.4f} MHz")
                        except Exception as e:
                            logger.error(f"Signal emit failed for freq {freq}: {e}")

                        # Dwell
                        time.sleep(self.dwell_sec)

                        # Next frequency
                        freq += self.step_hz

                    except RadioConnectionError as e:
                        error_msg = f"Radio connection lost at {freq/1e6:.3f} MHz: {e}"
                        logger.error(error_msg)
                        try:
                            self.log_signal.emit(error_msg)
                        except:
                            pass
                        return  # Exit scan completely on connection loss
                    except Exception as e:
                        error_msg = f"Error at {freq/1e6:.3f} MHz: {e}\n{traceback.format_exc()}"
                        logger.error(error_msg)
                        try:
                            self.log_signal.emit(f"Error at {freq/1e6:.3f} MHz: {e}")
                        except:
                            pass
                        break

                if not self.running:
                    break

            try:
                self.log_signal.emit("Scan complete")
            except Exception as e:
                logger.error(f"Signal emit failed for scan complete: {e}")
        except Exception as e:
            error_msg = f"Scan thread crashed: {e}\n{traceback.format_exc()}"
            logger.error(error_msg)
            try:
                self.log_signal.emit(f"Scan error: {e}")
            except:
                pass

    def stop(self):
        """Stop scanning"""
        self.running = False


class MainWindow(QMainWindow):
    """Main application window"""

    def __init__(self):
        super().__init__()

        self.config = get_config()

        # Phase 1: Radio control
        self.radio: HamlibController = None
        self.rigctld_manager: RigctldManager = None

        # Phase 2-8: Advanced features (initialized on-demand)
        self.audio: AudioCapture = None
        self.audio_pipeline: AudioPipeline = None
        self.auto_tuner: SSBAutoTuner = None
        self.transcriber: SpeechTranscriber = None
        self.voice_embedder: VoiceEmbedder = None
        self.voice_db: VoiceDatabase = None
        self.callsign_extractor: CallsignExtractor = None
        self.behavior_analyzer: BehaviorAnalyzer = None
        self.band_map: BandMapState = None

        # Scanning
        self.scan_thread: ScanThread = None
        self.band_scanner: BandScanner = None
        self.use_full_scanner = False  # Enable when Phase 2+ components ready

        # Audio monitoring
        self.last_audio_level = 0.0  # 0.0 to 1.0

        self.init_ui()
        self.setup_timers()

        logger.info("Main window initialized")

    def init_advanced_features(self):
        """Initialize Phase 2-8 advanced features (audio processing, AI models, etc.)"""
        try:
            self.log("Initializing advanced features...")

            # Audio capture
            if not self.audio:
                self.log("  Initializing audio capture...")
                self.audio = AudioCapture()

            # Audio pipeline (denoiser + VAD)
            if not self.audio_pipeline:
                self.log("  Initializing audio pipeline...")
                self.audio_pipeline = AudioPipeline(
                    sample_rate=self.config.audio.sample_rate,
                    denoise_level=self.config.audio.noise_reduction_level,
                    vad_threshold=self.config.audio.vad_sensitivity,
                    whisper_model=self.config.audio.whisper_model_size,
                    enable_voice_id=True
                )

            # SSB Auto-tuner
            if not self.auto_tuner:
                self.log("  Initializing SSB auto-tuner...")
                self.auto_tuner = SSBAutoTuner()

            # Speech transcriber (Whisper - may download model)
            if not self.transcriber:
                self.log("  Initializing speech transcriber (may download AI model)...")
                self.transcriber = SpeechTranscriber()

            # Voice embedder (speaker ID - may download model)
            if not self.voice_embedder:
                self.log("  Initializing voice embedder...")
                self.voice_embedder = VoiceEmbedder()

            # Voice database
            if not self.voice_db:
                self.log("  Initializing voice database...")
                self.voice_db = VoiceDatabase()

            # Contest logic
            if not self.callsign_extractor:
                self.log("  Initializing callsign extractor...")
                self.callsign_extractor = CallsignExtractor()

            if not self.behavior_analyzer:
                self.log("  Initializing behavior analyzer...")
                self.behavior_analyzer = BehaviorAnalyzer()

            # Band map
            if not self.band_map:
                self.log("  Initializing band map...")
                self.band_map = BandMapState()

            self.use_full_scanner = True
            self.log("✓ Advanced features initialized successfully!")
            self.log("  Full scanner with audio processing, AI transcription, and voice ID enabled.")

            # Start audio monitoring for level meter
            self.start_audio_monitoring()

            QMessageBox.information(self, "Advanced Features Enabled",
                "All advanced features initialized:\n\n"
                "✓ Audio processing (noise reduction, voice detection)\n"
                "✓ AI speech transcription (Whisper)\n"
                "✓ Voice fingerprinting (speaker ID)\n"
                "✓ SSB auto-centering\n"
                "✓ Contest logic (callsign extraction, behavior analysis)\n"
                "✓ Band map tracking\n\n"
                "The scanner will now use full AI-powered features!")

        except Exception as e:
            self.log(f"ERROR initializing advanced features: {e}")
            logger.error(f"Failed to initialize advanced features: {e}", exc_info=True)
            QMessageBox.warning(self, "Advanced Features Failed",
                f"Could not initialize advanced features:\n{e}\n\n"
                "Using basic scanner mode instead.")
            self.use_full_scanner = False

    def start_audio_monitoring(self):
        """Start audio stream for level monitoring"""
        if not self.audio:
            return

        try:
            def audio_callback(audio_chunk):
                """Process audio chunks for level meter"""
                # Calculate RMS level (0.0 to 1.0)
                rms = np.sqrt(np.mean(audio_chunk**2))
                self.last_audio_level = min(1.0, rms * 10)  # Scale up and clamp

            self.audio.start_stream(audio_callback)
            logger.info("Audio monitoring started for level meter")
        except Exception as e:
            logger.warning(f"Failed to start audio monitoring: {e}")

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

        # Scanner menu
        scanner_menu = menubar.addMenu("&Scanner")

        enable_advanced_action = QAction("Enable &Advanced Features", self)
        enable_advanced_action.setToolTip("Initialize AI models, audio processing, and voice recognition")
        enable_advanced_action.triggered.connect(self.init_advanced_features)
        scanner_menu.addAction(enable_advanced_action)

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

        # Frequency display (large, centered)
        freq_layout = QHBoxLayout()
        freq_layout.addWidget(QLabel("Frequency:"))

        self.freq_label = QLabel("0.000 MHz")
        freq_font = QFont()
        freq_font.setPointSize(24)
        freq_font.setBold(True)
        self.freq_label.setFont(freq_font)
        self.freq_label.setMinimumWidth(250)  # Prevent label from resizing
        freq_layout.addWidget(self.freq_label)
        freq_layout.addStretch()
        layout.addLayout(freq_layout)

        # Mode and S-meter display (separate row)
        status_layout = QHBoxLayout()

        # Mode display
        status_layout.addWidget(QLabel("Mode:"))
        self.mode_label = QLabel("USB")
        mode_font = QFont()
        mode_font.setPointSize(16)
        self.mode_label.setFont(mode_font)
        self.mode_label.setMinimumWidth(80)  # Fixed width
        status_layout.addWidget(self.mode_label)

        status_layout.addStretch()

        # S-meter
        status_layout.addWidget(QLabel("S-Meter:"))
        self.smeter_label = QLabel("S0")
        self.smeter_label.setFont(mode_font)
        self.smeter_label.setMinimumWidth(80)  # Fixed width
        status_layout.addWidget(self.smeter_label)

        layout.addLayout(status_layout)

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

                # Log current config for debugging
                logger.info(f"Radio config:")
                logger.info(f"  Model: {self.config.radio.model} (ID: {self.config.radio.model_id})")
                logger.info(f"  CI-V address: '{self.config.radio.civ_address}'")
                logger.info(f"  Serial port (saved): '{self.config.radio.serial_port}'")
                logger.info(f"  Baud rate: {self.config.radio.baud_rate}")

                # Get serial port (auto-detect if not configured)
                serial_port = self.config.radio.serial_port
                if not serial_port:
                    self.log("No serial port configured, auto-detecting...")
                    serial_port = find_serial_port()
                    if not serial_port:
                        raise RadioConnectionError(
                            "No serial port configured and auto-detection failed. "
                            "Please configure serial port in Settings."
                        )
                    self.log(f"Auto-detected serial port: {serial_port}")
                else:
                    self.log(f"Using saved serial port: {serial_port}")

                # Create and start rigctld manager
                self.rigctld_manager = RigctldManager(
                    model_id=self.config.radio.model_id,
                    serial_port=serial_port,
                    baud_rate=self.config.radio.baud_rate,
                    port=self.config.radio.rigctld_port,
                    civ_address=self.config.radio.civ_address
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
        if self.scan_btn.text() == "Start Scan":
            # Check if radio is connected
            if not self.radio or not self.radio.is_connected:
                self.log("ERROR: Radio not connected. Please connect radio first.")
                QMessageBox.warning(self, "Radio Not Connected",
                    "Please connect to the radio before starting scan.")
                return

            # Get enabled bands
            enabled_bands = [band for band, cb in self.band_checkboxes.items() if cb.isChecked()]
            if not enabled_bands:
                self.log("ERROR: No bands selected. Please select at least one band.")
                QMessageBox.warning(self, "No Bands Selected",
                    "Please select at least one band to scan.")
                return

            # Start scanner
            self.log(f"Starting scan on bands: {', '.join(enabled_bands)}")

            if self.use_full_scanner and self.audio_pipeline:
                # Use full-featured BandScanner with all Phase 2-8 features
                self.log("Using FULL SCANNER with AI features:")
                self.log("  ✓ Audio processing (noise reduction + voice detection)")
                self.log("  ✓ Speech transcription (Whisper AI)")
                self.log("  ✓ Voice fingerprinting (speaker identification)")
                self.log("  ✓ SSB auto-centering")
                self.log("  ✓ Contest logic (callsign extraction)")

                # Initialize BandScanner
                self.band_scanner = BandScanner(
                    radio_controller=self.radio,
                    audio_capture=self.audio,
                    audio_pipeline=self.audio_pipeline,
                    auto_tuner=self.auto_tuner,
                    voice_database=self.voice_db,
                    callsign_extractor=self.callsign_extractor,
                    behavior_analyzer=self.behavior_analyzer,
                    band_map=self.band_map,
                    on_station_detected=lambda station: self.log(f"STATION: {station}"),
                    on_progress_update=lambda prog: self.log(f"Progress: {prog.progress_percent:.1f}%")
                )

                # Get frequency ranges for selected bands
                for band_name in enabled_bands:
                    if band_name in BAND_PROFILES:
                        profile = BAND_PROFILES[band_name]
                        self.log(f"  Scanning {profile.name}: {profile.freq_start/1e6:.3f}-{profile.freq_end/1e6:.3f} MHz")
                        # TODO: Start multi-band scan
                        # For now, scan first band only
                        self.band_scanner.start_scan(
                            freq_start=profile.freq_start,
                            freq_end=profile.freq_end,
                            step_size=self.config.scan.step_size_hz
                        )
                        break  # First band only for now
            else:
                # Use simple Phase 1 scanner (frequency stepping only)
                self.log("Using BASIC SCANNER (frequency stepping only)")
                self.log("  Enable advanced features via Scanner menu for AI capabilities")

                self.scan_thread = ScanThread(
                    radio=self.radio,
                    bands=enabled_bands,
                    step_hz=self.config.scan.step_size_hz,
                    dwell_sec=2.0  # Phase 1: 2 second dwell per frequency
                )
                self.scan_thread.log_signal.connect(self.log)
                self.scan_thread.freq_update_signal.connect(self.update_freq_display)
                self.scan_thread.finished.connect(self.on_scan_finished)
                self.scan_thread.start()

            self.scan_btn.setText("Stop Scan")
            self.connect_btn.setEnabled(False)
            for cb in self.band_checkboxes.values():
                cb.setEnabled(False)
        else:
            # Stop scanner
            self.log("Stopping scan...")
            if self.band_scanner:
                self.band_scanner.stop_scan()
                self.band_scanner = None
            if self.scan_thread:
                self.scan_thread.stop()
                self.scan_thread.wait(3000)  # Wait up to 3 seconds

            self.scan_btn.setText("Start Scan")
            self.connect_btn.setEnabled(True)
            for cb in self.band_checkboxes.values():
                cb.setEnabled(True)

    def on_scan_finished(self):
        """Called when scan completes"""
        self.log("Scan finished")
        self.scan_btn.setText("Start Scan")
        self.connect_btn.setEnabled(True)
        for cb in self.band_checkboxes.values():
            cb.setEnabled(True)
        self.scan_thread = None

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

            # Update audio level meter
            audio_level_percent = int(self.last_audio_level * 100)
            self.audio_meter.setValue(audio_level_percent)

        except RadioConnectionError:
            self.log("Lost connection to radio")
            self.disconnect_radio()

    def log(self, message: str):
        """Add message to log panel"""
        self.log_text.append(message)
        logger.info(message)

    def update_freq_display(self, freq_hz: int):
        """Update frequency display from scan thread (prevents race condition)"""
        self.freq_label.setText(f"{freq_hz/1e6:.4f} MHz")

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
