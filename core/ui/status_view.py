"""Status view implementation for the terminal UI."""
import curses
import time
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
            # Service Status Section
            self.win.addstr(1, 2, "Service Status", curses.A_BOLD | curses.A_UNDERLINE)

            # Placeholder: Replace with actual status checks
            socket_status = self.process_manager.is_process_running('socket')
            screenshot_status = self.process_manager.screenshot_manager.is_running()

            socket_color = curses.color_pair(STATUS_RUNNING if socket_status else STATUS_STOPPED)
            screenshot_color = curses.color_pair(STATUS_RUNNING if screenshot_status else STATUS_STOPPED)

            self.win.addstr(3, 4, "SocketIO Server: ")
            self.win.addstr("Running" if socket_status else "Stopped", socket_color | curses.A_BOLD)

            self.win.addstr(4, 4, "Screenshot Capture: ")
            self.win.addstr("Running" if screenshot_status else "Stopped", screenshot_color | curses.A_BOLD)

            # Connection Status Section
            self.win.addstr(6, 2, "Connection Status", curses.A_BOLD | curses.A_UNDERLINE)

            # Safely get iOS client count, default to 0 if None or not an int
            ios_clients = self.process_manager.get_ios_client_count()
            if not isinstance(ios_clients, int):
                 ios_clients = 0 # Default to 0 if the value is None or unexpected type

            local_connected = self.process_manager.local_connected
            room_joined = self.process_manager.room_joined

            ios_color = curses.color_pair(CONNECTION_ACTIVE if ios_clients > 0 else STATUS_STOPPED)
            local_color = curses.color_pair(CONNECTION_ACTIVE if local_connected else STATUS_STOPPED)
            room_color = curses.color_pair(CONNECTION_ACTIVE if room_joined else STATUS_STOPPED)

            self.win.addstr(8, 4, f"iOS Clients Connected: {ios_clients}", ios_color | curses.A_BOLD)
            self.win.addstr(9, 4, f"Local Client Connected: {'Yes' if local_connected else 'No'}", local_color | curses.A_BOLD)
            self.win.addstr(10, 4, f"Joined Room: {'Yes' if room_joined else 'No'}", room_color | curses.A_BOLD)

            # Log Output Section
            self.win.addstr(12, 2, "Status Log", curses.A_BOLD | curses.A_UNDERLINE)

            log_lines = self.process_manager.get_output("status")

            # Display last few log lines
            start_line = max(0, len(log_lines) - (max_y - 15)) # Calculate how many lines fit
            for i, line in enumerate(log_lines[start_line:]):
                draw_y = 14 + i
                if draw_y >= max_y - 1: break # Prevent writing outside window

                # Basic coloring based on level
                color = curses.A_NORMAL
                if "[ERROR]" in line:
                    color = curses.color_pair(STATUS_STOPPED) | curses.A_BOLD
                elif "[WARNING]" in line:
                    color = curses.color_pair(MENU_PAIR) | curses.A_BOLD

                # Truncate line safely
                safe_line = line[:max_x-5]
                self.win.addstr(draw_y, 4, safe_line, color)

        except curses.error as e:
             # Ignore drawing errors (e.g., terminal too small)
             pass

    def get_help_content(self) -> list[tuple[str, str]]:
        """Return help content specific to the Status view."""
        return [
            ("1, 2, 3", "Switch Views (Status, Screenshot, Debug)"),
            ("q", "Quit Application"),
            ("h", "Toggle Help"),
            # Add any Status view specific help here if needed
        ]
