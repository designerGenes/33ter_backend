"""Debug view implementation for the terminal UI."""
import curses
import time
from .base_view import BaseView
from .color_scheme import *

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
            # Convert trigger message to match expected format
            result = self.process_manager.post_message_to_socket(
                message="trigger",
                title="OCR Trigger",
                msg_type="trigger"
            )
            if result:  # If error message returned
                self.process_manager.output_queues["debug"].append(result)

    def get_message_input(self):
        """Get and send a new socket message."""
        height, width = self.height, self.width
        
        # Increase form height and adjust layout
        form_height = 9  # Increased to accommodate all fields properly
        form_width = 60
        win = curses.newwin(form_height, form_width, 
                           (height-form_height)//2, 
                           (width-form_width)//2)
        win.keypad(1)
        win.box()
        
        fields = [
            {"label": "Type", "value": "info", 
             "options": ["info", "warning", "trigger", "ocrResult"]},
            {"label": "Title", "value": "", "length": 30},
            {"label": "Value", "value": "", "length": 40}
        ]
        current_field = 0
        
        while True:
            win.clear()
            win.box()
            win.addstr(0, 2, " Socket Message ", curses.A_BOLD)
            
            # Draw fields
            for i, field in enumerate(fields):
                y = i * 2 + 1
                win.addstr(y, 2, f"{field['label']}: ")
                
                attr = curses.A_BOLD | curses.A_UNDERLINE if i == current_field else curses.A_NORMAL
                
                if "options" in field:
                    value_text = f"< {field['value']} >"
                    icon = {"info": "ℹ️ ", "warning": "⚠️ ", 
                           "trigger": "🎯", "ocrResult": "📝"}[field['value']]
                    win.addstr(y, len(field['label']) + 4, f"{icon}{value_text}", attr)
                else:
                    win.addstr(y, len(field['label']) + 4, field['value'], attr)
            
            # Move instructions to actual bottom of form
            win.addstr(form_height-2, 2, 
                      "↑↓:Move  ←→:Change Type  Enter:Send  Esc:Cancel",
                      curses.color_pair(MENU_PAIR))
            
            win.refresh()
            ch = win.getch()
            
            if ch == 27:  # ESC
                break
            elif ch == 10:  # Enter
                if fields[1]['value'].strip() and fields[2]['value'].strip():
                    # Convert to ProcessManager expected format
                    result = self.process_manager.post_message_to_socket(
                        message=fields[2]['value'],
                        title=fields[1]['value'],
                        msg_type=fields[0]['value']
                    )
                    if result:  # If error message returned
                        self.process_manager.output_queues["debug"].append(result)
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
