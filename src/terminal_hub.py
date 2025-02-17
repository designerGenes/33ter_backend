import curses
import os
import sys
import json
import subprocess
from utils.path_config import (
    get_app_root,
    get_config_dir,
    get_screenshots_dir
)
from utils.system_check import print_system_status
from src.process_manager import ProcessManager
from src.ui.terminal_ui import TerminalUI
from src.ui.view_managers import (
    MainViewManager,
    ScreenshotViewManager,
    ProcessViewManager,
    SocketViewManager
)

class TerminalHub:
    def __init__(self, force_setup=False):
        self.app_dir = get_app_root()
        self.screenshots_dir = get_screenshots_dir()
        self.venv_path = os.path.join(self.app_dir, "venv")
        
        self.config = {}
        self.load_config()
        
        # Set up the environment if needed
        if force_setup:
            self.cleanup_venv()
        if not os.path.exists(self.venv_path):
            self.setup_venv()
        else:
            self.setup_env_vars()

        self.process_manager = ProcessManager()
        self.ui = TerminalUI()
        
        # Initialize view managers
        self.view_managers = {
            "main": MainViewManager(self.process_manager, self.config),
            "screenshot": ScreenshotViewManager(self.process_manager, self.config),
            "process": ProcessViewManager(self.process_manager, self.config),
            "socket": SocketViewManager(self.process_manager, self.config)
        }
        
        os.makedirs(self.screenshots_dir, exist_ok=True)

    def load_config(self):
        config_path = os.path.join(get_config_dir(), 'config.json')
        with open(config_path) as f:
            self.config = json.load(f)

    def setup_env_vars(self):
        """Set up environment variables without reinstalling"""
        self.env = os.environ.copy()
        self.env["RUN_MODE"] = "local"
        self.env["PATH"] = f"{os.path.join(self.venv_path, 'bin')}{os.pathsep}{self.env.get('PATH', '')}"
        self.env["VIRTUAL_ENV"] = self.venv_path
        
        conda_vars = ["CONDA_PREFIX", "CONDA_DEFAULT_ENV", "CONDA_EXE", "CONDA_PYTHON_EXE"]
        for var in conda_vars:
            self.env.pop(var, None)
            
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
                print("Continuing without process management features...")  # Fixed syntax

    def cleanup_venv(self):
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
        is_conda = any(var in os.environ for var in ["CONDA_PREFIX", "CONDA_DEFAULT_ENV", "CONDA_EXE"])
        if is_conda:
            print("Detected active Conda environment...")
            try:
                system_python = '/usr/bin/python3'
                if not os.path.exists(system_python):
                    result = subprocess.run(['which', 'python3'], capture_output=True, text=True)
                    if result.returncode == 0:
                        system_python = result.stdout.strip()
                    else:
                        raise Exception("Could not find system Python")
                        
                print("Switching to system Python for virtual environment...")
                os.environ.pop("CONDA_PREFIX", None)
                os.environ.pop("CONDA_DEFAULT_ENV", None)
                os.environ.pop("CONDA_EXE", None)
                os.environ.pop("CONDA_PYTHON_EXE", None)
                
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
        if not os.path.exists(self.venv_path):
            system_python = self.handle_conda_environment()
            if not system_python:
                system_python = '/usr/bin/python3'
            
            print("Creating new virtual environment...")
            try:
                subprocess.run([system_python, "-m", "venv", self.venv_path], check=True)
            except subprocess.CalledProcessError as e:
                print(f"Error creating virtual environment: {e}")
                sys.exit(1)
        
        pip_path = os.path.join(self.venv_path, "bin", "pip")
        requirements_path = os.path.join(self.app_dir, "req", "requirements.txt")
        
        print("Installing dependencies...")
        try:
            subprocess.run([pip_path, "install", "-r", requirements_path], check=True)
        except Exception as e:
            print(f"Error installing dependencies: {e}")
            sys.exit(1)
            
        self.setup_env_vars()

    def start_services(self):
        """Start all required services"""
        self.process_manager.start_process(
            "screenshot",
            f"{self.venv_path}/bin/python3 {os.path.join(self.app_dir, 'beginRecording.py')}",
            cwd=self.app_dir,
            env=self.env
        )

        self.process_manager.start_process(
            "process",
            f"{self.venv_path}/bin/python3 {os.path.join(self.app_dir, 'scripts/processStream/server_process_stream.py')} --port {self.config['services']['processStream']['port']}",
            cwd=os.path.join(self.app_dir, "scripts/processStream"),
            env=self.env
        )

        socket_config = self.config['services']['publishMessage']
        self.process_manager.start_process(
            "socket",
            f"{self.venv_path}/bin/python3 {os.path.join(self.app_dir, 'scripts/publishMessage/server_socketio.py')} --port {socket_config['port']} --room {socket_config['room']}",
            cwd=os.path.join(self.app_dir, "scripts/publishMessage"),
            env=self.env
        )

    def run(self, stdscr):
        curses.mousemask(curses.REPORT_MOUSE_POSITION)
        self.ui.setup_colors()
        stdscr.timeout(100)
        
        self.start_services()

        while True:
            stdscr.clear()
            self.ui.draw_header(stdscr)
            current_view = self.ui.current_view
            
            if self.ui.help_active:
                self.ui.draw_help_screen(stdscr)
            else:
                current_manager = self.view_managers[current_view]
                if current_view == "main":
                    current_manager.draw(stdscr)
                else:
                    if current_view == "screenshot":
                        current_manager.draw_controls(stdscr, 4)
                    else:
                        controls = "[T]rigger Processing [?]Help" if current_view == "process" else "[P]ost Message [?]Help"
                        stdscr.addstr(4, 2, controls, curses.color_pair(2))  # MENU_PAIR
                        
                    if not (self.ui.post_message_active and current_view == "socket"):
                        output = self.process_manager.get_output(current_view)
                        # Display output handling is done in respective view managers

            stdscr.refresh()

            try:
                key = stdscr.getch()
                if self.ui.help_active:
                    if key == 27:  # ESC
                        self.ui.help_active = False
                elif self.ui.post_message_active and current_view == "socket":
                    if key == 27:  # ESC
                        self.ui.post_message_active = False
                    else:
                        result = self.view_managers["socket"].get_message_input(stdscr)
                        self.ui.post_message_active = False
                        if result:
                            message, title, log_type = result
                            self.view_managers["socket"].post_message_to_socket(message, title, log_type)
                elif key == ord('?'):
                    self.ui.help_active = True
                elif key == ord('q'):
                    break
                elif key == ord('r'):
                    self.process_manager.restart_service(current_view)
                elif key in (ord('1'), ord('2'), ord('3'), ord('4')):
                    self.ui.current_view = {
                        ord('1'): "main",
                        ord('2'): "screenshot",
                        ord('3'): "process",
                        ord('4'): "socket"
                    }[key]
                elif current_view == "screenshot":
                    screenshot_manager = self.view_managers["screenshot"]
                    if key == ord(' '):
                        screenshot_manager.toggle_screenshot_pause()
                    elif key == ord('o'):
                        screenshot_manager.open_screenshots_folder()
                    elif key == curses.KEY_LEFT:
                        screenshot_manager.current_frequency = max(0.5, screenshot_manager.current_frequency - 0.5)
                        screenshot_manager.save_screenshot_frequency()
                    elif key == curses.KEY_RIGHT:
                        screenshot_manager.current_frequency = min(10.0, screenshot_manager.current_frequency + 0.5)
                        screenshot_manager.save_screenshot_frequency()
                    elif key == ord('f'):
                        new_freq = screenshot_manager.get_frequency_input(stdscr)
                        if new_freq is not None:
                            screenshot_manager.current_frequency = new_freq
                            screenshot_manager.save_screenshot_frequency()
                elif current_view == "process":
                    if key == ord('t'):
                        result = self.view_managers["process"].trigger_process()
                        if result:
                            self.process_manager.output_queues["process"].append(result)
                elif current_view == "socket":
                    if key == ord('p'):
                        self.ui.post_message_active = True

            except curses.error:
                pass

        self.process_manager.stop_all()

def main():
    import argparse
    parser = argparse.ArgumentParser(description='33ter Process Manager')
    parser.add_argument('--force-setup', action='store_true', 
                       help='Force recreation of virtual environment')
    parser.add_argument('--skip-checks', action='store_true',
                       help='Skip system requirement checks')
    args = parser.parse_args()
    
    if not args.skip_checks:
        print_system_status()
    
    hub = TerminalHub(force_setup=args.force_setup)
    curses.wrapper(hub.run)

if __name__ == "__main__":
    main()