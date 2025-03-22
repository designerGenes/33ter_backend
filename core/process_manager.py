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
            server_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            server_script = os.path.join(server_dir, 'socketio_server', 'server.py')

            # Server should bind to all interfaces
            server_host = '127.0.0.1'
            # Client should connect to localhost
            client_host = '127.0.0.1'
            port = 5348

            command = [
                sys.executable,
                server_script,
                '--host', server_host,
                '--port', str(port),
                '--room', '33ter_room',
                '--log-level', 'DEBUG'
            ]
            
            # Start server process
            process = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1
            )
            
            self.processes['socket'] = process
            self.logger.info(f"Started SocketIO server on {server_host}:{port} (PID: {process.pid})")
            
            # Wait for server to start
            time.sleep(2)
            
            # Try connecting multiple times
            max_retries = 3
            retry_delay = 1
            
            for attempt in range(max_retries):
                try:
                    sio = socketio.Client(logger=False, engineio_logger=False)
                    url = f"http://{client_host}:{port}"
                    self.logger.info(f"Attempting to connect to SocketIO server at {url} (attempt {attempt + 1})")
                    sio.connect(url, wait_timeout=5)
                    self.socketio_client = sio
                    self.logger.info("Successfully connected to SocketIO server")
                    return
                except Exception as e:
                    if attempt < max_retries - 1:
                        self.logger.warning(f"Connection attempt {attempt + 1} failed, retrying in {retry_delay}s")
                        time.sleep(retry_delay)
                    else:
                        raise
            
        except Exception as e:
            self.logger.error(f"Failed to start SocketIO service: {e}")
            if 'socket' in self.processes:
                self.stop_service('socket')
            raise

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

    def get_ios_client_count(self):
        """Get the number of connected iOS clients."""
        return self.ios_clients_connected

    def post_message_to_socket(self, message, title, msg_type):
        """Post a custom message to the SocketIO server."""
        if not self.socketio_client:
            self._add_to_buffer("debug", "Cannot post message: SocketIO not connected", "warning")
            return
            
        try:
            # Prepare message format
            formatted_message = {
                "type": "custom",
                "data": {  # Add data wrapper to match expected format
                    "title": title,
                    "message": message,
                    "msg_type": msg_type,
                    "timestamp": time.time()
                }
            }
            
            # Send to current room
            room = self.config['server']['room']
            self.socketio_client.emit('message', formatted_message, room=room)
            
            # Add to debug output buffer with formatted display
            self._add_to_buffer("debug", f"{title}: {message}", msg_type)
            
        except Exception as e:
            error_msg = f"Failed to post message: {str(e)}"
            self.logger.error(error_msg)
            self._add_to_buffer("debug", error_msg, "error")

    def reload_screen(self):
        """Force a reload of the current view's code from disk."""
        # Note: The actual reload happens in BaseView.reload_view()
        # This just provides a success indicator and feedback
        self.output_buffers["debug"].append("Reloading view from disk...")
        return True

    def get_output_queues(self):
        """Access to output queues for reload feedback."""
        if not hasattr(self, 'output_queues'):
            self.output_queues = {
                "status": [],
                "debug": [],
                "screenshot": []
            }
        return self.output_queues