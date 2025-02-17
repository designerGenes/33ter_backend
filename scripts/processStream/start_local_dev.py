// ...existing code...

    def draw_process_output(self, stdscr, process_name):
        height, width = stdscr.getmaxyx()
        
        if process_name == "screenshot":
            self.draw_screenshot_controls(stdscr, 4)
            start_y = 8  # Start output after controls
        elif process_name == "process":
            # Draw process controls
            controls = "[T]rigger Processing [?]Help"
            stdscr.addstr(4, 2, controls, curses.color_pair(MENU_PAIR))
            
            # Draw cooldown timer if active
            current_time = time.time()
            if current_time - self.last_trigger_time < self.trigger_cooldown:
                remaining = int(self.trigger_cooldown - (current_time - self.last_trigger_time))
                cooldown_msg = f" (Cooldown: {remaining}s)"
                stdscr.addstr(4, len(controls) + 3, cooldown_msg, curses.color_pair(STATUS_STOPPED))
            
            stdscr.addstr(5, 0, "=" * width, curses.color_pair(HEADER_PAIR))
            start_y = 6
        elif process_name == "socket":
            # Draw socket controls
            controls = "[P]ost Message [?]Help"
            stdscr.addstr(4, 2, controls, curses.color_pair(MENU_PAIR))
            stdscr.addstr(5, 0, "=" * width, curses.color_pair(HEADER_PAIR))
            start_y = 6
        else:
            start_y = 5

        if self.help_active:
            self.draw_help_screen(stdscr)
            return
        elif self.post_message_active and process_name == "socket":
            result = self.get_message_input(stdscr)
            self.post_message_active = False
            if result:
                message, title, log_type = result
                response = self.post_message_to_socket(message, title, log_type)
                if response:
                    self.process_manager.output_queues["socket"].append(response)
            return

        output_lines = self.process_manager.get_output(process_name)
        max_lines = height - start_y
        start_line = max(0, len(output_lines) - max_lines)
        
        # Add a colored header for the current view using the view-specific color
        view_header = f"=== {process_name.upper()} OUTPUT ==="
        view_color = self.get_view_color(process_name)
        stdscr.addstr(4, (width - len(view_header)) // 2, view_header, 
                     view_color | curses.A_BOLD)

// ...existing code...