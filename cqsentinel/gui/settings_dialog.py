"""
Settings Dialog for CQSentinel

Allows users to configure:
- Radio model and connection settings
- Serial port (auto-detected on Windows)
- Audio devices
- Contest profiles
- AI model settings
"""

import logging
import platform
from typing import List, Tuple

from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLabel, QPushButton, QComboBox, QSpinBox, QDoubleSpinBox,
    QLineEdit, QGroupBox, QTabWidget, QWidget,
    QCheckBox, QMessageBox, QDialogButtonBox
)
from PyQt5.QtCore import Qt

from cqsentinel.config import get_config_manager, RadioConfig
from cqsentinel.radio.radio_database import (
    get_manufacturers, get_models_by_manufacturer,
    get_radio_info, is_icom_radio
)

logger = logging.getLogger(__name__)


def get_serial_ports() -> List[Tuple[str, str]]:
    """
    Get list of available serial ports

    Returns:
        List of (port_name, description) tuples
    """
    ports = []

    try:
        import serial.tools.list_ports

        for port in serial.tools.list_ports.comports():
            # On Windows, show COM ports; on Linux/Mac show /dev/tty*
            if platform.system() == 'Windows':
                ports.append((port.device, f"{port.device} - {port.description}"))
            else:
                ports.append((port.device, f"{port.device} - {port.description}"))

    except ImportError:
        logger.warning("pyserial not installed, cannot auto-detect serial ports")
        # Provide some common defaults
        if platform.system() == 'Windows':
            ports = [(f"COM{i}", f"COM{i}") for i in range(1, 9)]
        else:
            ports = [
                ("/dev/ttyUSB0", "/dev/ttyUSB0"),
                ("/dev/ttyUSB1", "/dev/ttyUSB1"),
                ("/dev/ttyACM0", "/dev/ttyACM0"),
            ]

    return ports


