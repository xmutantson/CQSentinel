"""
Configuration Management for CQSentinel

Handles loading, saving, and validating configuration settings.
"""

import os
import yaml
from typing import Dict, Any, Optional
from dataclasses import dataclass, asdict, field
from pathlib import Path
import logging

logger = logging.getLogger(__name__)


@dataclass
class RadioConfig:
    """Radio hardware configuration"""
    manufacturer: str = "Icom"  # Radio manufacturer
    model: str = "IC-705"  # Radio model
    model_id: int = 3085  # Hamlib model ID
    civ_address: str = ""  # CI-V address for Icom radios (hex, e.g., "94" for 0x94), empty for default
    serial_port: str = ""  # Auto-detect if empty
    baud_rate: int = 115200
    rigctld_host: str = "localhost"
    rigctld_port: int = 4532
    auto_start_rigctld: bool = True  # Auto-start rigctld on connect
    audio_device_name: str = ""  # Auto-detect if empty
    audio_sample_rate: int = 16000
    cat_poll_interval_ms: int = 1000


@dataclass
class BandPlan:
    """Band plan configuration (in Hz)"""
    band_160m: list = field(default_factory=lambda: [1_800_000, 2_000_000])
    band_80m: list = field(default_factory=lambda: [3_700_000, 4_000_000])
    band_40m: list = field(default_factory=lambda: [7_125_000, 7_300_000])
    band_20m: list = field(default_factory=lambda: [14_150_000, 14_350_000])
    band_15m: list = field(default_factory=lambda: [21_200_000, 21_450_000])
    band_10m: list = field(default_factory=lambda: [28_300_000, 29_700_000])

    def get_band_edges(self, band_name: str) -> Optional[tuple]:
        """Get frequency edges for a band"""
        attr_name = f"band_{band_name}"
        return getattr(self, attr_name, None)


@dataclass
class ScanConfig:
    """Scanning parameters"""
    step_size_hz: int = 1000  # 1 kHz steps
    scan_speed_steps_per_sec: float = 1.0  # Range: 0.2 (1 step/5sec) to 5.0 (5 steps/sec)
    s_meter_threshold: int = 3  # S-units (0-9+), skip frequencies below this
    use_s_meter_scan: bool = True  # Use S-meter for fast scanning
    dwell_with_voice_sec: int = 60
    dwell_without_voice_sec: int = 5
    auto_center_enabled: bool = True
    center_tolerance_hz: int = 50
    max_center_iterations: int = 3
    enabled_bands: list = field(default_factory=lambda: ["20m", "40m", "15m"])

    # Local noise avoidance - skip frequencies with persistent non-voice signals
    noise_skip_threshold: int = 3  # Mark as noise after N stuck occurrences (1-10, 0=disabled)

    # FM-specific auto-centering configuration
    fm_auto_center_enabled: bool = True  # Enable FM power-based centering
    fm_scan_range_hz: int = 10000  # ±10 kHz scan range for edge detection
    fm_scan_step_hz: int = 100     # 100 Hz steps for edge scanning
    fm_power_threshold_db: float = -80.0  # Power threshold for signal detection


@dataclass
class AudioConfig:
    """Audio processing parameters"""
    sample_rate: int = 16000
    noise_reduction_level: str = "medium"  # off, low, medium, high

    # Whisper transcription settings
    # Model is hardcoded to "medium.en" - best balance for SSB contest audio
    use_gpu: bool = True  # Try GPU first, auto-fallback to CPU
    gpu_memory_fraction: float = 0.85  # Use 85% of free VRAM for workers
    whisper_beam_size: int = 5  # Beam search size (1=greedy, 5=balanced)
    whisper_temperature: float = 0.0  # 0.0 = deterministic decoding
    whisper_no_speech_threshold: float = 0.6  # Higher = fewer false positives

    # OpenAI Whisper API (cloud-based, supersedes local when API key provided)
    openai_api_key: str = ""  # Empty = use local Whisper, set key = use OpenAI API
    openai_whisper_model: str = "whisper-1"  # OpenAI Whisper model

    # Pitch detection (for SSB auto-centering)
    use_crepe_pitch: bool = False  # GPU-accelerated pitch detection
    pitch_fmin: int = 50  # Hz
    pitch_fmax: int = 600  # Hz


@dataclass
class ContestConfig:
    """Contest-specific settings"""
    active_profile: str = "FD"  # Field Day default
    contestness_threshold: int = 70  # 0-100
    n3fjp_enabled: bool = False
    n3fjp_host: str = "localhost"
    n3fjp_port: int = 1100


