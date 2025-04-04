"""Base class for terminal UI views."""
import curses
import sys
import importlib.util
import os
import time
import logging # Import logging
from abc import ABC, abstractmethod
from .color_scheme import HEADER_PAIR, MENU_PAIR, SELECTED_VIEW, get_view_color

class BaseView(ABC):
    """Abstract base class for all terminal UI views."""
    def __init__(self, stdscr, process_manager):
        self.stdscr = stdscr
        self.process_manager = process_manager
        self.height, self.width = stdscr.getmaxyx()
        # Create a new window for the view content area
        # Ensure dimensions are valid before creating window
        win_height = max(1, self.height - 4)
        win_width = max(1, self.width - 2)
        win_y = 3
        win_x = 1
        self.win = curses.newwin(win_height, win_width, win_y, win_x)
        self.win.keypad(True) # Enable special keys
        self.view_name = "Base" # Should be overridden by subclasses
        self.show_help = False

    def resize(self, height, width):
        """Handle terminal resize."""
        self.height, self.width = height, width
        try:
            # Ensure dimensions are valid before resizing
            new_height = max(1, height - 4)
            new_width = max(1, width - 2)
            self.win.resize(new_height, new_width)
            # Optionally move the window if needed, e.g., self.win.mvwin(3, 1)
        except curses.error as e:
            # Handle potential errors during resize, e.g., size too small
            # Log this error?
            pass # Avoid crashing on resize errors

    def draw_header(self, current_view):
        """Draw the common header."""
        # Use self.stdscr.getmaxyx() for main screen dimensions
        scr_h, scr_w = self.stdscr.getmaxyx()
        try:
            # Check width before drawing
            if scr_w > 0:
                self.stdscr.hline(0, 0, ' ', scr_w, curses.color_pair(HEADER_PAIR))
                title = " Threethreeter Local Backend Monitor "
                # Ensure title fits, adjust centering if needed
                start_col = max(0, (scr_w - len(title)) // 2)
                # Truncate title if needed
                self.stdscr.addstr(0, start_col, title[:scr_w], curses.color_pair(HEADER_PAIR) | curses.A_BOLD)

            # Draw view tabs only if width allows
            if scr_w > 10: # Need some minimum width for tabs
                tabs = ["1:Status", "2:Screenshot", "3:Debug"]
                x_offset = 2
                for i, tab in enumerate(tabs):
                    view_name = tab.split(":")[1].lower()
                    attr = curses.color_pair(SELECTED_VIEW) | curses.A_BOLD if view_name == current_view else curses.color_pair(HEADER_PAIR)
                    # Check width before drawing tab
                    tab_text = f" {tab} "
                    if x_offset + len(tab_text) < scr_w: # Check if the whole tab fits
                        self.stdscr.addstr(1, x_offset, tab_text, attr)
                        x_offset += len(tab_text) + 1 # Add spacing
                    else:
                        break # Stop drawing tabs if no more space

        except curses.error as e:
            # Log errors if drawing outside screen bounds (e.g., small terminal)
            logging.debug(f"Curses error drawing header: {e}")
            pass

    def draw_footer(self):
        """Draw the common footer."""
        # Use self.stdscr.getmaxyx() for main screen dimensions
        scr_h, scr_w = self.stdscr.getmaxyx()
        try:
            # Draw footer line only if width > 0 and height > 0
            if scr_w > 0 and scr_h > 0:
                self.stdscr.hline(scr_h - 1, 0, ' ', scr_w, curses.color_pair(MENU_PAIR))

                # Draw footer text if width allows
                footer_text = " (q) Quit | (h) Help "
                if scr_w > len(footer_text):
                    self.stdscr.addstr(scr_h - 1, 1, footer_text, curses.color_pair(MENU_PAIR))

                # Add time if width allows
                current_time = time.strftime("%H:%M:%S")
                time_len = len(current_time)
                # Ensure enough space for footer_text and time
                if scr_w > len(footer_text) + time_len + 3: # +3 for spacing
                    self.stdscr.addstr(scr_h - 1, scr_w - time_len - 2, current_time, curses.color_pair(MENU_PAIR))

        except curses.error as e:
            # Log errors if drawing outside screen bounds
            logging.debug(f"Curses error drawing footer: {e}")
            pass

    @abstractmethod
    def draw_content(self):
        """Draw the specific content for the view. Must be implemented by subclasses."""
        pass

    @abstractmethod
    def get_help_content(self) -> list[tuple[str, str]]:
        """Return a list of (key, description) tuples for the help overlay. Must be implemented."""
        # Example: return [("q", "Quit"), ("h", "Toggle Help")]
        pass

    def draw_help_overlay(self):
        """Draw the help overlay."""
        help_content = self.get_help_content()
        if not help_content:
            return # Don't draw if no content

        # Calculate overlay dimensions
        max_key_len = max(len(key) for key, desc in help_content) if help_content else 0
        max_desc_len = max(len(desc) for key, desc in help_content) if help_content else 0
        box_width = max(30, max_key_len + max_desc_len + 7) # Key: Desc
        box_height = len(help_content) + 4 # Title + content + padding

        # Center the box
        start_y = (self.height - box_height) // 2
        start_x = (self.width - box_width) // 2

        # Ensure coordinates are valid
        if start_y < 0 or start_x < 0 or start_y + box_height > self.height or start_x + box_width > self.width:
             # Too small to draw help overlay, maybe show a message?
             try:
                  self.win.addstr(1, 2, "Terminal too small for help", curses.A_BOLD | curses.color_pair(STATUS_STOPPED))
             except curses.error: pass
             return

        try:
            help_win = curses.newwin(box_height, box_width, start_y, start_x)
            help_win.erase()
            help_win.box()
            help_win.addstr(1, (box_width - 10) // 2, " Help Menu ", curses.A_BOLD | curses.A_UNDERLINE)

            for i, (key, desc) in enumerate(help_content):
                help_win.addstr(i + 3, 3, f"{key.upper():<{max_key_len}} : {desc}")

            help_win.refresh()

            # Wait for any key press to close
            self.stdscr.nodelay(False) # Blocking wait for key
            self.stdscr.getch()
            self.stdscr.nodelay(True) # Restore non-blocking

            # Clean up - redraw underlying screen elements
            self.stdscr.touchwin()
            self.stdscr.refresh()
            del help_win

        except curses.error as e:
             # Log error if help overlay fails
             logging.error(f"Failed to draw help overlay: {e}")
             # Try to restore terminal state
             self.stdscr.nodelay(True)


    def draw(self):
        """Draw the entire view (header, content, footer)."""
        try:
            # Get dimensions each time in case of resize
            scr_h, scr_w = self.stdscr.getmaxyx()
            # Check for minimal terminal size
            if scr_h < 5 or scr_w < 20:
                 try:
                     self.stdscr.erase()
                     self.stdscr.addstr(0, 0, "Terminal too small.", curses.A_BOLD | curses.color_pair(STATUS_STOPPED))
                     self.stdscr.refresh()
                 except curses.error: pass # Ignore if even this fails
                 return # Don't attempt further drawing

            # Resize content window first
            self.resize(scr_h, scr_w)

            self.stdscr.erase() # Clear entire screen
            self.win.erase() # Clear content window

            # Draw components, they now have internal checks
            self.draw_header(self.view_name)
            self.draw_content() # Call subclass implementation
            self.draw_footer()

            # Refresh the main screen and the content window
            self.stdscr.noutrefresh()
            self.win.noutrefresh()
            curses.doupdate()

            if self.show_help:
                self.draw_help_overlay()
                self.show_help = False # Automatically hide after showing once

        except curses.error as e:
            # Log errors related to drawing (e.g., terminal too small)
            logging.error(f"Error drawing view {self.view_name}: {e}")
            # Attempt to draw a minimal error message if possible
            # This is the block causing the loop if it also fails
            try:
                 # Check dimensions *before* trying to write error
                 h, w = self.stdscr.getmaxyx()
                 if h > 0 and w > 0:
                     self.stdscr.erase()
                     error_msg = f"Error drawing UI: {e}. Resize terminal."
                     self.stdscr.addstr(0, 0, error_msg[:w-1]) # Truncate error msg
                     self.stdscr.refresh()
            except curses.error as inner_e:
                 # If drawing the error message *also* fails, log it and stop
                 logging.critical(f"CRITICAL: Failed even to draw error message: {inner_e}. Terminal likely unusable.")
                 # Avoid infinite loop by not trying to draw again here.
                 # The main loop might catch this or exit.
                 pass
            except Exception as final_e:
                 logging.critical(f"CRITICAL: Unexpected exception during error handling: {final_e}")
                 pass

    def handle_input(self, key):
        """Handle common input keys."""
        if key == ord('h'):
            self.show_help = True
            return True # Indicate input was handled
        elif key == curses.KEY_RESIZE:
             # Let the main loop handle resize by redrawing
             self.height, self.width = self.stdscr.getmaxyx()
             self.resize(self.height, self.width)
             # Force redraw
             self.stdscr.clear()
             self.win.clear()
             return True
        # Allow subclasses to handle other keys or return False
        return False
