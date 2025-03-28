"""Debug view implementation for the terminal UI."""
import curses
import time
import traceback
import json  # Added json import
from .base_view import BaseView
from .color_scheme import *
from ..message_system import MessageManager, MessageLevel, MessageCategory

class DebugView(BaseView):
    """Debug view for SocketIO messages and client communication."""
    def __init__(self, stdscr, process_manager):
        super().__init__(stdscr, process_manager)
        self.view_name = "debug"
        self.scroll_pos = 0

    def draw_content(self):
        """Draw the debug view content."""
        max_y, max_x = self.height, self.width
        self.win.addstr(1, 2, "Socket.IO Debug Log", curses.A_BOLD | curses.A_UNDERLINE)

        log_lines = self.process_manager.get_output("debug")  # Use MessageManager output

        # Calculate visible lines (adjust for header/footer/borders)
        visible_lines = max_y - 4  # Height of the content window

        # Adjust scroll position if necessary
        if len(log_lines) <= visible_lines:
            self.scroll_pos = 0
        elif self.scroll_pos > len(log_lines) - visible_lines:
            self.scroll_pos = len(log_lines) - visible_lines
        if self.scroll_pos < 0:
            self.scroll_pos = 0

        # Get the slice of lines to display
        display_lines = log_lines[self.scroll_pos : self.scroll_pos + visible_lines]

        # Display log lines
        for i, line_str in enumerate(display_lines):
            y_pos = 3 + i  # Start drawing below header
            if y_pos >= max_y - 1:
                break  # Prevent drawing outside window

            # Basic coloring
            color = curses.A_NORMAL
            if "ERROR" in line_str:
                color = curses.color_pair(STATUS_STOPPED) | curses.A_BOLD
            elif "WARNING" in line_str:
                color = curses.color_pair(MENU_PAIR) | curses.A_BOLD
            elif "Sending message" in line_str:
                color = curses.color_pair(CONNECTION_ACTIVE)  # Example: Green for sending

            # Handle multi-line JSON-like strings from _add_to_buffer
            lines_to_draw = line_str.split('\n')
            current_y = y_pos
            for line_part in lines_to_draw:
                if current_y >= max_y - 1:
                    break
                try:
                    # Ensure line part fits width, truncate if necessary
                    truncated_line = line_part[:max_x - 3]  # Leave space for border
                    self.win.addstr(current_y, 2, truncated_line, color)
                except curses.error:
                    # Ignore errors trying to write outside window bounds
                    pass
                current_y += 1

        # Add scroll indicator if needed
        if len(log_lines) > visible_lines:
            scroll_perc = int((self.scroll_pos / (len(log_lines) - visible_lines)) * 100) if len(log_lines) > visible_lines else 0
            self.win.addstr(max_y - 2, max_x - 10, f"Scroll:{scroll_perc:3d}%", curses.A_REVERSE)

    def handle_input(self, key):
        """Handle debug view specific input"""
        if super().handle_input(key):  # Handle help overlay
            return

        if key == ord('p'):
            self.get_message_input()
        elif key == ord('r'):
            self.clear_messages()
        elif key == ord('t'):
            self.trigger_ocr_processing()  # Use helper method
        elif key == curses.KEY_UP:
            self.scroll_pos = max(0, self.scroll_pos - 1)
        elif key == curses.KEY_DOWN:
            # Allow scrolling down only if there are lines below the current view
            log_lines = self.process_manager.get_output("debug")
            visible_lines = self.height - 4
            if self.scroll_pos < len(log_lines) - visible_lines:
                self.scroll_pos += 1
        elif key == curses.KEY_PPAGE:  # Page Up
            visible_lines = self.height - 4
            self.scroll_pos = max(0, self.scroll_pos - (visible_lines - 1))
        elif key == curses.KEY_NPAGE:  # Page Down
            log_lines = self.process_manager.get_output("debug")
            visible_lines = self.height - 4
            max_scroll = len(log_lines) - visible_lines
            if max_scroll > 0:
                self.scroll_pos = min(max_scroll, self.scroll_pos + (visible_lines - 1))

    def trigger_ocr_processing(self):
        """Send trigger message and handle feedback."""
        try:
            # Attempt to trigger OCR via ProcessManager method
            success = self.process_manager.process_and_send_ocr_result()

            if success:
                self.process_manager._add_to_buffer("debug", "Manual OCR trigger successful.", "info")
            else:
                # Error/Warning messages should be added by process_and_send_ocr_result itself
                pass

        except Exception as e:
            error_msg = f"Unexpected error during manual OCR trigger: {str(e)}"
            self.process_manager._add_to_buffer("debug", f"ERROR: {error_msg}", "error")
            self.process_manager.logger.error(error_msg, exc_info=True)

    def get_message_input(self):
        """Get and send a new socket message."""
        height, width = self.height, self.width

        # Ensure window dimensions are valid
        form_height = 7
        form_width = 60
        form_y = max(0, (height - form_height) // 2)
        form_x = max(0, (width - form_width) // 2)

        # Check if window can be created
        if form_y + form_height > height or form_x + form_width > width:
             self.process_manager._add_to_buffer("status", "Terminal too small to post message", "warning")
             return

        win = curses.newwin(form_height, form_width, form_y, form_x)
        win.keypad(1)  # Enable special key input
        curses.curs_set(1) # Show cursor

        fields = [
            {"label": "Type", "value": "info",
             "options": ["info", "warning", "trigger", "ocrResult"]}, # Ensure consistent casing
            {"label": "Value", "value": "", "length": 40}
        ]
        current_field = 0

        while True:
            try:
                win.erase() # Clear window each loop
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
                        # Display current value, ensure cursor is positioned correctly
                        win.addstr(y, len(label) + 2, field['value'], attr)

                # Draw instructions
                win.addstr(form_height-2, 2,
                          "↑↓:Move  ←→:Change Type  Enter:Send  Esc:Cancel",
                          curses.color_pair(MENU_PAIR))

                # Position cursor for editing the value field
                if current_field == 1: # Value field
                     # Calculate y position based on label (usually 1*2+1 = 3)
                     cursor_y = fields[0]['label'].count('\n')*2 + 1 + 2 # Y position for value field
                     cursor_x = len(fields[current_field]['label']) + 2 + len(fields[current_field]['value'])
                     win.move(cursor_y, cursor_x)


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
                            messageType=msg_type # Use correct casing
                        )

                        # No need to manually add error here, post_message_to_socket handles it
                        break
                    else:
                        # Add error message for empty value to debug buffer
                        self.process_manager._add_to_buffer("debug", "ERROR: Cannot send empty message", "error")
                        # Optional: Flash screen or show temporary message in form
                        win.addstr(form_height-1, 2, "Cannot send empty message!", curses.color_pair(STATUS_STOPPED))
                        win.refresh()
                        time.sleep(1)
                        break # Exit form after showing error hint

                elif ch == curses.KEY_UP:
                    current_field = (current_field - 1) % len(fields)
                elif ch == curses.KEY_DOWN:
                    current_field = (current_field + 1) % len(fields)
                elif current_field == 0 and "options" in fields[current_field]: # Handle type selection
                    if ch in (curses.KEY_LEFT, curses.KEY_RIGHT):
                        options = fields[current_field]["options"]
                        current_idx = options.index(fields[current_field]["value"])
                        direction = 1 if ch == curses.KEY_RIGHT else -1
                        fields[current_field]["value"] = options[(current_idx + direction) % len(options)]
                elif current_field == 1: # Handle value input
                     if ch in (8, 127, curses.KEY_BACKSPACE):  # Backspace
                         fields[current_field]["value"] = fields[current_field]["value"][:-1]
                     elif ch >= 32 and ch <= 126:  # Printable chars
                         if len(fields[current_field]["value"]) < fields[current_field]["length"]:
                             fields[current_field]["value"] += chr(ch)
            except curses.error as e:
                 logging.error(f"Error in message input form: {e}")
                 break # Exit form on error
            except KeyboardInterrupt:
                 break # Exit on Ctrl+C

        # Cleanup
        curses.curs_set(0) # Hide cursor again
        del win
        self.stdscr.touchwin() # Make sure main screen is refreshed
        self.stdscr.refresh()

    def clear_messages(self):
        """Clear the debug message buffer."""
        # Clear using MessageManager
        self.message_manager.clear_buffer("debug")
        self.scroll_pos = 0 # Reset scroll position
        self.process_manager._add_to_buffer("debug", "Debug log cleared.", "info")

    def get_help_content(self) -> list[tuple[str, str]]:
        """Return help content specific to the Debug view."""
        return [
            ("p", "Post Socket Message"),
            ("t", "Trigger Manual OCR"),
            ("r", "Clear Debug Log"),
            ("↑ / ↓", "Scroll Log Up/Down"),
            ("PgUp/PgDn", "Scroll Log Page Up/Down"),
            ("Home / End", "Scroll to Top/Bottom"),
            ("h", "Toggle Help"),
            ("q", "Quit Application"),
        ]
