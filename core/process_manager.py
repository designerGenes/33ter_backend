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
from typing import Dict, Optional, List, Union, IO
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

        if not logger.handlers:
            file_handler = logging.FileHandler(log_file)
            formatter = logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            )
            file_handler.setFormatter(formatter)
            logger.addHandler(file_handler)

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

    def start_service(self, service_name: str):
        """Start a specific service process."""
        if service_name in self.processes and self.processes[service_name].poll() is None:
            self.logger.warning(f"Service {service_name} is already running (PID: {self.processes[service_name].pid})")
            if service_name == 'socket':
                if not self.socketio_client or not self.socketio_client.connected:
                    self.logger.info("Server process running but client not connected. Attempting client connection...")
                    server_host = self.config['server']['host']
                    client_host = '127.0.0.1' if server_host == '0.0.0.0' else server_host
                    port = self.config['server']['port']
                    room_name = self.config['server']['room']
                    try:
                        self._connect_socketio_client(client_host, port, room_name)
                    except ConnectionError as e:
                        self.logger.error(f"Failed to connect client to existing server: {e}")
                        self._add_to_buffer("status", f"Failed reconnect client: {e}", "error")
            return

        try:
            if service_name == 'socket':
                self._start_socketio_service()
            elif service_name == 'screenshot':
                self.screenshot_manager.start_capturing()
                self._add_to_buffer("status", "Screenshot capture started", "info")

            self.logger.info(f"Successfully initiated start for {service_name} service.")

        except (FileNotFoundError, RuntimeError, TimeoutError, ConnectionError) as e:
            self.logger.error(f"Failed to start {service_name} service: {e}")
            self._add_to_buffer("status", f"Failed start {service_name}: {e}", "error")
            raise
        except Exception as e:
            self.logger.error(f"Unexpected error starting {service_name} service: {e}", exc_info=True)
            self._add_to_buffer("status", f"Unexpected error starting {service_name}: {e}", "error")
            raise

    def _start_socketio_service(self):
        pass

    def _log_subprocess_output(self, pipe: Optional[IO[str]], prefix: str, output_log: List[str]):
        pass

    def _connect_socketio_client(self, client_host: str, port: int, room_name: str):
        pass

    def _room_join_callback(self, success: bool):
        pass

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

    def stop_service(self, service_name: str):
        """Stop a specific service process."""
        process = self.processes.pop(service_name, None)

        if service_name == 'socket':
            if self.socketio_client:
                self.logger.info("Disconnecting internal SocketIO client...")
                try:
                    if self.socketio_client.connected:
                        self.socketio_client.disconnect()
                except Exception as e:
                    self.logger.error(f"Error disconnecting SocketIO client: {e}", exc_info=True)
                finally:
                    self.socketio_client = None
                    self.local_connected = False
                    self.room_joined = False
                    self.ios_clients_connected = 0
                    self.logger.info("Internal SocketIO client state reset.")

            if process and process.poll() is None:
                pid = process.pid
                self.logger.info(f"Terminating SocketIO server process (PID: {pid})...")
                try:
                    process.terminate()
                    process.wait(timeout=5)
                    self.logger.info(f"SocketIO server process (PID: {pid}) terminated.")
                except subprocess.TimeoutExpired:
                    self.logger.warning(f"SocketIO server process (PID: {pid}) did not terminate gracefully. Killing...")
                    process.kill()
                    process.wait()
                    self.logger.info(f"SocketIO server process (PID: {pid}) killed.")
                except Exception as e:
                    self.logger.error(f"Error terminating SocketIO server process (PID: {pid}): {e}", exc_info=True)
            elif process:
                self.logger.info(f"SocketIO server process (PID: {process.pid}) was already stopped.")
            else:
                self.logger.info("No running SocketIO server process found to stop.")

            self._add_to_buffer("status", "SocketIO service stopped", "info")

        elif service_name == 'screenshot':
            self.screenshot_manager.stop_capturing()
            self._add_to_buffer("status", "Screenshot capture stopped", "info")

        if process or service_name == 'screenshot':
            self.logger.info(f"Stopped {service_name} service.")

    def restart_service(self, service_name: str):
        pass

    def start_all_services(self):
        """Start all required services."""
        try:
            self.logger.info("Starting all services...")
            
            # First check if configuration is valid
            if 'screenshot' not in self.config:
                self.logger.warning("No screenshot section in config, using defaults")
                
            # Start SocketIO server first
            self.start_service('socket')
            
            # Then start screenshot capture with careful error handling
            try:
                self.start_service('screenshot')
            except Exception as e:
                self.logger.error(f"Failed to start screenshot service: {e}", exc_info=True)
                self._add_to_buffer("status", f"Screenshot service error: {e}", "error")
                # Continue with other services even if screenshot fails
                
            self.logger.info("All services started successfully")
            
        except Exception as e:
            self.logger.error(f"Failed to start all services: {e}", exc_info=True)
            raise

    def stop_all(self):
        pass

    def is_process_running(self, service_name: str) -> bool:
        pass

    def get_output(self, service_name: str) -> list:
        """Get the formatted messages for a specific buffer from the MessageManager."""
        valid_buffers = ["status", "debug", "screenshot", "ocr"]
        if service_name in valid_buffers:
            return self.message_manager.get_formatted_messages(service_name)

        self.logger.warning(f"Attempted to get output for unknown buffer/service: {service_name}")
        return []

    def get_ios_client_count(self):
        """Return the current count of connected iOS clients."""
        # Return the stored count, which is initialized to 0
        return self.ios_clients_connected

    def _log_post_error(self, error_msg: str, exc_info=False):
        """Helper to log errors from post_message_to_socket."""
        self.logger.error(error_msg, exc_info=exc_info)
        self._add_to_buffer("status", f"Send Error: {error_msg}", "error")
        self._add_to_buffer("debug", f"ERROR: {error_msg}", "error")

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

    def reload_screen(self):
        pass

    def get_output_queues(self):
        pass

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