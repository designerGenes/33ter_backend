"""Debug view implementation for the terminal UI."""
import curses
import time
import traceback
from .base_view import BaseView
from .color_scheme import *
from ..message_system import MessageManager, MessageLevel, MessageCategory

class DebugView(BaseView):
    """Debug view for SocketIO messages and client communication."""
    
    def __init__(self, stdscr, process_manager):
        super().__init__(stdscr, process_manager)
        self.view_name = "debug"
        self.message_form_active = False
        self.message_manager = MessageManager()  # Get the singleton instance
        self.last_message_count = 0  # Track message count to detect changes
        self.last_refresh_time = time.time()
        self.refresh_interval = 0.25  # Refresh more frequently (4 times per second)
        
        # Debug message counts
        self.last_buffer_size = 0
        self.missed_messages = 0
        # Keep track of the last few messages to ensure they're always shown
        self.recent_messages = []
        self.recent_message_count = 10  # Keep last 10 messages always visible

    def draw(self):
        """Override draw method to add periodic refresh."""
        current_time = time.time()
        
        # Force refresh if it's been too long or message count has changed
        current_message_count = len(self.process_manager.output_buffers["debug"])
        
        # Track buffer size changes for debugging
        if current_message_count != self.last_buffer_size:
            diff = current_message_count - self.last_buffer_size
            if diff > 0:
                self.missed_messages += diff
            self.last_buffer_size = current_message_count
        
        # Force refresh on timer or when buffer changes
        if (current_time - self.last_refresh_time >= self.refresh_interval or 
                current_message_count != self.last_message_count):
            self.last_refresh_time = current_time
            self.last_message_count = current_message_count
            self.stdscr.clear()  # Force complete redraw
        
        # Call the parent draw method
        super().draw()
    
    def draw_content(self):
        """Draw the debug view content."""
        self.draw_header("DEBUG LOG")
        
        # Draw controls with iOS client status
        ios_clients = self.process_manager.get_ios_client_count()
        status_text = f"{ios_clients} iOS client{'s' if ios_clients != 1 else ''}"
        status_color = curses.color_pair(CONNECTION_ACTIVE if ios_clients > 0 else STATUS_STOPPED)
        
        # Show message count for debugging
        msg_count = len(self.process_manager.output_buffers["debug"])
        buffer_info = f"Messages: {msg_count} (+{self.missed_messages})"
        
        controls = "P:Post  T:Trigger  R:Clear"
        status_x = self.width - len(status_text) - 2
        
        self.draw_controls(controls, 6)
        
        # Draw message count if there's room
        if self.width > len(controls) + len(buffer_info) + 10:
            self.stdscr.addstr(6, len(controls) + 4, buffer_info, get_view_color("debug"))
        
        # Draw iOS client status with higher visibility when active
        if ios_clients > 0:
            status_attr = curses.A_BOLD | curses.A_STANDOUT  # Make it more prominent
        else:
            status_attr = curses.A_BOLD
        
        if status_x > len(controls) + len(buffer_info) + 6:
            self.stdscr.addstr(6, status_x, status_text, status_color | status_attr)
        
        # Draw separator
        self.stdscr.addstr(7, 0, "=" * self.width, curses.color_pair(HEADER_PAIR))
        
        # Get messages from debug buffer
        debug_lines = self.process_manager.output_buffers["debug"]
        
        if not debug_lines:
            self.stdscr.addstr(10, (self.width - 13) // 2, "(No messages)", 
                             get_view_color("debug") | curses.A_DIM)
            return
        
        # Process output lines
        y_pos = 8
        
        # Calculate how many lines we can display
        max_display_lines = self.height - 9
        
        # Use a different approach for collecting messages
        display_lines = []
        
        # First, process the debug lines to collect complete messages
        i = 0
        while i < len(debug_lines):
            line = debug_lines[i]
            
            # Check if this starts a JSON-formatted message
            if ": {" in line:
                # Collect all lines for this message block
                message_block = [line]
                j = i + 1
                
                # Find the end of this message block
                while j < len(debug_lines) and "}" not in debug_lines[j]:
                    message_block.append(debug_lines[j])
                    j += 1
                
                # Add the closing bracket if found
                if j < len(debug_lines):
                    message_block.append(debug_lines[j])
                
                # Add this complete message block to display lines
                display_lines.extend(message_block)
                
                # Move past this message block
                i = j + 1
            else:
                # For non-JSON lines, add directly
                display_lines.append(line)
                i += 1
        
        # Now update our recent messages cache with any new message blocks
        # This ensures that recent messages are always displayed
        for i in range(len(display_lines) - 1, -1, -1):
            if ": {" in display_lines[i]:
                # Find the full message block
                message_start = i
                message_end = i
                
                for j in range(i + 1, len(display_lines)):
                    if j >= len(display_lines):
                        break
                    if "}" in display_lines[j]:
                        message_end = j
                        break
                
                if message_end > message_start:
                    # Add this complete message to recent messages
                    message_block = display_lines[message_start:message_end + 1]
                    message_sig = "".join(message_block)
                    
                    # Check if it's a commandLine message and add to our recent list
                    if "from: commandLine" in message_sig or "from: commandLine" in message_sig:
                        # Make a deep copy to ensure we don't lose the message
                        self.recent_messages.append(message_block.copy())
                        # Limit the size of recent messages
                        if len(self.recent_messages) > self.recent_message_count:
                            self.recent_messages.pop(0)
        
        # If the display is too full, trim older messages but keep recent ones
        if len(display_lines) > max_display_lines:
            # First, calculate how many lines recent messages will take
            recent_lines_count = 0
            for msg_block in self.recent_messages:
                recent_lines_count += len(msg_block)
            
            # Only keep older lines if there's space
            older_lines_to_keep = max(0, max_display_lines - recent_lines_count)
            
            # Create a new display lines list with the most recent older messages
            # and all the recent messages
            new_display_lines = []
            
            # Add a subset of older messages to fill available space
            if older_lines_to_keep > 0:
                new_display_lines.extend(display_lines[-older_lines_to_keep:])
            
            # Now add all recent messages
            for msg_block in self.recent_messages:
                new_display_lines.extend(msg_block)
            
            display_lines = new_display_lines

        # Now display the lines
        line_index = 0
        while line_index < len(display_lines) and y_pos < self.height - 1:
            line = display_lines[line_index]
            
            try:
                # Check if this is a JSON-formatted message
                if ": {" in line:
                    # Draw the timestamp part
                    timestamp = line.split(": {")[0]
                    self.stdscr.addstr(y_pos, 2, timestamp)
                    self.stdscr.addstr(": {", get_view_color("debug"))
                    y_pos += 1
                    
                    # Process indented content lines until we find a closing bracket
                    line_index += 1
                    while line_index < len(display_lines) and "}" not in display_lines[line_index]:
                        content_line = display_lines[line_index]
                        
                        # Highlight based on message parts
                        if "ERROR:" in content_line:
                            # Error message
                            parts = content_line.split("ERROR:", 1)
                            self.stdscr.addstr(y_pos, 2, parts[0], get_view_color("debug"))
                            self.stdscr.addstr("ERROR:", curses.color_pair(STATUS_STOPPED) | curses.A_BOLD)
                            self.stdscr.addstr(parts[1], curses.color_pair(STATUS_STOPPED))
                        elif "from: commandLine" in content_line:
                            # Highlight commandLine messages source but don't modify the value
                            parts = content_line.split("from: ", 1)
                            self.stdscr.addstr(y_pos, 2, parts[0] + "from: ", get_view_color("debug"))
                            self.stdscr.addstr("commandLine", curses.color_pair(CONNECTION_ACTIVE) | curses.A_BOLD)
                        else:
                            self.stdscr.addstr(y_pos, 2, content_line, get_view_color("debug"))
                            
                        y_pos += 1
                        line_index += 1
                    
                    # Draw the closing bracket
                    if line_index < len(display_lines):
                        self.stdscr.addstr(y_pos, 2, display_lines[line_index], get_view_color("debug"))
                        y_pos += 1
                else:
                    # For non-JSON format lines, just display them directly
                    self.stdscr.addstr(y_pos, 2, line[:self.width-3])
                    y_pos += 1
            except curses.error:
                # Handle display errors
                break
                
            line_index += 1

    def handle_input(self, key):
        """Handle debug view specific input"""
        if super().handle_input(key):  # Handle help overlay
            return
            
        if key == ord('p'):
            self.get_message_input()
        elif key == ord('r'):
            self.clear_messages()
        elif key == ord('t'):
            try:
                result = self.process_manager.post_message_to_socket(
                    value="trigger",
                    messageType="trigger"
                )
                
                if result is not None:  # Error message returned
                    error_details = f"Trigger failed: {result}"
                    if not self.process_manager.get_ios_client_count():
                        error_details += "\nNote: No iOS clients are currently connected to receive the trigger"
                    
                    # Format error message
                    timestamp = time.strftime("%H:%M:%S")
                    self.process_manager.output_buffers["debug"].append(f"{timestamp}: {{")
                    self.process_manager.output_buffers["debug"].append(f"    ERROR: {error_details}")
                    self.process_manager.output_buffers["debug"].append("}")
                    
            except Exception as e:
                error_msg = f"Unexpected error during trigger: {str(e)}"
                
                # Format error message
                timestamp = time.strftime("%H:%M:%S")
                self.process_manager.output_buffers["debug"].append(f"{timestamp}: {{")
                self.process_manager.output_buffers["debug"].append(f"    ERROR: {error_msg}")
                self.process_manager.output_buffers["debug"].append("}")

    def get_message_input(self):
        """Get and send a new socket message."""
        height, width = self.height, self.width
        
        # Set proper form dimensions
        form_height = 7
        form_width = 60
        form_y = (height - form_height) // 2
        form_x = (width - form_width) // 2
        
        # Create window with proper position and size
        win = curses.newwin(form_height, form_width, form_y, form_x)
        win.keypad(1)  # Enable special key input
        
        fields = [
            {"label": "Type", "value": "info", 
             "options": ["info", "warning", "trigger", "ocrResult"]},
            {"label": "Value", "value": "", "length": 40}
        ]
        current_field = 0
        
        while True:
            win.clear()
            win.box()
            win.addstr(0, 2, " Socket Message ", curses.A_BOLD)
            
            # Draw fields without emojis
            for i, field in enumerate(fields):
                y = i * 2 + 1
                label = f"{field['label']}: "
                win.addstr(y, 2, label)
                
                attr = curses.A_BOLD | curses.A_UNDERLINE if i == current_field else curses.A_NORMAL
                
                if "options" in field:
                    value_text = f"< {field['value']} >"
                    win.addstr(y, len(label) + 2, value_text, attr)
                else:
                    win.addstr(y, len(label) + 2, field['value'], attr)
            
            # Draw instructions
            win.addstr(form_height-2, 2, 
                      "↑↓:Move  ←→:Change Type  Enter:Send  Esc:Cancel",
                      curses.color_pair(MENU_PAIR))
            
            win.refresh()
            ch = win.getch()
            
            if ch == 27:  # ESC
                break
            elif ch == 10:  # Enter
                value = fields[1]['value'].strip()
                if value:  # Check value field is not empty
                    msg_type = fields[0]['value']
                    
                    # Send the message
                    result = self.process_manager.post_message_to_socket(
                        value=value,
                        messageType=msg_type
                    )
                    
                    if result:  # Show error message if returned
                        # Error messages are handled in post_message_to_socket
                        pass
                    break
                else:
                    # Add error message for empty value
                    timestamp = time.strftime("%H:%M:%S")
                    self.process_manager.output_buffers["debug"].append(f"{timestamp}: {{")
                    self.process_manager.output_buffers["debug"].append(f"    ERROR: Cannot send empty message")
                    self.process_manager.output_buffers["debug"].append("}")
            elif ch == curses.KEY_UP:
                current_field = (current_field - 1) % len(fields)
            elif ch == curses.KEY_DOWN:
                current_field = (current_field + 1) % len(fields)
            elif "options" in fields[current_field]:
                if ch in (curses.KEY_LEFT, curses.KEY_RIGHT):
                    options = fields[current_field]["options"]
                    current = options.index(fields[current_field]["value"])
                    direction = 1 if ch == curses.KEY_RIGHT else -1
                    fields[current_field]["value"] = options[(current + direction) % len(options)]
            elif ch in (8, 127, curses.KEY_BACKSPACE):  # Backspace
                if not "options" in fields[current_field]:
                    fields[current_field]["value"] = fields[current_field]["value"][:-1]
            elif ch >= 32 and ch <= 126:  # Printable chars
                if not "options" in fields[current_field] and \
                   len(fields[current_field]["value"]) < fields[current_field]["length"]:
                    fields[current_field]["value"] += chr(ch)

    def clear_messages(self):
        """Clear the debug message buffer."""
        # Clear both systems
        self.message_manager.clear_buffer("debug")
        self.process_manager.output_buffers["debug"].clear()

    def get_help_content(self):
        """Get help content for debug view."""
        return [
            "Debug View - SocketIO Communication Interface",
            "",
            "Controls:",
            "P: Post new message",
            "T: Trigger OCR text extraction",
            "R: Clear message history",
            "?: Show/hide this help",
            "",
            "Message Types:",
            "info - Basic information",
            "trigger - Request OCR processing",
            "ocrResult - Extracted text",
            "warning - Alert message",
            "",
            "Message Format:",
            "{",
            "  type: (message type),",
            "  value: (message content),",
            "  from: (message source)",
            "}",
            "",
            "Error Format:",
            "{",
            "  ERROR: (error details)",
            "}",
            "",
            "Notes:",
            "- Messages include timestamp",
            "- iOS client count shown in status"
        ]
