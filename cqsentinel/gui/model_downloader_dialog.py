"""
Model Downloader Dialog

Downloads AI models at application startup with progress feedback.
"""

import logging
import threading
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QLabel, QProgressBar, QPushButton,
    QTextEdit, QMessageBox
)
from PyQt5.QtCore import Qt, pyqtSignal, QThread

logger = logging.getLogger(__name__)


class ModelDownloadThread(QThread):
    """Background thread for downloading models"""

    progress_signal = pyqtSignal(str)  # Status message
    finished_signal = pyqtSignal(bool)  # Success/failure

    def __init__(self, model_size="small"):
        super().__init__()
        self.model_size = model_size

    def run(self):
        """Download all models"""
        try:
            success = True

            # Download Whisper
            self.progress_signal.emit("Downloading Whisper speech recognition model...")
            if not self._download_whisper():
                success = False

            # Download Silero VAD
            self.progress_signal.emit("Downloading Silero VAD model...")
            if not self._download_silero_vad():
                success = False

            # Download Resemblyzer
            self.progress_signal.emit("Downloading Resemblyzer voice encoder...")
            if not self._download_resemblyzer():
                success = False

            if success:
                self.progress_signal.emit("✓ All models downloaded successfully!")
            else:
                self.progress_signal.emit("⚠ Some models failed to download")

            self.finished_signal.emit(success)

        except Exception as e:
            logger.error(f"Model download failed: {e}", exc_info=True)
            self.progress_signal.emit(f"✗ Download failed: {e}")
            self.finished_signal.emit(False)

    def _download_whisper(self):
        """Download Whisper model"""
        try:
            from faster_whisper import WhisperModel

            self.progress_signal.emit(f"  Downloading Whisper {self.model_size} (~460 MB)...")

            # This will download the model if not already cached
            model = WhisperModel(
                self.model_size,
                device="cpu",
                compute_type="int8",
                download_root=None  # Use default cache
            )

            self.progress_signal.emit(f"  ✓ Whisper {self.model_size} downloaded")
            return True

        except ImportError:
            self.progress_signal.emit("  ✗ faster-whisper not installed")
            logger.error("faster-whisper not installed")
            return False
        except Exception as e:
            self.progress_signal.emit(f"  ✗ Whisper download failed: {e}")
            logger.error(f"Whisper download failed: {e}")
            return False

    def _download_silero_vad(self):
        """Download Silero VAD model"""
        try:
            import torch

            self.progress_signal.emit("  Downloading Silero VAD (~1.5 MB)...")

            # Load model (will download if needed)
            model, utils = torch.hub.load(
                repo_or_dir='snakers4/silero-vad',
                model='silero_vad',
                force_reload=False,
                onnx=False
            )

            self.progress_signal.emit("  ✓ Silero VAD downloaded")
            return True

        except ImportError:
            self.progress_signal.emit("  ✗ torch not installed")
            logger.error("torch not installed")
            return False
        except Exception as e:
            self.progress_signal.emit(f"  ✗ Silero VAD download failed: {e}")
            logger.error(f"Silero VAD download failed: {e}")
            return False

    def _download_resemblyzer(self):
        """Download Resemblyzer model"""
        try:
            from resemblyzer import VoiceEncoder

            self.progress_signal.emit("  Downloading Resemblyzer (~20 MB)...")

            # Initialize encoder (downloads model if needed)
            encoder = VoiceEncoder()

            self.progress_signal.emit("  ✓ Resemblyzer downloaded")
            return True

        except ImportError:
            self.progress_signal.emit("  ✗ resemblyzer not installed")
            logger.error("resemblyzer not installed")
            return False
        except Exception as e:
            self.progress_signal.emit(f"  ✗ Resemblyzer download failed: {e}")
            logger.error(f"Resemblyzer download failed: {e}")
            return False


