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
        self.help_active = False
        
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

    def draw_menu(self):
        """Draw the application header and menu."""
        header = "33ter"
        self.stdscr.addstr(0, 0, "=" * self.width, curses.color_pair(HEADER_PAIR))
        self.stdscr.addstr(1, (self.width - len(header)) // 2, header, 
                          curses.color_pair(HEADER_PAIR) | curses.A_BOLD)
        
        # Menu items
        menu_items = [
            ("[1]Status", "status"),
            ("[2]Screenshot", "screenshot"),
            ("[3]Debug", "debug")
        ]
        
        quit_text = "[Q]uit"
        help_text = "[?]Help"
        
        # Calculate positions
        total_menu_width = sum(len(item[0]) + 2 for item in menu_items)
        total_width = len(quit_text) + total_menu_width + len(help_text) + 2
        start_pos = (self.width - total_width) // 2
        
        # Draw menu bar
        self.stdscr.addstr(2, start_pos, quit_text, curses.color_pair(MENU_PAIR))
        current_pos = start_pos + len(quit_text) + 1
        
        for item, view in menu_items:
            color = get_view_color(view) if self.view_name == view else curses.color_pair(MENU_PAIR)
            if self.view_name == view:
                self.stdscr.addstr(2, current_pos, f"|{item}|", color | curses.A_BOLD)
            else:
                self.stdscr.addstr(2, current_pos, f" {item} ", color)
            current_pos += len(item) + 2
        
        self.stdscr.addstr(2, current_pos, help_text, curses.color_pair(MENU_PAIR))
        self.stdscr.addstr(3, 0, "=" * self.width, curses.color_pair(HEADER_PAIR))

    def draw(self):
        """Draw the view content."""
        if self.check_size():
            self.stdscr.clear()
        self.draw_menu()
        self.draw_content()

    @abstractmethod
    def draw_content(self):
        """Draw the view-specific content."""
        pass

    @abstractmethod
    def handle_input(self, key):
        """Handle user input."""
        if key == ord('?'):
            self.help_active = True
            self.show_help(self.get_help_title(), self.get_help_content())
            self.help_active = False
            return True
        return False

    def show_help(self, title, help_lines):
        """Show help overlay with the given content."""
        if not help_lines:
            return
            
        box_height = len(help_lines) + 4
        box_width = max(len(line) for line in help_lines) + 4
        start_y = (self.height - box_height) // 2
        start_x = (self.width - box_width) // 2
        
        # Create help window
        help_win = curses.newwin(box_height, box_width, start_y, start_x)
        help_win.box()
        
        # Draw title
        help_win.addstr(0, (box_width - len(title)) // 2, f" {title} ", 
                       get_view_color(self.view_name) | curses.A_BOLD)
        
        # Draw help content
        for i, line in enumerate(help_lines):
            if line.endswith(":"):  # Headers
                help_win.addstr(i + 2, 2, line, curses.A_BOLD)
            else:
                help_win.addstr(i + 2, 2, line)
                
        # Draw footer
        help_win.addstr(box_height-1, 2, "Press ESC to close",
                       curses.color_pair(MENU_PAIR))
        
        help_win.refresh()
        
        # Wait for ESC
        while True:
            ch = help_win.getch()
            if ch == 27:  # ESC
                break
        
        # Cleanup
        help_win.clear()
        help_win.refresh()
        del help_win
        self.stdscr.touchwin()
        self.stdscr.refresh()

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

    def get_help_title(self):
        """Get the help screen title."""
        return f"{self.view_name.title()} View Help"

    @abstractmethod
    def get_help_content(self):
        """Get the help screen content lines."""
        pass
