#!/usr/bin/env python3
"""
CQSentinel - SSB Contest Band Scanner
Main application entry point
"""

import sys
import logging
import traceback
import atexit
from pathlib import Path

logger = logging.getLogger(__name__)

# Global reference to main window for cleanup
_main_window = None


def cleanup_resources():
    """Cleanup all resources (rigctld, audio, etc.) on exit"""
    global _main_window

    if _main_window is None:
        return

    try:
        logger.info("Cleaning up resources on exit...")

        # Stop rigctld
        if hasattr(_main_window, 'rigctld_manager') and _main_window.rigctld_manager:
            logger.info("Stopping rigctld process...")
            try:
                _main_window.rigctld_manager.stop()
            except Exception as e:
                logger.error(f"Error stopping rigctld: {e}")

        # Stop audio
        if hasattr(_main_window, 'audio') and _main_window.audio:
            try:
                _main_window.audio.stop_stream()
            except Exception as e:
                logger.error(f"Error stopping audio: {e}")

        # Disconnect radio
        if hasattr(_main_window, 'radio') and _main_window.radio:
            try:
                _main_window.radio.disconnect()
            except Exception as e:
                logger.error(f"Error disconnecting radio: {e}")

        logger.info("Resource cleanup complete")
    except Exception as e:
        logger.error(f"Error during cleanup: {e}")


def excepthook(exc_type, exc_value, exc_tb):
    """Global exception handler to catch uncaught exceptions"""
    error_msg = ''.join(traceback.format_exception(exc_type, exc_value, exc_tb))
    logger.critical("=" * 60)
    logger.critical("UNCAUGHT EXCEPTION - Application crashed!")
    logger.critical("=" * 60)
    logger.critical(error_msg)
    logger.critical("=" * 60)

    # Clean up resources before crash
    logger.critical("Attempting to clean up resources...")
    cleanup_resources()

    # Call the default handler to ensure proper cleanup
    sys.__excepthook__(exc_type, exc_value, exc_tb)


def main():
    """Main entry point"""
    global _main_window

    try:
        # Import PyQt5 first (this is fast)
        from PyQt5.QtWidgets import QApplication
        from PyQt5.QtCore import Qt

        # Create Qt application FIRST (very fast)
        app = QApplication(sys.argv)
        app.setApplicationName("CQSentinel")
        app.setOrganizationName("CQSentinel")

        # Show splash screen IMMEDIATELY (before any other imports)
        from cqsentinel.gui.splash_screen import SplashScreen
        splash = SplashScreen()
        splash.update_message("Starting CQSentinel...")
        app.processEvents()  # Force UI update

        # Now load configuration (after splash is visible)
        splash.update_message("Loading configuration...")
        app.processEvents()
        from cqsentinel.config import get_config_manager, get_config
        from cqsentinel.utils.logging import setup_logging

        config_manager = get_config_manager()
        config = config_manager.load()

        # Setup logging
        log_file = None
        if config.config_dir:
            log_dir = Path(config.config_dir) / "logs"
            log_dir.mkdir(parents=True, exist_ok=True)
            log_file = str(log_dir / "cqsentinel.log")

        setup_logging(log_level=config.log_level, log_file=log_file)

        # Install global exception handler to catch crashes
        sys.excepthook = excepthook

        # Register cleanup handler for normal exit and crashes
        atexit.register(cleanup_resources)

        logger.info("=" * 60)
        logger.info("CQSentinel starting...")
        logger.info("=" * 60)

        # Check for required components
        splash.update_message("Checking dependencies...")
        app.processEvents()
        check_dependencies()

        # Import MainWindow after splash is shown (this is a slow import)
        splash.update_message("Loading modules...")
        app.processEvents()
        from cqsentinel.gui.main_window import MainWindow

        # Create main window (this loads heavy modules)
        splash.update_message("Initializing user interface...")
        app.processEvents()
        window = MainWindow()
        _main_window = window  # Store globally for cleanup

        # Finish splash and show main window
        splash.finish_loading(window)
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

    except Exception as e:
        logger.critical("=" * 60)
        logger.critical("FATAL ERROR in main()")
        logger.critical("=" * 60)
        logger.critical(f"{e}", exc_info=True)
        logger.critical("=" * 60)
        return 1


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
