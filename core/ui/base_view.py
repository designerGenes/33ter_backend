"""Base class for terminal UI views."""
import curses
import sys
import importlib.util
import os
import time
import logging # Import logging
from abc import ABC, abstractmethod
from .color_scheme import *

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
        try:
            self.stdscr.hline(0, 0, ' ', self.width, curses.color_pair(HEADER_PAIR))
            title = " 33ter Local Backend Monitor "
            # Ensure title fits, adjust centering if needed
            start_col = max(0, (self.width - len(title)) // 2)
            self.stdscr.addstr(0, start_col, title[:self.width], curses.color_pair(HEADER_PAIR) | curses.A_BOLD)

            # Draw view tabs
            tabs = ["1:Status", "2:Screenshot", "3:Debug"]
            x_offset = 2
            for i, tab in enumerate(tabs):
                view_name = tab.split(":")[1].lower()
                attr = curses.color_pair(SELECTED_VIEW) | curses.A_BOLD if view_name == current_view else curses.color_pair(HEADER_PAIR)
                # Check width before drawing tab
                if x_offset + len(tab) + 3 < self.width:
                    self.stdscr.addstr(1, x_offset, f" {tab} ", attr)
                    x_offset += len(tab) + 3 # Add spacing
                else:
                    break # Stop drawing tabs if no more space

        except curses.error as e:
            # Log errors if drawing outside screen bounds (e.g., small terminal)
            logging.debug(f"Curses error drawing header: {e}")
            pass

    def draw_footer(self):
        """Draw the common footer."""
        try:
            footer_text = " (q) Quit | (h) Help "
            self.stdscr.hline(self.height - 1, 0, ' ', self.width, curses.color_pair(MENU_PAIR))
            self.stdscr.addstr(self.height - 1, 1, footer_text, curses.color_pair(MENU_PAIR))
            # Add time or other status if needed
            current_time = time.strftime("%H:%M:%S")
            self.stdscr.addstr(self.height - 1, self.width - len(current_time) - 2, current_time, curses.color_pair(MENU_PAIR))
        except curses.error:
            # Ignore errors if drawing outside screen bounds
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
            self.height, self.width = self.stdscr.getmaxyx()
            self.resize(self.height, self.width) # Adjust window size

            self.stdscr.erase() # Clear entire screen
            self.win.erase() # Clear content window

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
            try:
                 self.stdscr.erase()
                 self.stdscr.addstr(0, 0, f"Error drawing UI: {e}. Please resize terminal.")
                 self.stdscr.refresh()
            except:
                 pass # Avoid further errors

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
