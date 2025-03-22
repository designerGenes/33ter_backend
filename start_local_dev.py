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
        
        try:
            # Start services
            process_manager.start_all_services()
            
            # Run the UI
            curses.wrapper(terminal_ui.run)
            
        except KeyboardInterrupt:
            logging.info("Shutdown requested by user...")
        except curses.error as e:
            logging.error(f"Terminal UI error: {e}")
            return 1
        finally:
            # Stop all services
            process_manager.stop_all()
        
        logging.info("Application shutdown complete")
        return 0
        
    except Exception as e:
        logging.error(f"Unhandled error: {e}")
        return 1

if __name__ == "__main__":
    sys.exit(main())
