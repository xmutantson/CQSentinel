#!/usr/bin/env python3
"""
CQSentinel - SSB Contest Band Scanner
Main application entry point
"""

# CRITICAL: Configure NumPy/MKL threading BEFORE any imports
# Must be set before NumPy is imported to prevent worker thread crashes
import os
os.environ['OMP_NUM_THREADS'] = '1'  # OpenMP threads
os.environ['MKL_NUM_THREADS'] = '1'  # MKL threads (Intel Math Kernel Library)
os.environ['NUMEXPR_NUM_THREADS'] = '1'  # NumExpr threads
os.environ['OPENBLAS_NUM_THREADS'] = '1'  # OpenBLAS threads
os.environ['VECLIB_MAXIMUM_THREADS'] = '1'  # Accelerate threads (macOS)
os.environ['BLIS_NUM_THREADS'] = '1'  # BLIS threads

import sys
import logging
import traceback
import atexit
import faulthandler
import signal
from pathlib import Path

logger = logging.getLogger(__name__)

# Global reference to main window for cleanup
_main_window = None
_cleanup_in_progress = False


def cleanup_resources():
    """Cleanup all resources (rigctld, audio, etc.) on exit"""
    global _main_window, _cleanup_in_progress

    # Prevent recursive cleanup
    if _cleanup_in_progress:
        return
    _cleanup_in_progress = True

    if _main_window is None:
        return

    try:
        logger.info("Cleaning up resources on exit...")

        # Stop transcription poll timer FIRST to prevent warning spam
        if hasattr(_main_window, 'transcription_poll_timer') and _main_window.transcription_poll_timer:
            try:
                _main_window.transcription_poll_timer.stop()
            except Exception as e:
                logger.error(f"Error stopping transcription poll timer: {e}")

        # Stop transcription subprocess (CUDA cleanup happens here)
        if hasattr(_main_window, 'subprocess_transcriber') and _main_window.subprocess_transcriber:
            logger.info("Stopping transcription subprocess (releasing GPU resources)...")
            try:
                _main_window.subprocess_transcriber.stop()
                logger.info("Transcription subprocess stopped")
            except Exception as e:
                logger.error(f"Error stopping transcription subprocess: {e}")

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


