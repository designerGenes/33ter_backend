import curses
import os
import sys
import subprocess
import json
import re
import requests
import time
from utils.path_config import get_temp_dir

from .terminal_ui import (
    TerminalUI,
    STATUS_RUNNING,
    STATUS_STOPPED,
    MENU_PAIR,
    HEADER_PAIR
)

class ViewManager:
    def __init__(self, process_manager, config):
        self.process_manager = process_manager
        self.config = config
        self.ui = TerminalUI()

    def strip_ansi(self, text):
        """Remove ANSI escape sequences from text."""
        ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
        return ansi_escape.sub('', text)

class MainViewManager(ViewManager):
    def draw(self, stdscr):
        height, width = stdscr.getmaxyx()
        processes = {
            "Screenshot Taker": "screenshot",
            "Process Server": "process",
            "SocketIO Server": "socket"
        }
        
        view_header = "=== PROCESS STATUS ==="
        view_color = self.ui.get_view_color("main")
        stdscr.addstr(4, (width - len(view_header)) // 2, view_header, 
                     view_color | curses.A_BOLD)
        
        for i, (name, key) in enumerate(processes.items()):
            status = "RUNNING" if key in self.process_manager.processes and \
                    self.process_manager.processes[key].poll() is None else "STOPPED"
            status_color = curses.color_pair(STATUS_RUNNING) if status == "RUNNING" \
                          else curses.color_pair(STATUS_STOPPED)
            try:
                process_color = self.ui.get_view_color(key)
                stdscr.addstr(i + 6, 2, f"{name}: ", process_color)
                stdscr.addstr(status, status_color | curses.A_BOLD)
            except curses.error:
                pass

