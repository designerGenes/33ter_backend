#!/usr/bin/env python3
"""Threethreeter Socket.IO Client

This module implements the Socket.IO client that connects to the Threethreeter server and manages
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
    from .config_loader import config as config_manager # Use ConfigManager
    # Assuming ScreenshotManager now uses OCRProcessor internally or OCRProcessor is separate
    from .ocr_processor import OCRProcessor
    from .message_utils import MessageType # Import MessageType
    from .event_utils import EventType # Import EventType
except ImportError as e:
    print(f"Error importing modules in client.py: {e}", file=sys.stderr)
    # Add more detailed error logging if possible
    sys.exit(1)


def setup_logging(log_level: str = "INFO") -> logging.Logger:
    """Configure logging for the client."""
    # Create a logger for this client
    logger = logging.getLogger("Threethreeter.client")
    logger.setLevel(getattr(logging, log_level.upper(), logging.INFO))
    
    # Create a file handler
    log_dir = os.path.join(os.getcwd(), "logs")
    os.makedirs(log_dir, exist_ok=True)
    log_file = os.path.join(log_dir, "client.log")
    file_handler = logging.FileHandler(log_file)
    
    # Set formatter
    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    file_handler.setFormatter(formatter)
    
    # Add handlers to logger
    logger.handlers = []  # Remove any existing handlers
    logger.addHandler(file_handler)  # Only add file handler, no stream handler
    
    return logger

class ScreenshotClient:
    def __init__(self):
        # Load configuration using ConfigManager
        self.config = config_manager.config # Get config dict
        log_level = config_manager.get('server', 'log_level', default='INFO')
        self.logger = setup_logging(log_level)

        # Initialize Socket.IO client with reduced logging
        self.sio = socketio.Client(logger=False, engineio_logger=False)
        self.setup_handlers()

        # Initialize OCR Processor (used for processing)
        self.ocr_processor = OCRProcessor()
        # ScreenshotManager might not be needed directly if OCRProcessor handles capture,
        # or if capture is triggered differently. Adjust based on actual implementation.
        # self.screenshot_manager = ScreenshotManager() # Remove if OCRProcessor handles capture

    def setup_handlers(self):
        """Set up Socket.IO event handlers."""
        @self.sio.event
        def connect():
            #self.logger.info("Connected to Socket.IO server")
            # No longer automatically joins room here, server handles via registration
            # No longer starts capture here, assuming capture runs independently or is triggered
            # Emit registration event instead
            #self.logger.info("Registering as internal client...")
            self.sio.emit('register_internal_client', {}) # Identify self to server

        @self.sio.event
        def disconnect():
            #self.logger.info("Disconnected from Socket.IO server")
            # Stop any ongoing processes if necessary
            self.screenshot_manager.stop_capturing()

        @self.sio.event
        def connect_error(data):
            self.logger.error(f"Connection failed: {data}")
            pass

        # --- Message Handlers ---

        # Handle request from server to perform OCR
        @self.sio.on(MessageType.PERFORM_OCR_REQUEST.value)
        def on_perform_ocr_request(data):
            requester_sid = data.get('requester_sid')
            if not requester_sid:
                self.logger.error(f"Received '{MessageType.PERFORM_OCR_REQUEST.value}' without requester_sid.")
                return
            #self.logger.info(f"Received OCR request from server for requester: {requester_sid}")
            # Call processing function, passing the requester_sid
            self.process_latest_screenshot(requester_sid=requester_sid)

        # Handle generic messages (e.g., INFO, WARNING from server)
        @self.sio.on('message')
        def on_message(data):
            msg_type = data.get('messageType')
            msg_value = data.get('value')
            msg_from = data.get('from')
            #self.logger.info(f"Received message from {msg_from}: Type={msg_type}, Value='{str(msg_value)[:100]}...'")
            # Add specific handling if needed (e.g., for CLIENT_COUNT message)
            if msg_type == MessageType.CLIENT_COUNT.value:
                 count = msg_value.get('count', '?')
                 #self.logger.info(f"Current iOS client count from server: {count}")


        # --- Event Handlers (for logging/awareness) ---
        # Use @self.sio.event for built-in events, @self.sio.on for custom ones

        @self.sio.on(EventType.SERVER_STARTED.value)
        def on_server_started(data):
            self.logger.info("Received event: Server Started")

        @self.sio.on(EventType.CLIENT_CONNECTED.value)
        def on_client_connected(data):
            self.logger.info(f"Received event: Client Connected - SID: {data.get('sid')}, Type: {data.get('client_type')}")

        @self.sio.on(EventType.CLIENT_DISCONNECTED.value)
        def on_client_disconnected(data):
            self.logger.info(f"Received event: Client Disconnected - SID: {data.get('sid')}")

        @self.sio.on(EventType.CLIENT_JOINED_ROOM.value)
        def on_client_joined(data):
            self.logger.info(f"Received event: Client Joined Room - SID: {data.get('sid')}, Room: {data.get('room')}")

        @self.sio.on(EventType.CLIENT_LEFT_ROOM.value)
        def on_client_left(data):
            self.logger.info(f"Received event: Client Left Room - SID: {data.get('sid')}, Room: {data.get('room')}")

        @self.sio.on(EventType.UPDATED_CLIENT_COUNT.value)
        def on_client_count_event(data):
             # Log the event payload directly
             self.logger.info(f"Received event: Updated Client Count - Payload: {data}")

        @self.sio.on(EventType.OCR_PROCESSING_STARTED.value)
        def on_ocr_started(data):
            self.logger.info(f"Received event: OCR Processing Started - Requester: {data.get('requester_sid')}")

        @self.sio.on(EventType.OCR_PROCESSING_COMPLETED.value)
        def on_ocr_completed(data):
            status = "Success" if data.get('success') else f"Failed ({data.get('error', 'Unknown')})"
            self.logger.info(f"Received event: OCR Processing Completed - Requester: {data.get('requester_sid')}, Status: {status}")

        @self.sio.on(EventType.PROCESSED_SCREENSHOT.value)
        def on_screenshot_processed(data):
             status = "Success" if data.get('success') else f"Failed ({data.get('error', 'Unknown')})"
             preview = data.get('text_preview', '')
             #self.logger.info(f"Received event: Processed Screenshot - Status: {status}, Preview: '{preview}'")

        # Catch-all for unhandled events (optional)
        @self.sio.on('*')
        def catch_all(event, data):
            # Avoid logging standard connect/disconnect/message here as they have specific handlers
            if event not in ['connect', 'disconnect', 'message',
                             MessageType.PERFORM_OCR_REQUEST.value, # Handled above
                             EventType.SERVER_STARTED.value, EventType.CLIENT_CONNECTED.value, # etc...
                             EventType.CLIENT_DISCONNECTED.value, EventType.CLIENT_JOINED_ROOM.value,
                             EventType.CLIENT_LEFT_ROOM.value, EventType.UPDATED_CLIENT_COUNT.value,
                             EventType.OCR_PROCESSING_STARTED.value, EventType.OCR_PROCESSING_COMPLETED.value,
                             EventType.PROCESSED_SCREENSHOT.value]:
                 self.logger.debug(f"Received unhandled event '{event}': {str(data)[:200]}")


    def register_as_internal_client(self):
        """Register this client as an internal client on the server."""
        self.sio.emit('register_internal_client', {}) # Identify self to server

    def connect_to_server(self):
        """Connect to the Socket.IO server."""
        host = config_manager.get('server', 'host', default='localhost')
        port = config_manager.get('server', 'port', default=5348)
        server_url = f"http://{host}:{port}"
        self.logger.info(f"Attempting to connect to server at {server_url}")
        try:
            # Set user agent to identify as Python client
            headers = {
                'User-Agent': 'Python/Threethreeter-Client'
            }
            # Add auth dictionary if needed by server
            auth = {'client_type': 'Internal'}
            self.sio.connect(server_url, headers=headers, auth=auth, transports=['websocket']) # Prefer websocket
            return True
        except socketio.exceptions.ConnectionError as e:
            self.logger.error(f"Failed to connect to server: {e}")
            return False
        except Exception as e:
            self.logger.error(f"An unexpected error occurred during connection: {e}", exc_info=True)
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
            self.logger.info("Disconnecting from server...")
            # self.screenshot_manager.stop_capturing() # Remove if not used
            self.sio.disconnect()
            self.logger.info("Disconnected.")
        else:
            self.logger.info("Already disconnected or client not initialized.")

def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description='Threethreeter Screenshot Client')
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