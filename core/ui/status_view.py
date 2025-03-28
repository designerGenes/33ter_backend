"""Status view implementation for the terminal UI."""
import curses
import logging
from .base_view import BaseView
from .color_scheme import *

class StatusView(BaseView):
    def __init__(self, stdscr, process_manager):
        super().__init__(stdscr, process_manager)
        self.view_name = "status"

    def draw_content(self):
        """Draw the status view content."""
        max_y, max_x = self.height, self.width
        try:
            self.win.addstr(1, 2, "System Status", curses.A_BOLD | curses.A_UNDERLINE)

            # --- Socket.IO Server Status ---
            # Use get_socketio_status() which returns a string like "Running", "Stopped", "Error", etc.
            socket_status_str = self.process_manager.get_socketio_status()
            is_socket_running = socket_status_str == "Running" # Check if the status string indicates running
            socket_status_color = curses.color_pair(STATUS_RUNNING if is_socket_running else STATUS_STOPPED)
            if "Error" in socket_status_str or "Crashed" in socket_status_str:
                 socket_status_color = curses.color_pair(STATUS_STOPPED) # Use stopped color for errors too

            self.win.addstr(3, 4, "Socket.IO Server: ")
            self.win.addstr(socket_status_str, socket_status_color | curses.A_BOLD)

            # --- Screenshot Manager Status ---
            screenshot_status_str = self.process_manager.get_screenshot_status()
            is_screenshot_running = "Running" in screenshot_status_str # Simple check if "Running" is in the status
            screenshot_status_color = curses.color_pair(STATUS_RUNNING if is_screenshot_running else STATUS_STOPPED)
            if "Error" in screenshot_status_str:
                 screenshot_status_color = curses.color_pair(STATUS_STOPPED)

            self.win.addstr(4, 4, "Screenshot Mgr:   ")
            self.win.addstr(screenshot_status_str, screenshot_status_color | curses.A_BOLD)


            # --- Log Output Section ---
            self.win.addstr(6, 2, "Status Log", curses.A_BOLD | curses.A_UNDERLINE)
            log_lines = self.process_manager.get_output("status")

            # Display last few log lines
            start_line = max(0, len(log_lines) - (max_y - 9)) # Adjust start line calculation if needed
            for i, line in enumerate(log_lines[start_line:]):
                draw_y = 8 + i
                if draw_y >= max_y - 1: # Ensure we don't write past the window boundary
                    break
                # Truncate line safely
                safe_line = line[:max_x-5] # Leave space for border/padding
                self.win.addstr(draw_y, 4, safe_line)

        except curses.error:
            # Ignore curses errors (e.g., writing outside window if resized quickly)
            pass
        except Exception as e:
            # Log other unexpected errors during drawing
            logging.error(f"Error drawing StatusView: {e}", exc_info=True)
            try:
                # Attempt to display an error message in the view
                self.win.addstr(max_y // 2, 4, f"Error drawing view: {e}", curses.A_BOLD | curses.color_pair(STATUS_STOPPED))
            except:
                pass # Ignore errors during error display


    def get_help_content(self):
        """Return help content specific to the Status view."""
        return [
            ("1", "Switch to Status View"),
            ("2", "Switch to Screenshot View"),
            ("3", "Switch to Debug View"),
            ("h", "Toggle Help"),
            ("q", "Quit Application"),
        ]
