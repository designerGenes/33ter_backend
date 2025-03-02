#!/usr/bin/env python3
"""
33ter Socket.IO Client
Handles communication between the Python screenshot/OCR service and the iOS app.
"""
import os
import sys
import logging
import argparse
import socketio
from datetime import datetime
from utils import get_server_config, get_logs_dir
from core.screenshot_manager import ScreenshotManager

def setup_logging(log_level: str = "INFO"):
    """Configure logging with the specified level."""
    log_file = os.path.join(get_logs_dir(), "socketio_client.log")
    
    logging.basicConfig(
        level=getattr(logging, log_level.upper()),
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_file),
            logging.StreamHandler()
        ]
    )
    return logging.getLogger('33ter-Client')

class ScreenshotClient:
    def __init__(self):
        # Load configuration
        self.config = get_server_config()
        self.logger = setup_logging(self.config['server']['log_level'])
        
        # Initialize Socket.IO client with reduced logging
        self.sio = socketio.Client(logger=False, engineio_logger=False)
        self.setup_handlers()
        
        # Initialize screenshot manager
        self.screenshot_manager = ScreenshotManager()
    
    def setup_handlers(self):
        """Set up Socket.IO event handlers."""
        @self.sio.event
        def connect():
            self.logger.info("Connected to Socket.IO server")
            # Join the configured room
            self.sio.emit('join_room', {'room': self.config['server']['room']})
            # Start screenshot capture once connected
            self.screenshot_manager.start_capturing()
        
        @self.sio.event
        def disconnect():
            self.logger.info("Disconnected from Socket.IO server")
            # Stop screenshot capture on disconnect
            self.screenshot_manager.stop_capturing()
        
        @self.sio.on('trigger_ocr')
        def on_trigger_ocr(data):
            self.logger.info("OCR trigger received from iOS client")
            self.process_latest_screenshot()
            
        @self.sio.on('client_count')
        def on_client_count(data):
            count = data.get('count', 0)
            self.logger.info(f"iOS clients connected: {count}")
    
    def connect_to_server(self):
        """Connect to the Socket.IO server."""
        server_url = f"http://{self.config['server']['host']}:{self.config['server']['port']}"
        try:
            # Set user agent to identify as Python client
            headers = {
                'User-Agent': 'Python/33ter-Client'
            }
            self.sio.connect(server_url, headers=headers)
            return True
        except Exception as e:
            self.logger.error(f"Failed to connect to server: {e}")
            return False
    
    def process_latest_screenshot(self):
        """Process the latest screenshot and send results."""
        result = self.screenshot_manager.process_latest_screenshot()
        if result:
            try:
                # Send result in standardized format
                self.sio.emit('ocr_result', [{
                    'text': result,
                    'timestamp': datetime.now().isoformat()
                }])
                self.logger.info("OCR result sent successfully")
            except Exception as e:
                self.logger.error(f"Failed to send OCR result: {e}")
    
    def disconnect(self):
        """Disconnect from the Socket.IO server."""
        if self.sio.connected:
            self.screenshot_manager.stop_capturing()
            self.sio.disconnect()

def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description='33ter Screenshot Client')
    parser.add_argument('--debug', action='store_true', help='Enable debug logging')
    args = parser.parse_args()
    
    try:
        client = ScreenshotClient()
        if args.debug:
            client.logger.setLevel(logging.DEBUG)
        
        if not client.connect_to_server():
            return 1
            
        # Keep the main thread running
        try:
            while True:
                import time
                time.sleep(0.1)  # Brief sleep to prevent high CPU usage
        except KeyboardInterrupt:
            client.logger.info("Shutdown requested by user")
        
    except Exception as e:
        print(f"Error: {e}")
        return 1
    finally:
        if hasattr(client, 'sio'):
            client.disconnect()
    
    return 0

if __name__ == '__main__':
    sys.exit(main())