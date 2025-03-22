"""Debug view implementation for the terminal UI."""
import curses
import time
from .base_view import BaseView
from .color_scheme import *
import traceback

class DebugView(BaseView):
    """Debug view for SocketIO messages and client communication."""
    
    def __init__(self, stdscr, process_manager):
        super().__init__(stdscr, process_manager)
        self.view_name = "debug"
        self.message_form_active = False

    def draw_content(self):
        """Draw the debug view content."""
        self.draw_header("DEBUG LOG")
        
        # Draw controls with iOS client status
        ios_clients = self.process_manager.get_ios_client_count()
        status_text = f"📱 {ios_clients} iOS client{'s' if ios_clients != 1 else ''}"
        status_color = curses.color_pair(CONNECTION_ACTIVE if ios_clients > 0 else STATUS_STOPPED)
        
        controls = "📝P:Post  🎯T:Trigger  🔄R:Clear"
        status_x = self.width - len(status_text) - 2
        
        self.draw_controls(controls, 6)
        if status_x > len(controls) + 4:
            self.stdscr.addstr(6, status_x, status_text, status_color | curses.A_BOLD)
        
        # Draw separator
        self.stdscr.addstr(7, 0, "=" * self.width, curses.color_pair(HEADER_PAIR))
        
        # Draw messages starting from line 8
        output_lines = self.process_manager.get_output("debug")
        if not output_lines:
            self.stdscr.addstr(10, (self.width - 13) // 2, "(No messages)", 
                             get_view_color("debug") | curses.A_DIM)
            return
            
        for i, line in enumerate(output_lines[-self.height+9:]):
            try:
                y_pos = 8 + i
                if y_pos >= self.height - 1:
                    break
                    
                # Parse line components
                parts = line.split(" ", 3)
                if len(parts) == 4:
                    timestamp, emoji, message, level = parts
                    level = level.strip("()")
                    
                    # Draw with appropriate colors
                    x = 2
                    self.stdscr.addstr(y_pos, x, timestamp)
                    x += len(timestamp) + 1
                    
                    self.stdscr.addstr(y_pos, x, emoji)
                    x += len(emoji) + 1
                    
                    msg_color = {
                        'info': curses.color_pair(MENU_PAIR),
                        'prime': curses.color_pair(SELECTED_VIEW),
                        'warning': curses.color_pair(STATUS_STOPPED),
                        'error': curses.color_pair(STATUS_STOPPED) | curses.A_BOLD
                    }.get(level.lower(), curses.A_NORMAL)
                    
                    self.stdscr.addstr(y_pos, x, message, msg_color)
                else:
                    self.stdscr.addstr(y_pos, 2, line[:self.width-3])
                    
            except curses.error:
                break

    def format_message(self, message):
        """Format received socket message for display."""
        if isinstance(message, str):  # Handle error messages
            timestamp = time.strftime('%H:%M:%S')
            return f"{timestamp} ❌ [error] {message} (error)"
            
        type_icons = {
            "info": "ℹ️ ",
            "warning": "⚠️ ",
            "trigger": "🎯",
            "ocrResult": "📝"
        }
        
        msg_type = message.get('messageType', 'unknown')
        msg_from = message.get('from', 'unknown')
        value = message.get('value', '')
        
        # Format array values for ocrResult
        if isinstance(value, list):
            value = ', '.join(str(v) for v in value)
            
        icon = type_icons.get(msg_type, '❓')
        timestamp = time.strftime('%H:%M:%S')
        return f"{timestamp} {icon} [{msg_from}] {value} ({msg_type})"

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
                
                if result:  # Error message returned
                    error_details = f"Trigger failed: {result}"
                    if not self.process_manager.get_ios_client_count():
                        error_details += "\nNote: No iOS clients are currently connected to receive the trigger"
                    
                    self.process_manager.output_buffers["debug"].append(error_details)
                else:
                    self.process_manager.output_buffers["debug"].append("Trigger message sent successfully")
                    
            except Exception as e:
                error_msg = f"Unexpected error during trigger: {str(e)}\n"
                error_msg += traceback.format_exc()
                self.process_manager.output_buffers["debug"].append(error_msg)

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
        win.keypad(1)
        win.box()
        
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
            
            # Draw fields (only two fields now)
            for i, field in enumerate(fields):
                y = i * 2 + 1
                label = f"{field['label']}: "
                win.addstr(y, 2, label)
                
                attr = curses.A_BOLD | curses.A_UNDERLINE if i == current_field else curses.A_NORMAL
                
                if "options" in field:
                    value_text = f"< {field['value']} >"
                    icon = {"info": "ℹ️ ", "warning": "⚠️ ", 
                           "trigger": "🎯", "ocrResult": "📝"}[field['value']]
                    win.addstr(y, len(label) + 2, f"{icon}{value_text}", attr)
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
                if fields[1]['value'].strip():  # Check value field is not empty
                    result = self.process_manager.post_message_to_socket(
                        value=fields[1]['value'],
                        messageType=fields[0]['value']
                    )
                    if result:  # Show error message if returned
                        self.process_manager.output_buffers["debug"].append(result)
                    break
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
            "ℹ️  Info - Basic information",
            "🎯 Trigger - Request OCR processing",
            "📝 OCR Result - Extracted text",
            "⚠️  Warning - Alert message",
            "",
            "Message Format:",
            "{",
            "  messageType: info/warning/trigger/ocrResult",
            "  from: localBackend/mobileApp",
            "  value: message content",
            "}",
            "",
            "Notes:",
            "- Messages show timestamp and source",
            "- iOS client count shown in status"
        ]