class ScreenshotViewManager(ViewManager):
    def __init__(self, process_manager, config):
        super().__init__(process_manager, config)
        self.current_frequency = 4.0
        self.load_screenshot_frequency()

    def load_screenshot_frequency(self):
        from utils.path_config import get_frequency_config_file
        try:
            config_file = get_frequency_config_file()
            if os.path.exists(config_file):
                with open(config_file, 'r') as f:
                    self.current_frequency = float(json.load(f).get('frequency', 4.0))
        except Exception:
            self.current_frequency = 4.0

    def save_screenshot_frequency(self):
        from utils.path_config import get_frequency_config_file, get_temp_dir
        try:
            config_file = get_frequency_config_file()
            with open(config_file, "w") as f:
                json.dump({'frequency': self.current_frequency}, f)
                
            # Create reload signal file
            with open(os.path.join(get_temp_dir(), "reload_frequency"), "w") as f:
                pass
                
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
        from utils.path_config import get_screenshots_dir
        try:
            screenshots_dir = get_screenshots_dir()
            if sys.platform == "darwin":  # macOS
                subprocess.run(["open", screenshots_dir])
            elif sys.platform == "linux":  # Linux
                subprocess.run(["xdg-open", screenshots_dir])
        except Exception as e:
            print(f"Error opening screenshots folder: {e}")

    def draw_controls(self, stdscr, start_y):
        try:
            width = stdscr.getmaxyx()[1]
            # Draw pause/resume status
            pause_file = os.path.join(get_temp_dir(), "signal_pause_capture")
            status = "PAUSED" if os.path.exists(pause_file) else "RUNNING"
            status_color = curses.color_pair(STATUS_STOPPED if status == "PAUSED" else STATUS_RUNNING)
            stdscr.addstr(start_y, 2, f"Status: ", self.ui.get_view_color("screenshot"))
            stdscr.addstr(status, status_color | curses.A_BOLD)

            # Draw frequency control
            freq_width = int((self.current_frequency / 10) * 20)
            freq_bar = "| " + "-" * freq_width + str(self.current_frequency) + "-" * (20 - freq_width) + " |"
            stdscr.addstr(start_y + 1, 2, "Frequency: ", self.ui.get_view_color("screenshot"))
            stdscr.addstr(freq_bar, self.ui.get_view_color("screenshot") | curses.A_BOLD)
            
            controls = "[Space]Pause [←/→]Adjust [F]Set [O]pen Folder [?]Help"
            stdscr.addstr(start_y + 2, 2, controls, curses.color_pair(MENU_PAIR))
            
            stdscr.addstr(start_y + 3, 0, "=" * width, curses.color_pair(HEADER_PAIR))
        except curses.error:
            pass

    def get_frequency_input(self, stdscr):
        height, width = stdscr.getmaxyx()
        input_win = curses.newwin(3, 40, height//2-1, (width-40)//2)
        input_win.box()
        input_win.addstr(0, 2, " Enter Frequency (0.5-10s) ", curses.A_BOLD)
        input_win.addstr(1, 2, "> ")
        input_win.keypad(1)
        curses.echo()
        
        freq_str = ""
        while True:
            try:
                ch = input_win.getch()
                if ch == 10:  # Enter
                    break
                elif ch == 27:  # Escape
                    freq_str = ""
                    break
                elif ch in (8, 127):  # Backspace
                    if freq_str:
                        freq_str = freq_str[:-1]
                        input_win.addstr(1, 2, "> " + freq_str + " ")
                        input_win.refresh()
                elif ch >= 32:  # Printable
                    if len(freq_str) < 4:
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

class ProcessViewManager(ViewManager):
    def __init__(self, process_manager, config):
        super().__init__(process_manager, config)
        self.last_trigger_time = 0
        self.trigger_cooldown = 30

    def trigger_process(self):
        current_time = time.time()
        if current_time - self.last_trigger_time < self.trigger_cooldown:
            remaining = int(self.trigger_cooldown - (current_time - self.last_trigger_time))
            return f"Please wait {remaining} seconds before triggering again"
        
        self.last_trigger_time = current_time
        try:
            process_url = f"http://localhost:{self.config['services']['processStream']['port']}/trigger"
            response = requests.post(process_url)
            if response.status_code == 204:
                return "Processing triggered successfully"
            else:
                return f"Error triggering process: {response.status_code}"
        except Exception as e:
            return f"Error connecting to process server: {str(e)}"

class SocketViewManager(ViewManager):
    def post_message_to_socket(self, message, title="Nice shot", log_type="info"):
        try:
            # Format message
            from utils.socketio_utils import format_socket_message
            formatted_message = format_socket_message(title, message, log_type)
            
            # Add to local display queue
            self.process_manager.output_queues["socket"].append(formatted_message)
            
            # Send to server
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
            
            if response.status_code != 200:
                error_msg = f"Error sending message: {response.status_code}"
                self.process_manager.output_queues["socket"].append(error_msg)
                return error_msg
                
            return None
            
        except Exception as e:
            error_msg = f"Error sending message: {str(e)}"
            self.process_manager.output_queues["socket"].append(error_msg)
            return error_msg

    def get_message_input(self, stdscr):
        height, width = stdscr.getmaxyx()
        form_height = 8
        form_width = 60
        win = curses.newwin(form_height, form_width, (height-form_height)//2, (width-form_width)//2)
        win.keypad(1)
        win.box()
        
        fields = [
            {"label": "Title", "value": "Nice shot", "length": 30},
            {"label": "Type", "value": "Info", "options": ["Info", "Prime", "Warning"]},
            {"label": "Message", "value": "Hey man", "length": 40}
        ]
        current_field = 0
        
        while True:
            win.clear()
            win.box()
            win.addstr(0, 2, " Socket Message ", curses.A_BOLD)
            
            for i, field in enumerate(fields):
                y = i * 2 + 1
                label = f"{field['label']}: "
                win.addstr(y, 2, label)
                
                if i == current_field:
                    attr = curses.A_BOLD | curses.A_UNDERLINE
                else:
                    attr = curses.A_NORMAL
                
                if "options" in field:
                    value_text = f"< {field['value']} >"
                    color = self.ui.get_view_color("socket") if field['value'] == "Info" else \
                           curses.color_pair(STATUS_RUNNING) if field['value'] == "Prime" else \
                           curses.color_pair(STATUS_STOPPED)  # For Warning
                    win.addstr(y, len(label) + 2, value_text, attr | color)
                else:
                    win.addstr(y, len(label) + 2, field['value'], attr)
            
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
                return (fields[2]['value'],  # message
                        fields[0]['value'],  # title
                        fields[1]['value'].lower())  # type
            elif ch == curses.KEY_UP:
                current_field = (current_field - 1) % len(fields)
            elif ch == curses.KEY_DOWN:
                current_field = (current_field + 1) % len(fields)
            elif "options" in fields[current_field]:
                if ch == curses.KEY_LEFT:
                    options = fields[current_field]["options"]
                    current_idx = options.index(fields[current_field]["value"])
                    fields[current_field]["value"] = options[(current_idx - 1) % len(options)]
                elif ch == curses.KEY_RIGHT:
                    options = fields[current_field]["options"]
                    current_idx = options.index(fields[current_field]["value"])
                    fields[current_field]["value"] = options[(current_idx + 1) % len(options)]
            elif ch in (8, 127, curses.KEY_BACKSPACE):
                if not "options" in fields[current_field]:
                    fields[current_field]["value"] = fields[current_field]["value"][:-1]
            elif ch >= 32 and ch <= 126:
                if not "options" in fields[current_field]:
                    if len(fields[current_field]["value"]) < fields[current_field]["length"]:
                        fields[current_field]["value"] += chr(ch)