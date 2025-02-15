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

    def start_process(self, name, cmd, cwd=None, env=None):
        if name in self.processes and self.processes[name].poll() is None:
            return

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

class TerminalHub:
    def __init__(self, force_setup=False):
        self.process_manager = ProcessManager()
        self.current_view = "main"
        self.views = ["main", "screenshot", "process", "socket"]
        self.app_dir = os.path.dirname(os.path.abspath(__file__))
        self.venv_path = os.path.join(self.app_dir, "venv")
        self._environment_validated = False
        
        if force_setup:
            print("Force setup requested...")
            self.cleanup_venv()
            self.setup_venv()
        else:
            validation_result = self.validate_environment()
            if not validation_result:
                if os.path.exists(self.venv_path) and validation_result == "VERSION_MISMATCH":
                    print("Package version mismatch detected, attempting repair...")
                    if self.repair_environment():
                        print("Environment repaired successfully")
                    else:
                        print("Repair failed, performing full setup...")
                        self.cleanup_venv()
                        self.setup_venv()
                else:
                    print("Environment needs setup...")
                    self.cleanup_venv()
                    self.setup_venv()
            else:
                print("Environment validated, using existing setup...")
                self.setup_env_vars()
        
    def validate_environment(self):
        """Check if the virtual environment is properly set up with all requirements"""
        if self._environment_validated:
            return True
            
        # Check for state file that indicates successful setup
        state_file = os.path.join(self.venv_path, '.setup_complete')
        if os.path.exists(state_file):
            try:
                with open(state_file, 'r') as f:
                    state = json.loads(f.read())
                    if state.get('setup_complete', False):
                        # Verify installed package versions match requirements
                        pip_path = os.path.join(self.venv_path, "bin", "pip")
                        requirements_path = os.path.join(self.app_dir, "req", "requirements.txt")
                        
                        # Get installed versions
                        result = subprocess.run(
                            [pip_path, "freeze"],
                            capture_output=True,
                            text=True
                        )
                        if result.returncode != 0:
                            print("Failed to get installed package versions")
                            return False
                            
                        installed_packages = dict(line.split('==') for line in result.stdout.splitlines() 
                                               if '==' in line)
                        
                        # Read required versions
                        with open(requirements_path, 'r') as f:
                            required_packages = {}
                            for line in f:
                                line = line.strip()
                                if line and not line.startswith('#') and '==' in line:
                                    name, version = line.split('==')
                                    required_packages[name] = version
                        
                        # Check critical packages and their versions
                        critical_packages = {
                            "psutil", "pyautogui", "python-socketio",
                            "aiohttp", "zeroconf", "python-dotenv"
                        }
                        
                        version_mismatch = False
                        for package in critical_packages:
                            if package not in installed_packages:
                                print(f"Critical package missing: {package}")
                                return False
                            if package in required_packages:
                                if installed_packages[package] != required_packages[package]:
                                    print(f"Version mismatch for {package}: "
                                          f"installed={installed_packages[package]}, "
                                          f"required={required_packages[package]}")
                                    version_mismatch = True
                        
                        if version_mismatch:
                            return "VERSION_MISMATCH"
                        
                        self._environment_validated = True
                        return True
                        
            except Exception as e:
                print(f"State file validation failed: {e}")
                return False
                
        return False
            
    def setup_env_vars(self):
        """Set up environment variables without reinstalling"""
        self.env = os.environ.copy()
        self.env["RUN_MODE"] = "local"
        self.env["PATH"] = f"{os.path.join(self.venv_path, 'bin')}:{self.env.get('PATH', '')}"
        self.env["VIRTUAL_ENV"] = self.venv_path
        
        # Remove any Conda-related environment variables
        conda_vars = ["CONDA_PREFIX", "CONDA_DEFAULT_ENV", "CONDA_EXE", "CONDA_PYTHON_EXE"]
        for var in conda_vars:
            self.env.pop(var, None)
            
        # Import required package
        try:
            global psutil
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
                global psutil
                psutil = None

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
        venv_path = os.path.join(self.app_dir, "venv")
        
        # Handle Conda environment if present
        system_python = self.handle_conda_environment()
        if not system_python:
            system_python = '/usr/bin/python3'
        
        print("Creating new virtual environment...")
        try:
            subprocess.run([system_python, "-m", "venv", venv_path], check=True)
        except subprocess.CalledProcessError as e:
            print(f"Error creating virtual environment: {e}")
            sys.exit(1)
        
        # Install requirements using the venv's pip
        pip_path = os.path.join(venv_path, "bin", "pip")
        requirements_path = os.path.join(self.app_dir, "req", "requirements.txt")
        
        print("Installing dependencies...")
        try:
            # Ensure pip is up to date first
            subprocess.run([pip_path, "install", "--upgrade", "pip"], check=True)
            # Install requirements
            subprocess.run([pip_path, "install", "-r", requirements_path], check=True)
            
            # Create state file with package versions
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
                    'package_versions': installed_packages
                }, f, indent=2)
                
        except Exception as e:
            print(f"Error installing dependencies: {e}")
            sys.exit(1)
            
        self.venv_path = venv_path
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
            f"{self.venv_path}/bin/python3 beginRecording.py",
            cwd=self.app_dir,
            env=self.env
        )

        # Start Process Screenshots server
        self.process_manager.start_process(
            "process",
            f"{self.venv_path}/bin/python3 server_process_stream.py",
            cwd=os.path.join(self.app_dir, "scripts/processStream"),
            env=self.env
        )

        # Start SocketIO Server
        self.process_manager.start_process(
            "socket",
            f"{self.venv_path}/bin/python3 server_socketio.py",
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
        output_lines = self.process_manager.get_output(process_name)
        max_lines = height - 5
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
                stdscr.addstr(i + 5, 0, line[:width-1])
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

    def run(self, stdscr):
        # Disable mouse events
        curses.mousemask(0)
        
        self.setup_colors()
        stdscr.timeout(100)
        
        self.start_services()

        while True:
            stdscr.clear()
            self.draw_header(stdscr)

            if self.current_view == "main":
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
                if key == ord('q'):
                    break
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
            except curses.error:
                pass

        self.process_manager.stop_all()

def main():
    import argparse
    parser = argparse.ArgumentParser(description='33ter Process Manager')
    parser.add_argument('--force-setup', action='store_true', 
                       help='Force recreation of virtual environment')
    args = parser.parse_args()
    
    hub = TerminalHub(force_setup=args.force_setup)
    curses.wrapper(hub.run)

if __name__ == "__main__":
    main()
