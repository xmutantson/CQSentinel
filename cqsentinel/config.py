"""
Configuration Management for CQSentinel

Handles loading, saving, and validating configuration settings.
"""

import os
import math
import yaml
import tempfile
from copy import deepcopy
from typing import Dict, Any, Optional
from dataclasses import dataclass, asdict, field, fields
from pathlib import Path
import logging

from cqsentinel.scanner.profiles import SUPPORTED_SCAN_BANDS

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

    # Network Whisper Server (self-hosted, supersedes local when enabled)
    # Priority: network > OpenAI API > local subprocess
    network_whisper_enabled: bool = False  # Enable network-based transcription
    network_whisper_url: str = "http://localhost:8000"  # Whisper server URL
    network_whisper_model: str = "medium.en"  # Model loaded on server
    network_whisper_timeout: float = 30.0  # Request timeout in seconds

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


def validate_config(config: AppConfig) -> None:
    """Validate known values before publishing or writing; never coerce YAML types.

    Unknown keys are retained separately for forward compatibility. Error messages
    identify fields, not their values (which can include credentials).
    """
    def validate_types(value, config_type, prefix=""):
        if not isinstance(value, config_type):
            raise ValueError(f"{prefix or 'config'} has an invalid section type")
        for item in fields(config_type):
            name = f"{prefix}.{item.name}" if prefix else item.name
            current = getattr(value, item.name)
            expected = item.type
            if hasattr(expected, '__dataclass_fields__'):
                validate_types(current, expected, name)
            elif expected is float:
                if type(current) not in (int, float) or not math.isfinite(current):
                    raise ValueError(f"{name} must be a finite number")
            elif type(current) is not expected:
                raise ValueError(f"{name} must be {expected.__name__}")

    validate_types(config, AppConfig)

    def bounded(section, field_name, low, high=None):
        value = getattr(getattr(config, section), field_name)
        if value < low or (high is not None and value > high):
            raise ValueError(f"{section}.{field_name} is outside its supported range")

    bounds = {
        'radio': {'model_id': (1, None), 'baud_rate': (1, None),
                  'rigctld_port': (1, 65535), 'cat_poll_interval_ms': (100, 5000)},
        'scan': {'step_size_hz': (1, None), 'scan_speed_steps_per_sec': (.2, 5),
                 's_meter_threshold': (0, 9), 'dwell_with_voice_sec': (1, None),
                 'dwell_without_voice_sec': (1, None), 'center_tolerance_hz': (1, None),
                 'max_center_iterations': (1, None), 'noise_skip_threshold': (0, 10),
                 'fm_scan_range_hz': (1, None), 'fm_scan_step_hz': (1, None),
                 'fm_power_threshold_db': (-120, 0)},
        'audio': {'gpu_memory_fraction': (.5, .95), 'whisper_beam_size': (1, 10),
                  'whisper_temperature': (0, 1), 'whisper_no_speech_threshold': (0, 1),
                  'network_whisper_timeout': (5, 120), 'pitch_fmin': (1, None),
                  'pitch_fmax': (1, None)},
        'contest': {'contestness_threshold': (0, 100), 'n3fjp_port': (1, 65535)},
        'voice_db': {'similarity_threshold': (.5, .95), 'auto_reset_days': (0, None),
                     'warn_age_days': (0, None)},
    }
    for section, limits in bounds.items():
        for field_name, (low, high) in limits.items():
            bounded(section, field_name, low, high)
    for section, name in (('audio', 'sample_rate'), ('radio', 'audio_sample_rate')):
        if getattr(getattr(config, section), name) not in (8000, 16000, 22050, 44100, 48000):
            raise ValueError(f"{section}.{name} is unsupported")
    if not config.audio.pitch_fmin < config.audio.pitch_fmax < config.audio.sample_rate / 2:
        raise ValueError("audio pitch limits must increase and remain below Nyquist")
    if config.scan.fm_scan_step_hz > 2 * config.scan.fm_scan_range_hz:
        raise ValueError("scan.fm_scan_step_hz exceeds the FM sweep span")
    if config.audio.noise_reduction_level not in ('off', 'low', 'medium', 'high'):
        raise ValueError("audio.noise_reduction_level is unsupported")
    if config.log_level not in ('DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'):
        raise ValueError("log_level is unsupported")
    if any(type(band) is not str or band not in SUPPORTED_SCAN_BANDS
           for band in config.scan.enabled_bands):
        raise ValueError("scan.enabled_bands must contain supported band names")
    for item in fields(BandPlan):
        edges = getattr(config.band_plan, item.name)
        if (len(edges) != 2 or any(type(edge) is not int for edge in edges)
                or not 0 < edges[0] < edges[1]):
            raise ValueError(f"band_plan.{item.name} must contain two increasing positive integer endpoints")


