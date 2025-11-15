"""
Model Downloader Dialog

Downloads AI models at application startup with progress feedback.
Also handles on-demand installation of AI dependencies for packaged builds.
"""

import os
import sys
import logging
import threading
import subprocess
from pathlib import Path
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QLabel, QProgressBar, QPushButton,
    QTextEdit, QMessageBox
)
from PyQt5.QtCore import Qt, pyqtSignal, QThread

logger = logging.getLogger(__name__)


def setup_cache_paths():
    """
    Setup cache directories for model downloads.

    For packaged builds: Put models next to the .exe
    For source builds: Use standard cache directories
    """
    # Check if running from packaged executable
    if getattr(sys, 'frozen', False):
        # Running from packaged build - put models next to executable
        if hasattr(sys, '_MEIPASS'):
            # PyInstaller temp folder - use parent of executable
            base_path = Path(sys.executable).parent
        else:
            base_path = Path(sys.executable).parent

        # Create models directory next to executable
        models_dir = base_path / "models"
        models_dir.mkdir(parents=True, exist_ok=True)

        # Set cache paths to models directory
        hf_cache = models_dir / "huggingface"
        hf_cache.mkdir(parents=True, exist_ok=True)
        os.environ["HF_HOME"] = str(hf_cache)
        os.environ["TRANSFORMERS_CACHE"] = str(hf_cache)

        torch_cache = models_dir / "torch"
        torch_cache.mkdir(parents=True, exist_ok=True)
        os.environ["TORCH_HOME"] = str(torch_cache)

        logger.info(f"Packaged build - models directory: {models_dir}")
    else:
        # Running from source - use standard cache directories
        home = Path.home()

        hf_cache = home / ".cache" / "huggingface"
        hf_cache.mkdir(parents=True, exist_ok=True)
        os.environ["HF_HOME"] = str(hf_cache)
        os.environ["TRANSFORMERS_CACHE"] = str(hf_cache)

        torch_cache = home / ".cache" / "torch"
        torch_cache.mkdir(parents=True, exist_ok=True)
        os.environ["TORCH_HOME"] = str(torch_cache)

        logger.info(f"Source build - using standard cache")

    logger.info(f"Cache paths configured:")
    logger.info(f"  HF_HOME: {os.environ['HF_HOME']}")
    logger.info(f"  TORCH_HOME: {os.environ['TORCH_HOME']}")


def setup_packages_path():
    """
    Setup packages directory for packaged builds.

    For packaged builds, creates a 'packages' directory next to the .exe
    and adds it to sys.path so pip-installed packages can be imported.

    Returns:
        Path: Path to packages directory, or None if not a packaged build
    """
    if getattr(sys, 'frozen', False):
        # Packaged build - create packages dir next to exe
        base_path = Path(sys.executable).parent
        packages_dir = base_path / "packages"
        packages_dir.mkdir(parents=True, exist_ok=True)

        # Add to sys.path if not already there
        packages_path_str = str(packages_dir)
        if packages_path_str not in sys.path:
            sys.path.insert(0, packages_path_str)
            logger.info(f"Added packages directory to sys.path: {packages_dir}")

        return packages_dir
    return None


def check_dependencies_installed():
    """
    Check if AI dependencies are installed.

    Returns:
        list: List of missing package names (empty if all installed)
    """
    dependencies = {
        'faster-whisper': 'faster_whisper',
        'torch': 'torch',
        'resemblyzer': 'resemblyzer'
    }

    missing = []
    for package_name, import_name in dependencies.items():
        try:
            __import__(import_name)
            logger.debug(f"✓ {package_name} is installed")
        except ImportError:
            logger.debug(f"✗ {package_name} is missing")
            missing.append(package_name)

    return missing


