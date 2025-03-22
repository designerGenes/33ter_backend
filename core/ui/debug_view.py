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
        
        controls = "📝P:Post Message  🔄R:Clear  ❔?:Help"
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

    def handle_input(self, key):
        """Handle debug view specific input"""
        if key == ord('p'):
            self.get_message_input()
        elif key == ord('r'):
            self.clear_messages()

    def get_message_input(self):
        """Get and send a new socket message."""
        height, width = self.height, self.width
        
        # Create message form window
        form_height = 8
        form_width = 60
        win = curses.newwin(form_height, form_width, 
                           (height-form_height)//2, 
                           (width-form_width)//2)
        win.keypad(1)
        win.box()
        
        fields = [
            {"label": "Title", "value": "", "length": 30},
            {"label": "Type", "value": "Info", "options": ["Info", "Prime", "Warning"]},
            {"label": "Message", "value": "", "length": 40}
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
                    color = get_view_color("debug") if field['value'] == "Info" else \
                           curses.color_pair(STATUS_RUNNING if field['value'] == "Prime" else STATUS_STOPPED)
                    win.addstr(y, len(field['label']) + 4, value_text, attr | color)
                else:
                    win.addstr(y, len(field['label']) + 4, field['value'], attr)
            
            # Instructions
            win.addstr(form_height-2, 2, 
                      "↑↓:Move  ←→:Change Type  Enter:Send  Esc:Cancel",
                      curses.color_pair(MENU_PAIR))
            
            win.refresh()
            ch = win.getch()
            
            if ch == 27:  # ESC
                break
            elif ch == 10:  # Enter
                if fields[0]['value'].strip() and fields[2]['value'].strip():
                    self.process_manager.post_message_to_socket(
                        fields[2]['value'],
                        fields[0]['value'],
                        fields[1]['value'].lower()
                    )
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
            "This view shows SocketIO communication and allows",
            "sending messages to connected iOS clients.",
            "",
            "Controls:",
            "P: Post new message",
            "R: Clear message history",
            "",
            "Message Types:",
            "📱 Info - Basic information",
            "✨ Prime - Important events",
            "⚠️  Warning - Potential issues",
            "❌ Error - Problems/failures",
            "",
            "Notes:",
            "- Ping/pong messages are filtered",
            "- iOS client count shown in status bar",
            "- Messages show timestamp and type"
        ]
