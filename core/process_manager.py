"""Process management module for 33ter application."""
import os
import sys
import time
import json
import logging
import subprocess
import threading
import traceback
import select
from collections import deque
from typing import Dict, Optional, List, Union, IO, Tuple

from pathlib import Path
from datetime import datetime

try:
    from utils.path_config import get_logs_dir, get_screenshots_dir, get_temp_dir, get_project_root
    from utils.server_config import get_server_config as load_server_config_util, DEFAULT_CONFIG as SERVER_DEFAULT_CONFIG
    from utils.config_loader import config
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
    """Manages the lifecycle of external processes like Socket.IO server."""

    def __init__(self):
        """Initialize the ProcessManager."""
        self.logger = logging.getLogger(__name__)
        self.message_manager = MessageManager()
        self.socketio_process: Optional[subprocess.Popen] = None
        self.socketio_monitor_thread: Optional[threading.Thread] = None
        self.socketio_monitor_stop_event = threading.Event()
        self.socketio_status = "Stopped"
        self.socketio_pid: Optional[int] = None
        self.internal_sio_client = None
        self.screenshot_manager = ScreenshotManager()
        self.logger.info("ProcessManager initialized")

    def _get_socketio_command(self) -> List[str]:
        """Constructs the command to start the Socket.IO server using loaded config."""
        python_executable = sys.executable
        server_script = os.path.join(get_project_root(), "socketio_server", "server.py")

        try:
            server_config_data = load_server_config_util()
            server_settings = server_config_data.get('server', SERVER_DEFAULT_CONFIG.get('server', {}))
            default_server_settings = SERVER_DEFAULT_CONFIG.get('server', {})
            host = server_settings.get('host', default_server_settings.get('host', '0.0.0.0'))
            port = server_settings.get('port', default_server_settings.get('port', 5348))
            room = server_settings.get('room', default_server_settings.get('room', '33ter_room'))
            log_level = server_settings.get('log_level', default_server_settings.get('log_level', 'INFO'))

            self.logger.info(f"SocketIO command config loaded: host={host}, port={port}, room={room}, log_level={log_level}")

        except Exception as e:
            self.logger.error(f"Failed to load server config for command generation: {e}. Using hardcoded defaults.", exc_info=True)
            host = '0.0.0.0'
            port = 5348
            room = '33ter_room'
            log_level = 'INFO'

        command = [
            python_executable,
            server_script,
            "--host", str(host),
            "--port", str(port),
            "--room", str(room),
            "--log-level", str(log_level)
        ]
        self.logger.info(f"Constructed Socket.IO server command: {' '.join(command)}")
        return command

    def start_socketio_server(self):
        """Starts the Socket.IO server process."""
        if self.socketio_process and self.socketio_process.poll() is None:
            self.logger.warning("Socket.IO server already running.")
            return

        command = self._get_socketio_command()
        self.logger.info(f"Starting Socket.IO server with command: {' '.join(command)}")
        self.socketio_status = "Starting"
        try:
            self.socketio_process = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
                universal_newlines=True
            )
            self.socketio_pid = self.socketio_process.pid
            self.logger.info(f"Socket.IO server process started (PID: {self.socketio_pid}).")

            self.socketio_monitor_stop_event.clear()
            self.socketio_monitor_thread = threading.Thread(
                target=self._monitor_socketio_process,
                name="SocketIOMonitorThread",
                daemon=True
            )
            self.socketio_monitor_thread.start()
            self.logger.info("Socket.IO monitor thread started.")

        except Exception as e:
            self.logger.error(f"Failed to start Socket.IO server: {e}", exc_info=True)
            self.socketio_status = "Error"
            self._add_to_buffer("debug", f"ERROR: Failed to start Socket.IO server: {e}", "error")

    def _monitor_socketio_process(self):
        """Monitors the Socket.IO server process's stdout/stderr and status."""
        if not self.socketio_process or not self.socketio_process.stdout or not self.socketio_process.stderr:
            self.logger.error("Socket.IO process or streams not available for monitoring.")
            self.socketio_status = "Error"
            return

        self.logger.info("Socket.IO monitor thread running.")
        startup_message = "Running on http://"
        startup_detected = False

        self.logger.info(f"Waiting for startup message: '{startup_message}...'")

        while not self.socketio_monitor_stop_event.is_set():
            process_poll = self.socketio_process.poll()
            if process_poll is not None:
                self.logger.warning(f"Socket.IO server process terminated unexpectedly with code {process_poll}.")
                self.socketio_status = f"Crashed (Code: {process_poll})"
                self._add_to_buffer("debug", f"WARNING: Socket.IO server process terminated unexpectedly with code {process_poll}.", "warning")
                self._drain_stream(self.socketio_process.stdout, "STDOUT")
                self._drain_stream(self.socketio_process.stderr, "STDERR")
                break

            self._read_stream_non_blocking(self.socketio_process.stdout, "STDOUT", startup_message)
            self._read_stream_non_blocking(self.socketio_process.stderr, "STDERR", startup_message)

            time.sleep(0.1)

        final_status = self.socketio_status
        self.logger.info(f"Socket.IO monitor thread finished. Final status: {final_status}")
        self.socketio_process = None
        self.socketio_pid = None

    def _read_stream_non_blocking(self, stream, stream_name, startup_message):
        """Reads lines from a stream without blocking indefinitely."""
        try:
            line = stream.readline()
            if line:
                line = line.strip()
                self._add_to_buffer("debug", f"Server {stream_name}: {line}", "info" if stream_name == "STDOUT" else "warning")

                if stream_name == "STDOUT" and startup_message in line and self.socketio_status == "Starting":
                    self.logger.info("Socket.IO server startup message detected.")
                    self.socketio_status = "Running"
                    self._add_to_buffer("debug", "Socket.IO server startup message detected.", "info")

        except BlockingIOError:
            pass
        except Exception as e:
            if not self.socketio_monitor_stop_event.is_set():
                self.logger.error(f"Error reading Socket.IO {stream_name}: {e}", exc_info=True)

    def _drain_stream(self, stream, stream_name):
        """Reads and logs all remaining lines from a stream."""
        try:
            for line in stream:
                line = line.strip()
                if line:
                    self._add_to_buffer("debug", f"Server {stream_name} (drain): {line}", "info" if stream_name == "STDOUT" else "warning")
            self.logger.info(f"Finished draining {stream_name}.")
        except Exception as e:
            self.logger.error(f"Error draining Socket.IO {stream_name}: {e}", exc_info=True)

    def stop_socketio_server(self):
        """Stops the Socket.IO server process."""
        self.logger.info("Stopping Socket.IO server...")
        self.socketio_monitor_stop_event.set()

        if self.socketio_process and self.socketio_process.poll() is None:
            try:
                self.logger.info(f"Terminating Socket.IO process (PID: {self.socketio_pid})...")
                self.socketio_process.terminate()
                try:
                    self.socketio_process.wait(timeout=5)
                    self.logger.info("Socket.IO process terminated gracefully.")
                except subprocess.TimeoutExpired:
                    self.logger.warning("Socket.IO process did not terminate gracefully, killing...")
                    self.socketio_process.kill()
                    self.socketio_process.wait()
                    self.logger.info("Socket.IO process killed.")
                self.socketio_status = "Stopped"
            except Exception as e:
                self.logger.error(f"Error stopping Socket.IO server: {e}", exc_info=True)
                self.socketio_status = "Error"
        else:
            self.logger.info("Socket.IO server process not running or already stopped.")
            self.socketio_status = "Stopped"

        if self.socketio_monitor_thread and self.socketio_monitor_thread.is_alive():
            self.logger.info("Waiting for Socket.IO monitor thread to join...")
            self.socketio_monitor_thread.join(timeout=2)
            if self.socketio_monitor_thread.is_alive():
                self.logger.warning("Socket.IO monitor thread did not join cleanly.")
            else:
                self.logger.info("Socket.IO monitor thread joined.")

        self.socketio_process = None
        self.socketio_pid = None
        self.socketio_monitor_thread = None
        self.logger.info("Socket.IO server stop sequence complete.")

    def start_screenshot_capture(self):
        """Starts the screenshot capture loop."""
        self.logger.info("Starting screenshot capture...")
        self.screenshot_manager.start_capturing()

    def stop_screenshot_capture(self):
        """Stops the screenshot capture loop."""
        self.logger.info("Stopping screenshot capture...")
        self.screenshot_manager.stop_capturing()

    def start_all_services(self):
        """Starts all managed services."""
        self.logger.info("Starting all services...")
        self.start_socketio_server()
        self.start_screenshot_capture()
        self.logger.info("All services initiated.")

    def stop_all(self):
        """Stops all managed services."""
        self.logger.info("Stopping all services...")
        self.stop_screenshot_capture()
        self.stop_socketio_server()
        self.logger.info("All services stopped.")

    def get_status(self) -> dict:
        """Returns the status of managed services."""
        screenshot_status = "Running" if self.screenshot_manager.is_running() else "Paused"
        return {
            "socketio": self.socketio_status,
            "screenshot": screenshot_status,
            "socketio_pid": self.socketio_pid
        }

    def get_output(self, buffer_name: str) -> List[str]:
        """Gets formatted output lines from a specific buffer."""
        return self.message_manager.get_formatted_messages(buffer_name)

    def _add_to_buffer(self, buffer_name: str, content: str, level: str):
        """Adds a message to the specified buffer via MessageManager."""
        try:
            msg_level = getattr(MessageLevel, level.upper(), MessageLevel.INFO)
            category = MessageCategory.SOCKET if buffer_name == "debug" else MessageCategory.SCREENSHOT
            source = "process_manager"
            self.message_manager.add_message(content, msg_level, category, source, buffer_name)
        except Exception as e:
            self.logger.error(f"Failed to add message to buffer '{buffer_name}': {e}", exc_info=True)

    def process_and_send_ocr_result(self) -> bool:
        """Takes a screenshot, performs OCR, and sends result via Socket.IO."""
        self.logger.info("Manual OCR trigger initiated.")
        try:
            screenshot_path = self.screenshot_manager.take_screenshot_now()
            if not screenshot_path:
                self.logger.error("Manual OCR failed: Could not take screenshot.")
                self._add_to_buffer("debug", "ERROR: Manual OCR failed: Could not take screenshot.", "error")
                return False

            ocr_text = self.screenshot_manager.perform_ocr(screenshot_path)
            if ocr_text is None:
                self.logger.error("Manual OCR failed: OCR processing returned None.")
                self._add_to_buffer("debug", "ERROR: Manual OCR failed: OCR processing returned None.", "error")
                return False

            ocr_data = [{
                'text': ocr_text,
                'timestamp': time.strftime("%Y-%m-%dT%H:%M:%S"),
                'source': 'manual_trigger'
            }]

            if self.internal_sio_client and self.internal_sio_client.connected:
                self.internal_sio_client.emit('ocr_result', ocr_data)
                self.logger.info(f"Manual OCR result sent via internal client. Length: {len(ocr_text)}")
                self._add_to_buffer("debug", f"SENT Manual OCR Result (len={len(ocr_text)})", "info")
                return True
            else:
                self.logger.error("Manual OCR failed: Internal Socket.IO client not connected.")
                self._add_to_buffer("debug", "ERROR: Manual OCR failed: Internal client not connected.", "error")
                return False

        except Exception as e:
            self.logger.error(f"Error during manual OCR processing/sending: {e}", exc_info=True)
            self._add_to_buffer("debug", f"ERROR: Exception during manual OCR: {e}", "error")
            return False

    def post_message_to_socket(self, value: str, messageType: str = "info") -> bool:
        """Posts a generic message to the Socket.IO server."""
        if self.internal_sio_client and self.internal_sio_client.connected:
            try:
                payload = {
                    'messageType': messageType,
                    'value': value,
                    'from': 'localUI'
                }
                self.internal_sio_client.emit('message', payload)
                self.logger.info(f"Posted message from UI: Type={messageType}, Value='{value[:50]}...'")
                self._add_to_buffer("debug", f"SENT Message from UI: Type={messageType}, Value='{value[:50]}...'", "info")
                return True
            except Exception as e:
                self.logger.error(f"Failed to post message via internal client: {e}", exc_info=True)
                self._add_to_buffer("debug", f"ERROR: Failed to post message: {e}", "error")
                return False
        else:
            self.logger.warning("Cannot post message: Internal Socket.IO client not connected.")
            self._add_to_buffer("debug", "WARNING: Cannot post message: Internal client not connected.", "warning")
            return False