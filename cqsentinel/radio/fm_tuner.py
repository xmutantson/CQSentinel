"""
FM Auto-Tuner using power-based edge detection

FM signals don't exhibit pitch shifting, so we use signal power
edges to find the center frequency. Takes advantage of FM capture effect.
"""

import numpy as np
import logging
import time
from typing import Tuple, Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class FMCenteringResult:
    """Result of FM auto-centering attempt"""
    success: bool
    final_frequency: int  # Hz
    signal_start_hz: int  # Signal lower edge
    signal_end_hz: int    # Signal upper edge
    bandwidth_hz: int     # Detected signal bandwidth
    peak_power_db: float


class FMAutoTuner:
    """
    Automatic FM signal centering using power-based edge detection.

    Uses narrow CW filter to find signal edges, then centers on midpoint.
    Takes advantage of FM capture effect for reliable locking.
    """

    def __init__(
        self,
        sample_rate: int = 16000,
        scan_range_hz: int = 10000,  # ±10 kHz scan
        scan_step_hz: int = 100,     # 100 Hz steps
        power_threshold_db: float = -80.0,  # Signal threshold
        edge_hysteresis_db: float = 10.0,   # Hysteresis for edge detection
    ):
        """
        Initialize FM auto-tuner

        Args:
            sample_rate: Audio sample rate
            scan_range_hz: Frequency range to scan (±)
            scan_step_hz: Step size for scanning
            power_threshold_db: Power threshold for signal detection
            edge_hysteresis_db: Hysteresis to avoid noise triggering edges
        """
        self.sample_rate = sample_rate
        self.scan_range_hz = scan_range_hz
        self.scan_step_hz = scan_step_hz
        self.power_threshold_db = power_threshold_db
        self.edge_hysteresis_db = edge_hysteresis_db

        logger.info(
            f"FMAutoTuner initialized: scan=±{scan_range_hz/1000:.1f}kHz, "
            f"step={scan_step_hz}Hz, threshold={power_threshold_db}dB"
        )

    def measure_power(self, audio: np.ndarray) -> float:
        """
        Measure audio power in dB

        Args:
            audio: Audio samples

        Returns:
            Power in dB
        """
        if len(audio) == 0:
            return -120.0

        rms = np.sqrt(np.mean(audio.astype(np.float64) ** 2))
        if rms > 1e-10:
            return 20 * np.log10(rms)
        else:
            return -120.0

    def find_signal_edges(
        self,
        radio_controller,
        audio_capture_func,
        center_frequency: int
    ) -> Tuple[Optional[int], Optional[int], float]:
        """
        Find FM signal edges using power scanning

        Args:
            radio_controller: Radio control interface
            audio_capture_func: Function to capture audio
            center_frequency: Starting frequency

        Returns:
            (start_hz, end_hz, peak_power_db) or (None, None, -120.0)
        """
        # Save current mode
        original_mode, original_bw = radio_controller.get_mode()

        try:
            # Switch to CW with narrow filter for edge detection
            logger.info("Switching to CW narrow filter for FM edge detection")
            radio_controller.set_mode("CW", bandwidth=500)
            time.sleep(0.2)  # Let filter settle

            # Scan power across frequency range
            frequencies = []
            powers = []

            start_freq = center_frequency - self.scan_range_hz
            end_freq = center_frequency + self.scan_range_hz

            logger.info(f"Scanning {start_freq/1e6:.4f} - {end_freq/1e6:.4f} MHz")

            current_freq = start_freq
            while current_freq <= end_freq:
                # Tune to frequency
                radio_controller.set_frequency(current_freq)
                time.sleep(0.05)  # Brief settle time

                # Capture audio and measure power
                audio = audio_capture_func(duration=0.2)
                power = self.measure_power(audio)

                frequencies.append(current_freq)
                powers.append(power)

                current_freq += self.scan_step_hz

            # Find signal edges using threshold with hysteresis
            peak_power = max(powers)
            threshold = self.power_threshold_db

            # Adjust threshold based on peak if peak is strong
            if peak_power > threshold + 20:
                # Strong signal - use adaptive threshold
                threshold = peak_power - 15  # 15 dB below peak

            logger.debug(f"Peak power: {peak_power:.1f} dB, threshold: {threshold:.1f} dB")

            # Find lower edge (first point above threshold)
            signal_start = None
            for freq, power in zip(frequencies, powers):
                if power > threshold:
                    signal_start = freq
                    break

            # Find upper edge (last point above threshold)
            signal_end = None
            for freq, power in zip(reversed(frequencies), reversed(powers)):
                if power > threshold:
                    signal_end = freq
                    break

            # Format edge frequencies (handle None values)
            start_str = f"{signal_start/1e6:.4f}" if signal_start is not None else "None"
            end_str = f"{signal_end/1e6:.4f}" if signal_end is not None else "None"

            logger.info(
                f"Edge detection: start={start_str} MHz, "
                f"end={end_str} MHz, "
                f"peak={peak_power:.1f} dB"
            )

            return signal_start, signal_end, peak_power

        except Exception as e:
            logger.error(f"FM edge detection failed: {e}")
            return None, None, -120.0

        finally:
            # Restore original mode
            logger.info(f"Restoring mode {original_mode}")
            try:
                radio_controller.set_mode(original_mode, original_bw)
                time.sleep(0.2)
            except Exception as e:
                logger.error(f"Failed to restore mode: {e}")

    def auto_center(
        self,
        radio_controller,
        audio_capture_func,
        initial_frequency: int
    ) -> FMCenteringResult:
        """
        Automatically center FM signal

        Args:
            radio_controller: Radio control interface
            audio_capture_func: Function to capture audio
            initial_frequency: Starting frequency

        Returns:
            FMCenteringResult with centering details
        """
        logger.info(f"FM auto-centering starting at {initial_frequency/1e6:.4f} MHz")

        # Find signal edges
        start_hz, end_hz, peak_power = self.find_signal_edges(
            radio_controller,
            audio_capture_func,
            initial_frequency
        )

        if start_hz is None or end_hz is None:
            logger.warning("Could not detect FM signal edges")
            return FMCenteringResult(
                success=False,
                final_frequency=initial_frequency,
                signal_start_hz=0,
                signal_end_hz=0,
                bandwidth_hz=0,
                peak_power_db=peak_power
            )

        # Calculate center frequency
        center_hz = (start_hz + end_hz) // 2
        bandwidth = end_hz - start_hz

        logger.info(
            f"FM signal detected: {start_hz/1e6:.4f} - {end_hz/1e6:.4f} MHz "
            f"(BW: {bandwidth/1000:.1f} kHz)"
        )

        # Tune to calculated center
        logger.info(f"Centering on {center_hz/1e6:.4f} MHz")
        try:
            radio_controller.set_frequency(center_hz)
            time.sleep(0.5)  # Let radio settle and capture effect lock

            return FMCenteringResult(
                success=True,
                final_frequency=center_hz,
                signal_start_hz=start_hz,
                signal_end_hz=end_hz,
                bandwidth_hz=bandwidth,
                peak_power_db=peak_power
            )

        except Exception as e:
            logger.error(f"Failed to set center frequency: {e}")
            return FMCenteringResult(
                success=False,
                final_frequency=initial_frequency,
                signal_start_hz=start_hz,
                signal_end_hz=end_hz,
                bandwidth_hz=bandwidth,
                peak_power_db=peak_power
            )