class ConfigManager:
    """Manages application configuration"""

    DEFAULT_CONFIG_FILE = "config.yaml"

    def __init__(self, config_file: Optional[str] = None):
        self.config_file = config_file or self._get_default_config_path()
        self.config = AppConfig()
        self._extra_data = {}
        self._load_failed = False

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
            with open(self.config_file, 'r', encoding='utf-8') as f:
                data = yaml.safe_load(f)
            if data is None:
                data = {}
            if not isinstance(data, dict):
                raise ValueError("Configuration must contain a YAML mapping")
            sections = {
                'radio': RadioConfig, 'band_plan': BandPlan, 'scan': ScanConfig,
                'audio': AudioConfig, 'contest': ContestConfig, 'voice_db': VoiceDBConfig,
            }
            values = {}
            for name, config_type in sections.items():
                section = data.get(name, {})
                if not isinstance(section, dict):
                    raise ValueError(f"Configuration section {name} must be a mapping")
                known = {item.name for item in fields(config_type)}
                values[name] = config_type(**{key: value for key, value in section.items() if key in known})
            candidate = AppConfig(
                **values,
                config_dir=data.get('config_dir', str(Path.home() / '.cqsentinel')),
                log_level=data.get('log_level', 'INFO'),
            )
            validate_config(candidate)
            self.config = candidate
            self._extra_data = deepcopy(data)  # Preserve fields from newer versions.
            self._load_failed = False
            logger.info(f"Configuration loaded from {self.config_file}")
        except Exception:
            self._load_failed = True
            logger.exception("Failed to load configuration; existing file was preserved")
            raise
        return self.config

    def save(self, config: Optional[AppConfig] = None) -> None:
        """Atomically save, publishing edited settings only after durable write.

        Failures propagate to the caller; the previous file and active settings
        remain intact. A malformed file must be repaired before it can be saved.
        """
        if self._load_failed:
            raise ValueError("Cannot overwrite configuration that failed to load")
        candidate = config if config is not None else self.config
        validate_config(candidate)
        data = deepcopy(self._extra_data)
        for key, value in asdict(candidate).items():
            if isinstance(value, dict):
                data[key] = {**data.get(key, {}), **value}
            else:
                data[key] = value
        target = Path(self.config_file).resolve()
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8',
                                             dir=target.parent, prefix=target.name + '.',
                                             suffix='.tmp', delete=False) as output:
                temporary = output.name
                yaml.safe_dump(data, output, default_flow_style=False, sort_keys=False)
                output.flush()
                os.fsync(output.fileno())
            os.replace(temporary, target)
            temporary = None
        except Exception:
            logger.exception("Failed to save configuration")
            raise
        finally:
            if temporary is not None:
                try:
                    os.unlink(temporary)
                except OSError:
                    logger.warning("Could not remove temporary configuration file")
        self.config = candidate
        self._extra_data = data
        logger.info(f"Configuration saved to {self.config_file}")

    def get_bands_list(self) -> list:
        """Get list of available band names"""
        return list(SUPPORTED_SCAN_BANDS)

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
