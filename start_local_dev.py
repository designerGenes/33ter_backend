import curses
import subprocess
import os
import sys
import time
import signal
import asyncio
from collections import deque
import threading
from queue import Queue
import json
import requests  # Add requests import
import logging  # Add logging import
from utils.path_config import get_config_dir  # Add path_config import

# Color pair definitions (will be initialized in TerminalHub)
HEADER_PAIR = 1
MENU_PAIR = 2
STATUS_RUNNING = 3
STATUS_STOPPED = 4
SELECTED_VIEW = 5
MAIN_VIEW = 6
SCREENSHOT_VIEW = 7
PROCESS_VIEW = 8
SOCKET_VIEW = 9

class ProcessManager:
    def __init__(self):
        self.processes = {}
        self.output_queues = {}
        self.stop_threads = {}
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
            while not self.stop_threads[name].is_set():
                line = process.stdout.readline()
                if not line and process.poll() is not None:
                    break
                if line:
                    self.output_queues[name].append(line.strip())

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
        return list(self.output_queues.get(name, []))

import os
import sys
import json
import time
import curses
import subprocess
import logging
import requests
from threading import Thread
from utils.path_config import (
    get_screenshots_dir, 
    get_app_root, 
    get_config_dir, 
    get_temp_dir,
    get_frequency_config_file
)