class SettingsDialog(QDialog):
    """Settings configuration dialog"""

    def __init__(self, parent=None):
        super().__init__(parent)

        self.config_manager = get_config_manager()
        self.config = self.config_manager.config

        self.init_ui()
        self.load_settings()

    def init_ui(self):
        """Initialize user interface"""
        self.setWindowTitle("CQSentinel Settings")
        self.setMinimumWidth(600)
        self.setMinimumHeight(500)

        layout = QVBoxLayout(self)

        # Create tabbed interface
        tabs = QTabWidget()
        tabs.addTab(self.create_radio_tab(), "Radio")
        tabs.addTab(self.create_audio_tab(), "Audio")
        tabs.addTab(self.create_contest_tab(), "Contest")
        tabs.addTab(self.create_advanced_tab(), "Advanced")

        layout.addWidget(tabs)

        # Dialog buttons
        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok |
            QDialogButtonBox.StandardButton.Cancel |
            QDialogButtonBox.StandardButton.Apply
        )
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        button_box.button(QDialogButtonBox.StandardButton.Apply).clicked.connect(self.apply_settings)

        layout.addWidget(button_box)

    def create_radio_tab(self) -> QWidget:
        """Create radio configuration tab"""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # Radio model group
        model_group = QGroupBox("Radio Model")
        model_layout = QFormLayout()

        # Manufacturer dropdown
        self.manufacturer_combo = QComboBox()
        self.manufacturer_combo.addItems(get_manufacturers())
        self.manufacturer_combo.currentTextChanged.connect(self.on_manufacturer_changed)
        model_layout.addRow("Manufacturer:", self.manufacturer_combo)

        # Model dropdown (populated when manufacturer is selected)
        self.model_combo = QComboBox()
        self.model_combo.currentTextChanged.connect(self.on_model_changed)
        model_layout.addRow("Model:", self.model_combo)

        # CI-V address (only for Icom radios)
        self.civ_label = QLabel("CI-V Address:")
        civ_layout = QHBoxLayout()
        self.civ_address_edit = QLineEdit()
        self.civ_address_edit.setPlaceholderText("Leave blank for default (e.g., 94 for 0x94)")
        self.civ_address_edit.setMaxLength(2)
        civ_layout.addWidget(self.civ_address_edit)

        civ_info = QLabel("ℹ")
        civ_info.setToolTip(
            "CI-V address in hex (without 0x prefix).\n"
            "Example: Enter '94' for IC-7300 address.\n"
            "Leave blank to use radio's default address."
        )
        civ_layout.addWidget(civ_info)

        civ_widget = QWidget()
        civ_widget.setLayout(civ_layout)
        model_layout.addRow(self.civ_label, civ_widget)

        # Store CI-V widgets for show/hide
        self.civ_label_widget = self.civ_label
        self.civ_address_widget = civ_widget

        model_group.setLayout(model_layout)
        layout.addWidget(model_group)

        # Connection settings group
        conn_group = QGroupBox("Connection Settings")
        conn_layout = QFormLayout()

        # Serial port
        serial_layout = QHBoxLayout()
        self.serial_combo = QComboBox()
        self.serial_combo.setEditable(True)

        # Populate serial ports
        ports = get_serial_ports()
        for port_name, port_desc in ports:
            self.serial_combo.addItem(port_desc, port_name)

        serial_layout.addWidget(self.serial_combo)

        refresh_btn = QPushButton("Refresh")
        refresh_btn.clicked.connect(self.refresh_serial_ports)
        serial_layout.addWidget(refresh_btn)

        conn_layout.addRow("Serial Port:", serial_layout)

        # Baud rate
        self.baud_combo = QComboBox()
        for baud in [4800, 9600, 19200, 38400, 57600, 115200]:
            self.baud_combo.addItem(str(baud), baud)
        self.baud_combo.setCurrentText("115200")
        conn_layout.addRow("Baud Rate:", self.baud_combo)

        # rigctld settings
        self.rigctld_host_edit = QLineEdit("localhost")
        conn_layout.addRow("rigctld Host:", self.rigctld_host_edit)

        self.rigctld_port_spin = QSpinBox()
        self.rigctld_port_spin.setRange(1, 65535)
        self.rigctld_port_spin.setValue(4532)
        conn_layout.addRow("rigctld Port:", self.rigctld_port_spin)

        # Auto-start rigctld checkbox
        self.auto_start_check = QCheckBox("Automatically start rigctld when connecting")
        self.auto_start_check.setChecked(True)
        conn_layout.addRow("", self.auto_start_check)

        conn_group.setLayout(conn_layout)
        layout.addWidget(conn_group)

        # CAT polling
        poll_group = QGroupBox("CAT Polling")
        poll_layout = QFormLayout()

        self.poll_interval_spin = QSpinBox()
        self.poll_interval_spin.setRange(100, 5000)
        self.poll_interval_spin.setSingleStep(100)
        self.poll_interval_spin.setValue(1000)
        self.poll_interval_spin.setSuffix(" ms")
        poll_layout.addRow("Poll Interval:", self.poll_interval_spin)

        poll_group.setLayout(poll_layout)
        layout.addWidget(poll_group)

        layout.addStretch()
        return widget

    def create_audio_tab(self) -> QWidget:
        """Create audio configuration tab"""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # Audio device group
        device_group = QGroupBox("Audio Device")
        device_layout = QFormLayout()

        self.audio_device_combo = QComboBox()
        self.audio_device_combo.addItem("(Auto-detect)", "")

        # Try to list audio devices
        try:
            from cqsentinel.audio import list_audio_devices
            for device in list_audio_devices():
                # AudioDevice is a dataclass - use attribute access not subscript
                self.audio_device_combo.addItem(device.name, device.index)
        except Exception as e:
            logger.warning(f"Could not list audio devices: {e}")

        device_layout.addRow("Input Device:", self.audio_device_combo)

        self.sample_rate_combo = QComboBox()
        for rate in [8000, 16000, 22050, 44100, 48000]:
            self.sample_rate_combo.addItem(f"{rate} Hz", rate)
        self.sample_rate_combo.setCurrentText("16000 Hz")
        device_layout.addRow("Sample Rate:", self.sample_rate_combo)

        device_group.setLayout(device_layout)
        layout.addWidget(device_group)

        # Processing group
        proc_group = QGroupBox("Audio Processing")
        proc_layout = QFormLayout()

        self.noise_reduction_combo = QComboBox()
        self.noise_reduction_combo.addItems(["Off", "Low", "Medium", "High"])
        self.noise_reduction_combo.setCurrentText("Medium")
        proc_layout.addRow("Noise Reduction:", self.noise_reduction_combo)

        # VAD sensitivity removed - Whisper handles speech detection internally
        # using no_speech_threshold parameter

        proc_group.setLayout(proc_layout)
        layout.addWidget(proc_group)

        # OpenAI API group (cloud transcription)
        openai_group = QGroupBox("OpenAI Whisper API (Cloud Transcription)")
        openai_layout = QFormLayout()

        self.openai_api_key_edit = QLineEdit()
        self.openai_api_key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.openai_api_key_edit.setPlaceholderText("Leave empty to use local GPU/CPU")
        openai_layout.addRow("API Key:", self.openai_api_key_edit)

        openai_info = QLabel(
            "If an API key is provided, cloud transcription will be used instead of local.\n"
            "Cost: ~$0.006 per minute of audio. Leave empty for free local processing."
        )
        openai_info.setWordWrap(True)
        openai_info.setStyleSheet("color: gray; font-size: 10px;")
        openai_layout.addRow(openai_info)

        openai_group.setLayout(openai_layout)
        layout.addWidget(openai_group)

        layout.addStretch()
        return widget

    def create_contest_tab(self) -> QWidget:
        """Create contest configuration tab"""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # Contest profile group
        profile_group = QGroupBox("Contest Profile")
        profile_layout = QFormLayout()

        self.contest_profile_combo = QComboBox()
        self.contest_profile_combo.addItems([
            "Field Day (FD)",
            "Winter Field Day (WFD)",
            "CQWW DX Contest",
            "CQ WPX Contest",
            "ARRL Sweepstakes",
            "State QSO Party"
        ])
        profile_layout.addRow("Active Profile:", self.contest_profile_combo)

        self.contestness_spin = QSpinBox()
        self.contestness_spin.setRange(0, 100)
        self.contestness_spin.setValue(70)
        self.contestness_spin.setSuffix("%")
        profile_layout.addRow("Contestness Threshold:", self.contestness_spin)

        profile_group.setLayout(profile_layout)
        layout.addWidget(profile_group)

        # N3FJP integration group
        n3fjp_group = QGroupBox("N3FJP Integration")
        n3fjp_layout = QFormLayout()

        self.n3fjp_enable_check = QCheckBox("Enable N3FJP integration")
        n3fjp_layout.addRow("", self.n3fjp_enable_check)

        self.n3fjp_host_edit = QLineEdit("localhost")
        n3fjp_layout.addRow("N3FJP Host:", self.n3fjp_host_edit)

        self.n3fjp_port_spin = QSpinBox()
        self.n3fjp_port_spin.setRange(1, 65535)
        self.n3fjp_port_spin.setValue(1100)
        n3fjp_layout.addRow("N3FJP Port:", self.n3fjp_port_spin)

        n3fjp_group.setLayout(n3fjp_layout)
        layout.addWidget(n3fjp_group)

        # Scanning settings group
        scan_group = QGroupBox("Scanning Settings")
        scan_layout = QFormLayout()

        self.scan_speed_spin = QDoubleSpinBox()
        self.scan_speed_spin.setRange(0.2, 5.0)
        self.scan_speed_spin.setSingleStep(0.1)
        self.scan_speed_spin.setValue(1.0)
        self.scan_speed_spin.setDecimals(1)
        self.scan_speed_spin.setSuffix(" steps/sec")
        self.scan_speed_spin.setToolTip(
            "Scanning speed when no signal is present.\n"
            "0.2 = 1 step every 5 seconds (slow)\n"
            "1.0 = 1 step per second (default)\n"
            "5.0 = 5 steps per second (fast)"
        )
        scan_layout.addRow("Scan Speed:", self.scan_speed_spin)

        scan_group.setLayout(scan_layout)
        layout.addWidget(scan_group)

        layout.addStretch()
        return widget

    def create_advanced_tab(self) -> QWidget:
        """Create advanced settings tab"""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # AI model group
        ai_group = QGroupBox("AI Transcription (Whisper medium.en)")
        ai_layout = QFormLayout()

        # Model info (read-only)
        model_label = QLabel("medium.en (~1.5 GB)")
        model_label.setStyleSheet("font-weight: bold;")
        ai_layout.addRow("Model:", model_label)

        # GPU settings
        self.use_gpu_check = QCheckBox("Enable GPU acceleration (auto-fallback to CPU)")
        self.use_gpu_check.setToolTip("If enabled, will use GPU if available. Falls back to CPU if no GPU detected.")
        ai_layout.addRow("GPU:", self.use_gpu_check)

        # GPU memory fraction
        self.gpu_memory_spin = QSpinBox()
        self.gpu_memory_spin.setRange(50, 95)
        self.gpu_memory_spin.setValue(85)
        self.gpu_memory_spin.setSuffix("% VRAM")
        self.gpu_memory_spin.setToolTip("Percentage of free GPU memory to use for Whisper workers")
        ai_layout.addRow("GPU Memory:", self.gpu_memory_spin)

        # Beam size for accuracy
        self.beam_size_spin = QSpinBox()
        self.beam_size_spin.setRange(1, 10)
        self.beam_size_spin.setValue(5)
        self.beam_size_spin.setToolTip("Higher = more accurate but slower (5 is good balance)")
        ai_layout.addRow("Beam Size:", self.beam_size_spin)

        self.use_crepe_check = QCheckBox("Use CREPE pitch detection (requires GPU)")
        ai_layout.addRow("", self.use_crepe_check)

        ai_group.setLayout(ai_layout)
        layout.addWidget(ai_group)

        # Voice database group
        voice_group = QGroupBox("Voice Database")
        voice_layout = QFormLayout()

        self.voice_threshold_spin = QSpinBox()
        self.voice_threshold_spin.setRange(50, 95)
        self.voice_threshold_spin.setValue(75)
        self.voice_threshold_spin.setSuffix("%")
        voice_layout.addRow("Similarity Threshold:", self.voice_threshold_spin)

        self.voice_age_spin = QSpinBox()
        self.voice_age_spin.setRange(0, 30)
        self.voice_age_spin.setValue(5)
        self.voice_age_spin.setSuffix(" days")
        self.voice_age_spin.setSpecialValueText("Never")
        voice_layout.addRow("Warn Age:", self.voice_age_spin)

        voice_group.setLayout(voice_layout)
        layout.addWidget(voice_group)

        # Logging group
        log_group = QGroupBox("Logging")
        log_layout = QFormLayout()

        self.log_level_combo = QComboBox()
        self.log_level_combo.addItems(["DEBUG", "INFO", "WARNING", "ERROR"])
        self.log_level_combo.setCurrentText("INFO")
        log_layout.addRow("Log Level:", self.log_level_combo)

        log_group.setLayout(log_layout)
        layout.addWidget(log_group)

        layout.addStretch()
        return widget

    def on_manufacturer_changed(self, manufacturer: str):
        """Handle manufacturer selection change"""
        if not manufacturer:
            return

        # Populate models for selected manufacturer
        self.model_combo.clear()
        models = get_models_by_manufacturer(manufacturer)
        self.model_combo.addItems(models)

        # Show/hide CI-V address field for Icom radios
        is_icom = is_icom_radio(manufacturer)
        self.civ_label_widget.setVisible(is_icom)
        self.civ_address_widget.setVisible(is_icom)

    def on_model_changed(self, model: str):
        """Handle model selection change"""
        if not model:
            return

        manufacturer = self.manufacturer_combo.currentText()
        if not manufacturer:
            return

        # Get radio info and populate CI-V address with default if Icom
        radio_info = get_radio_info(manufacturer, model)
        if radio_info and is_icom_radio(manufacturer):
            hamlib_id, default_civ, notes = radio_info
            if default_civ is not None:
                # Show default CI-V address as placeholder
                self.civ_address_edit.setPlaceholderText(
                    f"Leave blank for default ({default_civ:02X})"
                )

    def refresh_serial_ports(self):
        """Refresh the list of serial ports"""
        current = self.serial_combo.currentData()
        self.serial_combo.clear()

        ports = get_serial_ports()
        for port_name, port_desc in ports:
            self.serial_combo.addItem(port_desc, port_name)

        # Try to restore previous selection
        if current:
            index = self.serial_combo.findData(current)
            if index >= 0:
                self.serial_combo.setCurrentIndex(index)

    def load_settings(self):
        """Load settings from configuration"""
        # Radio settings - set manufacturer first
        manufacturer_index = self.manufacturer_combo.findText(self.config.radio.manufacturer)
        if manufacturer_index >= 0:
            self.manufacturer_combo.setCurrentIndex(manufacturer_index)
            # This will trigger on_manufacturer_changed which populates models

            # Then set model
            model_index = self.model_combo.findText(self.config.radio.model)
            if model_index >= 0:
                self.model_combo.setCurrentIndex(model_index)

        # CI-V address
        if self.config.radio.civ_address:
            self.civ_address_edit.setText(self.config.radio.civ_address)

        # Serial port
        if self.config.radio.serial_port:
            index = self.serial_combo.findData(self.config.radio.serial_port)
            if index >= 0:
                self.serial_combo.setCurrentIndex(index)
            else:
                # Add it if not in list
                self.serial_combo.addItem(self.config.radio.serial_port, self.config.radio.serial_port)
                self.serial_combo.setCurrentIndex(self.serial_combo.count() - 1)

        # Baud rate
        baud_index = self.baud_combo.findData(self.config.radio.baud_rate)
        if baud_index >= 0:
            self.baud_combo.setCurrentIndex(baud_index)

        self.rigctld_host_edit.setText(self.config.radio.rigctld_host)
        self.rigctld_port_spin.setValue(self.config.radio.rigctld_port)
        self.auto_start_check.setChecked(self.config.radio.auto_start_rigctld)
        self.poll_interval_spin.setValue(self.config.radio.cat_poll_interval_ms)

        # Audio settings
        if self.config.radio.audio_device_name:
            # Handle both old format (int) and new format (string)
            if isinstance(self.config.radio.audio_device_name, int):
                # Old format: find by index in userData
                for i in range(self.audio_device_combo.count()):
                    if self.audio_device_combo.itemData(i) == self.config.radio.audio_device_name:
                        self.audio_device_combo.setCurrentIndex(i)
                        break
            else:
                # New format: find by device name
                index = self.audio_device_combo.findText(str(self.config.radio.audio_device_name))
                if index >= 0:
                    self.audio_device_combo.setCurrentIndex(index)

        sample_rate_text = f"{self.config.audio.sample_rate} Hz"
        index = self.sample_rate_combo.findText(sample_rate_text)
        if index >= 0:
            self.sample_rate_combo.setCurrentIndex(index)

        self.noise_reduction_combo.setCurrentText(self.config.audio.noise_reduction_level.title())
        # VAD sensitivity removed - Whisper handles speech detection

        # OpenAI API key (if configured)
        if hasattr(self.config.audio, 'openai_api_key') and self.config.audio.openai_api_key:
            self.openai_api_key_edit.setText(self.config.audio.openai_api_key)

        # Contest settings
        self.contestness_spin.setValue(self.config.contest.contestness_threshold)
        self.n3fjp_enable_check.setChecked(self.config.contest.n3fjp_enabled)
        self.n3fjp_host_edit.setText(self.config.contest.n3fjp_host)
        self.n3fjp_port_spin.setValue(self.config.contest.n3fjp_port)

        # Scanning settings
        if hasattr(self.config.scan, 'scan_speed_steps_per_sec'):
            self.scan_speed_spin.setValue(self.config.scan.scan_speed_steps_per_sec)
        else:
            self.scan_speed_spin.setValue(1.0)

        # Advanced settings
        # GPU settings
        if hasattr(self.config.audio, 'use_gpu'):
            self.use_gpu_check.setChecked(self.config.audio.use_gpu)
        else:
            self.use_gpu_check.setChecked(True)  # Default to GPU enabled

        if hasattr(self.config.audio, 'gpu_memory_fraction'):
            self.gpu_memory_spin.setValue(int(self.config.audio.gpu_memory_fraction * 100))
        else:
            self.gpu_memory_spin.setValue(85)

        if hasattr(self.config.audio, 'whisper_beam_size'):
            self.beam_size_spin.setValue(self.config.audio.whisper_beam_size)
        else:
            self.beam_size_spin.setValue(5)

        self.use_crepe_check.setChecked(self.config.audio.use_crepe_pitch)
        self.voice_threshold_spin.setValue(int(self.config.voice_db.similarity_threshold * 100))
        self.voice_age_spin.setValue(self.config.voice_db.warn_age_days)
        self.log_level_combo.setCurrentText(self.config.log_level)

    def apply_settings(self):
        """Apply settings to configuration"""
        # Radio settings
        manufacturer = self.manufacturer_combo.currentText()
        model = self.model_combo.currentText()

        self.config.radio.manufacturer = manufacturer
        self.config.radio.model = model

        # Get Hamlib ID from database
        radio_info = get_radio_info(manufacturer, model)
        if radio_info:
            self.config.radio.model_id = radio_info[0]  # hamlib_id
        else:
            logger.warning(f"Could not find Hamlib ID for {manufacturer} {model}")

        # CI-V address
        civ_address = self.civ_address_edit.text().strip().upper()
        self.config.radio.civ_address = civ_address
        logger.info(f"Saving CI-V address: '{civ_address}' (was: '{self.config.radio.civ_address}')")

        serial_port = self.serial_combo.currentData() or ""
        self.config.radio.serial_port = serial_port
        logger.info(f"Saving serial port: '{serial_port}'")

        self.config.radio.baud_rate = self.baud_combo.currentData()
        self.config.radio.rigctld_host = self.rigctld_host_edit.text()
        self.config.radio.rigctld_port = self.rigctld_port_spin.value()
        self.config.radio.auto_start_rigctld = self.auto_start_check.isChecked()
        self.config.radio.cat_poll_interval_ms = self.poll_interval_spin.value()

        # Audio settings
        audio_device = self.audio_device_combo.currentData()
        # Store device name, not index
        audio_device_text = self.audio_device_combo.currentText()
        if audio_device_text != "(Auto-detect)":
            self.config.radio.audio_device_name = audio_device_text
        else:
            self.config.radio.audio_device_name = ""
        self.config.audio.sample_rate = self.sample_rate_combo.currentData()
        self.config.audio.noise_reduction_level = self.noise_reduction_combo.currentText().lower()
        # VAD sensitivity removed - Whisper handles speech detection

        # OpenAI API key (cloud transcription)
        openai_key = self.openai_api_key_edit.text().strip()
        self.config.audio.openai_api_key = openai_key
        if openai_key:
            logger.info("OpenAI API key configured - will use cloud transcription")
        else:
            logger.info("No OpenAI API key - will use local GPU/CPU transcription")

        # Contest settings
        self.config.contest.contestness_threshold = self.contestness_spin.value()
        self.config.contest.n3fjp_enabled = self.n3fjp_enable_check.isChecked()
        self.config.contest.n3fjp_host = self.n3fjp_host_edit.text()
        self.config.contest.n3fjp_port = self.n3fjp_port_spin.value()

        # Scanning settings
        self.config.scan.scan_speed_steps_per_sec = self.scan_speed_spin.value()
        logger.info(f"Scan speed set to {self.config.scan.scan_speed_steps_per_sec} steps/sec")

        # Advanced settings - GPU and transcription
        self.config.audio.use_gpu = self.use_gpu_check.isChecked()
        self.config.audio.gpu_memory_fraction = self.gpu_memory_spin.value() / 100.0
        self.config.audio.whisper_beam_size = self.beam_size_spin.value()
        self.config.audio.use_crepe_pitch = self.use_crepe_check.isChecked()
        self.config.voice_db.similarity_threshold = self.voice_threshold_spin.value() / 100.0
        self.config.voice_db.warn_age_days = self.voice_age_spin.value()
        self.config.log_level = self.log_level_combo.currentText()

        # Save configuration
        try:
            self.config_manager.save()
            logger.info(f"Settings saved successfully to: {self.config_manager.config_file}")
            logger.info(f"  CI-V address: {self.config.radio.civ_address}")
            logger.info(f"  Serial port: {self.config.radio.serial_port}")
            logger.info(f"  Model: {self.config.radio.model} (ID: {self.config.radio.model_id})")
        except Exception as e:
            logger.error(f"Failed to save settings: {e}")
            QMessageBox.critical(self, "Error", f"Failed to save settings: {e}")

    def accept(self):
        """Accept and save settings"""
        self.apply_settings()
        super().accept()

    def get_serial_port(self) -> str:
        """Get selected serial port"""
        return self.serial_combo.currentData() or ""

    def get_baud_rate(self) -> int:
        """Get selected baud rate"""
        return self.baud_combo.currentData()

    def get_radio_model_id(self) -> int:
        """Get Hamlib model ID for selected radio"""
        return self.radio_combo.currentData()

    def is_auto_start_enabled(self) -> bool:
        """Check if auto-start rigctld is enabled"""
        return self.auto_start_check.isChecked()
