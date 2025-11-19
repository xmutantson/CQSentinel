#!/usr/bin/env python3
"""
Download AI models for CQSentinel

This script downloads all required AI models for offline operation:
- Whisper speech recognition
- Silero VAD
- Resemblyzer voice encoder

Usage:
    python scripts/download_models.py [--model-size small]
"""

import sys
import argparse
import logging
from pathlib import Path

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def download_whisper(model_size: str = "medium.en"):
    """Download Whisper model"""
    logger.info(f"Downloading Whisper {model_size} model...")

    try:
        from faster_whisper import WhisperModel

        # This will download the model if not already cached
        # Note: Use int8 for download compatibility, app will use float32 as needed
        model = WhisperModel(
            model_size,
            device="cpu",
            compute_type="int8",
            download_root=None  # Use default cache
        )

        logger.info(f"✓ Whisper {model_size} model downloaded")
        return True

    except ImportError:
        logger.error("faster-whisper not installed. Run: pip install faster-whisper")
        return False
    except Exception as e:
        logger.error(f"Failed to download Whisper: {e}")
        return False


def download_silero_vad():
    """Download Silero VAD model"""
    logger.info("Downloading Silero VAD model...")

    try:
        import torch

        # Load model (will download if needed)
        model, utils = torch.hub.load(
            repo_or_dir='snakers4/silero-vad',
            model='silero_vad',
            force_reload=False,
            onnx=False
        )

        logger.info("✓ Silero VAD model downloaded")
        return True

    except ImportError:
        logger.error("torch not installed. Run: pip install torch")
        return False
    except Exception as e:
        logger.error(f"Failed to download Silero VAD: {e}")
        return False


def download_resemblyzer():
    """Download Resemblyzer model"""
    logger.info("Downloading Resemblyzer voice encoder...")

    try:
        from resemblyzer import VoiceEncoder

        # Initialize encoder (downloads model if needed)
        encoder = VoiceEncoder()

        logger.info("✓ Resemblyzer voice encoder downloaded")
        return True

    except ImportError:
        logger.error("resemblyzer not installed. Run: pip install resemblyzer")
        return False
    except Exception as e:
        logger.error(f"Failed to download Resemblyzer: {e}")
        return False


def check_disk_space():
    """Check available disk space"""
    try:
        import shutil
        stats = shutil.disk_usage(Path.home())
        free_gb = stats.free / (1024**3)

        logger.info(f"Available disk space: {free_gb:.1f} GB")

        if free_gb < 2.0:
            logger.warning("Less than 2 GB free space. Models may not download.")
            return False

        return True

    except Exception as e:
        logger.warning(f"Could not check disk space: {e}")
        return True


def main():
    parser = argparse.ArgumentParser(
        description='Download AI models for CQSentinel'
    )
    parser.add_argument(
        '--model-size',
        choices=['tiny', 'tiny.en', 'base', 'base.en', 'small', 'small.en', 'medium', 'medium.en', 'large'],
        default='medium.en',
        help='Whisper model size (default: medium.en - matches application)'
    )
    parser.add_argument(
        '--skip-whisper',
        action='store_true',
        help='Skip Whisper download'
    )
    parser.add_argument(
        '--skip-vad',
        action='store_true',
        help='Skip VAD download'
    )
    parser.add_argument(
        '--skip-resemblyzer',
        action='store_true',
        help='Skip Resemblyzer download'
    )

    args = parser.parse_args()

    print("=" * 60)
    print("CQSentinel Model Download")
    print("=" * 60)
    print()

    # Check disk space
    if not check_disk_space():
        response = input("Continue anyway? (y/n): ")
        if response.lower() != 'y':
            return 1

    print()

    success_count = 0
    total_count = 0

    # Download models
    if not args.skip_whisper:
        total_count += 1
        if download_whisper(args.model_size):
            success_count += 1
        print()

    if not args.skip_vad:
        total_count += 1
        if download_silero_vad():
            success_count += 1
        print()

    if not args.skip_resemblyzer:
        total_count += 1
        if download_resemblyzer():
            success_count += 1
        print()

    # Summary
    print("=" * 60)
    print(f"Download complete: {success_count}/{total_count} successful")
    print("=" * 60)
    print()

    if success_count == total_count:
        print("✓ All models downloaded successfully!")
        print()
        print("CQSentinel is now ready for offline operation.")
        print()
        print("Model locations:")
        print(f"  Whisper: ~/.cache/huggingface/")
        print(f"  Silero VAD: ~/.cache/torch/")
        print(f"  Resemblyzer: ~/.cache/torch/")
        print()
        return 0
    else:
        print("⚠ Some models failed to download.")
        print("Check error messages above and try again.")
        print()
        return 1


if __name__ == '__main__':
    sys.exit(main())