class TerminalHub:
    def __init__(self, force_setup=False):
        self.app_dir = get_app_root()
        self.screenshots_dir = get_screenshots_dir()
        self.venv_path = os.path.join(self.app_dir, "venv")  # Add venv path
        
        self.config = {}
        self.load_config()
        self.process_manager = ProcessManager()  # Initialize the ProcessManager
        self.current_view = "main"
        self.help_active = False
        self.post_message_active = False
        self.current_frequency = 4.0
        self.muted = False
        self.trigger_cooldown = 30  # seconds
        self.last_trigger_time = 0
        self.load_screenshot_frequency()
        os.makedirs(self.screenshots_dir, exist_ok=True)
        
        # Set up the environment if needed
        if force_setup:
            self.cleanup_venv()
        if not os.path.exists(self.venv_path):
            self.setup_venv()
        else:
            self.setup_env_vars()  # Just set up environment variables for existing venv

    def load_config(self):
        config_path = os.path.join(get_config_dir(), 'config.json')
        with open(config_path) as f:
            self.config = json.load(f)
        self.env = os.environ.copy()  # Initialize environment variables
        self.env["RUN_MODE"] = "local"  # Set RUN_MODE

    def setup_env_vars(self):
        """Set up environment variables without reinstalling"""
        self.env = os.environ.copy()
        self.env["RUN_MODE"] = "local"
        self.env["PATH"] = f"{os.path.join(self.venv_path, 'bin')}{os.pathsep}{self.env.get('PATH', '')}"
        self.env["VIRTUAL_ENV"] = self.venv_path
        
        # Remove any Conda-related environment variables
        conda_vars = ["CONDA_PREFIX", "CONDA_DEFAULT_ENV", "CONDA_EXE", "CONDA_PYTHON_EXE"]
        for var in conda_vars:
            self.env.pop(var, None)
            
        # Import required package
        try:
            import psutil
        except ImportError:
            print("Warning: psutil not available in current environment")
            print("Installing psutil...")
            try:
                pip_path = os.path.join(self.venv_path, "bin", "pip")
                subprocess.run([pip_path, "install", "psutil"], check=True)
                import psutil
            except Exception as e:
                print(f"Failed to install psutil: {e}")
                print("Continuing without process management features...")

    def cleanup_venv(self):
        """Remove existing virtual environment if it exists"""
        state_file = os.path.join(self.venv_path, '.setup_complete')
        if os.path.exists(state_file):
            try:
                os.remove(state_file)
            except Exception as e:
                print(f"Warning: Could not remove state file: {e}")
                
        if os.path.exists(self.venv_path):
            print(f"Removing existing virtual environment at {self.venv_path}")
            try:
                import shutil
                shutil.rmtree(self.venv_path)
            except Exception as e:
                print(f"Warning: Could not remove existing venv: {e}")

    def handle_conda_environment(self):
        """Detect and handle Conda environment gracefully"""
        is_conda = any(var in os.environ for var in ["CONDA_PREFIX", "CONDA_DEFAULT_ENV", "CONDA_EXE"])
        if is_conda:
            print("Detected active Conda environment...")
            try:
                # Try to get system Python path
                system_python = '/usr/bin/python3'
                if not os.path.exists(system_python):
                    # Fallback to which python3
                    result = subprocess.run(['which', 'python3'], capture_output=True, text=True)
                    if result.returncode == 0:
                        system_python = result.stdout.strip()
                    else:
                        raise Exception("Could not find system Python")
                        
                # Create new environment using system Python
                print("Switching to system Python for virtual environment...")
                os.environ.pop("CONDA_PREFIX", None)
                os.environ.pop("CONDA_DEFAULT_ENV", None)
                os.environ.pop("CONDA_EXE", None)
                os.environ.pop("CONDA_PYTHON_EXE", None)
                
                # Update PATH to remove Conda paths
                path_parts = os.environ["PATH"].split(":")
                new_path = ":".join(p for p in path_parts if "conda" not in p.lower())
                os.environ["PATH"] = new_path
                
                return system_python
            except Exception as e:
                print(f"Warning: Failed to handle Conda environment: {e}")
                print("Please deactivate Conda manually using 'conda deactivate'")
                sys.exit(1)
        return None

    def setup_venv(self):
        """Set up and validate virtual environment"""
        # Only create venv if it doesn't exist
        if not os.path.exists(self.venv_path):
            # Handle Conda environment if present
            system_python = self.handle_conda_environment()
            if not system_python:
                system_python = '/usr/bin/python3'
            
            print("Creating new virtual environment...")
            try:
                subprocess.run([system_python, "-m", "venv", self.venv_path], check=True)
            except subprocess.CalledProcessError as e:
                print(f"Error creating virtual environment: {e}")
                sys.exit(1)
        
        # Install requirements using the venv's pip
        pip_path = os.path.join(self.venv_path, "bin", "pip")
        requirements_path = os.path.join(self.app_dir, "req", "requirements.txt")
        
        print("Installing dependencies...")
        try:
            # Install requirements without upgrading pip
            subprocess.run([pip_path, "install", "-r", requirements_path], check=True)
        except Exception as e:
            print(f"Error installing dependencies: {e}")
            sys.exit(1)
            
        self.setup_env_vars()

    def repair_environment(self):
        """Repair package versions without recreating the entire environment"""
        print("Repairing environment...")
        pip_path = os.path.join(self.venv_path, "bin", "pip")
        requirements_path = os.path.join(self.app_dir, "req", "requirements.txt")
        
        try:
            # Just reinstall requirements to ensure correct versions
            subprocess.run([pip_path, "install", "-r", requirements_path, "--force-reinstall"], check=True)
            
            # Update state file
            state_file = os.path.join(self.venv_path, '.setup_complete')
            result = subprocess.run(
                [pip_path, "freeze"],
                capture_output=True,
                text=True,
                check=True
            )
            
            installed_packages = dict(line.split('==') for line in result.stdout.splitlines() 
                                   if '==' in line)
            
            with open(state_file, 'w') as f:
                json.dump({
                    'setup_complete': True,
                    'timestamp': time.time(),
                    'python_version': sys.version.split()[0],
                    'package_versions': installed_packages,
                    'last_repair': time.time()
                }, f, indent=2)
                
            return True
        except Exception as e:
            print(f"Repair failed: {e}")
            return False

    def setup_colors(self):
        """Initialize color pairs for the UI"""
        curses.start_color()
        curses.use_default_colors()
        
        # Define colors using RGB values
        curses.init_pair(HEADER_PAIR, curses.COLOR_CYAN, -1)  # Cyan header
        curses.init_pair(MENU_PAIR, 51, -1)  # Aquamarine menu text
        curses.init_pair(STATUS_RUNNING, curses.COLOR_GREEN, -1)  # Green for running status
        curses.init_pair(STATUS_STOPPED, curses.COLOR_RED, -1)  # Red for stopped status
        curses.init_pair(SELECTED_VIEW, 213, -1)  # Bright purple for selected view
        
        # New color pairs for each view
        curses.init_pair(MAIN_VIEW, 226, -1)  # Yellow for main view
        curses.init_pair(SCREENSHOT_VIEW, 118, -1)  # Light green for screenshot view
        curses.init_pair(PROCESS_VIEW, 147, -1)  # Purple for process view
        curses.init_pair(SOCKET_VIEW, 208, -1)  # Orange for socket view

    def get_view_color(self, view_name):
        """Get the color pair for a specific view"""
        color_map = {
            "main": MAIN_VIEW,
            "screenshot": SCREENSHOT_VIEW,
            "process": PROCESS_VIEW,
            "socket": SOCKET_VIEW
        }
        return curses.color_pair(color_map.get(view_name, MENU_PAIR))

    def start_services(self):
        """Start all required services"""
        # Start Screenshot Taker
        self.process_manager.start_process(
            "screenshot",
            f"{self.venv_path}/bin/python3 {os.path.join(self.app_dir, 'beginRecording.py')}",
            cwd=self.app_dir,
            env=self.env
        )

        # Start Process Screenshots server
        self.process_manager.start_process(
            "process",
            f"{self.venv_path}/bin/python3 {os.path.join(self.app_dir, 'scripts/processStream/server_process_stream.py')} --port {self.config['services']['processStream']['port']}",
            cwd=os.path.join(self.app_dir, "scripts/processStream"),
            env=self.env
        )

        # Start SocketIO Server
        socket_config = self.config['services']['publishMessage']
        self.process_manager.start_process(
            "socket",
            f"{self.venv_path}/bin/python3 {os.path.join(self.app_dir, 'scripts/publishMessage/server_socketio.py')} --port {socket_config['port']} --room {socket_config['room']}",
            cwd=os.path.join(self.app_dir, "scripts/publishMessage"),
            env=self.env
        )

    def draw_header(self, stdscr):
        height, width = stdscr.getmaxyx()
        header = "33ter Process Manager"
        
        stdscr.addstr(0, 0, "=" * width, curses.color_pair(HEADER_PAIR))
        stdscr.addstr(1, (width - len(header)) // 2, header, 
                     curses.color_pair(HEADER_PAIR) | curses.A_BOLD)
        
        # Draw menu items with different colors for selected view
        menu_items = [
            ("[1]Main", "main"),
            ("[2]Screenshot", "screenshot"),
            ("[3]Process", "process"),
            ("[4]Socket", "socket")
        ]
        
        quit_text = "[Q]uit"
        restart_text = "[R]estart Current"
        
        # Calculate positions
        total_menu_width = sum(len(item[0]) + 2 for item in menu_items)
        total_width = len(quit_text) + total_menu_width + len(restart_text) + 2
        start_pos = (width - total_width) // 2
        
        # Draw the menu bar
        stdscr.addstr(2, start_pos, quit_text, curses.color_pair(MENU_PAIR))
        current_pos = start_pos + len(quit_text) + 1
        
        for item, view in menu_items:
            color = self.get_view_color(view) if view == self.current_view else curses.color_pair(MENU_PAIR)
            if view == self.current_view:
                stdscr.addstr(2, current_pos, f"|{item}|", color | curses.A_BOLD)
                current_pos += len(item) + 2
            else:
                stdscr.addstr(2, current_pos, f" {item} ", color)
                current_pos += len(item) + 2
        
        stdscr.addstr(2, current_pos, restart_text, curses.color_pair(MENU_PAIR))
        stdscr.addstr(3, 0, "=" * width, curses.color_pair(HEADER_PAIR))

    def draw_process_output(self, stdscr, process_name):
        height, width = stdscr.getmaxyx()
        
        if process_name == "screenshot":
            self.draw_screenshot_controls(stdscr, 4)
            start_y = 8  # Start output after controls
        elif process_name == "process":
            # Draw process controls
            controls = "[M]ute Upload Messages [T]rigger Processing [?]Help"
            stdscr.addstr(4, 2, controls, curses.color_pair(MENU_PAIR))
            
            # Draw mute status
            mute_status = "MUTED" if self.muted else "UNMUTED"
            status_color = curses.color_pair(STATUS_STOPPED if self.muted else STATUS_RUNNING)
            status_pos = len(controls) + 4
            stdscr.addstr(4, status_pos, f"Status: ", self.get_view_color("process"))
            stdscr.addstr(mute_status, status_color | curses.A_BOLD)
            
            # Draw cooldown timer if active
            current_time = time.time()
            if current_time - self.last_trigger_time < self.trigger_cooldown:
                remaining = int(self.trigger_cooldown - (current_time - self.last_trigger_time))
                cooldown_msg = f" (Cooldown: {remaining}s)"
                stdscr.addstr(4, status_pos + len(f"Status: {mute_status}") + 1, 
                            cooldown_msg, curses.color_pair(STATUS_STOPPED))
            
            stdscr.addstr(5, 0, "=" * width, curses.color_pair(HEADER_PAIR))
            start_y = 6
        elif process_name == "socket":
            # Draw socket controls
            controls = "[P]ost Message [?]Help"
            stdscr.addstr(4, 2, controls, curses.color_pair(MENU_PAIR))
            stdscr.addstr(5, 0, "=" * width, curses.color_pair(HEADER_PAIR))
            start_y = 6
        else:
            start_y = 5
            
        if self.help_active:
            self.draw_help_screen(stdscr)
            return
        elif self.post_message_active and process_name == "socket":
            result = self.get_message_input(stdscr)
            self.post_message_active = False
            if result:
                message, title, log_type = result
                response = self.post_message_to_socket(message, title, log_type)
                if response:
                    self.process_manager.output_queues["socket"].append(response)
            return

        output_lines = self.process_manager.get_output(process_name)
        
        # Filter out standard upload messages if muted
        if process_name == "process" and self.muted:
            output_lines = [line for line in output_lines if not line.startswith("Saved file:")]
            
        max_lines = height - start_y
        start_line = max(0, len(output_lines) - max_lines)
        
        # Add a colored header for the current view using the view-specific color
        view_header = f"=== {process_name.upper()} OUTPUT ==="
        view_color = self.get_view_color(process_name)
        stdscr.addstr(4, (width - len(view_header)) // 2, view_header, 
                     view_color | curses.A_BOLD)
        
        for i, line in enumerate(output_lines[start_line:]):
            if i >= max_lines - 1:
                break
            try:
                stdscr.addstr(i + start_y, 0, line[:width-1])
            except curses.error:
                pass

    def draw_main_view(self, stdscr):
        height, width = stdscr.getmaxyx()
        processes = {
            "Screenshot Taker": "screenshot",
            "Process Server": "process",
            "SocketIO Server": "socket"
        }
        
        # Add a colored header for the main view using the main view color
        view_header = "=== PROCESS STATUS ==="
        view_color = self.get_view_color("main")
        stdscr.addstr(4, (width - len(view_header)) // 2, view_header, 
                     view_color | curses.A_BOLD)
        
        for i, (name, key) in enumerate(processes.items()):
            status = "RUNNING" if key in self.process_manager.processes and \
                    self.process_manager.processes[key].poll() is None else "STOPPED"
            status_color = curses.color_pair(STATUS_RUNNING) if status == "RUNNING" \
                          else curses.color_pair(STATUS_STOPPED)
            try:
                process_color = self.get_view_color(key)
                stdscr.addstr(i + 6, 2, f"{name}: ", process_color)
                stdscr.addstr(status, status_color | curses.A_BOLD)
            except curses.error:
                pass

    def load_screenshot_frequency(self):
        try:
            config_file = get_frequency_config_file()
            if os.path.exists(config_file):
                with open(config_file, 'r') as f:
                    self.current_frequency = float(json.load(f).get('frequency', 4.0))
        except Exception:
            self.current_frequency = 4.0

    def save_screenshot_frequency(self):
        try:
            config_file = get_frequency_config_file()
            with open(config_file, "w") as f:
                json.dump({'frequency': self.current_frequency}, f)
                
            # Create reload signal file
            with open(os.path.join(get_temp_dir(), "reload_frequency"), "w") as f:
                pass  # Just create the file
                
        except Exception as e:
            print(f"Error saving frequency: {e}")

    def toggle_screenshot_pause(self):
        tmp_dir = get_temp_dir()
        pause_file = os.path.join(tmp_dir, "signal_pause_capture")
        resume_file = os.path.join(tmp_dir, "signal_resume_capture")
        
        if os.path.exists(pause_file):
            os.rmdir(pause_file)
            os.makedirs(resume_file)
        else:
            if os.path.exists(resume_file):
                os.rmdir(resume_file)
            os.makedirs(pause_file)

    def open_screenshots_folder(self):
        """Open screenshots folder in Finder"""
        try:
            if sys.platform == "darwin":  # macOS
                subprocess.run(["open", self.screenshots_dir])
            elif sys.platform == "linux":  # Linux
                subprocess.run(["xdg-open", self.screenshots_dir])
            else:
                logging.error("Platform not supported for opening folders")
        except Exception as e:
            logging.error(f"Error opening screenshots folder: {e}")

    def draw_help_screen(self, stdscr):
        height, width = stdscr.getmaxyx()
        help_texts = {
            "main": [
                "Main View Help",
                "",
                "1-4: Switch between views",
                "Q: Quit application",
                "R: Restart current service",
                "ESC: Close help",
                "?: Show this help"
            ],
            "screenshot": [
                "Screenshot View Help",
                "",
                "This view manages the automatic screenshot capture service that monitors",
                "your screen for coding challenges. Screenshots are automatically captured",
                "at regular intervals and sent to the process server for OCR analysis.",
                "",
                "Space: Pause/Resume screenshot capture",
                "Left/Right: Adjust frequency by 0.5s (saves automatically)",
                "F: Enter new frequency value",
                "O: Open screenshots folder",
                "ESC: Close help",
                "?: Show this help"
            ],
            "process": [
                "Process View Help",
                "",
                "This view shows the processing of screenshots through OCR and AI analysis.",
                "Screenshots are processed using Azure Computer Vision for text extraction,",
                "followed by AI analysis to identify and solve coding challenges.",
                "",
                "M: Toggle muting of standard upload messages",
                "T: Trigger processing of latest screenshot (30s cooldown)",
                "R: Restart process service",
                "ESC: Close help",
                "?: Show this help"
            ],
            "socket": [
                "Socket View Help",
                "",
                "P: Post a new message to the chat",
                "R: Restart socket service",
                "ESC: Close help",
                "?: Show this help"
            ]
        }

        texts = help_texts.get(self.current_view, help_texts["main"])
        box_height = len(texts) + 4
        box_width = max(len(line) for line in texts) + 4
        start_y = (height - box_height) // 2
        start_x = (width - box_width) // 2

        # Draw box
        for y in range(box_height):
            for x in range(box_width):
                if y in (0, box_height-1) or x in (0, box_width-1):
                    try:
                        stdscr.addch(start_y + y, start_x + x, curses.ACS_CKBOARD, 
                                   self.get_view_color(self.current_view))
                    except curses.error:
                        pass

        # Draw text
        for i, text in enumerate(texts):
            try:
                stdscr.addstr(start_y + i + 2, start_x + 2, text, 
                            self.get_view_color(self.current_view))
            except curses.error:
                pass

    def draw_screenshot_controls(self, stdscr, start_y):
        try:
            width = stdscr.getmaxyx()[1]
            # Draw pause/resume status
            pause_file = os.path.join(get_temp_dir(), "signal_pause_capture")
            status = "PAUSED" if os.path.exists(pause_file) else "RUNNING"
            status_color = curses.color_pair(STATUS_STOPPED if status == "PAUSED" else STATUS_RUNNING)
            stdscr.addstr(start_y, 2, f"Status: ", self.get_view_color("screenshot"))
            stdscr.addstr(status, status_color | curses.A_BOLD)

            # Draw frequency control
            freq_width = int((self.current_frequency / 10) * 20)  # Scale to max 20 chars for 0-10s
            freq_bar = "| " + "-" * freq_width + str(self.current_frequency) + "-" * (20 - freq_width) + " |"
            stdscr.addstr(start_y + 1, 2, "Frequency: ", self.get_view_color("screenshot"))
            stdscr.addstr(freq_bar, self.get_view_color("screenshot") | curses.A_BOLD)
            
            # Draw controls help (added [O]pen)
            controls = "[Space]Pause [←/→]Adjust [F]Set [O]pen Folder [?]Help"
            stdscr.addstr(start_y + 2, 2, controls, curses.color_pair(MENU_PAIR))
            
            # Separator line
            stdscr.addstr(start_y + 3, 0, "=" * width, curses.color_pair(HEADER_PAIR))
        except curses.error:
            pass

    def get_frequency_input(self, stdscr):
        height, width = stdscr.getmaxyx()
        # Create a small window for input
        input_win = curses.newwin(3, 40, height//2-1, (width-40)//2)
        input_win.box()
        input_win.addstr(0, 2, " Enter Frequency (0.5-10s) ", curses.A_BOLD)
        input_win.addstr(1, 2, "> ")
        input_win.keypad(1)
        curses.echo()
        
        # Get input
        freq_str = ""
        while True:
            try:
                ch = input_win.getch()
                if ch == 10:  # Enter key
                    break
                elif ch == 27:  # Escape key
                    freq_str = ""
                    break
                elif ch in (8, 127):  # Backspace/Delete
                    if freq_str:
                        freq_str = freq_str[:-1]
                        input_win.addstr(1, 2, "> " + freq_str + " ")
                        input_win.refresh()
                elif ch >= 32:  # Printable characters
                    if len(freq_str) < 4:  # Limit input length
                        freq_str += chr(ch)
                        input_win.addstr(1, 2, "> " + freq_str)
                        input_win.refresh()
            except curses.error:
                pass
                
        curses.noecho()
        del input_win
        stdscr.touchwin()
        stdscr.refresh()
        
        if freq_str:
            try:
                freq = float(freq_str)
                if 0.5 <= freq <= 10.0:
                    return freq
            except ValueError:
                pass
        return None

    def trigger_process(self):
        """Trigger processing of the latest screenshot with cooldown."""
        current_time = time.time()
        if current_time - self.last_trigger_time < self.trigger_cooldown:
            remaining = int(self.trigger_cooldown - (current_time - self.last_trigger_time))
            return f"Please wait {remaining} seconds before triggering again"
        
        self.last_trigger_time = current_time
        try:
            process_url = f"http://localhost:{self.config['services']['processStream']['port']}/trigger"
            response = requests.post(process_url)
            if response.status_code == 200:
                return "Processing triggered successfully"
            else:
                return f"Error triggering process: {response.json().get('message', 'Unknown error')}"
        except Exception as e:
            return f"Error triggering process: {str(e)}"

    def post_message_to_socket(self, message, title="Nice shot", log_type="info"):
        """Post a message to the Socket.IO server."""
        try:
            socket_port = self.config['services']['publishMessage']['port']
            socket_room = self.config['services']['publishMessage']['room']
            
            payload = {
                "room": socket_room,
                "data": {
                    "title": title,
                    "message": message,
                    "logType": log_type
                }
            }
            
            response = requests.post(
                f"http://localhost:{socket_port}/broadcast",
                json=payload
            )
            
            if response.status_code == 200:
                return f"Message sent successfully"
            else:
                return f"Error sending message: {response.status_code}"
        except Exception as e:
            return f"Error sending message: {str(e)}"

    def get_message_input(self, stdscr):
        """Get message input from user with a form-like interface."""
        height, width = stdscr.getmaxyx()
        
        # Create input window
        form_height = 8
        form_width = 60
        win = curses.newwin(form_height, form_width, (height-form_height)//2, (width-form_width)//2)
        win.keypad(1)
        win.box()
        
        # Form fields with default values
        fields = [
            {"label": "Message", "value": "Hey man", "length": 40},
            {"label": "Type", "value": "Info", "options": ["Info", "Prime", "Warning"]},
            {"label": "Title", "value": "Nice shot", "length": 30}
        ]
        current_field = 0
        
        while True:
            win.clear()
            win.box()
            win.addstr(0, 2, " Post Message ", curses.A_BOLD)
            
            # Draw fields
            for i, field in enumerate(fields):
                y = i * 2 + 1
                win.addstr(y, 2, f"{field['label']}: ")
                
                if i == current_field:
                    attr = curses.A_BOLD | curses.A_UNDERLINE
                else:
                    attr = curses.A_NORMAL
                
                if "options" in field:
                    win.addstr(y, len(field['label']) + 4, f"< {field['value']} >", attr)
                else:
                    win.addstr(y, len(field['label']) + 4, field['value'], attr)
            
            # Draw instructions
            y = form_height - 2
            if "options" in fields[current_field]:
                win.addstr(y, 2, "← → to change, ↑ ↓ to move, Enter to submit, ESC to cancel")
            else:
                win.addstr(y, 2, "Type to edit, ↑ ↓ to move, Enter to submit, ESC to cancel")
            
            win.refresh()
            
            ch = win.getch()
            if ch == 27:  # ESC
                return None, None, None
            elif ch == 10:  # Enter
                return (fields[0]['value'],  # message
                        fields[2]['value'],  # title
                        fields[1]['value'].lower())  # type
            elif ch == curses.KEY_UP:
                current_field = (current_field - 1) % len(fields)
            elif ch == curses.KEY_DOWN:
                current_field = (current_field + 1) % len(fields)
            elif "options" in fields[current_field]:
                # Handle option cycling
                if ch == curses.KEY_LEFT:
                    options = fields[current_field]["options"]
                    current_idx = options.index(fields[current_field]["value"])
                    fields[current_field]["value"] = options[(current_idx - 1) % len(options)]
                elif ch == curses.KEY_RIGHT:
                    options = fields[current_field]["options"]
                    current_idx = options.index(fields[current_field]["value"])
                    fields[current_field]["value"] = options[(current_idx + 1) % len(options)]
            elif ch in (8, 127, curses.KEY_BACKSPACE):  # Backspace
                if not "options" in fields[current_field]:
                    fields[current_field]["value"] = fields[current_field]["value"][:-1]
            elif ch >= 32 and ch <= 126:  # Printable characters
                if not "options" in fields[current_field]:
                    if len(fields[current_field]["value"]) < fields[current_field]["length"]:
                        fields[current_field]["value"] += chr(ch)

    def run(self, stdscr):
        # Only disable click events, but allow text selection
        curses.mousemask(curses.REPORT_MOUSE_POSITION)
        
        self.setup_colors()
        stdscr.timeout(100)
        
        self.start_services()

        while True:
            stdscr.clear()
            self.draw_header(stdscr)

            if self.help_active:
                self.draw_help_screen(stdscr)
            elif self.current_view == "main":
                self.draw_main_view(stdscr)
            elif self.current_view == "screenshot":
                self.draw_process_output(stdscr, "screenshot")
            elif self.current_view == "process":
                self.draw_process_output(stdscr, "process")
            elif self.current_view == "socket":
                self.draw_process_output(stdscr, "socket")

            stdscr.refresh()

            try:
                key = stdscr.getch()
                if self.help_active:
                    if key == 27:  # ESC
                        self.help_active = False
                elif self.post_message_active:
                    if key == 27:  # ESC
                        self.post_message_active = False
                else:
                    if key == ord('q'):
                        break
                    elif key == ord('?'):
                        self.help_active = True
                    elif key == ord('1'):
                        self.current_view = "main"
                    elif key == ord('2'):
                        self.current_view = "screenshot"
                    elif key == ord('3'):
                        self.current_view = "process"
                    elif key == ord('4'):
                        self.current_view = "socket"
                    elif key == ord('r'):
                        if self.current_view in ["screenshot", "process", "socket"]:
                            self.process_manager.stop_process(self.current_view)
                            time.sleep(1)
                            self.start_services()
                    elif self.current_view == "screenshot":
                        if key == ord(' '):  # Space
                            self.toggle_screenshot_pause()
                        elif key == ord('o'):  # Open folder
                            self.open_screenshots_folder()
                        elif key == curses.KEY_LEFT:
                            self.current_frequency = max(0.5, self.current_frequency - 0.5)
                            self.save_screenshot_frequency()  # Save immediately after change
                        elif key == curses.KEY_RIGHT:
                            self.current_frequency = min(10.0, self.current_frequency + 0.5)
                            self.save_screenshot_frequency()  # Save immediately after change
                        elif key == ord('f'):
                            new_freq = self.get_frequency_input(stdscr)
                            if new_freq is not None:
                                self.current_frequency = new_freq
                                self.save_screenshot_frequency()
                                # Signal screenshot process to reload frequency
                                tmp_dir = os.path.join(self.app_dir, ".tmp")
                                os.makedirs(tmp_dir, exist_ok=True)
                                with open(os.path.join(tmp_dir, "reload_frequency"), "w") as f:
                                    f.write("")
                    elif self.current_view == "process":
                        if key == ord('m'):  # Toggle mute
                            self.muted = not self.muted
                        elif key == ord('t'):  # Trigger processing
                            result = self.trigger_process()
                            if result:
                                self.process_manager.output_queues["process"].append(result)
                    elif self.current_view == "socket":
                        if key == ord('p'):  # Post message
                            self.post_message_active = True

            except curses.error:
                pass

        self.process_manager.stop_all()

import sys
import os

# Add the utils directory to Python path
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'utils'))
from system_check import print_system_status

def main():
    import argparse
    parser = argparse.ArgumentParser(description='33ter Process Manager')
    parser.add_argument('--force-setup', action='store_true', 
                       help='Force recreation of virtual environment')
    parser.add_argument('--skip-checks', action='store_true',
                       help='Skip system requirement checks (use with caution)')
    args = parser.parse_args()
    
    if not args.skip_checks:
        print_system_status()
    
    hub = TerminalHub(force_setup=args.force_setup)
    curses.wrapper(hub.run)

if __name__ == "__main__":
    main()
