"""Process management module for 33ter application."""
import os
import sys
import time
import json
import logging
import subprocess
import socketio
import threading
import traceback
import select
from collections import deque
from typing import Dict, Optional, List, Union, IO, Tuple

from pathlib import Path
from datetime import datetime

# Add app root to Python path if needed
app_root = str(Path(__file__).parent.parent.absolute())
if app_root not in sys.path:
    sys.path.insert(0, app_root)

try:
    from utils.path_config import get_logs_dir, get_screenshots_dir, get_temp_dir
    from utils.server_config import get_server_config
    from utils.config_loader import config
    from core.screenshot_manager import ScreenshotManager
    from core.message_system import MessageManager, MessageLevel, MessageCategory
except ImportError as e:
    print(f"Error importing required modules in process_manager.py: {e}")
    sys.exit(1)

import glob

SOCKETIO_SERVER_SCRIPT = os.path.join(app_root, "socketio_server", "server.py")
STARTUP_TIMEOUT = 10  # seconds to wait for server startup message

class ProcessManager:
    """Manages the various service processes for the 33ter application."""

    def __init__(self):
        self.config = config.get_config()
        self.logger = self._setup_logging()
        self.processes: Dict[str, subprocess.Popen] = {}

        self.output_buffers: Dict[str, list] = {
            'status': [],
            'screenshot': [],
            'debug': [],
            'ocr': []
        }

        self.message_manager = MessageManager()

        self.ios_clients_connected = 0
        self.local_connected = False
        self.socketio_client: Optional[socketio.Client] = None
        self.screenshot_manager = ScreenshotManager()
        self.room_joined = False

        self.ocr_processing_active = False
        self.last_ocr_time = 0
        self.ocr_lock = threading.Lock()

        self.max_display_length = 150

        self.socketio_server_process: Optional[subprocess.Popen] = None
        self.socketio_server_status = "Stopped"
        self.socketio_server_running = False
        self._stop_event = threading.Event()
        self._monitor_thread: Optional[threading.Thread] = None

        self.logger.info("ProcessManager initialized")
        
        # Add diagnostic logging for screenshot configuration
        try:
            self.logger.debug("Checking screenshot manager configuration...")
            screenshot_config = self.config.get('screenshot', {})
            if screenshot_config is None:
                self.logger.warning("Screenshot config section is None")
            else:
                frequency = screenshot_config.get('frequency')
                cleanup_age = screenshot_config.get('cleanup_age')
                self.logger.debug(f"Screenshot frequency: {frequency} (type: {type(frequency).__name__})")
                self.logger.debug(f"Screenshot cleanup_age: {cleanup_age} (type: {type(cleanup_age).__name__})")
        except Exception as e:
            self.logger.error(f"Error logging screenshot configuration: {e}", exc_info=True)

    def _setup_logging(self):
        """Configure process manager logging."""
        log_file = os.path.join(get_logs_dir(), "process_manager.log")
        log_level_str = self.config.get("logging", {}).get("level", "INFO")
        log_level = getattr(logging, log_level_str.upper(), logging.INFO)

        logger = logging.getLogger('33ter-ProcessManager')
        logger.setLevel(log_level)
        logger.propagate = False  # Prevent duplicate logging

        if not logger.handlers:
            # Ensure log directory exists
            try:
                os.makedirs(os.path.dirname(log_file), exist_ok=True)
            except OSError as e:
                print(f"Warning: Could not create log directory for ProcessManager: {e}", file=sys.stderr)
                # Continue without file logging if directory creation fails

            formatter = logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(threadName)s - %(message)s'
            )

            # Attempt to add FileHandler
            try:
                file_handler = logging.FileHandler(log_file)
                file_handler.setFormatter(formatter)
                logger.addHandler(file_handler)
            except Exception as e:
                print(f"Warning: Failed to create file handler for ProcessManager log: {e}", file=sys.stderr)

            console_handler = logging.StreamHandler()
            console_handler.setFormatter(formatter)
            # Set console level based on main log level for ProcessManager itself
            console_handler.setLevel(log_level)  # Match the logger's level for console output
            logger.addHandler(console_handler)

        return logger

    def _truncate_message(self, message: Union[str, dict, list]) -> str:
        """Truncate long messages for display purposes."""
        if isinstance(message, (dict, list)):
            try:
                message_str = json.dumps(message)
            except Exception:
                message_str = str(message)
        elif not isinstance(message, str):
            message_str = str(message)
        else:
            message_str = message

        if not message_str:
            return ""

        if len(message_str) > self.max_display_length:
            return message_str[:self.max_display_length] + "... [truncated]"
        return message_str

    def _start_socketio_server(self):
        """Starts the Socket.IO server as a subprocess."""
        if self.socketio_server_process and self.socketio_server_process.poll() is None:
            self.logger.warning("Socket.IO server already running.")
            return

        server_config = self.config.get('server', {})
        host = server_config.get('host', '0.0.0.0')
        port = server_config.get('port', 5348)
        room = server_config.get('room', '33ter_room')
        log_level = self.config.get('logging', {}).get('level', 'INFO')

        if not os.path.exists(SOCKETIO_SERVER_SCRIPT):
            self.logger.error(f"Socket.IO server script not found at: {SOCKETIO_SERVER_SCRIPT}")
            self.socketio_server_status = "Error: Script not found"
            self._add_to_buffer("status", self.socketio_server_status, "error")
            return

        env = os.environ.copy()
        env['PYTHONPATH'] = app_root + os.pathsep + env.get('PYTHONPATH', '')
        env['PYTHONUNBUFFERED'] = '1'

        command = [
            sys.executable,
            SOCKETIO_SERVER_SCRIPT,
            '--host', str(host),
            '--port', str(port),
            '--room', str(room),
            '--log-level', log_level
        ]

        self.logger.info(f"Starting Socket.IO server with command: {' '.join(command)}")
        self.logger.debug(f"Server environment: {env}")
        self.socketio_server_status = "Starting..."
        self._add_to_buffer("status", "Socket.IO Server: Starting...", "info")

        try:
            self.socketio_server_process = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=env,
                bufsize=1
            )
            self.logger.info(f"Socket.IO server process started (PID: {self.socketio_server_process.pid}).")

            self._stop_event.clear()
            self._monitor_thread = threading.Thread(
                target=self._monitor_socketio_server,
                name="SocketIOMonitorThread",
                daemon=True
            )
            self._monitor_thread.start()

        except Exception as e:
            self.logger.error(f"Failed to start Socket.IO server: {e}", exc_info=True)
            self.socketio_server_status = f"Error: {e}"
            self._add_to_buffer("status", f"Socket.IO Server: Error - {e}", "error")
            self.socketio_server_process = None
            self.socketio_server_running = False

    def _monitor_socketio_server(self):
        """Monitors the Socket.IO server process output for startup and errors."""
        if not self.socketio_server_process or not self.socketio_server_process.stdout:
            self.logger.error("Monitor thread started but server process or stdout is invalid.")
            self.socketio_server_status = "Error: Invalid process"
            self.socketio_server_running = False
            return

        self.logger.info("Socket.IO monitor thread started.")
        startup_message = f"Running on http://{self.config.get('server', {}).get('host', '0.0.0.0')}:{self.config.get('server', {}).get('port', 5348)}"
        self.logger.info(f"Waiting for startup message: '{startup_message}'")

        start_time = time.time()
        startup_detected = False

        stdout_lines: Deque[str] = deque(maxlen=50)
        stderr_lines: Deque[str] = deque(maxlen=50)

        process = self.socketio_server_process
        stdout_fd = process.stdout.fileno()
        stderr_fd = process.stderr.fileno()

        os.set_blocking(stdout_fd, False)
        os.set_blocking(stderr_fd, False)

        while not self._stop_event.is_set():
            if process.poll() is not None:
                self.logger.warning(f"Socket.IO server process terminated unexpectedly with code {process.poll()}.")
                self.socketio_server_status = f"Crashed (Code: {process.poll()})"
                self.socketio_server_running = False
                self._add_to_buffer("status", f"Socket.IO Server: {self.socketio_server_status}", "error")
                break

            ready_to_read, _, _ = select.select([stdout_fd, stderr_fd], [], [], 0.1)

            for fd in ready_to_read:
                try:
                    if fd == stdout_fd:
                        line = process.stdout.readline()
                        if line:
                            line = line.strip()
                            self.logger.debug(f"Server STDOUT: {line}")
                            stdout_lines.append(line)
                            if not startup_detected and startup_message in line:
                                self.logger.info("Socket.IO server startup message detected.")
                                startup_detected = True
                                self.socketio_server_status = "Running"
                                self.socketio_server_running = True
                                self._add_to_buffer("status", "Socket.IO Server: Running", "info")
                    elif fd == stderr_fd:
                        line = process.stderr.readline()
                        if line:
                            line = line.strip()
                            self.logger.warning(f"Server STDERR: {line}")
                            stderr_lines.append(line)
                            if "error" in line.lower() and self.socketio_server_status != "Running":
                                self.socketio_server_status = "Error (see logs)"
                                self._add_to_buffer("status", f"Socket.IO Server: Error - {line}", "error")

                except Exception as e:
                    self.logger.error(f"Error reading server output: {e}", exc_info=True)
                    time.sleep(0.1)

            if not startup_detected and (time.time() - start_time > STARTUP_TIMEOUT):
                self.logger.error(f"Socket.IO server startup timed out after {STARTUP_TIMEOUT} seconds.")
                self.socketio_server_status = "Error: Startup Timeout"
                self.socketio_server_running = False
                self._add_to_buffer("status", f"Socket.IO Server: {self.socketio_server_status}", "error")
                self.logger.error("Recent STDOUT:\n" + "\n".join(stdout_lines))
                self.logger.error("Recent STDERR:\n" + "\n".join(stderr_lines))
                self._stop_socketio_server(force=True)
                break

            if not ready_to_read:
                time.sleep(0.05)

        if self._stop_event.is_set():
            self.logger.info("Socket.IO monitor thread stopping due to stop event.")
            if self.socketio_server_running:
                self.socketio_server_status = "Stopped"
                self.socketio_server_running = False
                self._add_to_buffer("status", "Socket.IO Server: Stopped", "info")
        else:
            self.logger.info(f"Socket.IO monitor thread finished. Final status: {self.socketio_server_status}")

        if process.poll() is not None:
            self.socketio_server_running = False
            if self.socketio_server_status == "Running":
                self.socketio_server_status = f"Stopped (Code: {process.poll()})"

    def _stop_socketio_server(self, force=False):
        """Stops the Socket.IO server process."""
        self.logger.info("Stopping Socket.IO server...")
        self._stop_event.set()

        if self.socketio_server_process:
            if self.socketio_server_process.poll() is None:
                try:
                    if force:
                        self.logger.warning("Forcing termination of Socket.IO server.")
                        self.socketio_server_process.kill()
                    else:
                        self.logger.info(f"Sending SIGTERM to Socket.IO server (PID: {self.socketio_server_process.pid}).")
                        self.socketio_server_process.terminate()
                    self.socketio_server_process.wait(timeout=5)
                    self.logger.info("Socket.IO server process terminated.")
                except subprocess.TimeoutExpired:
                    self.logger.warning("Socket.IO server did not terminate gracefully, killing.")
                    self.socketio_server_process.kill()
                    self.socketio_server_process.wait()
                except Exception as e:
                    self.logger.error(f"Error stopping Socket.IO server: {e}", exc_info=True)
            else:
                self.logger.info("Socket.IO server process already stopped.")

        if self._monitor_thread and self._monitor_thread.is_alive():
            self.logger.debug("Waiting for monitor thread to join...")
            self._monitor_thread.join(timeout=2)
            if self._monitor_thread.is_alive():
                self.logger.warning("Monitor thread did not join cleanly.")
        self._monitor_thread = None

        self.socketio_server_process = None
        self.socketio_server_running = False
        if self.socketio_server_status not in ["Error: Script not found", "Error: Startup Timeout"] and not self.socketio_server_status.startswith("Crashed"):
            self.socketio_server_status = "Stopped"
            self._add_to_buffer("status", "Socket.IO Server: Stopped", "info")
        self.logger.info("Socket.IO server stop sequence complete.")

    def start_all_services(self):
        """Starts all managed services."""
        self.logger.info("Starting all services...")
        self._start_socketio_server()
        self.screenshot_manager.start_capturing()
        self._add_to_buffer("status", "Screenshot Manager: Started", "info")
        self.logger.info("All services initiated.")

    def stop_all(self):
        """Stops all managed services gracefully."""
        self.logger.info("Stopping all services...")
        self._stop_socketio_server()
        self.screenshot_manager.stop_capturing()
        self._add_to_buffer("status", "Screenshot Manager: Stopped", "info")
        self.logger.info("All services stopped.")

    def get_socketio_status(self) -> str:
        """Returns the current status of the Socket.IO server."""
        if self.socketio_server_running and self.socketio_server_process and self.socketio_server_process.poll() is not None:
            self.logger.warning("Detected Socket.IO server process died unexpectedly.")
            self.socketio_server_status = f"Crashed (Code: {self.socketio_server_process.poll()})"
            self.socketio_server_running = False
            self._add_to_buffer("status", f"Socket.IO Server: {self.socketio_server_status}", "error")

        return self.socketio_server_status

    def get_screenshot_status(self) -> str:
        """Returns the current status of the Screenshot Manager."""
        return self.screenshot_manager.get_status()

    def _add_to_buffer(self, buffer_name: str, message: str, level: str = "info"):
        """Add a formatted message to a specific output buffer."""
        if buffer_name not in self.output_buffers:
            if buffer_name not in ["status", "debug", "screenshot", "ocr"]:
                self.logger.warning(f"Attempted write to non-existent legacy buffer '{buffer_name}'")
                return

        timestamp = time.strftime("%H:%M:%S")
        display_message = self._truncate_message(message)
        msg_from = "system"

        if buffer_name == "debug":
            if "ERROR:" in message:
                level = "error"
                display_message = message.replace("ERROR:", "").strip()
                msg_from = "error"
            elif "WARNING:" in message:
                level = "warning"
                display_message = message.replace("WARNING:", "").strip()
                msg_from = "warning"
            elif "Sending message:" in message or "OCR result sent" in message:
                msg_from = "localBackend"
            elif "Received message:" in message:
                try:
                    parts = message.split(", ")
                    msg_from = next((p.split("=")[1] for p in parts if p.startswith("from=")), "unknown")
                except Exception:
                    msg_from = "unknown"
            elif "client count changed" in message:
                msg_from = "server"

            log_entry = f"{timestamp}: {{"
            log_entry += f"\n    type: {level},"
            try:
                log_entry += f"\n    value: {json.dumps(display_message)},"
            except TypeError:
                log_entry += f"\n    value: {json.dumps(str(display_message))},"
            log_entry += f"\n    from: {msg_from}"
            log_entry += f"\n}}"
            if buffer_name in self.output_buffers:
                self.output_buffers[buffer_name].append(log_entry)

        elif buffer_name in self.output_buffers:
            self.output_buffers[buffer_name].append(f"{timestamp} [{level.upper()}] {display_message}")

        if buffer_name in self.output_buffers and len(self.output_buffers[buffer_name]) > 1000:
            self.output_buffers[buffer_name].pop(0)

        msg_level_enum = MessageLevel.INFO
        if level == "warning":
            msg_level_enum = MessageLevel.WARNING
        elif level == "error":
            msg_level_enum = MessageLevel.ERROR

        category = MessageCategory.SYSTEM
        if buffer_name == "ocr":
            category = MessageCategory.OCR
        elif buffer_name == "status":
            category = MessageCategory.SYSTEM
        elif buffer_name == "screenshot":
            category = MessageCategory.SCREENSHOT
        elif buffer_name == "debug":
            msg_lower = message.lower()
            legacy_source = msg_from if 'msg_from' in locals() else "system"

            if "socket" in msg_lower or "client" in msg_lower or "room" in msg_lower or "connect" in msg_lower or legacy_source == "server":
                category = MessageCategory.SOCKET
            elif "ocr" in msg_lower or "screenshot" in msg_lower:
                category = MessageCategory.OCR
            elif legacy_source == "localBackend":
                category = MessageCategory.SYSTEM

        source = msg_from if 'msg_from' in locals() else "system"

        self.message_manager.add_message(
            content=message,
            level=msg_level_enum,
            category=category,
            source=source,
            buffer_name=buffer_name
        )

    def get_output(self, service_name: str) -> list:
        """Get the formatted messages for a specific buffer from the MessageManager."""
        valid_buffers = ["status", "debug", "screenshot", "ocr"]
        if service_name in valid_buffers:
            return self.message_manager.get_formatted_messages(service_name)

        self.logger.warning(f"Attempted to get output for unknown buffer/service: {service_name}")
        return []

    def get_ios_client_count(self):
        """Return the current count of connected iOS clients."""
        return self.ios_clients_connected

    def post_message_to_socket(self, value: str, messageType: str):
        """Post a generic 'message' event to the SocketIO server."""
        if not self.socketio_client or not self.socketio_client.connected:
            error_msg = "SocketIO client not connected. Cannot send message."
            self._log_post_error(error_msg)
            return error_msg

        try:
            display_value = self._truncate_message(value)
            self._add_to_buffer("debug", f"Sending message: type={messageType}, value={display_value}", "info")

            formatted_message = {
                "messageType": messageType,
                "from": "localBackend",
                "value": value
            }

            room = self.config['server']['room']

            if not self.room_joined:
                self.logger.warning(f"Not joined to room '{room}', attempting join before sending message.")
                self.socketio_client.emit('join_room', {'room': room}, callback=self._room_join_callback)
                time.sleep(0.1)
                if not self.room_joined:
                    self.logger.error(f"Still not joined to room '{room}' after re-attempt. Message might not be delivered.")
                    self._add_to_buffer("status", f"Send Warning: Not joined to room '{room}'", "warning")
                    self._add_to_buffer("debug", f"WARNING: Not joined to room '{room}' when sending message", "warning")

            self.socketio_client.emit('message', formatted_message)

            return None

        except Exception as e:
            error_msg = f"Failed to send message via SocketIO: {str(e)}"
            self._log_post_error(error_msg, exc_info=True)
            return error_msg

    def process_and_send_ocr_result(self):
        """Process the latest screenshot with OCR and send results to SocketIO room."""
        if not self.ocr_lock.acquire(blocking=False):
            self.logger.info("OCR processing already in progress. Skipping.")
            self._add_to_buffer("debug", "OCR processing already in progress. Skipping request.", "info")
            return False
            
        try:
            screenshots_dir = get_screenshots_dir()
            screenshots = glob.glob(os.path.join(screenshots_dir, "*.png"))
            
            if not screenshots:
                self.logger.warning("No screenshots available for OCR processing")
                self._add_to_buffer("ocr", "No screenshots available for OCR processing", "warning")
                return False
            
            ocr_result = self.screenshot_manager.process_latest_screenshot()
            
            if not ocr_result or not isinstance(ocr_result, str) or not ocr_result.strip():
                self.logger.warning("OCR processing failed or no text found")
                self._add_to_buffer("ocr", "OCR processing failed or no text found", "warning")
                return False
            
            formatted_result = ocr_result.strip()
            
            try:
                if self.socketio_client and self.socketio_client.connected:
                    ocr_payload = [{
                        'text': formatted_result,
                        'timestamp': datetime.now().isoformat()
                    }]
                    self.socketio_client.emit('ocr_result', ocr_payload)
                    self.logger.info(f"OCR result sent successfully via 'ocr_result' event ({len(formatted_result)} chars)")
                    self._add_to_buffer("ocr", f"OCR Success - Sent {len(formatted_result)} chars", "info")
                    return True
                elif not self.socketio_client:
                    self.logger.error("Cannot send OCR result: SocketIO client not initialized")
                    self._add_to_buffer("ocr", "OCR Send Error: Client not initialized", "error")
                    return False
                elif not self.socketio_client.connected:
                    self.logger.error("Cannot send OCR result: SocketIO client not connected")
                    self._add_to_buffer("ocr", "OCR Send Error: Client not connected", "error")
                    return False

            except Exception as send_e:
                self.logger.error(f"Failed to send OCR result via SocketIO: {send_e}", exc_info=True)
                self._add_to_buffer("ocr", f"OCR Send Error: {send_e}", "error")
                return False
                
            return True
            
        except Exception as e:
            error_msg = f"OCR processing error: {str(e)}"
            self.logger.error(error_msg, exc_info=True)
            self._add_to_buffer("ocr", f"OCR Error: {str(e)}", "error")
            return False
        finally:
            self.ocr_lock.release()