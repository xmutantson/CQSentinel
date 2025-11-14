#!/usr/bin/env python3
"""
CQSentinel - SSB Contest Band Scanner
Main application entry point
"""

import sys
import logging
from pathlib import Path

from PyQt5.QtWidgets import QApplication

from cqsentinel.config import get_config_manager, get_config
from cqsentinel.utils.logging import setup_logging
from cqsentinel.gui.main_window import MainWindow

logger = logging.getLogger(__name__)


def main():
    """Main entry point"""

    # Load configuration
    config_manager = get_config_manager()
    config = config_manager.load()

    # Setup logging
    log_file = None
    if config.config_dir:
        log_dir = Path(config.config_dir) / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        log_file = str(log_dir / "cqsentinel.log")

    setup_logging(log_level=config.log_level, log_file=log_file)

    logger.info("=" * 60)
    logger.info("CQSentinel starting...")
    logger.info("=" * 60)

    # Check for required components
    check_dependencies()

    # Create Qt application
    app = QApplication(sys.argv)
    app.setApplicationName("CQSentinel")
    app.setOrganizationName("CQSentinel")

    # Create and show main window
    window = MainWindow()
    window.show()

    logger.info("Main window displayed")

    # Show initial instructions
    window.log("Welcome to CQSentinel - SSB Contest Scanner!")
    window.log("=" * 40)
    window.log("Quick Start:")
    window.log("1. Click 'File > Settings' to configure your radio")
    window.log("2. Click 'Connect Radio' - rigctld will start automatically")
    window.log("3. Select bands and contest profile")
    window.log("4. Click 'Start Scan' to begin")
    window.log("=" * 40)
    window.log("")
    window.log("Tip: The app will auto-detect your radio's serial port")
    window.log("and start rigctld automatically when you connect.")

    # Run application
    exit_code = app.exec()

    logger.info("CQSentinel shutting down...")

    return exit_code


def check_dependencies():
    """Check for required dependencies and warn if missing"""

    missing = []

    # Check for rigctld
    import shutil
    if not shutil.which('rigctld'):
        logger.warning("rigctld not found in PATH. Please install Hamlib.")
        missing.append("rigctld (Hamlib)")

    # Check for optional AI models
    models_dir = Path(__file__).parent.parent / "models"
    if not models_dir.exists():
        logger.warning(f"Models directory not found: {models_dir}")
        logger.warning("AI features will be limited until models are downloaded.")

    # Report missing dependencies
    if missing:
        logger.warning(f"Missing dependencies: {', '.join(missing)}")
        logger.warning("Some features may not work correctly.")


if __name__ == '__main__':
    sys.exit(main())
