"""Status view implementation for the terminal UI."""
import curses
import logging
from .base_view import BaseView
from .color_scheme import *

# Get logger for this module
logger = logging.getLogger(__name__)

class StatusView(BaseView):
    """Displays the overall status of managed services."""
    def __init__(self, stdscr, process_manager):
        super().__init__(stdscr, process_manager)
        self.view_name = "status"

    def draw_content(self):
        """Draw the status view content."""
        max_y, max_x = self.height, self.width
        try:
            self.win.addstr(1, 2, "System Status & Control", curses.A_BOLD | curses.A_UNDERLINE)

            # Get status from ProcessManager
            status = self.process_manager.get_status()

            # --- Defensive Check ---
            if not isinstance(status, dict):
                logger.error(f"Received invalid status type from ProcessManager: {type(status)}. Expected dict.")
                # Display an error message in the view
                try:
                    self.win.addstr(3, 4, "ERROR: Invalid status data received!", curses.color_pair(STATUS_STOPPED))
                except curses.error:
                    pass # Ignore if window too small even for error
                status = {} # Set to empty dict to prevent further errors in .get() calls

            # --- Service Status ---
            self.win.addstr(3, 4, "Services:", curses.A_BOLD)

            # Socket.IO Server Status
            sio_status = status.get("socketio_server", "Unknown") # Default to Unknown
            sio_color = curses.color_pair(STATUS_RUNNING) if "Running" in sio_status else \
                        curses.color_pair(STATUS_STOPPED) if "Stopped" in sio_status else \
                        curses.color_pair(MENU_PAIR) # Use menu color for Error/Unknown
            self.win.addstr(5, 6, "Socket.IO Server: ")
            self.win.addstr(sio_status, sio_color | curses.A_BOLD)

            # Screenshot Capture Status
            sc_status = status.get("screenshot_capture", "Unknown") # Default to Unknown
            sc_color = curses.color_pair(STATUS_RUNNING) if "Running" in sc_status else \
                       curses.color_pair(MENU_PAIR) if "Paused" in sc_status else \
                       curses.color_pair(STATUS_STOPPED) # Stopped or Error/Unknown
            self.win.addstr(7, 6, "Screenshot Capture: ")
            self.win.addstr(sc_status, sc_color | curses.A_BOLD)

            # Internal Client Connection Status
            internal_conn = status.get("internal_sio_connected", False)
            conn_status_text = "Connected" if internal_conn else "Disconnected"
            conn_color = curses.color_pair(CONNECTION_ACTIVE) if internal_conn else curses.color_pair(STATUS_STOPPED)
            self.win.addstr(9, 6, "Internal Client: ")
            self.win.addstr(conn_status_text, conn_color | curses.A_BOLD)

            # --- Configuration ---
            self.win.addstr(11, 4, "Configuration:", curses.A_BOLD)
            config_data = status.get("config", {})
            server_cfg = config_data.get('server', {})
            host = server_cfg.get('host', 'N/A')
            port = server_cfg.get('port', 'N/A')
            room = server_cfg.get('room', 'N/A')
            self.win.addstr(13, 6, f"Server: {host}:{port}")
            self.win.addstr(14, 6, f"Room:   {room}")

            # --- Controls ---
            self.win.addstr(max_y - 4, 4, "Controls:", curses.A_BOLD)
            controls = [
                ("1", "Start Socket.IO", "socketio_server", "Running"),
                ("2", "Stop Socket.IO", "socketio_server", "Stopped"),
                ("3", "Start Screenshot", "screenshot_capture", "Running"),
                ("4", "Stop Screenshot", "screenshot_capture", "Stopped"),
                ("0", "Stop All", None, None) # Special case for Stop All
            ]

            col_width = (max_x - 8) // 3
            for i, (key, label, service_key, target_state) in enumerate(controls):
                row = max_y - 2
                col = 4 + (i % 3) * col_width
                if col + len(f"({key}) {label}") >= max_x -1: continue # Prevent writing out of bounds

                # Determine if control should be enabled/disabled based on current status
                enabled = True
                if service_key:
                    current_service_status = status.get(service_key, "Unknown")
                    if target_state == "Running" and "Running" in current_service_status:
                        enabled = False # Don't enable "Start" if already running
                    elif target_state == "Stopped" and "Stopped" in current_service_status:
                         enabled = False # Don't enable "Stop" if already stopped

                attr = curses.A_BOLD if enabled else curses.A_DIM
                color = curses.color_pair(MENU_PAIR) if enabled else curses.A_DIM

                try:
                    self.win.addstr(row, col, f"({key}) ", curses.A_BOLD | color)
                    self.win.addstr(label, attr | color)
                except curses.error:
                    pass # Ignore if too small

        except curses.error:
            pass # Ignore drawing errors if window is too small
        except Exception as e:
            # Log other unexpected errors during drawing
            logger.error(f"Error drawing StatusView: {e}", exc_info=True)
            try:
                # Try to display an error message in the view
                self.win.addstr(max_y // 2, 2, f"ERROR drawing view: {e}", curses.color_pair(STATUS_STOPPED))
            except:
                pass # Ignore if even error message fails

    def handle_input(self, key):
        """Handle status view specific input"""
        if super().handle_input(key): # Handle help overlay first
            return True

        if key == ord('1'):
            self.process_manager.start_socketio_server()
        elif key == ord('2'):
            self.process_manager.stop_socketio_server()
        elif key == ord('3'):
            self.process_manager.start_screenshot_manager()
        elif key == ord('4'):
            self.process_manager.stop_screenshot_manager()
        elif key == ord('0'):
            self.process_manager.stop_all()
        else:
            return False # Indicate key was not handled here

        return True # Indicate key was handled

    def get_help_content(self) -> list[tuple[str, str]]:
        """Return help content specific to the Status view."""
        return [
            ("h", "Toggle Help"),
            ("q", "Quit Application"),
            # Add other relevant global commands if needed
        ]
