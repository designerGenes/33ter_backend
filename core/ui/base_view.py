"""Base class for terminal UI views."""
import curses
import sys
import importlib.util
import os
import time
from abc import ABC, abstractmethod
from .color_scheme import *

class BaseView(ABC):
    def __init__(self, stdscr, process_manager):
        self.stdscr = stdscr
        self.process_manager = process_manager
        self.height, self.width = stdscr.getmaxyx()
        self.active = False
        self.help_active = False
        self.show_help = False
        self.view_name = "base"
        self.reload_feedback_time = 0
        self.reload_feedback_duration = 0.5  # seconds
        
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
        self.draw_reload_feedback()

    @abstractmethod
    def draw_content(self):
        """Draw the view-specific content."""
        pass

    def handle_input(self, key):
        """Handle common input across all views."""
        if key == ord('?'):
            self.help_active = not self.help_active
            return True
        elif key == 18:  # Ctrl-R
            try:
                # First attempt ProcessManager notification
                self.process_manager.reload_screen()
                # Then do the actual code reload
                self.reload_view()
                # Set feedback time for visual indicator
                self.reload_feedback_time = time.time()
                return True
            except Exception as e:
                self.process_manager.get_output_queues()["debug"].append(
                    f"Reload failed: {str(e)}")
        return False

    def reload_view(self):
        """Reload the current view's module from disk."""
        try:
            # Get the current module's file path
            module_file = sys.modules[self.__class__.__module__].__file__
            
            # Remove the module from sys.modules to force a fresh reload
            module_name = self.__class__.__module__
            if module_name in sys.modules:
                del sys.modules[module_name]
            
            # Load the module spec
            spec = importlib.util.spec_from_file_location(module_name, module_file)
            module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = module
            spec.loader.exec_module(module)
            
            # Get the view class and create new instance
            view_class = getattr(module, self.__class__.__name__)
            new_view = view_class(self.stdscr, self.process_manager)
            
            # Preserve important state
            new_view.height = self.height
            new_view.width = self.width
            new_view.show_help = self.show_help
            
            # Update self with new instance's attributes
            self.__class__ = view_class
            self.__dict__.update(new_view.__dict__)
            
        except Exception as e:
            # Log error but don't crash
            with open(os.path.join(os.path.dirname(module_file), "reload_error.log"), "w") as f:
                f.write(f"Error reloading view: {str(e)}")

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

    def draw_reload_feedback(self):
        """Draw reload feedback if recently reloaded."""
        if time.time() - self.reload_feedback_time < self.reload_feedback_duration:
            text = "⟳ Reloaded"
            x = self.width - len(text) - 2
            y = 0  # Top right corner
            self.stdscr.addstr(y, x, text, curses.A_BOLD | curses.color_pair(STATUS_RUNNING))
