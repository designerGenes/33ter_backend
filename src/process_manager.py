import os
import sys
import json
import signal
import subprocess
import threading
from collections import deque
from queue import Queue
import psutil

class ProcessManager:
    def __init__(self):
        self.processes = {}
        self.output_queues = {}
        self.stop_threads = {}
        
        from utils.path_config import get_config_dir
        config_path = os.path.join(get_config_dir(), 'config.json')
        self.config = self.load_config(config_path)

    def load_config(self, config_path):
        with open(config_path) as f:
            return json.load(f)

    def start_process(self, name, cmd, cwd=None, env=None):
        """Start a process and capture its output."""
        if name in self.processes and self.processes[name].poll() is None:
            return

        # Set up basic environment if none provided
        if env is None:
            env = os.environ.copy()
            env["RUN_MODE"] = "local"

        process = subprocess.Popen(
            cmd,
            cwd=cwd,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            shell=True
        )
        
        self.processes[name] = process
        self.output_queues[name] = deque(maxlen=1000)
        self.stop_threads[name] = threading.Event()

        def output_reader():
            # Buffer for multi-line messages
            buffer = []
            
            while not self.stop_threads[name].is_set():
                line = process.stdout.readline()
                if not line and process.poll() is not None:
                    break
                    
                if name == "socket" and line.strip():
                    # For socket messages, collect until we see a separator
                    if "=" * 50 in line and buffer:
                        # Join and add the complete message
                        self.output_queues[name].append('\n'.join(buffer))
                        buffer = [line.rstrip('\n')]
                    else:
                        buffer.append(line.rstrip('\n'))
                elif line:
                    # For other processes, add lines directly
                    self.output_queues[name].append(line.rstrip('\n'))
            
            # Add any remaining buffered content
            if buffer:
                self.output_queues[name].append('\n'.join(buffer))

        thread = threading.Thread(target=output_reader, daemon=True)
        thread.start()

    def stop_process(self, name):
        if name in self.processes:
            self.stop_threads[name].set()
            try:
                pid = self.processes[name].pid
                # Only attempt psutil operations if it's available
                if 'psutil' in sys.modules:
                    parent = psutil.Process(pid)
                    children = parent.children(recursive=True)
                    for child in children:
                        child.terminate()
                    parent.terminate()
                else:
                    # Fallback to basic process termination
                    os.kill(pid, signal.SIGTERM)
            except:
                pass
            self.processes[name].terminate()
            self.processes[name].wait()
            del self.processes[name]
            del self.output_queues[name]
            del self.stop_threads[name]

    def stop_all(self):
        for name in list(self.processes.keys()):
            self.stop_process(name)

    def get_output(self, name):
        """Get raw output lines without any processing."""
        return list(self.output_queues.get(name, []))

    def restart_service(self, service_name):
        """Restart a specific service."""
        if service_name not in ["screenshot", "process", "socket"]:
            return
            
        self.stop_process(service_name)
        
        from utils.path_config import get_app_root
        app_dir = get_app_root()
        venv_path = os.path.join(app_dir, "venv")
        env = os.environ.copy()
        env["RUN_MODE"] = "local"
        
        if service_name == "screenshot":
            self.start_process(
                "screenshot",
                f"{venv_path}/bin/python3 {os.path.join(app_dir, 'beginRecording.py')}",
                cwd=app_dir,
                env=env
            )
        elif service_name == "process":
            self.start_process(
                "process",
                f"{venv_path}/bin/python3 {os.path.join(app_dir, 'scripts/processStream/server_process_stream.py')} --port {self.config['services']['processStream']['port']}",
                cwd=os.path.join(app_dir, "scripts/processStream"),
                env=env
            )
        elif service_name == "socket":
            socket_config = self.config['services']['publishMessage']
            self.start_process(
                "socket",
                f"{venv_path}/bin/python3 {os.path.join(app_dir, 'scripts/publishMessage/server_socketio.py')} --port {socket_config['port']} --room {socket_config['room']}",
                cwd=os.path.join(app_dir, "scripts/publishMessage"),
                env=env
            )