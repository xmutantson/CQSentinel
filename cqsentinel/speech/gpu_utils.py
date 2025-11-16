"""
GPU Utility Functions for Whisper Model Management

Handles GPU memory detection and worker pool sizing for optimal performance.
"""

import logging
from typing import Tuple

logger = logging.getLogger(__name__)

# Model VRAM requirements (fp16 on GPU)
# These are approximate values for openai-whisper models
MODEL_VRAM_GB = {
    "tiny.en": 1.0,
    "base.en": 1.5,
    "small.en": 2.0,
    "medium.en": 2.5,  # Our target model
    "large": 4.0,
    "large-v2": 4.0,
    "large-v3": 4.0,
}

# Model RAM requirements (fp32 on CPU)
MODEL_RAM_GB = {
    "tiny.en": 0.4,
    "base.en": 0.6,
    "small.en": 1.0,
    "medium.en": 1.5,  # Our target model
    "large": 3.0,
    "large-v2": 3.0,
    "large-v3": 3.0,
}


def get_gpu_info() -> dict:
    """
    Get detailed GPU information.

    Returns:
        dict with keys:
        - available: bool
        - device_name: str or None
        - total_memory_gb: float
        - free_memory_gb: float
        - used_memory_gb: float
        - cuda_version: str or None
    """
    result = {
        "available": False,
        "device_name": None,
        "total_memory_gb": 0.0,
        "free_memory_gb": 0.0,
        "used_memory_gb": 0.0,
        "cuda_version": None,
    }

    try:
        import torch

        if not torch.cuda.is_available():
            logger.info("CUDA not available")
            return result

        result["available"] = True
        result["cuda_version"] = torch.version.cuda
        result["device_name"] = torch.cuda.get_device_name(0)

        # Get memory info
        free_bytes, total_bytes = torch.cuda.mem_get_info(0)
        result["total_memory_gb"] = total_bytes / (1024**3)
        result["free_memory_gb"] = free_bytes / (1024**3)
        result["used_memory_gb"] = (total_bytes - free_bytes) / (1024**3)

        logger.info(
            f"GPU detected: {result['device_name']}, "
            f"Free: {result['free_memory_gb']:.2f} GB / {result['total_memory_gb']:.2f} GB"
        )

    except ImportError:
        logger.warning("PyTorch not available for GPU detection")
    except Exception as e:
        logger.warning(f"GPU detection failed: {e}")

    return result


def calculate_gpu_workers(
    model_name: str = "medium.en",
    memory_fraction: float = 0.85
) -> Tuple[int, str, str]:
    """
    Calculate how many Whisper workers can fit in GPU memory.

    Uses 85% of free GPU memory by default to leave headroom.

    Args:
        model_name: Whisper model name (default: "medium.en")
        memory_fraction: Fraction of free VRAM to use (default: 0.85)

    Returns:
        Tuple of (num_workers, device_string, status_message)
        - If GPU available with space: (N, "cuda", "Using N GPU workers")
        - If GPU but no space: (0, "cpu", "GPU has insufficient VRAM")
        - If no GPU: (0, "cpu", "No GPU detected")

    Examples:
        >>> calculate_gpu_workers("medium.en", 0.85)
        (2, "cuda", "Using 2 GPU workers (5.0 GB available)")
    """
    gpu_info = get_gpu_info()

    if not gpu_info["available"]:
        return (0, "cpu", "No GPU detected, falling back to CPU workers")

    # Get model VRAM requirement
    model_vram = MODEL_VRAM_GB.get(model_name, 2.5)  # Default to medium.en

    # Calculate available memory
    available_gb = gpu_info["free_memory_gb"] * memory_fraction
    num_workers = int(available_gb / model_vram)

    if num_workers < 1:
        msg = (
            f"GPU {gpu_info['device_name']} has {gpu_info['free_memory_gb']:.1f} GB free, "
            f"but {model_name} needs {model_vram:.1f} GB per worker. "
            f"Falling back to CPU workers."
        )
        logger.warning(msg)
        return (0, "cpu", msg)

    msg = (
        f"Using {num_workers} GPU worker(s) on {gpu_info['device_name']} "
        f"({available_gb:.1f} GB available for Whisper, {model_vram:.1f} GB per worker)"
    )
    logger.info(msg)

    return (num_workers, "cuda", msg)


