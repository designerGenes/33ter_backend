"""Process management module for 33ter application.

This module serves as the central coordinator for all 33ter services, managing the lifecycle
of the SocketIO server, screenshot capture, and OCR processing components. It handles
inter-process communication, service health monitoring, and client message routing.

#TODO:
- Implement graceful shutdown with proper cleanup of all resources
- Add service recovery mechanisms for unexpected failures
- Implement proper process isolation
- Add service health monitoring and automatic restart
- Consider implementing a proper IPC mechanism instead of file-based signaling
- Add proper resource usage monitoring (CPU, memory, disk)
"""
import os
import sys
import time
import json
import logging
import subprocess
import socketio
from typing import Dict, Optional, List
from utils import get_logs_dir, get_screenshots_dir, get_temp_dir
from utils import get_server_config
import glob
from .screenshot_manager import ScreenshotManager

class ProcessManager:
    """Manages the various service processes for the 33ter application.
    
    This class serves as the central coordinator for:
    - Service lifecycle management (start/stop/restart)
    - Inter-process communication
    - Client message routing
    - Service health monitoring
    - Output buffering and filtering
    
    #TODO:
    - Implement process monitoring with automatic recovery
    - Add proper process resource cleanup on shutdown
    - Implement better error handling for subprocess management
    - Add proper process isolation and sandboxing
    - Consider using a proper service mesh for process communication
    """
    
    def __init__(self):
        self.config = get_server_config()
        self.logger = self._setup_logging()
        self.processes: Dict[str, subprocess.Popen] = {}
        self.output_buffers: Dict[str, list] = {
            'screenshot': [],
            'debug': []  # Renamed from 'socket' to 'debug'
        }
        self.ios_clients_connected = 0
        self.socketio_client = None
        self.screenshot_manager = ScreenshotManager()
        
    def _setup_logging(self):
        """Configure process manager logging."""
        log_file = os.path.join(get_logs_dir(), "process_manager.log")
        
        logger = logging.getLogger('33ter-ProcessManager')
        logger.setLevel(logging.INFO)
        
        if not logger.handlers:
            handler = logging.FileHandler(log_file)
            formatter = logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            )
            handler.setFormatter(formatter)
            logger.addHandler(handler)
        
        return logger

    def start_service(self, service_name: str):
        """Start a specific service process."""
        if service_name in self.processes:
            self.logger.warning(f"Service {service_name} is already running")
            return
            
        try:
            if service_name == 'socket':
                self._start_socketio_service()
            elif service_name == 'screenshot':
                self.screenshot_manager.start_capturing()
                self.output_buffers['screenshot'] = []  # Clear buffer on restart
            
        except Exception as e:
            self.logger.error(f"Failed to start {service_name} service: {e}")
            
    def _start_socketio_service(self):
        """Start the SocketIO server and establish client connection."""
        try:
            env = os.environ.copy()
            command = [
                sys.executable,
                'socketio_server/server.py',
                '--host', self.config['server']['host'],
                '--port', str(self.config['server']['port']),
                '--room', self.config['server']['room']
            ]
            
            # Start the SocketIO server process
            process = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                env=env
            )
            
            self.processes['socket'] = process
            self.logger.info(f"Started SocketIO server (PID: {process.pid})")
            
            # Start output monitoring
            self._monitor_output('socket', process)
            
            # Connect our client after brief delay to ensure server is ready
            time.sleep(2)
            self._connect_to_socketio()
            
        except Exception as e:
            raise Exception(f"Failed to start SocketIO service: {e}")

    def _connect_to_socketio(self):
        """Connect to our own SocketIO server for sending messages."""
        try:
            sio = socketio.Client()
            host = self.config['server']['host']
            port = self.config['server']['port']
            
            @sio.event
            def connect():
                self.logger.info("Connected to SocketIO server")
                self._add_to_buffer("debug", "Connected to SocketIO server", "info")
                
            @sio.event
            def disconnect():
                self.logger.info("Disconnected from SocketIO server")
                self._add_to_buffer("debug", "Disconnected from SocketIO server", "warning")
                
            @sio.event
            def client_count(data):
                prev_count = self.ios_clients_connected
                self.ios_clients_connected = data.get('count', 0)
                if prev_count != self.ios_clients_connected:
                    self._add_to_buffer("debug", f"iOS clients connected: {self.ios_clients_connected}", "info")
            
            sio.connect(f"http://{host}:{port}")
            self.socketio_client = sio
            
        except Exception as e:
            self.logger.error(f"Failed to connect to SocketIO server: {e}")
            self.socketio_client = None

    def _add_to_buffer(self, buffer_name: str, message: str, level: str = "info"):
        """Add a formatted message to a specific output buffer."""
        timestamp = time.strftime("%H:%M:%S")
        emoji = {
            "info": "📱",
            "prime": "✨",
            "warning": "⚠️",
            "error": "❌"
        }.get(level, "ℹ️")
        
        self.output_buffers[buffer_name].append(f"{timestamp} {emoji} {message} ({level})")
        
        # Keep buffer size manageable
        while len(self.output_buffers[buffer_name]) > 1000:
            self.output_buffers[buffer_name].pop(0)

    def stop_service(self, service_name: str):
        """Stop a specific service process."""
        if service_name not in self.processes and service_name != 'screenshot':
            return
            
        try:
            if service_name == 'socket':
                if self.socketio_client:
                    try:
                        self.socketio_client.disconnect()
                        self.socketio_client = None
                    except:
                        pass
                
                process = self.processes.get('socket')
                if process and process.poll() is None:
                    process.terminate()
                    try:
                        process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        
                self.processes.pop('socket', None)
                self._add_to_buffer("debug", "SocketIO server stopped", "info")
                
            elif service_name == 'screenshot':
                self.screenshot_manager.stop_capturing()
                
            self.logger.info(f"Stopped {service_name} service")
            
        except Exception as e:
            self.logger.error(f"Error stopping {service_name} service: {e}")

    def restart_service(self, service_name: str):
        """Restart a specific service."""
        self.stop_service(service_name)
        time.sleep(1)  # Brief pause to ensure cleanup
        self.start_service(service_name)

    def start_all_services(self):
        """Start all required services."""
        self.start_service('socket')
        time.sleep(2)  # Wait for socket server to be ready
        self.start_service('screenshot')

    def stop_all(self):
        """Stop all running services."""
        self.stop_service('screenshot')
        self.stop_service('socket')

    def is_process_running(self, service_name: str) -> bool:
        """Check if a specific service is running."""
        if service_name == 'screenshot':
            return self.screenshot_manager.is_capturing()
            
        if service_name not in self.processes:
            return False
            
        process = self.processes[service_name]
        return process.poll() is None

    def get_output(self, service_name: str) -> list:
        """Get the filtered output buffer for a specific service."""
        if service_name == "screenshot":
            return self.screenshot_manager.get_output()
        elif service_name == "debug":
            return self.output_buffers["debug"]
        return []

    def _monitor_output(self, service_name: str, process: subprocess.Popen):
        """Monitor and filter process output."""
        def _read_output():
            while True:
                if process.poll() is not None:
                    break
                    
                line = process.stdout.readline()
                if not line:
                    break
                
                # Filter out noise
                line = line.strip()
                if not line:
                    continue
                    
                # Skip ping/pong messages
                if "ping" in line.lower() or "pong" in line.lower():
                    continue
                    
                # Skip engineio debug messages
                if "engineio" in line.lower() and "debug" in line.lower():
                    continue
                
                # Add relevant messages to buffer
                if "error" in line.lower():
                    self._add_to_buffer("debug", line, "error")
                elif "warning" in line.lower():
                    self._add_to_buffer("debug", line, "warning")
                elif "client connected" in line.lower():
                    self._add_to_buffer("debug", "New client connection", "info")
                elif "client disconnected" in line.lower():
                    self._add_to_buffer("debug", "Client disconnected", "info")
        
        import threading
        thread = threading.Thread(target=_read_output, daemon=True)
        thread.start()

    def open_screenshots_folder(self):
        """Open the screenshots directory in the system file explorer."""
        screenshots_dir = get_screenshots_dir()
        try:
            if sys.platform == 'darwin':  # macOS
                subprocess.run(['open', screenshots_dir])
            elif sys.platform == 'win32':  # Windows
                subprocess.run(['explorer', screenshots_dir])
            else:  # Linux and others
                subprocess.run(['xdg-open', screenshots_dir])
        except Exception as e:
            self.logger.error(f"Failed to open screenshots folder: {e}")

    def trigger_processing(self):
        """Trigger OCR processing of the latest screenshot and send to iOS app."""
        try:
            self.logger.info("Manually triggering OCR processing")
            self._add_to_buffer("debug", "Manual OCR processing triggered", "info")
            
            extracted_text = self.screenshot_manager.process_latest_screenshot()
            
            if not extracted_text:
                self._add_to_buffer("debug", "Failed to extract text from screenshot", "warning")
                return None
                
            # Send extracted text to iOS app via SocketIO
            self.send_ocr_result_to_socket(extracted_text)
            return extracted_text
            
        except Exception as e:
            error_msg = f"Error during manual processing: {str(e)}"
            self.logger.error(error_msg)
            self._add_to_buffer("debug", error_msg, "error")
            return None

    def send_ocr_result_to_socket(self, text):
        """Send OCR result to SocketIO server in a standardized format for iOS app."""
        if not self.socketio_client:
            self._add_to_buffer("debug", "Cannot send OCR result: SocketIO not connected", "warning")
            return
            
        try:
            # Prepare standardized message format for the iOS app
            message = {
                "type": "ocr_result",
                "timestamp": time.time(),
                "data": {
                    "text": text,
                    "source": "manual_trigger"
                }
            }
            
            # Send to the room
            room = self.config['server']['room']
            self.socketio_client.emit('message', message, room=room)
            
            # Log success
            chars = len(text)
            preview = text[:50] + "..." if len(text) > 50 else text
            self._add_to_buffer("debug", f"OCR result sent ({chars} chars): {preview}", "info")
            
        except Exception as e:
            error_msg = f"Failed to send OCR result: {str(e)}"
            self.logger.error(error_msg)
            self._add_to_buffer("debug", error_msg, "warning")

    def post_message_to_socket(self, message, title, msg_type):
        """Post a custom message to the SocketIO server."""
        if not self.socketio_client:
            self._add_to_buffer("debug", "Cannot post message: SocketIO not connected", "warning")
            return
            
        try:
            # Prepare message format
            formatted_message = {
                "type": "custom",
                "title": title,
                "message": message,
                "msg_type": msg_type
            }
            
            # Send to the room
            room = self.config['server']['room']
            self.socketio_client.emit('message', formatted_message, room=room)
            
            # Add to debug output buffer with formatted display
            self._add_to_buffer("debug", f"{title}: {message}", msg_type)
            
        except Exception as e:
            error_msg = f"Failed to post message: {str(e)}"
            self.logger.error(error_msg)
            self._add_to_buffer("debug", error_msg, "warning")
    
    def get_ios_client_count(self):
        """Get the number of connected iOS clients."""
        return self.ios_clients_connected

    def clear_output(self, service_name: str):
        """Clear the output buffer for a specific service."""
        if service_name in self.output_buffers:
            self.output_buffers[service_name].clear()
            self._add_to_buffer("debug", "Message history cleared", "info")