def signal_handler(signum, frame):
    """Handle termination signals for graceful shutdown"""
    signal_name = signal.Signals(signum).name if hasattr(signal, 'Signals') else str(signum)
    print(f"\nReceived signal {signal_name} - initiating graceful shutdown...")
    logger.warning(f"Received signal {signal_name} - initiating graceful shutdown")

    # Clean up resources (especially GPU workers)
    cleanup_resources()

    # Exit gracefully
    sys.exit(0)


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

    # CRITICAL: Detect if we're running in a multiprocessing worker subprocess
    # On Windows, multiprocessing creates subprocesses by re-launching the executable,
    # which would re-run main() and create infinite window spawning.
    # We must exit early if we're in a worker subprocess.
    #
    # Note: This is a defense-in-depth measure. freeze_support() should handle
    # worker processes, but in case it doesn't detect them (e.g., due to PyInstaller
    # quirks), we check here too. Returning early from main() prevents GUI initialization
    # while still allowing the worker function to execute (it runs via multiprocessing
    # internals independent of main()).
    import multiprocessing
    if multiprocessing.current_process().name != 'MainProcess':
        # We're in a worker subprocess - don't initialize GUI, just return
        # The worker function will be invoked by multiprocessing internals
        return 0

    # CRITICAL FIX: PyInstaller sets sys.stderr and sys.stdout to None in frozen builds
    # This breaks logging and causes crashes throughout the application
    # We must restore them PERMANENTLY at application startup
    import io
    if getattr(sys, 'frozen', False):
        if sys.stderr is None:
            sys.stderr = io.StringIO()
        if sys.stdout is None:
            sys.stdout = io.StringIO()

    # Enable faulthandler for C-level crash diagnostics (before anything else)
    # This will print a traceback on segfaults, aborts, etc.
    try:
        faulthandler.enable()
        print("Faulthandler enabled for crash diagnostics")
    except Exception as e:
        print(f"Warning: Could not enable faulthandler: {e}")

    # Print to console for debugging (before logging is set up)
    print("CQSentinel starting...")
    print(f"Python version: {sys.version}")
    print(f"Frozen: {getattr(sys, 'frozen', False)}")
    print(f"Executable: {sys.executable}")
    print("")

    # Verify NumPy/MKL threading configuration
    print("NumPy/MKL threading configuration:")
    print(f"  MKL_NUM_THREADS: {os.environ.get('MKL_NUM_THREADS', 'not set')}")
    print(f"  OMP_NUM_THREADS: {os.environ.get('OMP_NUM_THREADS', 'not set')}")
    print(f"  OPENBLAS_NUM_THREADS: {os.environ.get('OPENBLAS_NUM_THREADS', 'not set')}")
    print("")

    try:
        # Import PyQt5 first (this is fast)
        print("Importing PyQt5...")
        from PyQt5.QtWidgets import QApplication
        from PyQt5.QtCore import Qt

        # Create Qt application FIRST (very fast)
        print("Creating Qt application...")
        app = QApplication(sys.argv)
        app.setApplicationName("CQSentinel")
        app.setOrganizationName("CQSentinel")

        # Show splash screen IMMEDIATELY (before any other imports)
        print("Loading splash screen...")
        from cqsentinel.gui.splash_screen import SplashScreen
        splash = SplashScreen()
        splash.update_message("Starting CQSentinel...")
        app.processEvents()  # Force UI update

        # Now load configuration (after splash is visible)
        print("Loading configuration...")
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

        # Register signal handlers for graceful shutdown (important for GPU cleanup)
        # SIGINT: Ctrl+C
        # SIGTERM: kill command (Unix) or TaskManager (Windows)
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)

        # Windows-specific: Handle console close events (closing PowerShell window)
        if sys.platform == 'win32':
            try:
                import win32api
                import win32con

                def windows_console_handler(ctrl_type):
                    """Handle Windows console events (close, logoff, shutdown)"""
                    # CTRL_CLOSE_EVENT (2): Console window being closed
                    # CTRL_LOGOFF_EVENT (5): User logging off
                    # CTRL_SHUTDOWN_EVENT (6): System shutting down
                    if ctrl_type in (win32con.CTRL_CLOSE_EVENT, win32con.CTRL_LOGOFF_EVENT,
                                     win32con.CTRL_SHUTDOWN_EVENT):
                        print(f"\nWindows console event {ctrl_type} - cleaning up GPU resources...")
                        cleanup_resources()
                        return True  # Signal handled
                    return False  # Let default handler run

                win32api.SetConsoleCtrlHandler(windows_console_handler, True)
                logger.info("Registered Windows console close handler for GPU cleanup")
            except ImportError:
                logger.warning("pywin32 not available - console close events may not trigger cleanup")
                logger.warning("If you see BSOD on console close, install pywin32: pip install pywin32")

        logger.info("=" * 60)
        logger.info("CQSentinel starting...")
        logger.info("=" * 60)

        # Check for required components
        splash.update_message("Checking dependencies...")
        app.processEvents()
        check_dependencies()

        # Check if AI models need to be downloaded
        splash.update_message("Checking AI models...")
        app.processEvents()
        from cqsentinel.gui.model_downloader_dialog import check_models_exist, ModelDownloaderDialog, setup_cache_paths, setup_packages_path

        # Setup packages path first (for packaged builds)
        # This ensures pip-installed packages can be imported
        setup_packages_path()

        # Setup cache paths (ensures models go to correct directory)
        setup_cache_paths()

        if not check_models_exist():
            # Hide splash and show model downloader
            splash.hide()

            logger.info("AI models not found - showing download dialog")
            downloader = ModelDownloaderDialog(model_size="medium.en")  # Hardcoded for best accuracy
            downloader.start_download()

            result = downloader.exec()

            # Show splash again
            splash.show()
            splash.update_message("Models ready, loading application...")
            app.processEvents()

            if result != downloader.Accepted:
                logger.warning("User skipped model download - advanced features will be disabled")
        else:
            logger.info("AI models already available")

        # Import MainWindow after splash is shown (this is a slow import)
        # Use QTimer to defer heavy import so splash screen stays responsive
        print("Scheduling main window load...")
        splash.update_message("Loading modules...")
        app.processEvents()

        def load_main_window():
            """Load main window in event loop (keeps splash responsive)"""
            global _main_window

            print("Importing main window module...")
            splash.update_message("Loading PyTorch and AI models...")
            app.processEvents()

            from cqsentinel.gui.main_window import MainWindow

            # Create main window (this loads heavy modules)
            print("Creating main window...")
            splash.update_message("Initializing user interface...")
            app.processEvents()

            window = MainWindow()
            _main_window = window  # Store globally for cleanup
            print("Main window created successfully!")

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
            window.log("3. Enable audio monitoring and transcription in Advanced Features")
            window.log("4. Start scanning with the 'Start Scan' button")
            window.log("")

        # Schedule main window load after splash is painted
        from PyQt5.QtCore import QTimer
        QTimer.singleShot(100, load_main_window)  # 100ms delay lets splash render

        # Run application (main window will show when loaded)
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

    # Report missing dependencies
    if missing:
        logger.warning(f"Missing dependencies: {', '.join(missing)}")
        logger.warning("Some features may not work correctly.")

    # Note: AI model checking is now handled by the model downloader dialog


if __name__ == '__main__':
    # CRITICAL: Required for multiprocessing support in frozen Windows executables
    # This must be called before any multiprocessing code runs
    # If this is a worker process, freeze_support() will handle it and call sys.exit()
    import multiprocessing
    multiprocessing.freeze_support()

    # If we get here, freeze_support() didn't detect a worker, so we should run normally
    try:
        exit_code = main()
        sys.exit(exit_code)
    except Exception as e:
        # Catch ANY exception during startup
        print("=" * 70)
        print("FATAL ERROR - Application crashed during startup!")
        print("=" * 70)
        print(f"\nError: {e}")
        print("\nFull traceback:")
        traceback.print_exc()
        print("=" * 70)
        print("\nPress any key to exit...")
        try:
            import msvcrt
            msvcrt.getch()  # Windows
        except ImportError:
            input()  # Linux/Mac
        sys.exit(1)