def ensure_pip_available(progress_callback=None):
    """
    Ensure pip is available in the Python environment.

    On fresh Windows machines or packaged builds, pip might not be available.
    This function bootstraps pip using ensurepip if needed.

    Args:
        progress_callback: Optional callback(message: str) for progress updates

    Returns:
        bool: True if pip is available, False if failed to bootstrap
    """
    # CRITICAL: For packaged/frozen builds, we cannot use subprocess with sys.executable
    # because sys.executable points to the .exe, not Python. This would cause infinite
    # spawning of application windows!
    if getattr(sys, 'frozen', False):
        if progress_callback:
            progress_callback("⚠ Packaged build detected")
            progress_callback("  Cannot install dependencies via pip in packaged builds")
        logger.warning("Frozen build - cannot use subprocess pip installation")
        return False

    try:
        # Check if pip is available (SOURCE BUILDS ONLY)
        result = subprocess.run(
            [sys.executable, '-m', 'pip', '--version'],
            capture_output=True,
            text=True,
            timeout=10
        )

        if result.returncode == 0:
            if progress_callback:
                progress_callback("✓ pip is available")
            logger.info(f"pip is available: {result.stdout.strip()}")
            return True

    except Exception as e:
        logger.warning(f"pip check failed: {e}")

    # pip not available, try to bootstrap it
    if progress_callback:
        progress_callback("Installing pip (package installer)...")

    try:
        # Try using ensurepip (included in Python 3.4+)
        result = subprocess.run(
            [sys.executable, '-m', 'ensurepip', '--default-pip'],
            capture_output=True,
            text=True,
            timeout=60
        )

        if result.returncode == 0:
            if progress_callback:
                progress_callback("✓ pip installed successfully")
            logger.info("pip bootstrapped using ensurepip")
            return True
        else:
            logger.warning(f"ensurepip failed: {result.stderr}")

    except Exception as e:
        logger.warning(f"ensurepip failed: {e}")

    # ensurepip failed, try downloading get-pip.py
    if progress_callback:
        progress_callback("Downloading pip installer...")

    try:
        import urllib.request
        import tempfile

        # Download get-pip.py
        get_pip_url = "https://bootstrap.pypa.io/get-pip.py"
        with tempfile.NamedTemporaryFile(mode='wb', suffix='.py', delete=False) as tmp_file:
            tmp_path = tmp_file.name

            if progress_callback:
                progress_callback(f"  Downloading from {get_pip_url}...")

            with urllib.request.urlopen(get_pip_url, timeout=30) as response:
                tmp_file.write(response.read())

        if progress_callback:
            progress_callback("  Running pip installer...")

        # Run get-pip.py
        result = subprocess.run(
            [sys.executable, tmp_path],
            capture_output=True,
            text=True,
            timeout=120
        )

        # Clean up temp file
        try:
            Path(tmp_path).unlink()
        except:
            pass

        if result.returncode == 0:
            if progress_callback:
                progress_callback("✓ pip installed successfully")
            logger.info("pip bootstrapped using get-pip.py")
            return True
        else:
            logger.error(f"get-pip.py failed: {result.stderr}")

    except Exception as e:
        logger.error(f"Failed to download/run get-pip.py: {e}")

    if progress_callback:
        progress_callback("✗ Failed to install pip")
        progress_callback("  Cannot proceed without pip")
        progress_callback("  Please run from source installation instead")

    return False


def install_dependencies(packages_dir, progress_callback=None):
    """
    Install AI dependencies using pip subprocess.

    Args:
        packages_dir: Directory to install packages to
        progress_callback: Optional callback(message: str) for progress updates

    Returns:
        bool: True if all packages installed successfully, False otherwise
    """
    # Ensure pip is available first
    if not ensure_pip_available(progress_callback):
        if progress_callback:
            progress_callback("")
            progress_callback("Cannot install dependencies without pip.")
            progress_callback("Please install Python with pip support.")
        return False

    if progress_callback:
        progress_callback("")

    # List of packages to install
    # Note: Installing torch is large (~700 MB), so we install CPU-only version
    dependencies = [
        'faster-whisper',
        'torch',  # Will get CPU version
        'torchaudio',
        'resemblyzer'
    ]

    for dep in dependencies:
        if progress_callback:
            progress_callback(f"Installing {dep}...")
            progress_callback(f"  (This may take several minutes, please wait)")

        try:
            # Use pip to install to specific directory
            cmd = [
                sys.executable, '-m', 'pip', 'install',
                '--target', str(packages_dir),
                '--upgrade',
                dep
            ]

            logger.info(f"Running: {' '.join(cmd)}")

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=600  # 10 minute timeout per package (torch is large)
            )

            if result.returncode == 0:
                if progress_callback:
                    progress_callback(f"  ✓ {dep} installed successfully")
                logger.info(f"✓ {dep} installed successfully")
            else:
                if progress_callback:
                    progress_callback(f"  ✗ {dep} failed to install")
                    progress_callback(f"  Error: {result.stderr[:200]}")  # First 200 chars
                logger.error(f"✗ {dep} failed: {result.stderr}")
                return False

        except subprocess.TimeoutExpired:
            if progress_callback:
                progress_callback(f"  ✗ {dep} installation timed out")
            logger.error(f"✗ {dep} installation timed out")
            return False
        except Exception as e:
            if progress_callback:
                progress_callback(f"  ✗ {dep} error: {e}")
            logger.error(f"✗ {dep} error: {e}")
            return False

    if progress_callback:
        progress_callback("✓ All dependencies installed successfully!")

    return True


