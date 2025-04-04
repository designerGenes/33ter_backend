#!/usr/bin/env python3
"""Threethreeter Process Manager Entry Point

This script serves as the main entry point for the Threethreeter application. It initializes and
manages all core services including screenshot capture, OCR processing, and Socket.IO
communication. It provides a terminal-based UI for monitoring and controlling these services.

Key Features:
- Service initialization and management
- Configuration loading and validation
- Logging setup and management
- Terminal UI initialization
- System requirement validation
- Graceful shutdown handling

#TODO:
- Add proper signal handling for graceful shutdown
- Implement service recovery mechanisms
- Add proper resource cleanup on exit
- Consider adding daemon mode support
- Add proper process isolation
- Implement proper error reporting
"""

import curses
import sys
import argparse
import logging
import traceback
from typing import Optional

try:
    # Use explicit relative imports since this script is inside the Threethreeter package
    from .system_check import print_system_status
    from .config_loader import config
    from .process_manager import ProcessManager
    from .terminal_ui import TerminalUI
except ImportError as e:
    print(f"Error importing required modules: {e}", file=sys.stderr)  # Print import errors to stderr
    print("Please ensure you're running from the correct directory and all dependencies are installed.", file=sys.stderr)
    sys.exit(1)

# Get a logger instance for this module specifically
module_logger = logging.getLogger(__name__)

def setup_logging():
    logging.root.handlers = []
    logging.basicConfig(level=logging.INFO)

    # Configure root logger
    root_logger = logging.getLogger()
    
    # Create a file handler for the root logger
    root_file_handler = logging.FileHandler("root.log")
    root_file_handler.setLevel(logging.INFO)
    root_formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    root_file_handler.setFormatter(root_formatter)
    
    # Remove all handlers and add only the file handler
    root_logger.handlers = []
    root_logger.addHandler(root_file_handler)
    
    # Set level for other modules
    logging.getLogger("werkzeug").setLevel(logging.ERROR)
    logging.getLogger("engineio").setLevel(logging.ERROR)
    logging.getLogger("socketio").setLevel(logging.ERROR)

def setup_environment() -> Optional[ProcessManager]:
    """Initialize application environment and process manager."""
    try:
        # Tesseract installation is assumed to be handled by Homebrew and available in PATH.
        # TESSDATA_PREFIX is also assumed to be configured correctly by the Homebrew installation.

        # Check for critical configuration
        try:
            sc_config = config.get('screenshot', None)
            if sc_config is None:
                module_logger.warning("No screenshot configuration found, using defaults")
                config.set('screenshot', 'frequency', 4.0)
                config.set('screenshot', 'cleanup_age', 180)
        except Exception as config_error:
            module_logger.warning(f"Error checking screenshot configuration: {config_error}")
            config.set('screenshot', 'frequency', 4.0)
            config.set('screenshot', 'cleanup_age', 180)

        # Initialize process manager
        process_manager = ProcessManager()
        return process_manager
    except Exception as e:
        module_logger.error(f"Failed to initialize environment: {e}", exc_info=True)
        return None

def main() -> int:
    """Main application entry point."""
    parser = argparse.ArgumentParser(description='Threethreeter Process Manager')
    parser.add_argument('--skip-checks', action='store_true',
                       help='Skip system requirement checks')
    parser.add_argument('--debug', action='store_true',
                       help='Enable debug logging')
    args = parser.parse_args()

    # Configure logging level based on args
    if args.debug:
        config.set("logging", "level", value="DEBUG")
    setup_logging()

    module_logger.info("Threethreeter Process Manager starting...")

    process_manager = None
    try:
        # Perform system checks
        if not args.skip_checks:
            if not print_system_status():
                module_logger.error("System check failed. Please fix the issues above.")
                return 1

        # Initialize environment
        process_manager = setup_environment()
        if not process_manager:
            return 1

        # Initialize UI
        terminal_ui = TerminalUI(process_manager)

        # Start services
        try:
            process_manager.start_all_services()
        except Exception as service_error:
            module_logger.error(f"Error starting services: {service_error}", exc_info=True)

        # Run the UI
        try:
            curses.wrapper(terminal_ui.run)
        except Exception as ui_error:
            # Ensure curses is cleaned up *before* printing, if possible
            try:
                curses.endwin()
            except Exception as cleanup_err:
                print(f"\nError during curses cleanup: {cleanup_err}", file=sys.stderr)

            # Print directly to stderr, bypassing logging for this specific case
            print("\n--- Terminal UI Crashed ---", file=sys.stderr)
            print(f"Error Type: {type(ui_error).__name__}", file=sys.stderr)
            print(f"Error Details: {ui_error}", file=sys.stderr)
            print("\n--- Traceback ---", file=sys.stderr)
            traceback.print_exc(file=sys.stderr)  # Print full traceback to stderr
            print("--- End Traceback ---", file=sys.stderr)
            print("\nCheck app.log and process_manager.log for further context.", file=sys.stderr)

            # Optionally, try logging again as a fallback (might still fail)
            try:
                module_logger.error(f"Error during Terminal UI execution: {ui_error}", exc_info=True)
            except NameError:
                print("\n*** Logging system failed during UI error handling ***", file=sys.stderr)
            except Exception as log_err:
                print(f"\n*** Error occurred while trying to log UI error: {log_err} ***", file=sys.stderr)

            return 1

    except KeyboardInterrupt:
        module_logger.info("Shutdown requested by user...")
    except Exception as e:
        # Catch any other unhandled errors during setup or initial checks
        try:
            curses.endwin()
        except:
            pass
        print("\n--- Unhandled Error During Setup ---", file=sys.stderr)
        print(f"Error Type: {type(e).__name__}", file=sys.stderr)
        print(f"Error Details: {e}", file=sys.stderr)
        print("\n--- Traceback ---", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        print("--- End Traceback ---", file=sys.stderr)
        try:
            module_logger.error(f"Unhandled error during setup: {e}", exc_info=True)
        except Exception as log_err:
            print(f"\n*** Error occurred while trying to log setup error: {log_err} ***", file=sys.stderr)

        return 1
    finally:
        try:
            curses.endwin()
        except:
            pass

        if process_manager:
            module_logger.info("Initiating service shutdown...")
            process_manager.stop_all()
        else:
            module_logger.info("Process manager not initialized, skipping service shutdown.")

        module_logger.info("Application shutdown complete")

    return 0

if __name__ == "__main__":
    sys.exit(main())
