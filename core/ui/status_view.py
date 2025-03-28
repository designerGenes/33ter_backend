"""Status view implementation for the terminal UI."""
import curses
import time
from .base_view import BaseView
from .color_scheme import *

class StatusView(BaseView):
    """Displays the overall status of managed services."""
    def __init__(self, stdscr, process_manager):
        super().__init__(stdscr, process_manager)
        self.view_name = "status"

    def draw_content(self):
        """Draw the status view content."""
        max_y, max_x = self.height, self.width
        self.win.addstr(1, 2, "System Status", curses.A_BOLD | curses.A_UNDERLINE)

        status = self.process_manager.get_status()

        # Socket.IO Status
        sio_status = status.get("socketio", "Unknown")
        sio_color = curses.color_pair(STATUS_RUNNING) if sio_status == "Running" else \
                    curses.color_pair(STATUS_STOPPED) if sio_status == "Stopped" else \
                    curses.color_pair(MENU_PAIR) # Default/Warning color for other states
        self.win.addstr(3, 4, "Socket.IO Server: ")
        self.win.addstr(sio_status, sio_color | curses.A_BOLD)
        if sio_status == "Running" and status.get("socketio_pid"):
             self.win.addstr(f" (PID: {status['socketio_pid']})")

        # Screenshot Status (Adjust y-position due to removal above)
        sc_status = status.get("screenshot", "Unknown")
        sc_color = curses.color_pair(STATUS_RUNNING) if sc_status == "Running" else \
                   curses.color_pair(STATUS_STOPPED)
        self.win.addstr(5, 4, "Screenshot Capture: ") # Changed y from 7 to 5
        self.win.addstr(sc_status, sc_color | curses.A_BOLD)

        # Log Output Section (Adjust y-position)
        self.win.addstr(7, 2, "Status Log", curses.A_BOLD | curses.A_UNDERLINE) # Changed y from 9 to 7
        log_lines = self.process_manager.get_output("status") # Assuming a 'status' buffer exists

        # Display last few log lines (Adjust y-position)
        start_line = max(0, len(log_lines) - (max_y - 10)) # Changed max_y - 12 to max_y - 10
        for i, line in enumerate(log_lines[start_line:]):
            draw_y = 9 + i # Changed y from 11 to 9
            if draw_y >= max_y - 1:
                break
            safe_line = line[:max_x-5]
            self.win.addstr(draw_y, 4, safe_line)


    def handle_input(self, key):
        """Handle status view specific input"""
        if super().handle_input(key):
            return True
        # No specific inputs for status view yet
        return False

    def get_help_content(self) -> list[tuple[str, str]]:
        """Return help content specific to the Status view."""
        return [
            ("h", "Toggle Help"),
            ("q", "Quit Application"),
            # Add other relevant global commands if needed
        ]
