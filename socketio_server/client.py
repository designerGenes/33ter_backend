#!/usr/bin/env python3
"""33ter Socket.IO Client

This module implements the Socket.IO client that connects to the 33ter server and manages
screenshot processing and OCR text transmission. It handles connection management,
screenshot triggers, and client status updates.

Key Features:
- Automatic server connection and reconnection
- Screenshot capture management
- OCR result transmission
- Client count monitoring
- Health check response handling

#TODO:
- Add connection retry with exponential backoff
- Implement proper error recovery for failed transmissions
- Add local caching of OCR results
- Consider adding compression for large text transmissions
- Add proper connection state management
- Implement proper SSL/TLS certificate validation
"""
import os
import sys
import logging
import argparse
import socketio
from datetime import datetime
# Ensure utils and core components are importable
try:
    from utils.config_loader import config as config_manager # Use ConfigManager
    from utils.path_config import get_logs_dir # Use path_config
    # Assuming ScreenshotManager now uses OCRProcessor internally or OCRProcessor is separate
    from core.ocr_processor import OCRProcessor
    from utils.message_utils import MessageType # Import MessageType
    from utils.event_utils import EventType # Import EventType
except ImportError as e:
    print(f"Error importing modules in client.py: {e}", file=sys.stderr)
    # Add more detailed error logging if possible
    sys.exit(1)


def setup_logging(self):
        """Configure logging for the client."""
        # Create a logger for this client
        self.logging = logging.getLogger(f"client.{self.client_id}")
        self.logging.setLevel(logging.INFO)
        
        # Create a file handler
        log_dir = os.path.join(os.getcwd(), "logs")
        os.makedirs(log_dir, exist_ok=True)
        log_file = os.path.join(log_dir, f"client_{self.client_id}.log")
        file_handler = logging.FileHandler(log_file)
        
        # Set formatter
        formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )
        file_handler.setFormatter(formatter)
        
        # Add handlers to logger
        self.logging.handlers = []  # Remove any existing handlers
        self.logging.addHandler(file_handler)  # Only add file handler, no stream handler

