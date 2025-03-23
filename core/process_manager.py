"""Process management module for 33ter application."""
import os
import sys
import time
import json
import logging
import subprocess
import socketio
import threading
from typing import Dict, Optional, List, Union
from utils import get_logs_dir, get_screenshots_dir, get_temp_dir
from utils import get_server_config
import glob
from .screenshot_manager import ScreenshotManager
from .message_system import MessageManager, MessageLevel, MessageCategory

class ProcessManager:
    """Manages the various service processes for the 33ter application."""
    
    def __init__(self):
        self.config = get_server_config()
        self.logger = self._setup_logging()
        self.processes: Dict[str, subprocess.Popen] = {}
        
        # Initialize legacy output buffers for backwards compatibility
        self.output_buffers: Dict[str, list] = {
            'screenshot': [],
            'debug': []
        }
        
        # Initialize the message manager
        self.message_manager = MessageManager()
        
        self.ios_clients_connected = 0
        self.local_connected = False
        self.socketio_client = None
        self.screenshot_manager = ScreenshotManager()
        self.room_joined = False
        
        # OCR processing status tracking
        self.ocr_processing_active = False
        self.last_ocr_time = 0
        self.ocr_lock = threading.Lock()
        
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

            room_name = '33ter_room'
            self.config['server']['room'] = room_name

            server_host = '0.0.0.0'
            client_host = '0.0.0.0'
            port = 5348

            command = [
                sys.executable,
                server_script,
                '--host', server_host,
                '--port', str(port),
                '--room', room_name,
                '--log-level', 'DEBUG'
            ]
            
            process = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1
            )
            
            self.processes['socket'] = process
            self.logger.info(f"Started SocketIO server on {server_host}:{port} (PID: {process.pid})")
            
            time.sleep(2)
            
            max_retries = 3
            retry_delay = 1
            
            for attempt in range(max_retries):
                try:
                    sio = socketio.Client(logger=False, engineio_logger=False)
                    
                    @sio.event
                    def connect():
                        self.logger.info("Socket.IO client connected to server")
                        self.local_connected = True
                        # Log connection status to debug buffer
                        timestamp = time.strftime("%H:%M:%S")
                        self.output_buffers["debug"].append(f"{timestamp}: {{")
                        self.output_buffers["debug"].append(f"    type: info,")
                        self.output_buffers["debug"].append(f"    value: Local client connected to SocketIO server,")
                        self.output_buffers["debug"].append(f"    from: system")
                        self.output_buffers["debug"].append("}")
                    
                    @sio.event
                    def disconnect():
                        self.logger.info("Socket.IO client disconnected from server")
                        self.local_connected = False
                        self.room_joined = False
                        # Log disconnection to debug buffer
                        timestamp = time.strftime("%H:%M:%S")
                        self.output_buffers["debug"].append(f"{timestamp}: {{")
                        self.output_buffers["debug"].append(f"    type: info,")
                        self.output_buffers["debug"].append(f"    value: Local client disconnected from SocketIO server,")
                        self.output_buffers["debug"].append(f"    from: system")
                        self.output_buffers["debug"].append("}")
                    
                    @sio.on('client_count')
                    def on_client_count(data):
                        if 'count' in data:
                            # Subtract our local connection from count
                            prev_count = self.ios_clients_connected
                            count = data['count']
                            if self.local_connected and count > 0:
                                count -= 1
                            self.ios_clients_connected = count
                            self.logger.info(f"iOS clients connected: {self.ios_clients_connected}")
                            
                            # Log client count changes
                            if prev_count != count:
                                timestamp = time.strftime("%H:%M:%S") 
                                self.output_buffers["debug"].append(f"{timestamp}: {{")
                                self.output_buffers["debug"].append(f"    type: info,")
                                self.output_buffers["debug"].append(f"    value: iOS client count changed: {prev_count} -> {count},")
                                self.output_buffers["debug"].append(f"    from: system")
                                self.output_buffers["debug"].append("}")
                    
                    @sio.on('message')
                    def on_message(data):
                        """Handle incoming socket messages with improved logging and processing."""
                        try:
                            # Log detailed information about the received message
                            self.logger.info(f"SOCKET MESSAGE RECEIVED: {json.dumps(data)}")
                            
                            # Log received messages to debug output in JSON format
                            if isinstance(data, dict):
                                msg_type = data.get('messageType', 'unknown')
                                msg_from = data.get('from', 'unknown')
                                value = data.get('value', '')
                                
                                # Generate consistent timestamp for this message
                                timestamp = time.strftime("%H:%M:%S")
                                
                                # Log more detailed info for debugging
                                log_message = f"Message received - Type: {msg_type}, From: {msg_from}, Value: {value}"
                                self.logger.info(log_message)
                                
                                # Critical: Check if this message is from an external source (not our own client)
                                # and log it, but don't modify the message value
                                if msg_from != "localBackend":
                                    # This is a message from an external source
                                    self.logger.info(f"EXTERNAL MESSAGE from {msg_from}: {value}")
                                
                                # Add message to debug buffer without modifying the value
                                self.output_buffers["debug"].append(f"{timestamp}: {{")
                                self.output_buffers["debug"].append(f"    type: {msg_type},")
                                self.output_buffers["debug"].append(f"    value: {value},")
                                self.output_buffers["debug"].append(f"    from: {msg_from}")
                                self.output_buffers["debug"].append("}")
                                
                                # Add to new message system too
                                self.message_manager.add_message(
                                    content=f"Message: {value}",
                                    level=MessageLevel.INFO if msg_type != "warning" else MessageLevel.WARNING,
                                    category=MessageCategory.SOCKET,
                                    source=msg_from,
                                    buffer_name="debug",
                                    metadata={"type": msg_type, "value": value}
                                )
                                
                                # If message is of type 'trigger', process the latest screenshot
                                if msg_type == 'trigger':
                                    # Rate limiting - check last OCR processing time
                                    current_time = time.time()
                                    if hasattr(self, 'last_ocr_time') and (current_time - self.last_ocr_time < 2.0):
                                        # Less than 2 seconds since last OCR, skip
                                        timestamp = time.strftime("%H:%M:%S")
                                        self.output_buffers["debug"].append(f"{timestamp}: {{")
                                        self.output_buffers["debug"].append(f"    type: info,")
                                        self.output_buffers["debug"].append(f"    value: Ignoring rapid trigger request (rate limited),")
                                        self.output_buffers["debug"].append(f"    from: system")
                                        self.output_buffers["debug"].append("}")
                                        return
                                        
                                    self.last_ocr_time = current_time
                                    
                                    # Add info message about triggering OCR
                                    timestamp = time.strftime("%H:%M:%S")
                                    self.output_buffers["debug"].append(f"{timestamp}: {{")
                                    self.output_buffers["debug"].append(f"    type: info,")
                                    self.output_buffers["debug"].append(f"    value: Received trigger message. Processing latest screenshot...,")
                                    self.output_buffers["debug"].append(f"    from: system")
                                    self.output_buffers["debug"].append("}")
                                    
                                    # Process in the main thread to avoid threading issues with SocketIO
                                    self.process_and_send_ocr_result()
                        except Exception as e:
                            # Log any errors during message processing
                            error_msg = f"Error processing received message: {str(e)}"
                            self.logger.error(error_msg)
                            self.logger.error(traceback.format_exc())
                            timestamp = time.strftime("%H:%M:%S")
                            self.output_buffers["debug"].append(f"{timestamp}: {{")
                            self.output_buffers["debug"].append(f"    ERROR: {error_msg}")
                            self.output_buffers["debug"].append("}")
                    
                    url = f"http://{client_host}:{port}"
                    self.logger.info(f"Attempting to connect to SocketIO server at {url} (attempt {attempt + 1})")
                    
                    # Connect with headers to identify as Python client
                    headers = {
                        'User-Agent': 'Python/33ter-Client-LocalBackend'  # Clear identifier
                    }
                    sio.connect(url, headers=headers, wait_timeout=5)
                    self.socketio_client = sio
                    
                    # Explicitly join the room
                    sio.emit('join_room', {'room': room_name}, callback=self._room_join_callback)
                    self.logger.info(f"Join room request sent for '{room_name}'")
                    
                    time.sleep(0.5)
                    
                    self._add_to_buffer("debug", f"Connected to SocketIO server and attempting to join room '{room_name}'", "info")
                    return
                    
                except Exception as e:
                    if attempt < max_retries - 1:
                        self.logger.warning(f"Connection attempt {attempt + 1} failed, retrying in {retry_delay}s: {e}")
                        time.sleep(retry_delay)
                    else:
                        raise
            
        except Exception as e:
            self.logger.error(f"Failed to start SocketIO service: {e}")
            if 'socket' in self.processes:
                self.stop_service('socket')
            raise
    
    def _room_join_callback(self, success):
        """Callback for room join operation."""
        if success:
            self.room_joined = True
            self._add_to_buffer("debug", f"Successfully joined room '{self.config['server']['room']}'", "info")
            self.logger.info(f"Room join successful for '{self.config['server']['room']}'")
        else:
            self.room_joined = False
            error_msg = f"Failed to join room '{self.config['server']['room']}'"
            self._add_to_buffer("debug", error_msg, "error")
            self.logger.error(error_msg)

    def _add_to_buffer(self, buffer_name: str, message: str, level: str = "info"):
        """Add a formatted message to a specific output buffer."""
        # For all debug messages, let's use the JSON-style format instead of the emoji format
        if buffer_name == "debug":
            timestamp = time.strftime("%H:%M:%S")
            
            # Special handling for received messages
            if "Received message:" in message:
                # Extract message details
                parts = message.split(", ")
                msg_type = next((p.split("=")[1] for p in parts if p.startswith("type=")), "unknown")
                msg_from = next((p.split("=")[1] for p in parts if p.startswith("from=")), "unknown")
                value = next((p.split("=")[1] for p in parts if p.startswith("value=")), "")
                
                # Format in JSON-like style
                self.output_buffers[buffer_name].append(f"{timestamp}: {{")
                self.output_buffers[buffer_name].append(f"    type: {msg_type},")
                self.output_buffers[buffer_name].append(f"    value: {value},")
                self.output_buffers[buffer_name].append(f"    from: {msg_from}")
                self.output_buffers[buffer_name].append("}")
                return
            
            # Format sending messages
            if "Sending message:" in message:
                # Extract message details
                parts = message.split(", ")
                msg_type = next((p.split("=")[1] for p in parts if p.startswith("type=")), "unknown")
                value = next((p.split("=")[1] for p in parts if p.startswith("value=")), "")
                
                # Format in JSON-like style
                self.output_buffers[buffer_name].append(f"{timestamp}: {{")
                self.output_buffers[buffer_name].append(f"    type: {msg_type},")
                self.output_buffers[buffer_name].append(f"    value: {value},")
                self.output_buffers[buffer_name].append(f"    from: localBackend")
                self.output_buffers[buffer_name].append("}")
                return
                
            # Handle errors
            if "error" in level.lower():
                self.output_buffers[buffer_name].append(f"{timestamp}: {{")
                self.output_buffers[buffer_name].append(f"    ERROR: {message}")
                self.output_buffers[buffer_name].append("}")
                return
                
            # Handle all other debug messages in JSON format
            self.output_buffers[buffer_name].append(f"{timestamp}: {{")
            self.output_buffers[buffer_name].append(f"    type: info,")
            self.output_buffers[buffer_name].append(f"    value: {message},")
            self.output_buffers[buffer_name].append(f"    from: system")
            self.output_buffers[buffer_name].append("}")
        else:
            # For non-debug buffers, keep using the old format but without emojis
            timestamp = time.strftime("%H:%M:%S")
            self.output_buffers[buffer_name].append(f"{timestamp} {message} ({level})")
        
        # Keep legacy buffer size manageable
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
                        self.room_joined = False
                        self.local_connected = False
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
            # Use the new message system but return in legacy format for compatibility
            messages = self.message_manager.get_formatted_messages("debug")
            
            # Fall back to the legacy buffer if new system has no messages
            if not messages:
                return self.output_buffers["debug"]
                
            return messages
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

    def post_message_to_socket(self, value: str, messageType: str):
        """Post a message to the SocketIO server using standardized format."""
        if not self.socketio_client:
            error_msg = "SocketIO client not connected - Use [R]estart Server in Status view"
            timestamp = time.strftime("%H:%M:%S")
            self.output_buffers["debug"].append(f"{timestamp}: {{")
            self.output_buffers["debug"].append(f"    ERROR: {error_msg}")
            self.output_buffers["debug"].append("}")
            return error_msg
            
        if not self.socketio_client.connected:
            error_msg = "SocketIO client not connected to server - Use [R]estart Server in Status view"
            timestamp = time.strftime("%H:%M:%S")
            self.output_buffers["debug"].append(f"{timestamp}: {{")
            self.output_buffers["debug"].append(f"    ERROR: {error_msg}")
            self.output_buffers["debug"].append("}")
            return error_msg
            
        try:
            # Add message in JSON format
            timestamp = time.strftime("%H:%M:%S")
            self.output_buffers["debug"].append(f"{timestamp}: {{")
            self.output_buffers["debug"].append(f"    type: {messageType},")
            self.output_buffers["debug"].append(f"    value: {value},")
            self.output_buffers["debug"].append(f"    from: localBackend")
            self.output_buffers["debug"].append("}")
            
            # Standardized message format
            formatted_message = {
                "messageType": messageType,
                "from": "localBackend",
                "value": value
            }
            
            # Get room from config
            room = self.config['server']['room']
            
            # Check if we've joined the room
            if not self.room_joined:
                # Try to join the room again
                self.logger.warning("Not joined to room, attempting to join before sending message")
                self.socketio_client.emit('join_room', {'room': room}, callback=self._room_join_callback)
                time.sleep(0.5)  # Brief wait for callback
                
                if not self.room_joined:
                    error_msg = f"Not joined to room '{room}' - messages may not be delivered properly"
                    self.message_manager.add_message(
                        content=error_msg,
                        level=MessageLevel.ERROR,
                        category=MessageCategory.SOCKET,
                        buffer_name="debug"
                    )
                    return error_msg
            
            # Send the message
            self.socketio_client.emit('message', formatted_message)
            
            # Add iOS client info if any are connected
            if self.ios_clients_connected > 0:
                status = f"({self.ios_clients_connected} iOS client{'s' if self.ios_clients_connected != 1 else ''} online)"
                self.message_manager.add_message(
                    content=status,
                    level=MessageLevel.INFO,
                    category=MessageCategory.SOCKET,
                    buffer_name="debug"
                )
            
            return None
            
        except Exception as e:
            error_msg = f"Failed to send message: {str(e)}"
            
            # Add error in JSON-like format
            timestamp = time.strftime("%H:%M:%S")
            self.output_buffers["debug"].append(f"{timestamp}: {{")
            self.output_buffers["debug"].append(f"    ERROR: {error_msg}")
            self.output_buffers["debug"].append("}")
            
            self.logger.error(error_msg)
            return error_msg

    def reload_screen(self):
        """Force a reload of the current view's code from disk."""
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

    def process_and_send_ocr_result(self):
        """Process the latest screenshot with OCR and send results to SocketIO room."""
        # Use a lock to prevent concurrent OCR processing
        if not self.ocr_lock.acquire(blocking=False):
            timestamp = time.strftime("%H:%M:%S")
            self.output_buffers["debug"].append(f"{timestamp}: {{")
            self.output_buffers["debug"].append(f"    type: info,")
            self.output_buffers["debug"].append(f"    value: OCR processing already in progress. Skipping.,")
            self.output_buffers["debug"].append(f"    from: system")
            self.output_buffers["debug"].append("}")
            return False
            
        try:
            # Check for screenshots
            screenshots_dir = get_screenshots_dir()
            screenshots = glob.glob(os.path.join(screenshots_dir, "*.png"))
            
            if not screenshots:
                timestamp = time.strftime("%H:%M:%S")
                self.output_buffers["debug"].append(f"{timestamp}: {{")
                self.output_buffers["debug"].append(f"    ERROR: No screenshots available for OCR processing")
                self.output_buffers["debug"].append("}")
                return False
            
            # Get OCR result
            ocr_result = self.screenshot_manager.process_latest_screenshot()
            
            if not ocr_result or not isinstance(ocr_result, str) or not ocr_result.strip():
                # Log error if OCR failed or returned no text
                timestamp = time.strftime("%H:%M:%S")
                self.output_buffers["debug"].append(f"{timestamp}: {{")
                self.output_buffers["debug"].append(f"    ERROR: OCR processing failed or no text found")
                self.output_buffers["debug"].append("}")
                return False
            
            # Format OCR result - remove extra whitespace and ensure it's a clean string
            formatted_result = ' '.join(ocr_result.strip().split())
            
            # Send OCR result to SocketIO room
            self.post_message_to_socket(
                value=formatted_result,
                messageType="ocrResult"
            )
            
            # Log success
            timestamp = time.strftime("%H:%M:%S")
            preview = formatted_result[:50] + "..." if len(formatted_result) > 50 else formatted_result
            self.output_buffers["debug"].append(f"{timestamp}: {{")
            self.output_buffers["debug"].append(f"    type: info,")
            self.output_buffers["debug"].append(f"    value: OCR processing successful. Text preview: {preview},")
            self.output_buffers["debug"].append(f"    from: system")
            self.output_buffers["debug"].append("}")
            
            return True
        except Exception as e:
            # Log error
            timestamp = time.strftime("%H:%M:%S")
            error_msg = f"OCR processing error: {str(e)}"
            self.output_buffers["debug"].append(f"{timestamp}: {{")
            self.output_buffers["debug"].append(f"    ERROR: {error_msg}")
            self.output_buffers["debug"].append("}")
            self.logger.error(error_msg)
            return False
        finally:
            self.ocr_lock.release()