class ModelDownloadThread(QThread):
    """Background thread for setting up AI features (dependencies + models)"""

    progress_signal = pyqtSignal(str)  # Status message
    finished_signal = pyqtSignal(bool)  # Success/failure

    def __init__(self, model_size="small"):
        super().__init__()
        self.model_size = model_size

    def run(self):
        """Download all models (and install dependencies if needed)"""
        try:
            # Setup cache paths first
            setup_cache_paths()

            # Check if running in frozen/packaged environment
            is_frozen = getattr(sys, 'frozen', False)
            if is_frozen:
                self.progress_signal.emit("Running in packaged mode")
                self.progress_signal.emit("AI dependencies are bundled in the .exe")
                self.progress_signal.emit("")
            else:
                # For source builds, check if dependencies need to be installed
                self.progress_signal.emit("Running from source")
                self.progress_signal.emit("Checking AI dependencies...")
                missing_deps = check_dependencies_installed()

                if missing_deps:
                    self.progress_signal.emit(f"Missing dependencies: {', '.join(missing_deps)}")
                    self.progress_signal.emit("")
                    self.progress_signal.emit("Please install missing packages:")
                    self.progress_signal.emit("  pip install faster-whisper torch resemblyzer")
                    self.progress_signal.emit("")
                    self.progress_signal.emit("Click 'Skip' to continue in basic mode")
                    self.finished_signal.emit(False)
                    return
                else:
                    self.progress_signal.emit("✓ All dependencies installed")
                    self.progress_signal.emit("")

            success = True
            failures = []

            # Download Whisper
            self.progress_signal.emit("Downloading Whisper speech recognition model...")
            if not self._download_whisper():
                success = False
                failures.append("Whisper")

            # Download Silero VAD
            self.progress_signal.emit("Downloading Silero VAD model...")
            if not self._download_silero_vad():
                success = False
                failures.append("Silero VAD")

            # Download Resemblyzer
            self.progress_signal.emit("Downloading Resemblyzer voice encoder...")
            if not self._download_resemblyzer():
                success = False
                failures.append("Resemblyzer")

            if success:
                self.progress_signal.emit("✓ All models downloaded successfully!")
            else:
                self.progress_signal.emit(f"⚠ Failed to download: {', '.join(failures)}")
                self.progress_signal.emit("")

                if is_frozen:
                    self.progress_signal.emit("Model download failed even though dependencies are installed.")
                    self.progress_signal.emit("")
                    self.progress_signal.emit("You can:")
                    self.progress_signal.emit("1. Click 'Retry' to try again")
                    self.progress_signal.emit("2. Click 'Skip' to continue in basic mode")
                else:
                    # Source build - show installation instructions
                    self.progress_signal.emit("This may indicate missing dependencies.")
                    self.progress_signal.emit("")
                    self.progress_signal.emit("Install required packages:")
                    self.progress_signal.emit("  pip install faster-whisper torch resemblyzer")
                    self.progress_signal.emit("")
                    self.progress_signal.emit("You can continue without these models.")
                    self.progress_signal.emit("Advanced features will be limited.")

            self.finished_signal.emit(success)

        except Exception as e:
            logger.error(f"Model download failed: {e}", exc_info=True)
            self.progress_signal.emit(f"✗ Download failed: {e}")
            self.finished_signal.emit(False)

    def _download_whisper(self):
        """Download Whisper model"""
        try:
            # Check ctranslate2 first (required by faster-whisper)
            try:
                import ctranslate2
                logger.info(f"ctranslate2 version: {ctranslate2.__version__}")

                # Check for StorageView (required for faster-whisper)
                if not hasattr(ctranslate2, 'StorageView'):
                    self.progress_signal.emit("  ✗ ctranslate2 is outdated (missing StorageView)")
                    self.progress_signal.emit(f"    Found version: {ctranslate2.__version__}")
                    self.progress_signal.emit("    Requires version >= 3.0.0")
                    logger.error(f"ctranslate2 {ctranslate2.__version__} missing StorageView")
                    return False
            except ImportError:
                self.progress_signal.emit("  ✗ ctranslate2 not installed")
                logger.error("ctranslate2 not installed")
                return False

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

        except ImportError as e:
            self.progress_signal.emit(f"  ✗ faster-whisper import failed: {e}")
            logger.error(f"faster-whisper import failed: {e}")
            return False
        except Exception as e:
            self.progress_signal.emit(f"  ✗ Whisper download failed: {e}")
            logger.error(f"Whisper download failed: {e}", exc_info=True)
            return False

    def _download_silero_vad(self):
        """Download Silero VAD model"""
        try:
            import torch

            # CRITICAL: PyInstaller sets sys.stderr to None, which breaks torch.hub
            # Temporarily restore stderr for the download
            import sys
            original_stderr = sys.stderr
            if sys.stderr is None:
                sys.stderr = sys.stdout  # Redirect to stdout temporarily
                logger.info("Restored sys.stderr for torch.hub (was None in frozen build)")

            try:
                self.progress_signal.emit("  Downloading Silero VAD (~1.5 MB)...")

                # Set torch hub directory based on frozen/source
                if getattr(sys, 'frozen', False):
                    # Packaged - use models dir next to exe
                    torch_hub_dir = Path(sys.executable).parent / "models" / "torch" / "hub"
                else:
                    # Source - use cache
                    torch_hub_dir = Path.home() / ".cache" / "torch" / "hub"

                torch_hub_dir.mkdir(parents=True, exist_ok=True)
                torch.hub.set_dir(str(torch_hub_dir))

                # Load model (will download if needed)
                model, utils = torch.hub.load(
                    repo_or_dir='snakers4/silero-vad',
                    model='silero_vad',
                    force_reload=False,
                    onnx=False,
                    trust_repo=True  # Trust the repository
                )

                self.progress_signal.emit("  ✓ Silero VAD downloaded")
                return True
            finally:
                # Restore original stderr
                sys.stderr = original_stderr

        except ImportError as e:
            self.progress_signal.emit(f"  ✗ torch not installed: {e}")
            logger.error(f"torch not installed: {e}")
            return False
        except Exception as e:
            self.progress_signal.emit(f"  ✗ Silero VAD download failed: {e}")
            logger.error(f"Silero VAD download failed: {e}", exc_info=True)
            return False

    def _download_resemblyzer(self):
        """Download Resemblyzer model"""
        try:
            self.progress_signal.emit("  Downloading Resemblyzer (~20 MB)...")

            # Set up torch hub directory based on frozen/source
            import torch
            if getattr(sys, 'frozen', False):
                # Packaged - use models dir next to exe
                torch_hub_dir = Path(sys.executable).parent / "models" / "torch" / "hub"
            else:
                # Source - use cache
                torch_hub_dir = Path.home() / ".cache" / "torch" / "hub"

            torch.hub.set_dir(str(torch_hub_dir))

            # Import and initialize encoder (downloads model if needed)
            from resemblyzer import VoiceEncoder

            # Initialize encoder (downloads model if needed)
            encoder = VoiceEncoder()

            self.progress_signal.emit("  ✓ Resemblyzer downloaded")
            return True

        except ImportError as e:
            self.progress_signal.emit(f"  ✗ resemblyzer or torch not installed: {e}")
            logger.error(f"resemblyzer or torch not installed: {e}")
            return False
        except Exception as e:
            self.progress_signal.emit(f"  ✗ Resemblyzer download failed: {e}")
            logger.error(f"Resemblyzer download failed: {e}", exc_info=True)
            return False


