"""Debug view implementation for the terminal UI."""
import curses
import time
import traceback
import json
import logging  # Ensure logging is imported

from .base_view import BaseView
from .color_scheme import *
from ..message_system import MessageManager, MessageLevel, MessageCategory

# Get a logger instance for this module
logger = logging.getLogger(__name__)

class DebugView(BaseView):
    """Debug view for SocketIO messages and client communication."""
    def __init__(self, stdscr, process_manager):
        super().__init__(stdscr, process_manager)
        self.view_name = "debug"
        self.scroll_pos = 0

    def draw_content(self):
        """Draw the debug view content."""
        # Use self.win.getmaxyx() for content window dimensions
        max_y, max_x = self.win.getmaxyx()
        try:
            self.win.addstr(1, 2, "Socket.IO Debug Log", curses.A_BOLD | curses.A_UNDERLINE)
        except curses.error:
            pass  # Ignore if too small

        # Use MessageManager output directly
        log_lines = self.process_manager.get_output("debug")

        # Calculate visible lines (adjust for header/footer/borders)
        visible_lines = max(0, max_y - 4)  # Leave space for title, border, scrollbar

        # Adjust scroll position if necessary (ensure scroll_pos is valid)
        max_scroll = max(0, len(log_lines) - visible_lines)
        self.scroll_pos = max(0, min(self.scroll_pos, max_scroll))

        # Get the slice of lines to display
        display_lines = log_lines[self.scroll_pos : self.scroll_pos + visible_lines]

        # Display log lines
        for i, line_str in enumerate(display_lines):
            y_pos = 3 + i  # Start drawing below header
            # Check against content window height (max_y)
            if y_pos >= max_y - 1:  # Stop before the last line (used for border)
                break

            # Basic coloring based on keywords in the formatted string
            color = curses.A_NORMAL
            line_upper = line_str.upper()  # Check uppercase for consistency
            if "[ERROR]" in line_upper or "(error)" in line_upper or "SERVER_STDERR" in line_upper:
                color = curses.color_pair(STATUS_STOPPED) | curses.A_BOLD
            elif "[WARNING]" in line_upper or "(warning)" in line_upper:
                color = curses.color_pair(MENU_PAIR) | curses.A_BOLD
            elif "SENDING MESSAGE" in line_upper or "(localui)" in line_upper:
                color = curses.color_pair(CONNECTION_ACTIVE)

            try:
                # Ensure line fits width, truncate if necessary
                # Check against content window width (max_x)
                truncated_line = line_str[:max_x - 3]  # Leave space for border (x=0, x=max_x-1) and margin (x=1)
                self.win.addstr(y_pos, 2, truncated_line, color)
            except curses.error as e:
                # Log curses errors if they happen unexpectedly
                logger.debug(f"Curses error in DebugView draw_content loop: {e} at y={y_pos}, max_y={max_y}, max_x={max_x}")
                # Don't re-raise, just stop drawing this line
                pass

        # Add scroll indicator if needed and if space allows
        # Check against content window dimensions (max_y, max_x)
        if len(log_lines) > visible_lines and max_y > 2 and max_x >= 10:
            try:
                # Ensure division by zero doesn't happen
                scroll_base = len(log_lines) - visible_lines
                scroll_perc = int((self.scroll_pos / scroll_base) * 100) if scroll_base > 0 else 0
                # Draw on second-to-last line of the content window
                self.win.addstr(max_y - 2, max_x - 10, f"Scroll:{scroll_perc:3d}%", curses.A_REVERSE)
            except curses.error as e:
                logger.debug(f"Curses error drawing scroll indicator: {e}, max_y={max_y}, max_x={max_x}")
                pass  # Ignore error if drawing fails
        elif max_y > 2 and max_x >= 10:
            try:
                # Clear scroll indicator area if not needed
                self.win.addstr(max_y - 2, max_x - 10, " " * 9, curses.A_NORMAL)
            except curses.error:
                pass  # Ignore error if clearing fails

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
                 logger.error(f"Error in message input form: {e}")
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
        self.process_manager.message_manager.clear_buffer("debug")  # Use process_manager's instance
        self.scroll_pos = 0  # Reset scroll position
        # Add message via manager
        self.process_manager.message_manager.add_message(
            content="Debug log cleared.",
            level=MessageLevel.INFO,
            category=MessageCategory.SYSTEM,
            source="ui_action",
            buffer_name="debug"
        )

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
