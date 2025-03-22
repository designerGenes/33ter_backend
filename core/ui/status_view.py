"""Status view implementation for the terminal UI."""
import curses
from .base_view import BaseView
from .color_scheme import *

class StatusView(BaseView):
    def draw(self):
        """Draw the status view showing connection information"""
        self.draw_header("STATUS VIEW")
        
        # Socket Server Status
        socket_running = self.process_manager.is_process_running("socket")
        status_color = curses.color_pair(STATUS_RUNNING if socket_running else STATUS_STOPPED)
        status_text = "RUNNING" if socket_running else "STOPPED"
        
        self.stdscr.addstr(6, 2, "SocketIO Server: ", get_view_color("status"))
        self.stdscr.addstr(status_text, status_color | curses.A_BOLD)
        
        # Screenshot Service Status
        screenshot_running = self.process_manager.is_process_running("screenshot")
        screenshot_status = "RUNNING" if screenshot_running else "STOPPED"
        screenshot_color = curses.color_pair(STATUS_RUNNING if screenshot_running else STATUS_STOPPED)
        
        self.stdscr.addstr(7, 2, "Screenshot Service: ", get_view_color("status"))
        self.stdscr.addstr(screenshot_status, screenshot_color | curses.A_BOLD)
        
        # iOS Connections
        ios_clients = self.process_manager.get_ios_client_count()
        ios_color = curses.color_pair(CONNECTION_ACTIVE if ios_clients > 0 else STATUS_STOPPED)
        ios_icon = "📱" if ios_clients > 0 else "❌"
        
        self.stdscr.addstr(9, 2, "Connected iOS Clients: ", get_view_color("status"))
        self.stdscr.addstr(f"{ios_icon} {ios_clients}", ios_color | curses.A_BOLD)
        
        # Server Info
        if socket_running:
            config = self.process_manager.config["server"]
            self.stdscr.addstr(11, 2, "Server Configuration:", get_view_color("status") | curses.A_BOLD)
            self.stdscr.addstr(12, 4, f"Address: {config['host']}:{config['port']}", get_view_color("status"))
            self.stdscr.addstr(13, 4, f"Room: {config['room']}", get_view_color("status"))
        
        # Controls
        self.draw_controls("[R]estart Server  [S]top/Start Server  [?]Help", self.height-2)

    def handle_input(self, key):
        """Handle status view specific input"""
        if key == ord('r'):
            self.process_manager.restart_service('socket')
        elif key == ord('s'):
            if self.process_manager.is_process_running('socket'):
                self.process_manager.stop_service('socket')
            else:
                self.process_manager.start_service('socket')
