"""Process management module for 33ter application."""
import os
import sys
import time
import json
import logging
import subprocess
import threading
import traceback
from collections import deque
from typing import Dict, Optional, List, Union, IO, Tuple, Any
from datetime import datetime
import socketio
import asyncio

from pathlib import Path

# Add MessageType import
from utils.message_utils import MessageType

try:
    from utils.path_config import get_logs_dir, get_screenshots_dir, get_temp_dir, get_project_root
    from utils.server_config import get_server_config, DEFAULT_CONFIG as SERVER_DEFAULT_CONFIG
    from utils.config_loader import config as config_manager
    from core.screenshot_manager import ScreenshotManager
    from core.message_system import MessageManager, MessageLevel, MessageCategory
except ImportError as e:
    print(f"Error importing required modules in process_manager.py: {e}", file=sys.stderr)
    traceback.print_exc(file=sys.stderr)
    sys.exit(1)

import glob

SOCKETIO_SERVER_SCRIPT = os.path.join(get_project_root(), "socketio_server", "server.py")
STARTUP_TIMEOUT = 10  # seconds to wait for server startup message

class ProcessManager:
    """Manages the lifecycle of core 33ter processes."""

    def __init__(self):
        self.logger = logging.getLogger('33ter-ProcessManager')
        self.config = get_server_config()
        self.message_manager = MessageManager()  # Initialize MessageManager first

        self.socketio_process: Optional[subprocess.Popen] = None
        self.socketio_monitor_thread: Optional[threading.Thread] = None
        self.socketio_stop_event = threading.Event()

        # Internal Socket.IO client for ProcessManager communication
        self.internal_sio_client: Optional[socketio.Client] = None
        self.internal_sio_connect_thread: Optional[threading.Thread] = None
        self.internal_sio_connected = threading.Event()  # Event to signal connection status

        # Screenshot Manager - Pass the initialized message_manager
        self.screenshot_manager = ScreenshotManager(self.message_manager)
        self.screenshot_thread: Optional[threading.Thread] = None
        self.screenshot_stop_event = threading.Event()

        self.logger.info("ProcessManager initialized.")

    def _add_to_buffer(self, buffer_name: str, content: str, level: str = "info"):
        """Helper to add messages to the MessageManager."""
        msg_level = getattr(MessageLevel, level.upper(), MessageLevel.INFO)
        category = MessageCategory.SYSTEM  # Default category
        if buffer_name == "screenshot":
            category = MessageCategory.SCREENSHOT
        elif buffer_name == "debug":
            category = MessageCategory.SOCKET  # FIX: Changed SOCKETIO to SOCKET

        self.message_manager.add_message(
            content=content,
            level=msg_level,
            category=category,
            source="process_manager",
            buffer_name=buffer_name
        )

    def get_output(self, buffer_name: str) -> List[str]:
        """Get formatted output from a specific buffer."""
        # FIX: Changed get_formatted_buffer to get_formatted_messages
        # The default format 'legacy' should work for the current UI views.
        return self.message_manager.get_formatted_messages(buffer_name, format_type="legacy")

    def get_status(self) -> Dict[str, Any]:
        """Get the current status of managed processes."""
        try:
            socketio_status = "Stopped"
            if self.socketio_process and self.socketio_process.poll() is None:
                socketio_status = "Running"
            elif self.socketio_process:
                socketio_status = f"Stopped (Code: {self.socketio_process.poll()})"

            screenshot_status = "Stopped"
            if self.screenshot_thread and self.screenshot_thread.is_alive():
                # Use the ScreenshotManager's internal state for more detail
                # Ensure screenshot_manager has get_status method
                if hasattr(self.screenshot_manager, 'get_status'):
                    screenshot_status = self.screenshot_manager.get_status()
                else:
                    # Fallback if get_status is missing (shouldn't happen now)
                    screenshot_status = "Running (Thread Alive)"

            status_dict = {
                "socketio_server": socketio_status,
                "screenshot_capture": screenshot_status,
                "internal_sio_connected": self.internal_sio_connected.is_set(),
                "config": self.config  # Include current config for status view
            }
            # Add logging before returning
            self.logger.debug(f"Returning status: {status_dict}")
            return status_dict

        except Exception as e:
            self.logger.error(f"Error getting process status: {e}", exc_info=True)
            # Return a default error status dictionary
            return {
                "socketio_server": "Error",
                "screenshot_capture": "Error",
                "internal_sio_connected": False,
                "config": self.config,  # Still return config if possible
                "error": str(e)
            }

    def start_socketio_server(self):
        """Start the Socket.IO server process."""
        if self.socketio_process and self.socketio_process.poll() is None:
            self.logger.warning("Socket.IO server already running.")
            self._add_to_buffer("status", "Socket.IO server already running.", "warning")
            return

        server_script = os.path.join(get_project_root(), 'socketio_server', 'server.py')
        if not os.path.exists(server_script):
            self.logger.error(f"Socket.IO server script not found: {server_script}")
            self._add_to_buffer("status", f"ERROR: Server script not found at {server_script}", "error")
            return

        # Get config values safely
        server_cfg = self.config.get('server', {})
        host = server_cfg.get('host', '0.0.0.0')
        port = server_cfg.get('port', 5348)

        # Prepare environment
        env = os.environ.copy()
        env['PYTHONPATH'] = get_project_root()

        command = [
            sys.executable,
            '-u',  # Unbuffered output
            server_script,
            '--host', host,
            '--port', str(port)
        ]

        self.logger.info(f"Starting Socket.IO server: {' '.join(command)}")
        self._add_to_buffer("status", f"Starting Socket.IO server on {host}:{port}...", "info")

        try:
            self.socketio_process = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,  # Line buffered
                env=env
            )

            self.socketio_stop_event.clear()
            self.socketio_monitor_thread = threading.Thread(
                target=self._monitor_socketio_process,
                daemon=True
            )
            self.socketio_monitor_thread.start()
            self.logger.info(f"Socket.IO server process started (PID: {self.socketio_process.pid}). Monitor thread active.")
            self._add_to_buffer("status", f"Socket.IO server process started (PID: {self.socketio_process.pid}).", "info")

        except Exception as e:
            self.logger.error(f"Failed to start Socket.IO server: {e}", exc_info=True)
            self._add_to_buffer("status", f"ERROR: Failed to start Socket.IO server: {e}", "error")
            self.socketio_process = None

    def _monitor_socketio_process(self):
        """Monitor the stdout/stderr of the Socket.IO server process."""
        if not self.socketio_process or not self.socketio_process.stdout or not self.socketio_process.stderr:
            self.logger.error("Socket.IO process or pipes not available for monitoring.")
            return

        self.logger.info("Socket.IO monitor thread started (Using simplified read loop for debug).")

        # --- Simplified STDOUT Reading Loop (for debugging) ---
        def read_stdout():
            if not self.socketio_process or not self.socketio_process.stdout:
                return
            try:
                for line in iter(self.socketio_process.stdout.readline, ''): # Blocking read line by line
                    line = line.strip()
                    if line:
                        self.logger.info(f"MONITOR_SIMPLE_READ [STDOUT]: {line}") # Use INFO for visibility
                        self._add_to_buffer("debug", f"SERVER_STDOUT: {line}", "info")
                    if self.socketio_stop_event.is_set():
                        break
            except Exception as e:
                 self.logger.error(f"Error in simplified stdout read loop: {e}", exc_info=True)
            finally:
                 self.logger.info("Simplified stdout read loop finished.")

        stdout_thread = threading.Thread(target=read_stdout, daemon=True)
        stdout_thread.start()
        # --- End Simplified STDOUT Reading Loop ---

        # --- Keep monitoring STDERR (using select or simplified) ---
        # For now, let's keep stderr monitoring simple too
        def read_stderr():
            if not self.socketio_process or not self.socketio_process.stderr:
                return
            try:
                for line in iter(self.socketio_process.stderr.readline, ''): # Blocking read line by line
                    line = line.strip()
                    if line:
                        self.logger.error(f"MONITOR_SIMPLE_READ [STDERR]: {line}") # Use ERROR for visibility
                        self._add_to_buffer("debug", f"SERVER_STDERR: {line}", "error")
                    if self.socketio_stop_event.is_set():
                        break
            except Exception as e:
                 self.logger.error(f"Error in simplified stderr read loop: {e}", exc_info=True)
            finally:
                 self.logger.info("Simplified stderr read loop finished.")

        stderr_thread = threading.Thread(target=read_stderr, daemon=True)
        stderr_thread.start()
        # --- End Simplified STDERR Reading Loop ---

        # Keep the main monitor thread alive to check for process termination and wait for stop event
        while not self.socketio_stop_event.is_set():
            if self.socketio_process and self.socketio_process.poll() is not None:
                self.logger.warning(f"Socket.IO server process terminated unexpectedly with code {self.socketio_process.poll()}.")
                self._add_to_buffer("status", f"WARNING: Socket.IO server stopped unexpectedly (Code: {self.socketio_process.poll()}).", "warning")
                self._add_to_buffer("debug", f"SERVER_EXIT: Process terminated with code {self.socketio_process.poll()}", "warning")
                if self.internal_sio_connected.is_set():
                    self.logger.info("Marking internal client as disconnected due to server process termination.")
                    self.internal_sio_connected.clear()
                break
            time.sleep(0.5) # Main loop sleep

        # Wait for reader threads to finish (they should exit when stop_event is set or process ends)
        self.logger.info("Waiting for stdout/stderr reader threads to join...")
        stdout_thread.join(timeout=1.0)
        stderr_thread.join(timeout=1.0)
        self.logger.info("Reader threads joined (or timed out).")

        exit_code = self.socketio_process.poll()
        if exit_code is not None:
            self.logger.info(f"Socket.IO process final exit code: {exit_code}")
            self._add_to_buffer("debug", f"SERVER_FINAL_EXIT: Code {exit_code}", "warning" if exit_code != 0 else "info")
            if self.internal_sio_connected.is_set():
                self.logger.info("Marking internal client disconnected as server process exited.")
                self.internal_sio_connected.clear()

    def stop_socketio_server(self):
        """Stop the Socket.IO server process."""
        self.logger.info("Stopping Socket.IO server...")
        self._add_to_buffer("status", "Stopping Socket.IO server...", "info")

        # Disconnect internal client first
        self._disconnect_internal_client()

        if self.socketio_monitor_thread:
            self.socketio_stop_event.set()  # Signal monitor thread to stop

        if self.socketio_process and self.socketio_process.poll() is None:
            try:
                self.socketio_process.terminate()  # Send SIGTERM
                try:
                    self.socketio_process.wait(timeout=5)  # Wait up to 5 seconds
                    self.logger.info("Socket.IO server process terminated gracefully.")
                    self._add_to_buffer("status", "Socket.IO server stopped.", "info")
                except subprocess.TimeoutExpired:
                    self.logger.warning("Socket.IO server did not terminate gracefully, sending SIGKILL.")
                    self.socketio_process.kill()  # Force kill
                    self.socketio_process.wait()  # Wait for kill
                    self.logger.info("Socket.IO server process killed.")
                    self._add_to_buffer("status", "Socket.IO server force-stopped.", "warning")
            except Exception as e:
                self.logger.error(f"Error stopping Socket.IO server: {e}", exc_info=True)
                self._add_to_buffer("status", f"ERROR: Failed to stop Socket.IO server: {e}", "error")
        else:
            self.logger.info("Socket.IO server process already stopped or not running.")
            self._add_to_buffer("status", "Socket.IO server already stopped.", "info")

        # Wait for monitor thread to finish
        if self.socketio_monitor_thread and self.socketio_monitor_thread.is_alive():
            self.logger.debug("Waiting for Socket.IO monitor thread to join...")
            self.socketio_monitor_thread.join(timeout=2)
            if self.socketio_monitor_thread.is_alive():
                self.logger.warning("Socket.IO monitor thread did not join cleanly.")
            else:
                self.logger.debug("Socket.IO monitor thread joined.")

        self.socketio_process = None
        self.socketio_monitor_thread = None
        self.logger.info("Socket.IO server stop sequence complete.")

    # --- Internal Socket.IO Client Methods ---

    def _setup_internal_client(self):
        """Initializes the internal Socket.IO client and its handlers."""
        if self.internal_sio_client:
            self.logger.debug("Internal client already exists.")
            return

        self.logger.info("Setting up internal Socket.IO client...")
        # Disable verbose library logging for the internal client
        # ProcessManager logs essential events to the debug buffer anyway.
        self.internal_sio_client = socketio.Client(logger=False, engineio_logger=False)

        @self.internal_sio_client.event
        def connect():
            self.logger.info("***** INTERNAL CLIENT CONNECTED *****")
            self.internal_sio_connected.set()
            self._add_to_buffer("debug", "INTERNAL_CLIENT: Connected successfully", "info")
            try:
                room = self.config.get('server', {}).get('room', '33ter_room')
                self.logger.info(f"Internal client joining room: {room}")
                # Emit register_internal_client instead of just join_room
                self.internal_sio_client.emit('register_internal_client', {})
                self.logger.info("Internal client registration emitted.")
                # Server side handles joining the room upon registration
                self._add_to_buffer("debug", f"INTERNAL_CLIENT: Registration sent (joins room '{room}' on server)", "info")
            except Exception as e:
                self.logger.error(f"Internal client failed during post-connection setup: {e}", exc_info=True)
                self._add_to_buffer("debug", f"INTERNAL_CLIENT_ERROR: Failed post-connection setup: {e}", "error")

        @self.internal_sio_client.event
        def connect_error(data):
            self.logger.error(f"***** INTERNAL CLIENT CONNECTION ERROR ***** Data: {data}")
            self.internal_sio_connected.clear()
            self._add_to_buffer("debug", f"INTERNAL_CLIENT_ERROR: Connection failed: {data}", "error")

        @self.internal_sio_client.event
        def disconnect():
            was_connected = self.internal_sio_connected.is_set()
            self.logger.warning(f"***** INTERNAL CLIENT DISCONNECTED ***** (Was previously connected: {was_connected})")
            self.internal_sio_connected.clear()
            if was_connected:
                self._add_to_buffer("debug", "INTERNAL_CLIENT: Disconnected (previously connected)", "warning")
            else:
                self._add_to_buffer("debug", "INTERNAL_CLIENT: Disconnected (never fully connected?)", "error")

        @self.internal_sio_client.on('*')
        def any_event(event, data):
            # Reduce noise by ignoring lower-level engineio events if library logging is on
            # Since logger/engineio_logger are False, this handler might not receive ping/pong,
            # but we keep the check just in case.
            if event not in ['ping', 'pong']:
                # Log non-ping/pong events received by the internal client to the debug buffer
                self.logger.debug(f"Internal client received event '{event}': {data}")
                self._add_to_buffer("debug", f"INTERNAL_CLIENT_RECV: Event='{event}', Data='{str(data)[:100]}...'", "info")

        # Add handler for PERFORM_OCR_REQUEST from the server
        @self.internal_sio_client.on(MessageType.PERFORM_OCR_REQUEST.value)
        def on_perform_ocr_request(data):
            self.logger.info(f"Internal client received '{MessageType.PERFORM_OCR_REQUEST.value}' request: {data}")
            self._add_to_buffer("debug", f"INTERNAL_CLIENT_RECV: Received OCR request: {data}", "info")
            requester_sid = data.get('requester_sid')
            if requester_sid:
                self.logger.info(f"Processing OCR request for original requester: {requester_sid}")
                # Call the processing function, passing the requester_sid
                self.process_and_send_ocr_result(requester_sid=requester_sid)
            else:
                self.logger.warning("Received OCR request without 'requester_sid'. Cannot process.")
                self._add_to_buffer("debug", "INTERNAL_CLIENT_WARN: OCR request missing requester_sid", "warning")

        self.logger.info("Internal client setup complete.")

    def _connect_internal_client_thread_target(self):
        """Target function for the internal client connection thread."""
        if not self.internal_sio_client:
            self.logger.error("Internal client not set up, cannot connect.")
            return

        try:
            # Add a small delay before attempting connection
            time.sleep(0.75)  # Increased delay slightly
            server_cfg = get_server_config().get('server', {})
            host = server_cfg.get('host', '0.0.0.0')
            connect_host = '127.0.0.1' if host == '0.0.0.0' else host
            port = server_cfg.get('port', 5348)
            server_url = f"http://{connect_host}:{port}"
            self.logger.info(f"Internal client attempting connection to {server_url}...")
            self._add_to_buffer("debug", f"INTERNAL_CLIENT: Connecting to {server_url}...", "info")

            self.logger.debug(f"Calling internal_sio_client.connect('{server_url}', wait_timeout=10)")
            # Specify transports to potentially avoid issues if websocket upgrade fails silently
            self.internal_sio_client.connect(server_url,
                                             transports=['websocket', 'polling'],  # Explicitly allow both
                                             wait_timeout=10
                                             )
            self.logger.debug("internal_sio_client.connect call finished without immediate exception.")

        except socketio.exceptions.ConnectionError as e:
            self.logger.error(f"Internal client connection error during connect call: {e}")
            self.internal_sio_connected.clear()
            self._add_to_buffer("debug", f"INTERNAL_CLIENT_ERROR: ConnectionError during connect(): {e}", "error")
        except Exception as e:
            self.logger.error(f"Unexpected error during internal client connection attempt: {e}", exc_info=True)
            self.internal_sio_connected.clear()
            self._add_to_buffer("debug", f"INTERNAL_CLIENT_ERROR: Unexpected error during connect(): {e}", "error")
        finally:
            # Check status after attempting connection
            # Note: client might disconnect *after* this thread finishes but before status is checked elsewhere
            if self.internal_sio_client and self.internal_sio_client.connected:
                self.logger.info("Internal client connection thread finished - Client IS connected at thread exit.")
            else:
                self.logger.warning("Internal client connection thread finished - Client IS NOT connected at thread exit.")

    def _start_internal_client_connection(self):
        """Sets up the internal client (if needed) and starts the connection thread."""
        if self.internal_sio_connected.is_set():
            self.logger.info("Internal client already connected.")
            return

        if self.internal_sio_connect_thread and self.internal_sio_connect_thread.is_alive():
            self.logger.warning("Internal client connection attempt already in progress.")
            return

        if not self.internal_sio_client:
            self._setup_internal_client()

        self.logger.info("Starting internal client connection thread.")
        self.internal_sio_connect_thread = threading.Thread(
            target=self._connect_internal_client_thread_target,
            daemon=True
        )
        self.internal_sio_connect_thread.start()

    def _disconnect_internal_client(self):
        """Disconnects the internal Socket.IO client."""
        if self.internal_sio_client and self.internal_sio_client.connected:
            self.logger.info("Disconnecting internal client...")
            try:
                self.internal_sio_client.disconnect()
            except Exception as e:
                self.logger.error(f"Error disconnecting internal client: {e}", exc_info=True)
                self._add_to_buffer("debug", f"INTERNAL_CLIENT_ERROR: Disconnect error: {e}", "error")
        else:
            self.logger.info("Internal client not connected or not initialized.")

        self.internal_sio_connected.clear()

        if self.internal_sio_connect_thread and self.internal_sio_connect_thread.is_alive():
            self.logger.debug("Waiting briefly for internal connection thread to potentially finish...")
            self.internal_sio_connect_thread.join(timeout=0.5)
            if self.internal_sio_connect_thread.is_alive():
                self.logger.warning("Internal connection thread still alive after disconnect request.")

    # --- Screenshot Manager Methods ---

    def start_screenshot_manager(self):
        """Start the screenshot manager thread."""
        if self.screenshot_thread and self.screenshot_thread.is_alive():
            self.logger.warning("Screenshot manager already running.")
            self._add_to_buffer("status", "Screenshot manager already running.", "warning")
            return

        self.logger.info("Starting screenshot manager...")
        self._add_to_buffer("status", "Starting screenshot manager...", "info")
        self.screenshot_stop_event.clear()
        self.screenshot_thread = threading.Thread(
            target=self.screenshot_manager.run,  # Ensure ScreenshotManager has a 'run' method
            args=(self.screenshot_stop_event,),
            daemon=True
        )
        self.screenshot_thread.start()
        self.logger.info("Screenshot manager thread started.")
        self._add_to_buffer("status", "Screenshot manager started.", "info")

    def stop_screenshot_manager(self):
        """Stop the screenshot manager thread."""
        self.logger.info("Stopping screenshot manager...")
        self._add_to_buffer("status", "Stopping screenshot manager...", "info")
        if self.screenshot_thread and self.screenshot_thread.is_alive():
            self.screenshot_stop_event.set()
            self.screenshot_thread.join(timeout=5)
            if self.screenshot_thread.is_alive():
                self.logger.warning("Screenshot manager thread did not stop gracefully.")
                self._add_to_buffer("status", "WARNING: Screenshot manager did not stop gracefully.", "warning")
            else:
                self.logger.info("Screenshot manager stopped.")
                self._add_to_buffer("status", "Screenshot manager stopped.", "info")
        else:
            self.logger.info("Screenshot manager already stopped or not running.")
            self._add_to_buffer("status", "Screenshot manager already stopped.", "info")

        self.screenshot_thread = None
        self.logger.info("Screenshot manager stop sequence complete.")

    # --- Combined Start/Stop ---

    def start_all_services(self):
        """Start all managed services."""
        self.logger.info("Starting all services...")
        self.start_socketio_server()
        # Wait a bit longer for the server process to initialize before attempting client connection
        self.logger.info("Waiting 2 seconds for server to initialize...")
        time.sleep(2.0)
        # Explicitly attempt internal client connection
        self.logger.info("Attempting initial internal client connection...")
        self._start_internal_client_connection()
        # Start screenshot manager (can start regardless of client connection)
        self.start_screenshot_manager()
        self.logger.info("All service start sequences initiated.")

    def stop_all(self):
        """Stop all managed services gracefully."""
        self.logger.info("Stopping all services...")
        self.stop_screenshot_manager()
        self.stop_socketio_server()
        self.logger.info("All services stopped.")

    # --- Communication Methods ---

    def post_message_to_socket(self, value: str, messageType: str = "info") -> bool:
        """Send a message via the internal Socket.IO client."""
        self.logger.debug(f"Attempting to post message via internal client: type={messageType}, value='{value[:50]}...'")
        if self.internal_sio_client and self.internal_sio_connected.is_set() and self.internal_sio_client.connected:
            try:
                payload = {
                    'messageType': messageType,
                    'value': value,
                    'from': 'localBackend'
                }
                self.internal_sio_client.emit('message', payload)
                self.logger.info(f"Message posted successfully via internal client: {payload}")
                self._add_to_buffer("debug", f"SENDING MESSAGE (localBackend): Type={messageType}, Value='{value[:50]}...'", "info")
                return True
            except Exception as e:
                self.logger.error(f"Failed to post message via internal client: {e}", exc_info=True)
                self._add_to_buffer("debug", f"INTERNAL_CLIENT_ERROR: Failed to emit message: {e}", "error")
                self._add_to_buffer("status", f"ERROR: Failed to send message: {e}", "error")
                return False
        else:
            self.logger.warning("Cannot post message: Internal client not connected.")
            self._add_to_buffer("debug", "INTERNAL_CLIENT_WARN: Cannot post message - not connected.", "warning")
            self._add_to_buffer("status", "WARNING: Cannot send message - Socket.IO not connected.", "warning")
            if self.socketio_process and self.socketio_process.poll() is None:
                self.logger.info("Attempting to reconnect internal client as server process is running.")
                self._start_internal_client_connection()
            return False

    def process_and_send_ocr_result(self, requester_sid: Optional[str] = None) -> bool:
        """
        Manually triggers the ScreenshotManager to process the latest screenshot
        and sends the result via the internal Socket.IO client.

        Args:
            requester_sid: The SID of the original client that requested the OCR (optional).
                           If provided, it's included in the result payload.
        """
        trigger_source = "Manual" if requester_sid is None else f"Remote (SID: {requester_sid})"
        self.logger.info(f"{trigger_source} OCR trigger initiated.")
        self._add_to_buffer("debug", f"{trigger_source} OCR trigger initiated.", "info")

        # --- Add detailed check logging ---
        client_exists = self.internal_sio_client is not None
        self._add_to_buffer("debug", f"Internal client exists: {client_exists}", "info")
        event_set = self.internal_sio_connected.is_set()
        client_connected_prop = self.internal_sio_client.connected if client_exists else False
        self.logger.debug(f"OCR Trigger Check: Client Exists={client_exists}, Event Set={event_set}, Client Property Connected={client_connected_prop}")
        # --- End detailed check logging ---

        try:
            ocr_text = self.screenshot_manager.process_latest_screenshot(manual_trigger=(requester_sid is None))
            if ocr_text is None:
                self.logger.warning("Manual OCR processing returned no text or failed.")
                self._add_to_buffer("debug", "Manual OCR processing returned no text or failed.", "warning")
                # Return False here as there's nothing to send
                return False
            elif isinstance(ocr_text, str):
                self.logger.info(f"Manual OCR processing successful: '{ocr_text[:50]}...'")
                self._add_to_buffer("debug", f"Manual OCR successful: '{ocr_text[:50]}...'", "info")
            else:
                self.logger.error(f"Manual OCR processing returned unexpected type: {type(ocr_text)}")
                self._add_to_buffer("debug", f"ERROR: Manual OCR returned unexpected type: {type(ocr_text)}", "error")
                return False

        except Exception as e:
            self.logger.error(f"Error during manual screenshot processing: {e}", exc_info=True)
            self._add_to_buffer("debug", f"ERROR during manual screenshot processing: {e}", "error")
            self._add_to_buffer("status", f"ERROR processing screenshot: {e}", "error")
            return False

        # Check connection status *after* OCR processing is done
        client_exists = self.internal_sio_client is not None
        event_set = self.internal_sio_connected.is_set()
        client_connected_prop = self.internal_sio_client.connected if client_exists else False

        if client_exists and event_set and client_connected_prop:
            try:
                # The server now expects 'ocr_result' event
                payload = {
                    'text': ocr_text,
                    'timestamp': datetime.now().isoformat(),
                    'from': 'localBackend',
                    # Include the original requester SID if available
                    'requester_sid': requester_sid
                }
                # Remove None values from payload before sending
                payload = {k: v for k, v in payload.items() if v is not None}

                self.internal_sio_client.emit(MessageType.OCR_RESULT.value, payload)
                self.logger.info(f"{trigger_source} OCR result sent successfully via internal client.")
                self._add_to_buffer("debug", f"SENDING OCR RESULT ({trigger_source}): '{ocr_text[:50]}...'", "info")
                return True
            except Exception as e:
                self.logger.error(f"Failed to send manual OCR result via internal client: {e}", exc_info=True)
                self._add_to_buffer("debug", f"INTERNAL_CLIENT_ERROR: Failed to emit manual OCR result: {e}", "error")
                self._add_to_buffer("status", f"ERROR sending OCR result: {e}", "error")
                return False
        else:
            # Log the state again when the check fails
            self.logger.warning(f"Cannot send manual OCR result: Internal client not connected. State: Exists={client_exists}, Event Set={event_set}, Client Prop Connected={client_connected_prop}")
            self._add_to_buffer("debug", "INTERNAL_CLIENT_WARN: Cannot send manual OCR - not connected.", "warning")
            self._add_to_buffer("status", "WARNING: Cannot send OCR - Socket.IO not connected.", "warning")
            if self.socketio_process and self.socketio_process.poll() is None:
                self.logger.info("Attempting to reconnect internal client as server process is running.")
                self._start_internal_client_connection()
            return False