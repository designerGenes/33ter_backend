import curses
import os
import re
import json
import time

from utils import (
    get_screenshots_dir, 
    get_temp_dir, 
    get_frequency_config_file
)

# Color pair definitions
HEADER_PAIR = 1
MENU_PAIR = 2
STATUS_RUNNING = 3
STATUS_STOPPED = 4
SELECTED_VIEW = 5
STATUS_VIEW = 6
SCREENSHOT_VIEW = 7
DEBUG_VIEW = 8
CONNECTION_ACTIVE = 9

from .ui import (
    setup_colors,
    StatusView,
    ScreenshotView,
    DebugView
)

class TerminalUI:
    """
    Terminal UI handler for the 33ter application.
    Manages the curses interface, user input, and display.
    """
    
    def __init__(self, process_manager):
        self.process_manager = process_manager
        self.current_view = "status"  # Changed default view
        self.help_active = False
        self.views = {}
        self.stdscr = None
        self._last_view = None

    def switch_view(self, new_view):
        """Handle proper view transitions."""
        if self._last_view and self._last_view in self.views:
            self.views[self._last_view].on_deactivate()
        
        self.current_view = new_view
        self.views[new_view].on_activate()
        self._last_view = new_view

    def init_views(self):
        """Initialize view components."""
        self.views = {
            "status": StatusView(self.stdscr, self.process_manager),
            "screenshot": ScreenshotView(self.stdscr, self.process_manager),
            "debug": DebugView(self.stdscr, self.process_manager)
        }
        self.switch_view(self.current_view)

    def run(self, stdscr):
        """Main UI loop"""
        self.stdscr = stdscr
        setup_colors()
        self.init_views()
        stdscr.timeout(100)

        while True:
            try:
                stdscr.clear()
                self.views[self.current_view].draw()
                stdscr.refresh()

                key = stdscr.getch()
                if key != -1:
                    if not self.handle_input(key):
                        break
            except curses.error:
                pass

        return True

    def handle_input(self, key):
        """Handle global input."""
        if key == ord('q'):
            return False
        elif key in (ord('1'), ord('2'), ord('3')):
            new_view = {
                ord('1'): "status",
                ord('2'): "screenshot",
                ord('3'): "debug"
            }[key]
            self.switch_view(new_view)
        else:
            self.views[self.current_view].handle_input(key)
        return True