class ScreenshotClient:
    def __init__(self):
        # Load configuration using ConfigManager
        self.config = config_manager.config # Get config dict
        log_level = config_manager.get('server', 'log_level', default='INFO')
        self.logger = setup_logging(log_level)

        # Initialize Socket.IO client with reduced logging
        self.sio = socketio.Client(logger=False, engineio_logger=False)
        self.register_handlers()

        # Initialize OCR Processor (used for processing)
        self.ocr_processor = OCRProcessor()
        # ScreenshotManager might not be needed directly if OCRProcessor handles capture,
        # or if capture is triggered differently. Adjust based on actual implementation.
        # self.screenshot_manager = ScreenshotManager() # Remove if OCRProcessor handles capture

    # --- Socket.IO Event Handlers ---

    def register_handlers(self):
        """Register Socket.IO event handlers."""
        # Use instance method decorators
        self.sio.on('connect', self.on_connect)
        self.sio.on('disconnect', self.on_disconnect)
        self.sio.on('message', self.on_message)
        # Add specific handler for PERFORM_OCR_REQUEST
        self.sio.on(MessageType.PERFORM_OCR_REQUEST.value, self.on_perform_ocr_request)

    # @self.sio.event # Decorator applied via sio.on in register_handlers
    def on_connect(self):
        """Handle connection to the server."""
        self.logger.info(f"Successfully connected to server with SID: {self.sio.sid}")
        self.is_connected = True
        # Register as the internal client upon connection
        self.register_as_internal_client()

    # @self.sio.event # Decorator applied via sio.on in register_handlers
    def on_disconnect(self):
        """Handle disconnection from the server."""
        self.logger.warning("Disconnected from server.")
        self.is_connected = False

    # @self.sio.event # Decorator applied via sio.on in register_handlers
    def on_message(self, data):
        """Handle generic messages received from the server."""
        self.logger.info(f"Received message: {data}")
        # Add specific message handling if needed

    # Handler for PERFORM_OCR_REQUEST message type
    # No decorator needed as it's registered via sio.on
    def on_perform_ocr_request(self, data):
        """Handle request from server to perform OCR."""
        requester_sid = data.get('requester_sid')
        self.logger.info(f"Received OCR request from server for iOS client: {requester_sid}")

        # Trigger the OCR process
        ocr_text = self.perform_ocr()

        # Send the result back to the server
        if ocr_text is not None:
            self.send_ocr_result(requester_sid, ocr_text)
        else:
            # Handle OCR failure (e.g., send an error message)
            self.logger.error("OCR process failed, not sending result.")
            # Optionally send an error message back to the server
            error_payload = {
                "requester_sid": requester_sid,
                "error": "OCR process failed on internal client."
            }
            # Define an appropriate error message type if needed, or use generic message
            # self.sio.emit('ocr_error', error_payload)

    # --- Internal Client Actions ---

    def register_as_internal_client(self):
        """Register this client as an internal client on the server."""
        self.sio.emit('register_internal_client', {}) # Identify self to server

    def connect_to_server(self):
        """Connect to the Socket.IO server."""
        host = config_manager.get('server', 'host', default='localhost')
        port = config_manager.get('server', 'port', default=5348)
        server_url = f"http://{host}:{port}"
        #self.logger.info(f"Attempting to connect to server at {server_url}")
        try:
            # Set user agent to identify as Python client
            headers = {
                'User-Agent': 'Python/33ter-Client'
            }
            # Add auth dictionary if needed by server
            auth = {'client_type': 'Internal'}
            self.sio.connect(server_url, headers=headers, auth=auth, transports=['websocket']) # Prefer websocket
            return True
        except socketio.exceptions.ConnectionError as e:
            #self.logger.error(f"Failed to connect to server: {e}")
            return False
        except Exception as e:
            #self.logger.error(f"An unexpected error occurred during connection: {e}", exc_info=True)
            return False

    # Modified to accept requester_sid and send result/error back to server
    def process_latest_screenshot(self, requester_sid: str):
        """Process the latest screenshot and send results or errors back to the server."""
        #self.logger.info(f"Processing latest screenshot for requester: {requester_sid}")
        try:
            # Use OCRProcessor instance to get the text
            result = self.ocr_processor.process_latest_screenshot()

            if result:
                #self.logger.info(f"OCR successful. Sending result back to server for {requester_sid}.")
                payload = {
                    'requester_sid': requester_sid,
                    'text': result
                }
                self.sio.emit(MessageType.OCR_RESULT.value, payload)
            else:
                error_msg = "OCR processing returned no text."
                self.logger.warning(f"{error_msg} Sending error back to server for {requester_sid}.")
                payload = {
                    'requester_sid': requester_sid,
                    'error': error_msg
                }
                self.sio.emit(MessageType.OCR_ERROR.value, payload)

        except Exception as e:
            error_msg = f"Error during OCR processing: {str(e)}"
            #self.logger.error(error_msg, exc_info=True)
            # Send error back to server
            payload = {
                'requester_sid': requester_sid,
                'error': error_msg
            }
            try:
                self.sio.emit(MessageType.OCR_ERROR.value, payload)
            except Exception as emit_e:
                 #self.logger.error(f"Failed to emit OCR error back to server: {emit_e}")
                 pass


    def disconnect(self):
        """Disconnect from the Socket.IO server."""
        if self.sio and self.sio.connected:
            #self.logger.info("Disconnecting from server...")
            # self.screenshot_manager.stop_capturing() # Remove if not used
            self.sio.disconnect()
            #self.logger.info("Disconnected.")
        else:
            pass
            #self.logger.info("Already disconnected or client not initialized.")

def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description='33ter Screenshot Client')
    parser.add_argument('--debug', action='store_true', help='Enable debug logging')
    args = parser.parse_args()
    client = None # Initialize client to None
    try:
        client = ScreenshotClient()
        if args.debug:
            client.logger.setLevel(logging.DEBUG)

        if not client.connect_to_server():
            return 1 # Exit if connection fails

        # Keep the main thread running, listening for events/messages
        try:
            # sio.wait() is blocking and suitable for client scripts
            client.sio.wait()
        except KeyboardInterrupt:
            client.logger.info("Shutdown requested by user")
        except Exception as loop_e:
             client.logger.error(f"Error during client wait loop: {loop_e}", exc_info=True)

    except Exception as e:
        # Use logger if available, otherwise print
        if client and client.logger:
            client.logger.critical(f"Client failed to start or run: {e}", exc_info=True)
        else:
            print(f"Critical Error: {e}", file=sys.stderr)
            import traceback
            traceback.print_exc(file=sys.stderr)
        return 1
    finally:
        # Ensure disconnect is called
        if client:
            client.disconnect()
        print("Client shutdown complete.") # Use print as logger might be closed

    return 0

if __name__ == '__main__':
    sys.exit(main())