class ModelDownloaderDialog(QDialog):
    """
    Dialog for downloading AI models at startup.

    For packaged builds: AI dependencies are bundled, only downloads models.
    For source builds: Checks dependencies are installed, then downloads models.
    Shows progress and allows user to continue or skip if download fails.
    """

    def __init__(self, model_size="small", parent=None):
        super().__init__(parent)

        self.model_size = model_size
        self.download_success = False

        self.setWindowTitle("Setting Up AI Features")
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
        title_label = QLabel("Setting Up AI Features")
        title_label.setStyleSheet("font-size: 16px; font-weight: bold;")
        layout.addWidget(title_label)

        # Description
        desc_label = QLabel(
            "Downloading AI models for speech recognition and voice fingerprinting.\n"
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
        log_label = QLabel("Setup Log:")
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
        """Start AI setup in background thread (dependencies + models)"""
        self.log("Starting AI setup...")

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
        """Handle setup completion"""
        self.download_success = success

        # Stop indeterminate progress bar
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(100 if success else 0)

        if success:
            self.status_label.setText("✓ Setup complete!")
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
            self.status_label.setText("⚠ Setup failed - see log for details")
            self.continue_btn.setText("Retry")
            self.continue_btn.setEnabled(True)
            self.skip_btn.setEnabled(True)

            # Check if running from source or packaged
            is_frozen = getattr(sys, 'frozen', False)

            if is_frozen:
                # Show message for packaged build
                QMessageBox.warning(
                    self,
                    "AI Setup Failed",
                    "Failed to install AI dependencies or download models.\n\n"
                    "You can:\n"
                    "1. Click 'Retry' to try again\n"
                    "2. Click 'Skip' to continue in basic mode\n"
                    "   (radio control and frequency scanning only)\n\n"
                    "Check the setup log for details."
                )
            else:
                # Show message for source installation
                QMessageBox.warning(
                    self,
                    "AI Setup Failed",
                    "Failed to download AI models.\n\n"
                    "Make sure dependencies are installed:\n"
                    "  pip install faster-whisper torch resemblyzer\n\n"
                    "You can continue in basic mode or retry after installing.\n\n"
                    "Check the setup log for details."
                )

    def log(self, message: str):
        """Add message to log"""
        self.log_text.append(message)
        logger.info(f"AI setup: {message}")


def check_models_exist():
    """
    Check if AI models are already downloaded.

    For packaged builds: Check models directory next to .exe
    For source builds: Check standard cache directories

    Returns:
        bool: True if models exist, False if need to download
    """
    try:
        # Determine where to check based on frozen/source
        if getattr(sys, 'frozen', False):
            # Packaged build - check models directory next to exe
            base_path = Path(sys.executable).parent
            models_dir = base_path / "models"

            hf_cache = models_dir / "huggingface" / "hub"
            torch_cache = models_dir / "torch" / "hub"
            resemblyzer_cache = models_dir / "torch" / "hub" / "checkpoints"

            logger.info(f"Checking for models in: {models_dir}")
        else:
            # Source build - check standard cache directories
            home = Path.home()
            hf_cache = home / ".cache" / "huggingface" / "hub"
            torch_cache = home / ".cache" / "torch" / "hub"
            resemblyzer_cache = home / ".cache" / "torch" / "hub" / "checkpoints"

            logger.info(f"Checking for models in standard cache")

        # Check for Whisper models
        whisper_exists = False
        if hf_cache.exists():
            whisper_models = list(hf_cache.glob("models--Systran--faster-whisper-*"))
            whisper_exists = len(whisper_models) > 0

        # Check for Silero VAD
        vad_exists = False
        if torch_cache.exists():
            vad_models = list(torch_cache.glob("snakers4_silero-vad_*"))
            vad_exists = len(vad_models) > 0

        # Check for Resemblyzer
        resemblyzer_exists = False
        if resemblyzer_cache.exists():
            resemblyzer_models = list(resemblyzer_cache.glob("*.pt"))
            resemblyzer_exists = len(resemblyzer_models) > 0

        # All models must exist
        models_ready = whisper_exists and vad_exists and resemblyzer_exists

        if models_ready:
            logger.info("✓ AI models already downloaded")
        else:
            logger.info(f"Models status: Whisper={whisper_exists}, VAD={vad_exists}, Resemblyzer={resemblyzer_exists}")
            logger.info("AI models need to be downloaded")

        return models_ready

    except Exception as e:
        logger.warning(f"Could not check model status: {e}")
        return False
