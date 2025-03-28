#!/usr/bin/env python3
"""33ter Process Manager Entry Point

This script serves as the main entry point for the 33ter application. It initializes and
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
import os
import sys
import argparse
import logging
from typing import Optional

try:
    from utils.system_check import print_system_status
    from utils.path_config import get_logs_dir
    from utils.config_loader import config
    from core.process_manager import ProcessManager
    from core.terminal_ui import TerminalUI
except ImportError as e:
    print(f"Error importing required modules: {e}")
    print("Please ensure you're running from the correct directory and all dependencies are installed.")
    sys.exit(1)

def setup_logging() -> None:
    """Configure application logging."""
    log_level = getattr(logging, config.get("logging", "level", default="INFO"))
    log_file = os.path.join(get_logs_dir(), "app.log")
    
    logging.basicConfig(
        level=log_level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_file),
            logging.StreamHandler()
        ]
    )

def setup_environment() -> Optional[ProcessManager]:
    """Initialize application environment and process manager."""
    try:
        # Check Tesseract installation
        tesseract_path = "/opt/homebrew/bin/tesseract"  # Common path on macOS with Homebrew
        if not os.path.exists(tesseract_path):
            logging.error(f"Tesseract not found at {tesseract_path}")
            logging.info("Please install Tesseract using: brew install tesseract")
            return None
            
        os.environ["TESSDATA_PREFIX"] = "/opt/homebrew/share/tessdata/"
        
        # Check for critical configuration
        try:
            sc_config = config.get('screenshot', None)
            if sc_config is None:
                logging.warning("No screenshot configuration found, using defaults")
                # Add default screenshot config to prevent None comparisons
                config.set('screenshot', 'frequency', 4.0)
                config.set('screenshot', 'cleanup_age', 180)
        except Exception as config_error:
            logging.warning(f"Error checking screenshot configuration: {config_error}")
            # Set defaults explicitly to avoid None comparisons
            config.set('screenshot', 'frequency', 4.0)
            config.set('screenshot', 'cleanup_age', 180)
        
        # Initialize process manager
        process_manager = ProcessManager()
        return process_manager
    except Exception as e:
        logging.error(f"Failed to initialize environment: {e}")
        return None

def main() -> int:
    """Main application entry point."""
    parser = argparse.ArgumentParser(description='33ter Process Manager')
    parser.add_argument('--skip-checks', action='store_true',
                       help='Skip system requirement checks')
    parser.add_argument('--debug', action='store_true',
                       help='Enable debug logging')
    args = parser.parse_args()

    # Configure logging
    if args.debug:
        config.set("logging", "level", value="DEBUG")
    setup_logging()

    # Log startup
    logging.info("33ter Process Manager starting...")

    process_manager = None # Initialize to None for finally block
    try:
        # Perform system checks
        if not args.skip_checks:
            if not print_system_status():
                logging.error("System check failed. Please fix the issues above.")
                return 1

        # Initialize environment
        process_manager = setup_environment()
        if not process_manager:
            return 1

        # Initialize UI
        terminal_ui = TerminalUI(process_manager)

        # Start services with additional error handling
        try:
            process_manager.start_all_services()
        except Exception as service_error:
            logging.error(f"Error starting services: {service_error}", exc_info=True)
            # Optionally decide if you want to exit or continue to UI
            # return 1 # Exit if services are critical

        # Run the UI - Wrap this specifically to catch errors during UI run
        try:
            curses.wrapper(terminal_ui.run)
        except Exception as ui_error:
            # Log the specific error encountered during curses UI execution
            logging.error(f"Error during Terminal UI execution: {ui_error}", exc_info=True)
            # Ensure curses state is cleaned up if possible
            try:
                curses.endwin()
            except:
                pass
            print(f"\nTerminal UI crashed: {ui_error}", file=sys.stderr)
            print("Check app.log and process_manager.log for details.", file=sys.stderr)
            return 1 # Indicate failure

    except KeyboardInterrupt:
        logging.info("Shutdown requested by user...")
    except Exception as e:
        # Catch any other unhandled errors during setup
        logging.error(f"Unhandled error during setup: {e}", exc_info=True)
        return 1
    finally:
        # Ensure services are stopped even if errors occurred
        if process_manager:
            logging.info("Initiating service shutdown...")
            process_manager.stop_all()
        else:
            logging.info("Process manager not initialized, skipping service shutdown.")

        logging.info("Application shutdown complete")

    return 0 # Indicate success if we reach here

if __name__ == "__main__":
    sys.exit(main())
