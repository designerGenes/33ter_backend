import curses
import time
import logging
import sys


from .process_manager import ProcessManager
from .status_view import StatusView
from .screenshot_view import ScreenshotView
from .debug_view import DebugView
from .color_scheme import setup_colors

class TerminalUI:
    """
    Terminal UI handler for the Threethreeter application.
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
                # Attempt to create a fallback BaseView if StatusView failed
                try:
                    self.views["status"] = BaseView(self.stdscr, self.process_manager)
                    self.views["status"].view_name = "status" # Manually set name
                    self.current_view = "status"
                    logging.warning("Fell back to basic StatusView due to initialization error.")
                except Exception as fallback_e:
                     logging.critical(f"CRITICAL: Failed even to initialize fallback BaseView: {fallback_e}")
                     raise RuntimeError("Failed to initialize any UI views.") from fallback_e

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
                    # --- Add temporary logging ---
                    try:
                        key_char = chr(key) if 32 <= key <= 126 else 'N/A'
                    except ValueError:
                        key_char = 'Invalid'
                    self.process_manager.logger.debug(f"TerminalUI.run received key: {key} (char: {key_char})")
                    # --- End temporary logging ---

                    # First, try global handling (quit, view switch)
                    if not self.handle_input(key):
                        # If not handled globally, pass to current view
                        if self.current_view and self.current_view in self.views:
                            if not self.views[self.current_view].handle_input(key):
                                # If view didn't handle it, check for quit again (redundant but safe)
                                if key == ord('q'):
                                    break  # Exit main loop
                        elif key == ord('q'): # Handle quit even if current_view is somehow invalid
                            break

                    # Input was handled (or ignored), force refresh potentially sooner
                    last_refresh_time = 0

                # Refresh screen periodically or after input
                if current_time - last_refresh_time >= refresh_interval:
                    if self.current_view and self.current_view in self.views:
                        self.views[self.current_view].draw()
                    else:
                        # Handle case where current_view is invalid
                        try:
                            stdscr.erase()
                            stdscr.addstr(0, 0, "ERROR: Current view unavailable. Press 'q' to quit.")
                            stdscr.refresh()
                        except curses.error:
                            pass # Ignore if even this fails
                    last_refresh_time = current_time

                time.sleep(0.01) # Small sleep to prevent high CPU usage

        except curses.error as e:
            logging.error(f"Curses error in main loop: {e}", exc_info=True)
            # Attempt to clean up curses state gracefully
            try:
                curses.curs_set(1)
                stdscr.keypad(False)
                stdscr.nodelay(False)
                curses.endwin()
            except:
                pass # Ignore errors during cleanup
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
        # --- Add temporary logging ---
        try:
            key_char = chr(key) if 32 <= key <= 126 else 'N/A'
        except ValueError:
            key_char = 'Invalid'
        self.process_manager.logger.debug(f"TerminalUI.handle_input processing key: {key} (char: {key_char})")
        # --- End temporary logging ---

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