class ModelDownloaderDialog(QDialog):
    """
    Dialog for downloading AI models at startup.

    Shows progress and allows user to continue or skip if download fails.
    """

    def __init__(self, model_size="small", parent=None):
        super().__init__(parent)

        self.model_size = model_size
        self.download_success = False

        self.setWindowTitle("Downloading AI Models")
        self.setModal(True)
        self.setMinimumWidth(500)
        self.setMinimumHeight(350)

        # Prevent closing during download
        self.setWindowFlags(
            Qt.WindowType.Dialog |
            Qt.WindowType.CustomizeWindowHint |
            Qt.WindowType.WindowTitleHint
        )

        self._init_ui()

    def _init_ui(self):
        """Initialize user interface"""
        layout = QVBoxLayout()

        # Title
        title_label = QLabel("Downloading AI Models")
        title_label.setStyleSheet("font-size: 16px; font-weight: bold;")
        layout.addWidget(title_label)

        # Description
        desc_label = QLabel(
            "CQSentinel requires AI models for speech recognition and voice fingerprinting.\n"
            "This is a one-time download (~500 MB total)."
        )
        desc_label.setWordWrap(True)
        layout.addWidget(desc_label)

        # Progress bar (indeterminate)
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 0)  # Indeterminate
        layout.addWidget(self.progress_bar)

        # Status label
        self.status_label = QLabel("Preparing to download...")
        layout.addWidget(self.status_label)

        # Log output
        log_label = QLabel("Download Log:")
        layout.addWidget(log_label)

        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setMaximumHeight(150)
        layout.addWidget(self.log_text)

        # Buttons
        self.continue_btn = QPushButton("Continue")
        self.continue_btn.setEnabled(False)
        self.continue_btn.clicked.connect(self.accept)
        layout.addWidget(self.continue_btn)

        self.skip_btn = QPushButton("Skip (Advanced features disabled)")
        self.skip_btn.setEnabled(False)
        self.skip_btn.clicked.connect(self.reject)
        layout.addWidget(self.skip_btn)

        self.setLayout(layout)

    def start_download(self):
        """Start model download in background thread"""
        self.log("Starting model download...")

        # Create download thread
        self.download_thread = ModelDownloadThread(model_size=self.model_size)
        self.download_thread.progress_signal.connect(self.on_progress)
        self.download_thread.finished_signal.connect(self.on_finished)

        # Start download
        self.download_thread.start()

    def on_progress(self, message: str):
        """Handle progress update"""
        self.log(message)
        self.status_label.setText(message)

    def on_finished(self, success: bool):
        """Handle download completion"""
        self.download_success = success

        # Stop indeterminate progress bar
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(100 if success else 0)

        if success:
            self.status_label.setText("✓ Download complete!")
            self.continue_btn.setText("Continue")
            self.continue_btn.setEnabled(True)
            self.skip_btn.setEnabled(False)

            # Auto-close after 2 seconds
            import threading
            def auto_close():
                import time
                time.sleep(2)
                try:
                    self.accept()
                except:
                    pass

            threading.Thread(target=auto_close, daemon=True).start()
        else:
            self.status_label.setText("⚠ Download failed - see log for details")
            self.continue_btn.setText("Retry")
            self.continue_btn.setEnabled(True)
            self.skip_btn.setEnabled(True)

            # Show warning
            QMessageBox.warning(
                self,
                "Download Failed",
                "Some AI models failed to download.\n\n"
                "You can continue without advanced features, or retry the download.\n\n"
                "Check the download log for details."
            )

    def log(self, message: str):
        """Add message to log"""
        self.log_text.append(message)
        logger.info(f"Model download: {message}")


def check_models_exist():
    """
    Check if AI models are already downloaded.

    Returns:
        bool: True if models exist, False if need to download
    """
    try:
        # Check Whisper (try to load without downloading)
        import os
        from pathlib import Path

        # Check Hugging Face cache for Whisper
        hf_cache = Path.home() / ".cache" / "huggingface" / "hub"
        whisper_exists = False
        if hf_cache.exists():
            # Look for whisper model directories
            whisper_models = list(hf_cache.glob("models--Systran--faster-whisper-*"))
            whisper_exists = len(whisper_models) > 0

        # Check torch cache for Silero VAD
        torch_cache = Path.home() / ".cache" / "torch" / "hub"
        vad_exists = False
        if torch_cache.exists():
            vad_models = list(torch_cache.glob("snakers4_silero-vad_*"))
            vad_exists = len(vad_models) > 0

        # Check for Resemblyzer
        resemblyzer_cache = Path.home() / ".cache" / "torch" / "hub" / "checkpoints"
        resemblyzer_exists = False
        if resemblyzer_cache.exists():
            resemblyzer_models = list(resemblyzer_cache.glob("*.pt"))
            resemblyzer_exists = len(resemblyzer_models) > 0

        # All models must exist
        models_ready = whisper_exists and vad_exists and resemblyzer_exists

        if models_ready:
            logger.info("AI models already downloaded")
        else:
            logger.info(f"Models status: Whisper={whisper_exists}, VAD={vad_exists}, Resemblyzer={resemblyzer_exists}")
            logger.info("AI models need to be downloaded")

        return models_ready

    except Exception as e:
        logger.warning(f"Could not check model status: {e}")
        return False