def calculate_cpu_workers(
    model_name: str = "medium.en",
    max_workers: int = 5
) -> Tuple[int, str]:
    """
    Calculate optimal number of CPU workers based on available system RAM.

    Args:
        model_name: Whisper model name (default: "medium.en")
        max_workers: Maximum workers to spawn (default: 5)

    Returns:
        Tuple of (num_workers, status_message)
    """
    import psutil

    # Get available system memory
    mem_info = psutil.virtual_memory()
    available_gb = mem_info.available / (1024**3)

    # Get model RAM requirement
    model_ram = MODEL_RAM_GB.get(model_name, 1.5)  # Default to medium.en

    # Use 80% of available RAM for workers
    usable_gb = available_gb * 0.8
    num_workers = int(usable_gb / model_ram)

    # Clamp to max_workers
    num_workers = min(num_workers, max_workers)

    # Minimum 1 worker
    num_workers = max(1, num_workers)

    msg = (
        f"Using {num_workers} CPU worker(s) "
        f"({available_gb:.1f} GB RAM available, {model_ram:.1f} GB per worker)"
    )
    logger.info(msg)

    return (num_workers, msg)


def select_device_and_workers(
    use_gpu: bool = True,
    memory_fraction: float = 0.85,
    cpu_fallback_workers: int = 3
) -> Tuple[str, int, bool, str]:
    """
    Select the best device and worker count for Whisper.

    This is the main entry point for device selection.

    Args:
        use_gpu: Whether to try GPU first (default: True)
        memory_fraction: Fraction of free VRAM to use (default: 0.85)
        cpu_fallback_workers: Number of CPU workers if GPU unavailable (default: 3)

    Returns:
        Tuple of (device, num_workers, use_fp16, status_message)
        - device: "cuda" or "cpu"
        - num_workers: Number of workers to spawn
        - use_fp16: Whether to use fp16 (True for GPU, False for CPU)
        - status_message: Human-readable status
    """
    model_name = "medium.en"  # Hardcoded model

    if use_gpu:
        num_workers, device, msg = calculate_gpu_workers(model_name, memory_fraction)

        if device == "cuda" and num_workers > 0:
            return (device, num_workers, True, msg)
        else:
            # Fall back to CPU
            logger.info("GPU not viable, falling back to CPU workers")

    # CPU mode
    num_workers, msg = calculate_cpu_workers(model_name, cpu_fallback_workers)
    return ("cpu", num_workers, False, msg)


def estimate_transcription_speed(device: str, num_workers: int) -> str:
    """
    Estimate transcription speed for the given configuration.

    Returns a human-readable estimate of processing capability.

    Args:
        device: "cuda" or "cpu"
        num_workers: Number of workers

    Returns:
        Status message about expected performance
    """
    if device == "cuda":
        # GPU processes 1s audio in ~0.1-0.2s with medium.en
        rtf = 0.15  # Real-time factor (lower is faster)
        throughput = num_workers / rtf
        msg = (
            f"GPU mode: {num_workers} worker(s) can process ~{throughput:.1f}x real-time. "
            f"Should easily keep up with continuous audio."
        )
    else:
        # CPU processes 1s audio in ~2-3s with medium.en
        rtf = 2.5  # Real-time factor
        throughput = num_workers / rtf
        if throughput >= 1.0:
            msg = (
                f"CPU mode: {num_workers} worker(s) can process ~{throughput:.1f}x real-time. "
                f"Should keep up with continuous audio."
            )
        else:
            msg = (
                f"CPU mode: {num_workers} worker(s) can only process ~{throughput:.1f}x real-time. "
                f"May fall behind with continuous audio. Consider reducing buffer rate or using GPU."
            )

    return msg
