"""Screenshot view implementation for the terminal UI."""
import os
import json
import curses
import sys
import subprocess
from .base_view import BaseView
from .color_scheme import *
from utils import get_temp_dir, get_frequency_config_file

class ScreenshotView(BaseView):
    def __init__(self, stdscr, process_manager):
        super().__init__(stdscr, process_manager)
        self.view_name = "screenshot"
        self.current_frequency = 4.0
        self.load_screenshot_frequency()

    def draw_content(self):
        """Draw the screenshot view content."""
        self.draw_header("SCREENSHOT LOG")
        
        # Service status
        pause_file = os.path.join(get_temp_dir(), "signal_pause_capture")
        status = "PAUSED" if os.path.exists(pause_file) else "RUNNING"
        status_color = curses.color_pair(STATUS_STOPPED if status == "PAUSED" else STATUS_RUNNING)
        status_icon = "⏸️ " if status == "PAUSED" else "▶️ "
        
        self.stdscr.addstr(6, 2, f"Status: ", get_view_color("screenshot"))
        self.stdscr.addstr(f"{status_icon}{status}", status_color | curses.A_BOLD)

        # Frequency control
        freq_width = int((self.current_frequency / 10.0) * 20)
        freq_bar = "▍" * freq_width + "░" * (20 - freq_width)
        
        self.stdscr.addstr(7, 2, "Frequency: ", get_view_color("screenshot"))
        self.stdscr.addstr(freq_bar, get_view_color("screenshot") | curses.A_BOLD)
        self.stdscr.addstr(f" {self.current_frequency:.1f}s", get_view_color("screenshot"))
        
        # Controls
        self.draw_controls("⌨️  Space:Pause  ◀️ ▶️ :Adjust  ⚡️S:Set  📂O:Open", 9)
        
        # Output
        start_y = 11
        output_lines = self.process_manager.get_output("screenshot")
        if output_lines:
            for i, line in enumerate(output_lines[-self.height+start_y:]):
                try:
                    self.stdscr.addstr(start_y + i, 2, line)
                except curses.error:
                    break

    def handle_input(self, key):
        """Handle screenshot view specific input"""
        if super().handle_input(key):  # Handle help overlay
            return
            
        if key == ord(' '):
            self.toggle_screenshot_pause()
        elif key == ord('o'):
            self.open_screenshots_folder()
        elif key == curses.KEY_LEFT:
            self.current_frequency = max(0.5, self.current_frequency - 0.5)
            self.save_screenshot_frequency()
        elif key == curses.KEY_RIGHT:
            self.current_frequency = min(10.0, self.current_frequency + 0.5)
            self.save_screenshot_frequency()
        elif key == ord('s'):  # Changed from 'f' to 's'
            new_freq = self.get_frequency_input()
            if new_freq:
                self.current_frequency = new_freq
                self.save_screenshot_frequency()

    def open_screenshots_folder(self):
        """Open the screenshots folder in the system file explorer."""
        # Use main screenshots directory instead of temp
        screenshots_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "screenshots")
        if not os.path.exists(screenshots_dir):
            os.makedirs(screenshots_dir)
        try:
            if os.name == 'nt':  # Windows
                os.startfile(screenshots_dir)
            elif os.name == 'posix':  # macOS and Linux
                subprocess.run(['open' if sys.platform == 'darwin' else 'xdg-open', screenshots_dir])
        except Exception as e:
            print(f"Error opening screenshots folder: {e}")

    def load_screenshot_frequency(self):
        """Load the screenshot frequency from config file."""
        try:
            config_file = get_frequency_config_file()
            if os.path.exists(config_file):
                with open(config_file, 'r') as f:
                    config = json.load(f)
                    self.current_frequency = float(config.get('frequency', 4.0))
        except Exception:
            self.current_frequency = 4.0

    def save_screenshot_frequency(self):
        """Save the current screenshot frequency to config."""
        try:
            config_file = get_frequency_config_file()
            with open(config_file, "w") as f:
                json.dump({'frequency': self.current_frequency}, f)
                
            # Create reload signal file
            with open(os.path.join(get_temp_dir(), "reload_frequency"), "w") as f:
                pass
                
        except Exception as e:
            print(f"Error saving frequency: {e}")

    def get_frequency_input(self):
        """Get screenshot frequency input from user."""
        height, width = self.height, self.width
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
                elif ch in (8, 127):  # Backspace/Delete
                    if freq_str:
                        freq_str = freq_str[:-1]
                        input_win.addstr(1, 2, "> " + freq_str + " ")
                        input_win.refresh()
                elif ch >= 32:  # Printable characters
                    if len(freq_str) < 4:
                        freq_str += chr(ch)
                        input_win.addstr(1, 2, "> " + freq_str)
                        input_win.refresh()
            except curses.error:
                pass
                
        curses.noecho()
        
        # Cleanup window
        input_win.clear()
        input_win.refresh()
        del input_win
        self.stdscr.touchwin()
        self.stdscr.refresh()
        
        if freq_str:
            try:
                freq = float(freq_str)
                if 0.5 <= freq <= 10.0:
                    return freq
            except ValueError:
                pass
        return None

    def toggle_screenshot_pause(self):
        """Toggle screenshot capture pause state."""
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

    def get_help_content(self):
        """Get help content for screenshot view."""
        return [
            "This view manages the screenshot capture service.",
            "Screenshots are taken at regular intervals and",
            "automatically cleaned up when older than 3 minutes.",
            "",
            "Controls:",
            "Space: Pause/Resume screenshot capture",
            "←→: Adjust frequency by 0.5s",
            "S: Set exact frequency (0.5-10s)",  # Changed from F to S
            "O: Open screenshots folder",
            "",
            "Status Icons:",
            "▶️  Capture running",
            "⏸️  Capture paused",
            "📸 Screenshot taken",
            "🗑️  Old screenshots cleaned",
            "",
            "Frequency Bar:",
            "▍ Current frequency setting",
            "░ Available frequency range"
        ]
