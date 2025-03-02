"""Process management module for 33ter application."""
import os
import sys
import time
import logging
import subprocess
from typing import Dict, Optional

from utils import get_logs_dir, get_screenshots_dir
from utils import get_server_config

class ProcessManager:
    """Manages the various service processes for the 33ter application."""
    
    def __init__(self):
        self.config = get_server_config()
        self.logger = self._setup_logging()
        self.processes: Dict[str, subprocess.Popen] = {}
        self.output_buffers: Dict[str, list] = {
            'screenshot': [],
            'process': [],
            'socket': []
        }
        
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
            env = os.environ.copy()
            command = []
            
            if service_name == 'socket':
                command = [
                    sys.executable,
                    'socketio_server/server.py',
                    '--host', self.config['server']['host'],
                    '--port', str(self.config['server']['port']),
                    '--room', self.config['server']['room']
                ]
            elif service_name == 'screenshot':
                command = [sys.executable, 'socketio_server/client.py']
            else:
                self.logger.error(f"Unknown service: {service_name}")
                return
                
            # Start the process
            process = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                env=env
            )
            
            self.processes[service_name] = process
            self.logger.info(f"Started {service_name} service (PID: {process.pid})")
            
            # Start output monitoring
            self._monitor_output(service_name, process)
            
        except Exception as e:
            self.logger.error(f"Failed to start {service_name} service: {e}")

    def stop_service(self, service_name: str):
        """Stop a specific service process."""
        if service_name not in self.processes:
            return
            
        try:
            process = self.processes[service_name]
            
            # Try graceful shutdown first
            if process.poll() is None:  # Process is still running
                process.terminate()
                try:
                    process.wait(timeout=5)  # Wait up to 5 seconds
                except subprocess.TimeoutExpired:
                    process.kill()  # Force kill if it doesn't exit
            
            self.processes.pop(service_name)
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
        for service_name in list(self.processes.keys()):
            self.stop_service(service_name)

    def is_process_running(self, service_name: str) -> bool:
        """Check if a specific service is running."""
        if service_name not in self.processes:
            return False
            
        process = self.processes[service_name]
        return process.poll() is None

    def get_output(self, service_name: str) -> list:
        """Get the output buffer for a specific service."""
        return self.output_buffers.get(service_name, [])

    def _monitor_output(self, service_name: str, process: subprocess.Popen):
        """Monitor and store process output."""
        def _read_output():
            while True:
                if process.poll() is not None:  # Process has ended
                    break
                    
                line = process.stdout.readline()
                if not line:
                    break
                    
                # Add to output buffer, maintaining a reasonable size
                buffer = self.output_buffers.setdefault(service_name, [])
                buffer.append(line.strip())
                
                # Keep buffer size manageable
                if len(buffer) > 1000:
                    buffer.pop(0)
        
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

    def get_service_status(self) -> Dict[str, bool]:
        """Get the status of all services."""
        return {
            name: self.is_process_running(name)
            for name in ['socket', 'screenshot']
        }