@dataclass
class VoiceDBConfig:
    """Voice fingerprinting database settings"""
    similarity_threshold: float = 0.75  # 0.5-0.95
    auto_reset_days: int = 0  # 0 = never auto-reset
    warn_age_days: int = 5
    database_file: str = "voice_database.pkl"


@dataclass
class AppConfig:
    """Main application configuration"""
    radio: RadioConfig = field(default_factory=RadioConfig)
    band_plan: BandPlan = field(default_factory=BandPlan)
    scan: ScanConfig = field(default_factory=ScanConfig)
    audio: AudioConfig = field(default_factory=AudioConfig)
    contest: ContestConfig = field(default_factory=ContestConfig)
    voice_db: VoiceDBConfig = field(default_factory=VoiceDBConfig)

    # Paths
    config_dir: str = field(default_factory=lambda: str(Path.home() / ".cqsentinel"))
    log_level: str = "INFO"


class ConfigManager:
    """Manages application configuration"""

    DEFAULT_CONFIG_FILE = "config.yaml"

    def __init__(self, config_file: Optional[str] = None):
        self.config_file = config_file or self._get_default_config_path()
        self.config = AppConfig()

    def _get_default_config_path(self) -> str:
        """Get default configuration file path"""
        config_dir = Path.home() / ".cqsentinel"
        config_dir.mkdir(parents=True, exist_ok=True)
        return str(config_dir / self.DEFAULT_CONFIG_FILE)

    def load(self) -> AppConfig:
        """Load configuration from file"""
        if not os.path.exists(self.config_file):
            logger.info(f"Config file not found, creating default: {self.config_file}")
            self.save()
            return self.config

        try:
            with open(self.config_file, 'r') as f:
                data = yaml.safe_load(f)

            if data:
                # Reconstruct nested dataclasses
                self.config = AppConfig(
                    radio=RadioConfig(**data.get('radio', {})),
                    band_plan=BandPlan(**data.get('band_plan', {})),
                    scan=ScanConfig(**data.get('scan', {})),
                    audio=AudioConfig(**data.get('audio', {})),
                    contest=ContestConfig(**data.get('contest', {})),
                    voice_db=VoiceDBConfig(**data.get('voice_db', {})),
                    config_dir=data.get('config_dir', str(Path.home() / ".cqsentinel")),
                    log_level=data.get('log_level', 'INFO'),
                )

            logger.info(f"Configuration loaded from {self.config_file}")

        except Exception as e:
            logger.error(f"Failed to load config: {e}")
            logger.info("Using default configuration")

        return self.config

    def save(self) -> None:
        """Save configuration to file"""
        try:
            # Convert dataclasses to dicts
            data = {
                'radio': asdict(self.config.radio),
                'band_plan': asdict(self.config.band_plan),
                'scan': asdict(self.config.scan),
                'audio': asdict(self.config.audio),
                'contest': asdict(self.config.contest),
                'voice_db': asdict(self.config.voice_db),
                'config_dir': self.config.config_dir,
                'log_level': self.config.log_level,
            }

            # Ensure config directory exists
            os.makedirs(os.path.dirname(self.config_file), exist_ok=True)

            with open(self.config_file, 'w') as f:
                yaml.safe_dump(data, f, default_flow_style=False, sort_keys=False)

            logger.info(f"Configuration saved to {self.config_file}")

        except Exception as e:
            logger.error(f"Failed to save config: {e}")

    def get_bands_list(self) -> list:
        """Get list of available band names"""
        return ["160m", "80m", "40m", "20m", "15m", "10m"]

    def freq_to_band(self, freq_hz: float) -> Optional[str]:
        """Convert frequency to band name"""
        bands = {
            '160m': self.config.band_plan.band_160m,
            '80m': self.config.band_plan.band_80m,
            '40m': self.config.band_plan.band_40m,
            '20m': self.config.band_plan.band_20m,
            '15m': self.config.band_plan.band_15m,
            '10m': self.config.band_plan.band_10m,
        }

        for band_name, (low, high) in bands.items():
            if low <= freq_hz <= high:
                return band_name

        return None


# Global config instance (lazy-loaded)
_config_manager: Optional[ConfigManager] = None


def get_config_manager() -> ConfigManager:
    """Get global configuration manager instance"""
    global _config_manager
    if _config_manager is None:
        _config_manager = ConfigManager()
        _config_manager.load()
    return _config_manager


def get_config() -> AppConfig:
    """Get current application configuration"""
    return get_config_manager().config
