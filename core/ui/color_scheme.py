"""Color scheme definitions for the terminal UI."""
import curses
import sys

# Color pair constants
HEADER_PAIR = 1
MENU_PAIR = 2
STATUS_RUNNING = 3
STATUS_STOPPED = 4
SELECTED_VIEW = 5
STATUS_VIEW = 6
SCREENSHOT_VIEW = 7
DEBUG_VIEW = 8
CONNECTION_ACTIVE = 9

def verify_color_support():
    """Verify terminal color support."""
    if not sys.stdout.isatty():
        raise RuntimeError("Not running in a terminal")
    
    if not curses.has_colors():
        raise RuntimeError("Terminal does not support colors")
    
    if not curses.can_change_color():
        print("Warning: Terminal cannot change colors, using defaults", file=sys.stderr)
    
    return True

def setup_colors():
    """Initialize color pairs for the UI"""
    verify_color_support()
    curses.start_color()
    curses.use_default_colors()
    
    curses.init_pair(HEADER_PAIR, curses.COLOR_CYAN, -1)
    curses.init_pair(MENU_PAIR, 51, -1)
    curses.init_pair(STATUS_RUNNING, curses.COLOR_GREEN, -1)
    curses.init_pair(STATUS_STOPPED, curses.COLOR_RED, -1)
    curses.init_pair(SELECTED_VIEW, 213, -1)
    curses.init_pair(STATUS_VIEW, 226, -1)
    curses.init_pair(SCREENSHOT_VIEW, 118, -1)
    curses.init_pair(DEBUG_VIEW, 208, -1)
    curses.init_pair(CONNECTION_ACTIVE, 46, -1)

def get_view_color(view_name):
    """Get the color pair for a specific view"""
    color_map = {
        "status": STATUS_VIEW,
        "screenshot": SCREENSHOT_VIEW,
        "debug": DEBUG_VIEW
    }
    return curses.color_pair(color_map.get(view_name, MENU_PAIR))
