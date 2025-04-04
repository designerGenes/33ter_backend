"""Screenshot view implementation for the terminal UI."""
import os
import json
import curses
import sys
import subprocess
import logging  # Import logging
from .base_view import BaseView
from .color_scheme import *  # Ensure color_scheme import is relative
from .path_config import get_temp_dir, get_frequency_config_file, get_screenshots_dir

# Get logger for this module
logger = logging.getLogger(__name__)

class ScreenshotView(BaseView):
    def __init__(self, stdscr, process_manager):
        super().__init__(stdscr, process_manager)
        self.view_name = "screenshot"
        self.current_frequency = 4.0  # Default
        self.is_paused = False
        self.load_screenshot_frequency()

    def draw_content(self):
        """Draw the screenshot view content."""
        max_y, max_x = self.height, self.width
        try:
            self.win.addstr(1, 2, "Screenshot Settings & Log", curses.A_BOLD | curses.A_UNDERLINE)

            # Display current frequency and status
            self.is_paused = not self.process_manager.screenshot_manager.is_running()
            status_text = "Paused" if self.is_paused else "Running"
            status_color = curses.color_pair(STATUS_STOPPED if self.is_paused else STATUS_RUNNING)
            self.win.addstr(3, 4, f"Capture Status: ")
            self.win.addstr(status_text, status_color | curses.A_BOLD)
            self.win.addstr(4, 4, f"Frequency: {self.current_frequency:.1f}s (Use ← → to adjust, 's' to set)")

            # Log Output Section
            self.win.addstr(6, 2, "Screenshot Log", curses.A_BOLD | curses.A_UNDERLINE)
            log_lines = self.process_manager.get_output("screenshot")

            # Display last few log lines
            start_line = max(0, len(log_lines) - (max_y - 9))
            for i, line in enumerate(log_lines[start_line:]):
                draw_y = 8 + i
                if draw_y >= max_y - 1:
                    break
                safe_line = line[:max_x-5]
                self.win.addstr(draw_y, 4, safe_line)

        except curses.error:
            pass

    def handle_input(self, key):
        """Handle screenshot view specific input"""
        if super().handle_input(key):
            return True

        if key == ord(' '):
            self.toggle_screenshot_pause()
        elif key == ord('o'):
            self.open_screenshots_folder()
        elif key == curses.KEY_LEFT:
            self.current_frequency = max(0.1, self.current_frequency - 0.5)
            self.save_screenshot_frequency()
        elif key == curses.KEY_RIGHT:
            self.current_frequency = min(60.0, self.current_frequency + 0.5)
            self.save_screenshot_frequency()
        elif key == ord('s'):
            new_freq = self.get_frequency_input()
            if new_freq is not None:
                self.current_frequency = new_freq
                self.save_screenshot_frequency()
        else:
            return False

        return True

    def toggle_screenshot_pause(self):
        """Toggle the screenshot capture pause state using signal files."""
        pause_signal_file = os.path.join(get_temp_dir(), "signal_pause_capture")

        if self.process_manager.screenshot_manager.is_running():
            # Currently running, so request pause
            try:
                # Create an empty file (like 'touch' command)
                with open(pause_signal_file, 'a'):
                    os.utime(pause_signal_file, None)
                self.is_paused = True  # Update UI state optimistically
                self.process_manager._add_to_buffer("screenshot", "Screenshot capture pause requested.", "info")
                logger.info("Pause signal file created.")
            except Exception as sig_e:
                logger.error(f"Error creating pause signal file: {sig_e}", exc_info=True)
                self.process_manager._add_to_buffer("status", f"Error signaling pause: {sig_e}", "error")
        else:
            # Currently paused or stopped, so request resume
            try:
                if os.path.exists(pause_signal_file):
                    os.remove(pause_signal_file)
                    logger.info("Pause signal file removed.")
                else:
                    logger.info("Pause signal file already removed or never existed.")
                self.is_paused = False  # Update UI state optimistically
                self.process_manager._add_to_buffer("screenshot", "Screenshot capture resume requested.", "info")
            except FileNotFoundError:
                # If file doesn't exist, it's already resumed or never paused
                self.is_paused = False
                logger.info("Pause signal file not found during resume request.")
                self.process_manager._add_to_buffer("screenshot", "Screenshot capture already resumed.", "info")
            except Exception as sig_e:
                logger.error(f"Error removing pause signal file: {sig_e}", exc_info=True)
                self.process_manager._add_to_buffer("status", f"Error signaling resume: {sig_e}", "error")

    def open_screenshots_folder(self):
        """Open the folder containing screenshots."""
        path = get_screenshots_dir()
        try:
            if sys.platform == "win32":
                os.startfile(path)
            elif sys.platform == "darwin":
                subprocess.Popen(["open", path])
            else:
                subprocess.Popen(["xdg-open", path])
            self.process_manager._add_to_buffer("screenshot", f"Opened folder: {path}", "info")
        except Exception as e:
            logging.error(f"Error opening screenshots folder '{path}': {e}", exc_info=True)
            self.process_manager._add_to_buffer("status", f"Error opening folder: {e}", "error")

    def load_screenshot_frequency(self):
        """Load the screenshot frequency from config file."""
        try:
            config_file = get_frequency_config_file()
            if os.path.exists(config_file):
                with open(config_file, 'r') as f:
                    config_data = json.load(f)
                    freq_value = config_data.get('frequency')
                    if freq_value is not None:
                        try:
                            freq_value = float(freq_value)
                            if 0.1 <= freq_value <= 60.0:
                                self.current_frequency = freq_value
                            else:
                                logging.warning(f"Loaded frequency {freq_value} out of range, using default.")
                                self.current_frequency = 4.0
                        except (TypeError, ValueError):
                            logging.warning(f"Invalid frequency '{freq_value}' in config, using default.")
                            self.current_frequency = 4.0
                    else:
                        self.current_frequency = 4.0
            else:
                self.current_frequency = 4.0

        except Exception as e:
            logging.error(f"Error loading frequency config: {e}", exc_info=True)
            self.current_frequency = 4.0

    def save_screenshot_frequency(self):
        """Save the current screenshot frequency to config and signal reload."""
        try:
            config_file = get_frequency_config_file()
            os.makedirs(os.path.dirname(config_file), exist_ok=True)
            with open(config_file, "w") as f:
                json.dump({'frequency': self.current_frequency}, f)
            logger.info(f"Screenshot frequency config saved: {self.current_frequency:.1f}s")

            # Signal the ScreenshotManager to reload the frequency
            try:
                signal_file = os.path.join(get_temp_dir(), "reload_frequency")
                # Create an empty file (like 'touch' command)
                with open(signal_file, 'a'):
                    os.utime(signal_file, None)
                # Update message to reflect request, not immediate change
                self.process_manager._add_to_buffer("screenshot", f"Frequency change to {self.current_frequency:.1f}s requested.", "info")
                logger.info("Frequency reload signal file created.")
            except Exception as sig_e:
                logger.error(f"Error creating frequency reload signal file: {sig_e}", exc_info=True)
                self.process_manager._add_to_buffer("status", f"Error signaling frequency reload: {sig_e}", "error")

        except Exception as e:
            logger.error(f"Error saving frequency config: {e}", exc_info=True)
            self.process_manager._add_to_buffer("status", f"Error saving frequency config: {e}", "error")

    def get_frequency_input(self):
        """Get screenshot frequency input from user."""
        height, width = self.height, self.width
        win_h = 3
        win_w = 40
        win_y = max(0, (height - win_h) // 2)
        win_x = max(0, (width - win_w) // 2)

        if win_y + win_h > height or win_x + win_w > width:
            self.process_manager._add_to_buffer("status", "Terminal too small to set frequency", "warning")
            return None

        input_win = curses.newwin(win_h, win_w, win_y, win_x)
        input_win.box()
        input_win.addstr(0, 2, " Enter Frequency (0.1-60s) ", curses.A_BOLD)
        input_win.addstr(1, 2, "> ")
        input_win.keypad(1)
        curses.curs_set(1)
        curses.echo()

        freq_str = ""
        try:
            input_win.move(1, 4)
            freq_str = input_win.getstr(4).decode('utf-8')

        except curses.error as e:
            logging.error(f"Error getting frequency input: {e}")
            freq_str = ""
        except KeyboardInterrupt:
            freq_str = ""

        finally:
            curses.noecho()
            curses.curs_set(0)
            del input_win
            self.stdscr.touchwin()
            self.stdscr.refresh()

        if freq_str:
            try:
                freq = float(freq_str)
                if 0.1 <= freq <= 60.0:
                    return freq
                else:
                    self.process_manager._add_to_buffer("status", f"Frequency {freq} out of range (0.1-60.0)", "warning")
            except ValueError:
                self.process_manager._add_to_buffer("status", f"Invalid frequency input: '{freq_str}'", "warning")
        return None

    def get_help_content(self):
        """Return help content specific to the Screenshot view."""
        return [
            ("SPACE", "Pause/Resume Screenshot Capture"),
            ("← / →", "Adjust Frequency (-/+ 0.5s)"),
            ("s", "Set Frequency (0.1-60s)"),
            ("o", "Open Screenshots Folder"),
            ("h", "Toggle Help"),
            ("q", "Quit Application"),
        ]
