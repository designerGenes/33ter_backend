import curses

# Color pair definitions
HEADER_PAIR = 1
MENU_PAIR = 2
STATUS_RUNNING = 3
STATUS_STOPPED = 4
SELECTED_VIEW = 5
MAIN_VIEW = 6
SCREENSHOT_VIEW = 7
PROCESS_VIEW = 8
SOCKET_VIEW = 9

class TerminalUI:
    def __init__(self):
        self.current_view = "main"
        self.help_active = False
        self.post_message_active = False

    def setup_colors(self):
        """Initialize color pairs for the UI"""
        curses.start_color()
        curses.use_default_colors()
        
        # Define colors using RGB values
        curses.init_pair(HEADER_PAIR, curses.COLOR_CYAN, -1)
        curses.init_pair(MENU_PAIR, 51, -1)
        curses.init_pair(STATUS_RUNNING, curses.COLOR_GREEN, -1)
        curses.init_pair(STATUS_STOPPED, curses.COLOR_RED, -1)
        curses.init_pair(SELECTED_VIEW, 213, -1)
        
        curses.init_pair(MAIN_VIEW, 226, -1)
        curses.init_pair(SCREENSHOT_VIEW, 118, -1)
        curses.init_pair(PROCESS_VIEW, 147, -1)
        curses.init_pair(SOCKET_VIEW, 208, -1)

    def get_view_color(self, view_name):
        """Get the color pair for a specific view"""
        color_map = {
            "main": MAIN_VIEW,
            "screenshot": SCREENSHOT_VIEW,
            "process": PROCESS_VIEW,
            "socket": SOCKET_VIEW
        }
        return curses.color_pair(color_map.get(view_name, MENU_PAIR))

    def draw_header(self, stdscr):
        height, width = stdscr.getmaxyx()
        header = "33ter Process Manager"
        
        stdscr.addstr(0, 0, "=" * width, curses.color_pair(HEADER_PAIR))
        stdscr.addstr(1, (width - len(header)) // 2, header, 
                     curses.color_pair(HEADER_PAIR) | curses.A_BOLD)
        
        menu_items = [
            ("[1]Main", "main"),
            ("[2]Screenshot", "screenshot"),
            ("[3]Process", "process"),
            ("[4]Socket", "socket")
        ]
        
        quit_text = "[Q]uit"
        restart_text = "[R]estart Current"
        
        total_menu_width = sum(len(item[0]) + 2 for item in menu_items)
        total_width = len(quit_text) + total_menu_width + len(restart_text) + 2
        start_pos = (width - total_width) // 2
        
        stdscr.addstr(2, start_pos, quit_text, curses.color_pair(MENU_PAIR))
        current_pos = start_pos + len(quit_text) + 1
        
        for item, view in menu_items:
            color = self.get_view_color(view) if view == self.current_view else curses.color_pair(MENU_PAIR)
            if view == self.current_view:
                stdscr.addstr(2, current_pos, f"|{item}|", color | curses.A_BOLD)
                current_pos += len(item) + 2
            else:
                stdscr.addstr(2, current_pos, f" {item} ", color)
                current_pos += len(item) + 2
        
        stdscr.addstr(2, current_pos, restart_text, curses.color_pair(MENU_PAIR))
        stdscr.addstr(3, 0, "=" * width, curses.color_pair(HEADER_PAIR))

    def draw_help_screen(self, stdscr):
        height, width = stdscr.getmaxyx()
        help_texts = {
            "main": [
                "Main View Help",
                "",
                "1-4: Switch between views",
                "Q: Quit application",
                "R: Restart current service",
                "ESC: Close help",
                "?: Show this help"
            ],
            "screenshot": [
                "Screenshot View Help",
                "",
                "This view manages the automatic screenshot capture service that monitors",
                "your screen for coding challenges. Screenshots are automatically captured",
                "at regular intervals and sent to the process server for OCR analysis.",
                "",
                "Space: Pause/Resume screenshot capture",
                "Left/Right: Adjust frequency by 0.5s (saves automatically)",
                "F: Enter new frequency value",
                "O: Open screenshots folder",
                "ESC: Close help",
                "?: Show this help"
            ],
            "process": [
                "Process View Help",
                "",
                "This view shows the processing of screenshots through OCR and AI analysis.",
                "Screenshots are processed using Azure Computer Vision for text extraction,",
                "followed by AI analysis to identify and solve coding challenges.",
                "",
                "T: Trigger processing of latest screenshot (30s cooldown)",
                "R: Restart process service",
                "ESC: Close help",
                "?: Show this help"
            ],
            "socket": [
                "Socket View Help",
                "",
                "This view shows messages and allows sending manual messages.",
                "",
                "P: Post a new message - opens a form where you can set:",
                "   • Title: The message header (shown in Socket theme color)",
                "   • Type: Info (blue), Prime (magenta), or Warning (yellow)",
                "   • Message: The content to send",
                "",
                "R: Restart socket service",
                "ESC: Close help/form",
                "?: Show this help"
            ]
        }

        texts = help_texts.get(self.current_view, help_texts["main"])
        box_height = len(texts) + 4
        box_width = max(len(line) for line in texts) + 4
        start_y = (height - box_height) // 2
        start_x = (width - box_width) // 2

        # Draw box
        for y in range(box_height):
            for x in range(box_width):
                if y in (0, box_height-1) or x in (0, box_width-1):
                    try:
                        stdscr.addch(start_y + y, start_x + x, curses.ACS_CKBOARD, 
                                   self.get_view_color(self.current_view))
                    except curses.error:
                        pass

        # Draw text
        for i, text in enumerate(texts):
            try:
                stdscr.addstr(start_y + i + 2, start_x + 2, text, 
                            self.get_view_color(self.current_view))
            except curses.error:
                pass