import curses
import os
import re
import json
import time
import logging
import sys

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
    DebugView,
    BaseView
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
        if new_view in self.views:
            self.current_view = new_view
            if self.stdscr:
                self.stdscr.clear()  # Clear screen to ensure clean redraw
                self.views[self.current_view].draw()  # Draw the new view immediately
        else:
            logging.warning(f"Attempted to switch to non-existent view: {new_view}")

    def init_views(self):
        """Initialize view components."""
        try:
            self.views = {}
            view_classes = {
                "status": StatusView,
                "screenshot": ScreenshotView,
                "debug": DebugView
            }

            for name, ViewClass in view_classes.items():
                try:
                    self.views[name] = ViewClass(self.stdscr, self.process_manager)
                    logging.debug(f"Successfully initialized view: {name}")
                except Exception as e:
                    logging.error(f"Error initializing {name} view: {e}", exc_info=True)

            if self.current_view not in self.views:
                logging.warning(f"Default view '{self.current_view}' failed to initialize. Falling back.")
                available_views = list(self.views.keys())
                self.current_view = available_views[0] if available_views else None
                if self.current_view is None:
                    logging.error("CRITICAL: No views could be initialized. UI cannot run.")
                    raise RuntimeError("Failed to initialize any UI views.")

            if self.current_view:
                self.switch_view(self.current_view)
        except Exception as e:
            logging.error(f"Error during view initialization: {e}", exc_info=True)
            if "status" not in self.views:
                self.views["status"] = BaseView(self.stdscr, self.process_manager)
                self.views["status"].view_name = "status"
                self.current_view = "status"

    def run(self, stdscr):
        """Main UI loop"""
        self.stdscr = stdscr
        curses.curs_set(0)  # Hide cursor
        stdscr.nodelay(True)  # Non-blocking input
        stdscr.keypad(True)  # Enable special keys

        try:
            setup_colors()
            self.height, self.width = stdscr.getmaxyx()
            self.init_views()

            if self.current_view is None:
                return False  # Indicate failure to run

            last_refresh_time = 0
            refresh_interval = 0.1  # Refresh rate (10 times per second)

            while True:
                current_time = time.time()
                key = stdscr.getch()  # Check for input (non-blocking)

                if key == curses.KEY_RESIZE:
                    self.height, self.width = stdscr.getmaxyx()
                    for view in self.views.values():
                        view.resize(self.height, self.width)
                    stdscr.clear()  # Force full redraw on resize
                    last_refresh_time = 0  # Force immediate redraw

                if key != -1:
                    if not self.handle_input(key):
                        if self.current_view and self.current_view in self.views:
                            if not self.views[self.current_view].handle_input(key):
                                if key == ord('q'):
                                    break  # Exit main loop
                        elif key == ord('q'):
                            break

                    last_refresh_time = 0

                if current_time - last_refresh_time >= refresh_interval:
                    if self.current_view and self.current_view in self.views:
                        self.views[self.current_view].draw()
                    else:
                        try:
                            stdscr.erase()
                            stdscr.addstr(0, 0, "ERROR: Current view unavailable. Press 'q' to quit.")
                            stdscr.refresh()
                        except:
                            pass
                    last_refresh_time = current_time

                time.sleep(0.01)

        except curses.error as e:
            logging.error(f"Curses error in main loop: {e}", exc_info=True)
            curses.curs_set(1)
            stdscr.keypad(False)
            stdscr.nodelay(False)
            curses.endwin()
            print(f"\nCurses error occurred: {e}", file=sys.stderr)
            return False
        except Exception as e:
            logging.error(f"Unexpected error in UI loop: {e}", exc_info=True)
            try:
                curses.curs_set(1)
                stdscr.keypad(False)
                stdscr.nodelay(False)
                curses.endwin()
            except:
                pass
            print(f"\nUnexpected UI error: {e}", file=sys.stderr)
            return False

        return True

    def handle_input(self, key):
        """Handle global input."""
        if key == ord('q'):
            return False
        elif key in (ord('1'), ord('2'), ord('3')):
            new_view_map = {
                ord('1'): "status",
                ord('2'): "screenshot",
                ord('3'): "debug"
            }
            new_view = new_view_map.get(key)
            if new_view and new_view in self.views:
                self.switch_view(new_view)
                return True
            else:
                logging.warning(f"Attempted to switch to unavailable view via key '{chr(key)}'")
                return False
        return False