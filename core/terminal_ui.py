import curses
import os
import re
import json
import time

from utils import (
    get_screenshots_dir, 
    get_temp_dir, 
    get_frequency_config_file
)

# Color pair definitions
HEADER_PAIR = 1
MENU_PAIR = 2
STATUS_RUNNING = 3
STATUS_STOPPED = 4
SELECTED_VIEW = 5
STATUS_VIEW = 6
SCREENSHOT_VIEW = 7
DEBUG_VIEW = 8
CONNECTION_ACTIVE = 9

class TerminalUI:
    """
    Terminal UI handler for the 33ter application.
    Manages the curses interface, user input, and display.
    """
    
    def __init__(self, process_manager):
        self.process_manager = process_manager
        self.current_view = "status"  # Changed default view
        self.help_active = False
        self.post_message_active = False
        self.current_frequency = 4.0
        self.trigger_cooldown = 30  # seconds
        self.last_trigger_time = 0
        self.screenshots_dir = get_screenshots_dir()
        self.stdscr = None
        self.load_screenshot_frequency()

    def setup_colors(self):
        """Initialize color pairs for the UI"""
        curses.start_color()
        curses.use_default_colors()
        
        # Define colors using RGB values
        curses.init_pair(HEADER_PAIR, curses.COLOR_CYAN, -1)  # Cyan header
        curses.init_pair(MENU_PAIR, 51, -1)  # Aquamarine menu text
        curses.init_pair(STATUS_RUNNING, curses.COLOR_GREEN, -1)  # Green for running
        curses.init_pair(STATUS_STOPPED, curses.COLOR_RED, -1)  # Red for stopped
        curses.init_pair(SELECTED_VIEW, 213, -1)  # Bright purple for selected
        
        # Colors for each view
        curses.init_pair(STATUS_VIEW, 226, -1)  # Yellow for status view
        curses.init_pair(SCREENSHOT_VIEW, 118, -1)  # Light green for screenshot
        curses.init_pair(DEBUG_VIEW, 208, -1)  # Orange for debug view
        curses.init_pair(CONNECTION_ACTIVE, 46, -1)  # Bright green for active connections

    def get_view_color(self, view_name):
        """Get the color pair for a specific view"""
        color_map = {
            "status": STATUS_VIEW,
            "screenshot": SCREENSHOT_VIEW,
            "debug": DEBUG_VIEW
        }
        return curses.color_pair(color_map.get(view_name, MENU_PAIR))

    def draw_header(self, stdscr):
        """Draw the application header and menu bar"""
        height, width = stdscr.getmaxyx()
        header = "33ter"
        
        stdscr.addstr(0, 0, "=" * width, curses.color_pair(HEADER_PAIR))
        stdscr.addstr(1, (width - len(header)) // 2, header, 
                     curses.color_pair(HEADER_PAIR) | curses.A_BOLD)
        
        # Updated menu items for new layout
        menu_items = [
            ("[1]Status", "status"),
            ("[2]Screenshot", "screenshot"),
            ("[3]Debug", "debug")
        ]
        
        quit_text = "[Q]uit"
        help_text = "[?]Help"
        
        # Calculate positions
        total_menu_width = sum(len(item[0]) + 2 for item in menu_items)
        total_width = len(quit_text) + total_menu_width + len(help_text) + 2
        start_pos = (width - total_width) // 2
        
        # Draw the menu bar
        stdscr.addstr(2, start_pos, quit_text, curses.color_pair(MENU_PAIR))
        current_pos = start_pos + len(quit_text) + 1
        
        for item, view in menu_items:
            color = self.get_view_color(view) if view == self.current_view else curses.color_pair(MENU_PAIR)
            if view == self.current_view:
                stdscr.addstr(2, current_pos, f"|{item}|", color | curses.A_BOLD)
            else:
                stdscr.addstr(2, current_pos, f" {item} ", color)
            current_pos += len(item) + 2
        
        stdscr.addstr(2, current_pos, help_text, curses.color_pair(MENU_PAIR))
        stdscr.addstr(3, 0, "=" * width, curses.color_pair(HEADER_PAIR))

    def strip_ansi(self, text):
        """Remove ANSI escape sequences from text."""
        ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
        return ansi_escape.sub('', text)

    def draw_process_output(self, stdscr, process_name):
        """Draw the output of a specific process view"""
        height, width = stdscr.getmaxyx()
        
        if process_name == "screenshot":
            self.draw_screenshot_controls(stdscr, 4)
            start_y = 8
        elif process_name == "debug":
            self.draw_debug_controls(stdscr, 4)
            start_y = 6
        else:
            start_y = 5
            
        if self.help_active:
            self.draw_help_screen(stdscr)
            return
        elif self.post_message_active and process_name == "debug":
            result = self.get_message_input(stdscr)
            self.post_message_active = False
            if result:
                message, title, log_type = result
                self.process_manager.post_message_to_socket(message, title, log_type)
            return

        # Get and filter output
        output_lines = self.process_manager.get_output(process_name)
        if not output_lines:
            view_color = self.get_view_color(process_name)
            empty_msg = "(No messages)" if process_name == "debug" else "(No screenshot events)"
            try:
                stdscr.addstr(start_y + 2, (width - len(empty_msg)) // 2, 
                             empty_msg, view_color | curses.A_DIM)
            except curses.error:
                pass
            return
            
        # Calculate visible range
        max_lines = height - start_y - 1
        start_line = max(0, len(output_lines) - max_lines)
        
        # Draw header
        view_header = f"=== {'DEBUG' if process_name == 'debug' else 'SCREENSHOT'} LOG ==="
        view_color = self.get_view_color(process_name)
        stdscr.addstr(4, (width - len(view_header)) // 2, view_header, 
                     view_color | curses.A_BOLD)
        
        # Draw output lines
        current_y = start_y
        for line in output_lines[start_line:]:
            if current_y >= height - 1:
                break
                
            try:
                # Parse line components (timestamp, emoji, message, level)
                parts = line.split(" ", 3)
                if len(parts) == 4:
                    timestamp, emoji, message, level = parts
                    level = level.strip("()")
                    
                    # Draw timestamp
                    x = 2
                    stdscr.addstr(current_y, x, timestamp)
                    x += len(timestamp) + 1
                    
                    # Draw emoji
                    stdscr.addstr(current_y, x, emoji)
                    x += len(emoji) + 1
                    
                    # Draw message with appropriate color
                    msg_color = {
                        'info': curses.color_pair(MENU_PAIR),
                        'prime': curses.color_pair(SELECTED_VIEW),
                        'warning': curses.color_pair(STATUS_STOPPED),
                        'error': curses.color_pair(STATUS_STOPPED) | curses.A_BOLD
                    }.get(level.lower(), curses.A_NORMAL)
                    
                    stdscr.addstr(current_y, x, message, msg_color)
                else:
                    stdscr.addstr(current_y, 2, line[:width-3])
                    
                current_y += 1
                
            except curses.error:
                break

    def draw_status_view(self, stdscr):
        """Draw the status view showing connection information"""
        height, width = stdscr.getmaxyx()
        
        # Header
        header = "=== STATUS VIEW ==="
        view_color = self.get_view_color("status")
        stdscr.addstr(4, (width - len(header)) // 2, header, view_color | curses.A_BOLD)
        
        # Socket Server Status
        socket_running = self.process_manager.is_process_running("socket")
        status_color = curses.color_pair(STATUS_RUNNING if socket_running else STATUS_STOPPED)
        status_text = "RUNNING" if socket_running else "STOPPED"
        
        stdscr.addstr(6, 2, "SocketIO Server: ", view_color)
        stdscr.addstr(status_text, status_color | curses.A_BOLD)
        
        # Screenshot Service Status
        screenshot_running = self.process_manager.is_process_running("screenshot")
        screenshot_status = "RUNNING" if screenshot_running else "STOPPED"
        screenshot_color = curses.color_pair(STATUS_RUNNING if screenshot_running else STATUS_STOPPED)
        
        stdscr.addstr(7, 2, "Screenshot Service: ", view_color)
        stdscr.addstr(screenshot_status, screenshot_color | curses.A_BOLD)
        
        # iOS Connections with icon
        ios_clients = self.process_manager.get_ios_client_count()
        ios_color = curses.color_pair(CONNECTION_ACTIVE if ios_clients > 0 else STATUS_STOPPED)
        ios_icon = "📱" if ios_clients > 0 else "❌"
        
        stdscr.addstr(9, 2, "Connected iOS Clients: ", view_color)
        stdscr.addstr(f"{ios_icon} {ios_clients}", ios_color | curses.A_BOLD)
        
        # Server Info
        if socket_running:
            config = self.process_manager.config["server"]
            stdscr.addstr(11, 2, "Server Configuration:", view_color | curses.A_BOLD)
            stdscr.addstr(12, 4, f"Address: {config['host']}:{config['port']}", view_color)
            stdscr.addstr(13, 4, f"Room: {config['room']}", view_color)
            stdscr.addstr(14, 4, f"CORS: {config['cors_origins']}", view_color)
        
        # Controls
        controls = "[R]estart Server  [S]top/Start Server  [?]Help"
        stdscr.addstr(height-2, 2, controls, curses.color_pair(MENU_PAIR))

    def draw_screenshot_controls(self, stdscr, start_y):
        """Draw screenshot service controls"""
        try:
            width = stdscr.getmaxyx()[1]
            
            # Service status
            pause_file = os.path.join(get_temp_dir(), "signal_pause_capture")
            status = "PAUSED" if os.path.exists(pause_file) else "RUNNING"
            status_color = curses.color_pair(STATUS_STOPPED if status == "PAUSED" else STATUS_RUNNING)
            status_icon = "⏸️ " if status == "PAUSED" else "▶️ "
            
            stdscr.addstr(start_y, 2, f"Status: ", self.get_view_color("screenshot"))
            stdscr.addstr(f"{status_icon}{status}", status_color | curses.A_BOLD)

            # Draw frequency control with visual indicator
            freq = self.current_frequency
            freq_width = int((freq / 10.0) * 20)  # Scale to 20 chars max
            freq_bar = "▍" * freq_width + "░" * (20 - freq_width)
            
            stdscr.addstr(start_y + 1, 2, "Frequency: ", self.get_view_color("screenshot"))
            stdscr.addstr(freq_bar, self.get_view_color("screenshot") | curses.A_BOLD)
            stdscr.addstr(f" {freq:.1f}s", self.get_view_color("screenshot"))
            
            # Draw controls help with icons
            controls = "⌨️  Space:Pause  ◀️ ▶️ :Adjust  ⚡️F:Set  📂O:Open  ❔?:Help"
            stdscr.addstr(start_y + 2, 2, controls, curses.color_pair(MENU_PAIR))
            
            # Separator line
            stdscr.addstr(start_y + 3, 0, "=" * width, curses.color_pair(HEADER_PAIR))
            
        except curses.error:
            pass

    def draw_debug_controls(self, stdscr, start_y):
        """Draw debug view controls"""
        try:
            width = stdscr.getmaxyx()[1]
            
            # iOS Connection Status
            ios_clients = self.process_manager.get_ios_client_count()
            status_icon = "📱" if ios_clients > 0 else "❌"
            status_text = f"{status_icon} {ios_clients} iOS client{'s' if ios_clients != 1 else ''}"
            status_color = curses.color_pair(CONNECTION_ACTIVE if ios_clients > 0 else STATUS_STOPPED)
            
            # Draw controls
            controls = "📝P:Post Message  🔄R:Clear  ❔?:Help"
            status_x = width - len(status_text) - 2
            
            stdscr.addstr(start_y, 2, controls, curses.color_pair(MENU_PAIR))
            if status_x > len(controls) + 4:
                stdscr.addstr(start_y, status_x, status_text, status_color | curses.A_BOLD)
            
            stdscr.addstr(start_y + 1, 0, "=" * width, curses.color_pair(HEADER_PAIR))
            
        except curses.error:
            pass

    def draw_main_view(self, stdscr):
        """Draw the main process status view"""
        height, width = stdscr.getmaxyx()
        processes = {
            "Screenshot Taker": "screenshot",
            "Process Server": "process",
            "SocketIO Server": "socket"
        }
        
        # Add a colored header for the main view
        view_header = "=== PROCESS STATUS ==="
        view_color = self.get_view_color("status")
        stdscr.addstr(4, (width - len(view_header)) // 2, view_header, 
                     view_color | curses.A_BOLD)
        
        for i, (name, key) in enumerate(processes.items()):
            status = "RUNNING" if self.process_manager.is_process_running(key) else "STOPPED"
            status_color = curses.color_pair(STATUS_RUNNING if status == "RUNNING" else STATUS_STOPPED)
            try:
                process_color = self.get_view_color(key)
                stdscr.addstr(i + 6, 2, f"{name}: ", process_color)
                stdscr.addstr(status, status_color | curses.A_BOLD)
            except curses.error:
                pass
                
        # Draw iOS connection status in main view
        ios_clients = self.process_manager.get_ios_client_count()
        ios_status = f"iOS Clients Connected: {ios_clients}"
        ios_color = curses.color_pair(CONNECTION_ACTIVE if ios_clients > 0 else STATUS_STOPPED)
        try:
            stdscr.addstr(10, 2, ios_status, ios_color | curses.A_BOLD)
        except curses.error:
            pass

    def load_screenshot_frequency(self):
        """Load the screenshot frequency from config file"""
        try:
            config_file = get_frequency_config_file()
            if os.path.exists(config_file):
                with open(config_file, 'r') as f:
                    self.current_frequency = float(json.load(f).get('frequency', 4.0))
        except Exception:
            self.current_frequency = 4.0

    def save_screenshot_frequency(self):
        """Save the current screenshot frequency to config"""
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
        """Toggle screenshot capture pause state"""
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

    def draw_process_controls(self, stdscr, start_y):
        """Draw process service controls"""
        try:
            width = stdscr.getmaxyx()[1]
            controls = "[T]rigger Processing [?]Help"
            stdscr.addstr(start_y, 2, controls, curses.color_pair(MENU_PAIR))
            
            current_time = time.time()
            if current_time - self.last_trigger_time < self.trigger_cooldown:
                remaining = int(self.trigger_cooldown - (current_time - self.last_trigger_time))
                cooldown_msg = f" (Cooldown: {remaining}s)"
                stdscr.addstr(start_y, len(controls) + 3, cooldown_msg, curses.color_pair(STATUS_STOPPED))
            
            stdscr.addstr(start_y + 1, 0, "=" * width, curses.color_pair(HEADER_PAIR))
        except curses.error:
            pass

    def draw_socket_controls(self, stdscr, start_y):
        """Draw socket service controls"""
        try:
            width = stdscr.getmaxyx()[1]
            
            # Display connection status in the control bar
            ios_clients = self.process_manager.get_ios_client_count()
            status_text = f"iOS: {ios_clients} connected"
            status_color = curses.color_pair(CONNECTION_ACTIVE if ios_clients > 0 else STATUS_STOPPED)
            
            controls = "[P]ost Message [?]Help"
            stdscr.addstr(start_y, 2, controls, curses.color_pair(MENU_PAIR))
            
            # Position the status on the right side of the screen
            status_x = width - len(status_text) - 2
            if status_x > len(controls) + 5:  # Ensure there's space
                stdscr.addstr(start_y, status_x, status_text, status_color | curses.A_BOLD)
            
            stdscr.addstr(start_y + 1, 0, "=" * width, curses.color_pair(HEADER_PAIR))
        except curses.error:
            pass

    def draw_help_screen(self, stdscr):
        """Draw the help screen for the current view"""
        height, width = stdscr.getmaxyx()
        help_texts = {
            "status": [
                "Status View Help",
                "",
                "This view shows the current state of all services and connections.",
                "",
                "Controls:",
                "1-3: Switch between views",
                "R: Restart SocketIO server",
                "S: Toggle server (start/stop)",
                "Q: Quit application",
                "ESC: Close help",
                "?: Show this help",
                "",
                "Status Icons:",
                "📱 Connected iOS client",
                "❌ No iOS clients connected",
                "✅ Service running",
                "❌ Service stopped"
            ],
            "screenshot": [
                "Screenshot View Help",
                "",
                "This view manages the automatic screenshot capture service.",
                "Screenshots are taken at regular intervals and automatically",
                "cleaned up when older than 3 minutes.",
                "",
                "Controls:",
                "⌨️  Space: Pause/Resume screenshot capture",
                "◀️ ▶️ : Adjust frequency by 0.5s",
                "⚡️ F: Set exact frequency (0.5-10s)",
                "📂 O: Open screenshots folder",
                "ESC: Close help",
                "?: Show this help",
                "",
                "Status Icons:",
                "▶️  Capture running",
                "⏸️  Capture paused",
                "📸 Screenshot taken",
                "🗑️  Old screenshots cleaned"
            ],
            "debug": [
                "Debug View Help",
                "",
                "This view shows filtered SocketIO messages and allows sending",
                "custom messages to connected iOS clients.",
                "",
                "Controls:",
                "📝 P: Post new message",
                "🔄 R: Clear message history",
                "ESC: Close help/message form",
                "?: Show this help",
                "",
                "Message Types & Icons:",
                "📱 Info - Basic information (blue)",
                "✨ Prime - Important events (magenta)",
                "⚠️  Warning - Issues/errors (yellow)",
                "",
                "Notes:",
                "• Ping/pong messages are filtered out",
                "• Client connections are shown in status bar",
                "• Messages show timestamp and type"
            ]
        }
        texts = help_texts.get(self.current_view, help_texts["status"])
        box_height = len(texts) + 4
        box_width = max(len(line) for line in texts) + 4
        start_y = (height - box_height) // 2
        start_x = (width - box_width) // 2

        # Draw box
        for y in range(box_height):
            for x in range(box_width):
                if y in (0, box_height-1) or x in (0, box_width-1):
                    try:
                        stdscr.addch(start_y + y, start_x + x, curses.ACS_CKBOARD, 
                                   self.get_view_color(self.current_view))
                    except curses.error:
                        pass

        # Draw text
        for i, text in enumerate(texts):
            try:
                if ":" in text and not text.startswith(" "):
                    # Make headers bold
                    header, content = text.split(":", 1)
                    stdscr.addstr(start_y + i + 2, start_x + 2, header + ":",
                                self.get_view_color(self.current_view) | curses.A_BOLD)
                    stdscr.addstr(content, self.get_view_color(self.current_view))
                else:
                    stdscr.addstr(start_y + i + 2, start_x + 2, text,
                                self.get_view_color(self.current_view))
            except curses.error:
                pass

    def get_frequency_input(self, stdscr):
        """Get screenshot frequency input from user"""
        height, width = stdscr.getmaxyx()
        # Create input window
        input_win = curses.newwin(3, 40, height//2-1, (width-40)//2)
        input_win.box()
        input_win.addstr(0, 2, " Enter Frequency (0.5-10s) ", curses.A_BOLD)
        input_win.addstr(1, 2, "> ")
        input_win.keypad(1)
        curses.echo()
        
        # Get input
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

    def get_message_input(self, stdscr):
        """Get socket message input from user"""
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
            
            # Draw fields
            for i, field in enumerate(fields):
                y = i * 2 + 1
                label = f"{field['label']}: "
                win.addstr(y, 2, label)
                
                attr = curses.A_BOLD | curses.A_UNDERLINE if i == current_field else curses.A_NORMAL
                
                if "options" in field:
                    value_text = f"< {field['value']} >"
                    color = self.get_view_color("debug") if field['value'] == "Info" else \
                           curses.color_pair(STATUS_RUNNING) if field['value'] == "Prime" else \
                           curses.color_pair(STATUS_STOPPED)
                    win.addstr(y, len(label) + 2, value_text, attr | color)
                else:
                    win.addstr(y, len(label) + 2, field['value'], attr)
            
            # Draw instructions
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
                # Handle option cycling
                if ch == curses.KEY_LEFT:
                    options = fields[current_field]["options"]
                    current_idx = options.index(fields[current_field]["value"])
                    fields[current_field]["value"] = options[(current_idx - 1) % len(options)]
                elif ch == curses.KEY_RIGHT:
                    options = fields[current_field]["options"]
                    current_idx = options.index(fields[current_field]["value"])
                    fields[current_field]["value"] = options[(current_idx + 1) % len(options)]
            elif ch in (8, 127, curses.KEY_BACKSPACE):  # Backspace
                if "options" not in fields[current_field]:
                    fields[current_field]["value"] = fields[current_field]["value"][:-1]
            elif ch >= 32 and ch <= 126:  # Printable characters
                if "options" not in fields[current_field] and len(fields[current_field]["value"]) < fields[current_field]["length"]:
                    fields[current_field]["value"] += chr(ch)

    def run(self, stdscr):
        """Main UI loop"""
        curses.mousemask(curses.REPORT_MOUSE_POSITION)
        self.stdscr = stdscr
        self.setup_colors()
        stdscr.timeout(100)

        while True:
            stdscr.clear()
            self.draw_header(stdscr)

            if self.help_active:
                self.draw_help_screen(stdscr)
            elif self.current_view == "status":
                self.draw_status_view(stdscr)
            elif self.current_view == "screenshot":
                self.draw_process_output(stdscr, "screenshot")
            elif self.current_view == "debug":
                self.draw_process_output(stdscr, "debug")

            stdscr.refresh()

            try:
                key = stdscr.getch()
                if key != -1:
                    if not self.handle_input(key):
                        break
            except curses.error:
                pass
        
        return True

    def handle_input(self, key):
        """Handle user input. Returns False if should exit."""
        if self.help_active:
            if key == 27:  # ESC
                self.help_active = False
        elif self.post_message_active:
            if key == 27:  # ESC
                self.post_message_active = False
        elif key == ord('?'):
            self.help_active = True
        elif key == ord('q'):
            return False
        elif key == ord('r'):
            self.process_manager.restart_service(self.current_view)
        elif key == ord('s') and self.current_view == "status":
            # Toggle the currently selected service
            service = "socket"  # Default to socket service
            running = self.process_manager.is_process_running(service)
            if running:
                self.process_manager.stop_service(service)
            else:
                self.process_manager.start_service(service)
        elif key in (ord('1'), ord('2'), ord('3')):
            self.current_view = {
                ord('1'): "status",
                ord('2'): "screenshot",
                ord('3'): "debug"
            }[key]
        elif self.current_view == "screenshot":
            self.handle_screenshot_input(key)
        elif self.current_view == "debug":
            self.handle_socket_input(key)
        
        return True

    def handle_screenshot_input(self, key):
        """Handle input specific to screenshot view"""
        if key == ord(' '):
            self.toggle_screenshot_pause()
        elif key == ord('o'):
            self.process_manager.open_screenshots_folder()
        elif key == curses.KEY_LEFT:
            self.current_frequency = max(0.5, self.current_frequency - 0.5)
            self.save_screenshot_frequency()
        elif key == curses.KEY_RIGHT:
            self.current_frequency = min(10.0, self.current_frequency + 0.5)
            self.save_screenshot_frequency()
        elif key == ord('f'):
            new_freq = self.get_frequency_input(self.stdscr)
            if new_freq is not None:
                self.current_frequency = new_freq
                self.save_screenshot_frequency()

    def handle_process_input(self, key):
        """Handle input specific to process view"""
        if key == ord('t'):  # Trigger processing
            current_time = time.time()
            if current_time - self.last_trigger_time >= self.trigger_cooldown:
                self.last_trigger_time = current_time
                self.process_manager.trigger_processing()

    def handle_socket_input(self, key):
        """Handle input specific to socket view"""
        if key == ord('p'):  # Post message
            self.post_message_active = True
        elif key == ord('r'):  # Clear messages
            self.process_manager.clear_output("debug")