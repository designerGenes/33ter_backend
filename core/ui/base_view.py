"""Base class for terminal UI views."""
import curses
from abc import ABC, abstractmethod
from .color_scheme import *

class BaseView(ABC):
    def __init__(self, stdscr, process_manager):
        self.stdscr = stdscr
        self.process_manager = process_manager
        self.height, self.width = stdscr.getmaxyx()
        self.active = False

    def on_activate(self):
        """Called when view becomes active."""
        self.active = True
        self.height, self.width = self.stdscr.getmaxyx()

    def on_deactivate(self):
        """Called when view becomes inactive."""
        self.active = False

    def check_size(self):
        """Update window dimensions and check if they changed."""
        new_h, new_w = self.stdscr.getmaxyx()
        if new_h != self.height or new_w != self.width:
            self.height, self.width = new_h, new_w
            return True
        return False

    @abstractmethod
    def draw(self):
        """Draw the view content."""
        if self.check_size():
            self.stdscr.clear()

    @abstractmethod
    def handle_input(self, key):
        """Handle user input."""
        pass

    def draw_header(self, title):
        """Draw a header for the view."""
        view_header = f"=== {title} ==="
        self.stdscr.addstr(4, (self.width - len(view_header)) // 2, 
                          view_header, curses.A_BOLD)

    def draw_controls(self, controls, y_pos):
        """Draw control instructions."""
        try:
            self.stdscr.addstr(y_pos, 2, controls, curses.color_pair(MENU_PAIR))
        except curses.error:
            pass
