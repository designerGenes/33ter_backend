"""Debug view implementation for the terminal UI."""
import curses
import time
from .base_view import BaseView
from .color_scheme import *
import traceback
from ..message_system import MessageManager, MessageLevel, MessageCategory

class DebugView(BaseView):
    """Debug view for SocketIO messages and client communication."""
    
    def __init__(self, stdscr, process_manager):
        super().__init__(stdscr, process_manager)
        self.view_name = "debug"
        self.message_form_active = False
        self.message_manager = MessageManager()  # Get the singleton instance

    def draw_content(self):
        """Draw the debug view content."""
        self.draw_header("DEBUG LOG")
        
        # Draw controls with iOS client status
        ios_clients = self.process_manager.get_ios_client_count()
        status_text = f"{ios_clients} iOS client{'s' if ios_clients != 1 else ''}"
        status_color = curses.color_pair(CONNECTION_ACTIVE if ios_clients > 0 else STATUS_STOPPED)
        
        controls = "P:Post  T:Trigger  R:Clear"
        status_x = self.width - len(status_text) - 2
        
        self.draw_controls(controls, 6)
        if status_x > len(controls) + 4:
            self.stdscr.addstr(6, status_x, status_text, status_color | curses.A_BOLD)
        
        # Draw separator
        self.stdscr.addstr(7, 0, "=" * self.width, curses.color_pair(HEADER_PAIR))
        
        # Get messages from both sources to handle all message formats
        debug_lines = self.process_manager.output_buffers["debug"]
        
        if not debug_lines:
            self.stdscr.addstr(10, (self.width - 13) // 2, "(No messages)", 
                             get_view_color("debug") | curses.A_DIM)
            return
        
        # Process output lines
        y_pos = 8
        line_index = 0
        
        # Get the last N lines that will fit in our display area
        visible_lines = min(self.height - 9, len(debug_lines))
        start_index = max(0, len(debug_lines) - visible_lines)
        
        # Track processed messages to avoid duplicates
        processed_messages = set()
        display_lines = []
        
        i = start_index
        while i < len(debug_lines):
            line = debug_lines[i]
            
            # Check if this is a JSON-formatted message
            if ": {" in line:
                # Extract timestamp for tracking
                timestamp = line.split(": {")[0]
                
                # Collect all lines for this message
                message_lines = [line]
                j = i + 1
                while j < len(debug_lines) and "}" not in debug_lines[j]:
                    message_lines.append(debug_lines[j])
                    j += 1
                
                # Add the closing bracket line
                if j < len(debug_lines):
                    message_lines.append(debug_lines[j])
                    
                # Create a unique signature for this message to avoid duplicates
                message_signature = "".join(message_lines)
                if message_signature not in processed_messages:
                    processed_messages.add(message_signature)
                    display_lines.extend(message_lines)
                
                # Skip ahead to after this message
                i = j + 1
            else:
                # For non-JSON format lines that don't have emojis
                if not any(emoji in line for emoji in ["📱", "📤", "ℹ️", "⚠️", "❌", "🎯", "📝"]):
                    display_lines.append(line)
                i += 1
        
        # Now display the filtered lines
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
                        
                        # Check for ERROR key which should be highlighted
                        if "ERROR:" in content_line:
                            parts = content_line.split("ERROR:", 1)
                            self.stdscr.addstr(y_pos, 2, parts[0], get_view_color("debug"))
                            self.stdscr.addstr("ERROR:", curses.color_pair(STATUS_STOPPED) | curses.A_BOLD)
                            self.stdscr.addstr(parts[1], curses.color_pair(STATUS_STOPPED))
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
