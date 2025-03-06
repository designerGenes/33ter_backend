#!/usr/bin/env python3
"""
33ter Process Manager Entry Point
Launches and manages the screenshot capture, OCR processing, and Socket.IO communication
components of the 33ter application.
"""
import curses
import os
import sys
import argparse
import logging
from typing import Optional

try:
    from app.utils.system_check import print_system_status
    from app.utils.path_config import get_logs_dir
    from app.utils.config_loader import config
    from app.core.process_manager import ProcessManager
    from app.core.terminal_ui import TerminalUI
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
