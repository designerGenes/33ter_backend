"""Screenshot management module for Threethreeter application.

This module handles continuous screenshot capture and management using a dedicated thread.
It maintains a configurable capture frequency and implements automatic cleanup of old files.

#TODO:
- Add memory management to prevent buffer overflow with high frequency captures
- Implement proper thread shutdown on system signals
- Add screenshot compression for long-term storage
- Consider implementing a screenshot queue for high-load situations
- Add disk space monitoring and automatic cleanup when space is low
"""
import os
import time
import json
import logging
import threading
from datetime import datetime

from path_config import get_temp_dir, get_logs_dir, get_frequency_config_file
from ocr_processor import OCRProcessor
from message_system import MessageManager, MessageLevel, MessageCategory

class ScreenshotManager:
    """Manages continuous screenshot capture and cleanup.
    
    This class provides functionality for:
    - Continuous screenshot capture in a background thread
    - Configurable capture frequency
    - Automatic cleanup of old screenshots
    - Pause/resume capture functionality
    - Real-time frequency adjustment
    
    #TODO:
    - Implement thread pooling for parallel screenshot processing
    - Add proper thread synchronization for shared resources
    - Consider implementing a producer-consumer pattern
    - Add health monitoring for the capture thread
    - Implement proper error handling for disk full scenarios
    """
    
    def __init__(self, message_manager: MessageManager):
        self.ocr_processor = OCRProcessor()
        self.logger = self._setup_logging()
        self.screenshot_interval = 4.0
        
        # Store the passed message manager instance
        self.message_manager = message_manager
        
        # Initialize legacy buffer
        self.output_buffer = []
        
        self.load_screenshot_config()
        
        # State flags
        self._running = False
        self._paused = False

    def _setup_logging(self):
        """Configure screenshot manager logging."""
        log_file = os.path.join(get_logs_dir(), "screenshot_manager.log")
        
        logger = logging.getLogger('Threethreeter-Screenshot')
        logger.setLevel(logging.INFO)
        
        if not logger.handlers:
            handler = logging.FileHandler(log_file)
            formatter = logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            )
            handler.setFormatter(formatter)
            logger.addHandler(handler)
        
        return logger

    def load_screenshot_config(self):
        """Load screenshot frequency from config."""
        try:
            config_file = get_frequency_config_file()
            if os.path.exists(config_file):
                with open(config_file) as f:
                    loaded_interval = float(json.load(f).get('frequency', 4.0))
                    if 0.1 <= loaded_interval <= 60.0:
                        if self.screenshot_interval != loaded_interval:
                            self.screenshot_interval = loaded_interval
                            self._add_to_buffer(f"Screenshot frequency updated to {self.screenshot_interval:.1f}s", "info")
                            self.logger.info(f"Screenshot frequency updated to {self.screenshot_interval:.1f}s")
                        else:
                            self.logger.debug(f"Screenshot frequency already {self.screenshot_interval:.1f}s, no change.")
                    else:
                        self.logger.warning(f"Loaded frequency {loaded_interval} out of range (0.1-60.0), keeping current value {self.screenshot_interval:.1f}s.")
            else:
                self.logger.info(f"Frequency config file not found at {config_file}, using current value {self.screenshot_interval:.1f}s.")
        except (ValueError, TypeError, json.JSONDecodeError) as e:
            self.logger.error(f"Error loading or parsing screenshot config: {e}. Using current value {self.screenshot_interval:.1f}s.")
        except Exception as e:
            self.logger.error(f"Unexpected error loading screenshot config: {e}. Using current value {self.screenshot_interval:.1f}s.", exc_info=True)

    def _add_to_buffer(self, message, level="info"):
        """Add a message to the output buffer with timestamp."""
        try:
            msg_level = getattr(MessageLevel, level.upper(), MessageLevel.INFO)
        except ValueError:
            msg_level = MessageLevel.INFO
            
        if "screenshot" in message.lower():
            category = MessageCategory.SCREENSHOT
        elif "deleted" in message.lower() or "cleaned" in message.lower():
            category = MessageCategory.SYSTEM
        else:
            category = MessageCategory.SCREENSHOT
            
        self.message_manager.add_message(
            content=message,
            level=msg_level,
            category=category,
            source="screenshot",
            buffer_name="screenshot"
        )
        
        timestamp = time.strftime("%H:%M:%S")
        emoji = "📸" if "screenshot" in message.lower() else "🗑️" if "deleted" in message.lower() else "ℹ️"
        self.output_buffer.append(f"{timestamp} {emoji} {message} ({level})")
        
        if len(self.output_buffer) > 1000:
            self.output_buffer.pop(0)

    def process_latest_screenshot(self, manual_trigger: bool = False):
        """Process the most recent screenshot."""
        self.logger.info(f"Processing latest screenshot (Manual Trigger: {manual_trigger})")
        result = self.ocr_processor.process_latest_screenshot()
        if result:
            self._add_to_buffer("OCR processing successful", "info")
        else:
            self._add_to_buffer("OCR processing returned no text or failed.", "warning")
        return result

    def is_running(self):
        """Check if the capture loop is running and not paused."""
        return self._running and not self._paused

    def get_output(self):
        """Get the current output buffer."""
        messages = self.message_manager.get_formatted_messages("screenshot")
        if not messages:
            return self.output_buffer.copy()
        return messages

    def get_status(self):
        """Returns the current status of the Screenshot Manager."""
        if not self._running:
            return "Stopped"
        elif self._paused:
            return "Paused"
        else:
            return "Running"

    def run(self, stop_event: threading.Event):
        """Main screenshot capture loop, intended to be run in a thread."""
        self.logger.info("ScreenshotManager run method started.")
        self._add_to_buffer("Screenshot capture service starting...", "info")

        self._running = True
        self._paused = False

        pause_file = os.path.join(get_temp_dir(), "signal_pause_capture")
        reload_file = os.path.join(get_temp_dir(), "reload_frequency")

        while not stop_event.is_set():
            try:
                if os.path.exists(pause_file):
                    if not self._paused:
                        self._paused = True
                        self._add_to_buffer("Screenshot capture paused.", "info")
                        self.logger.info("Screenshot capture paused.")
                    time.sleep(1)
                    continue
                else:
                    if self._paused:
                        self._paused = False
                        self._add_to_buffer("Screenshot capture resumed.", "info")
                        self.logger.info("Screenshot capture resumed.")

                filepath = self.ocr_processor.capture_screenshot()
                if filepath:
                    filename = os.path.basename(filepath)
                    self._add_to_buffer(f"Captured: {filename}", "info")

                deleted = self.ocr_processor.cleanup_old_screenshots()
                if deleted:
                    self._add_to_buffer(f"Cleaned up {deleted} old screenshots", "info")

                if os.path.exists(reload_file):
                    self.logger.info("Reload frequency signal detected.")
                    self.load_screenshot_config()
                    try:
                        os.remove(reload_file)
                        self.logger.info("Reload frequency signal file removed.")
                    except OSError as e:
                        self.logger.warning(f"Could not remove reload signal file: {e}")
                    except Exception as e:
                        self.logger.error(f"Unexpected error removing reload signal file: {e}", exc_info=True)

                wait_until = time.time() + self.screenshot_interval
                while time.time() < wait_until and not stop_event.is_set():
                    if os.path.exists(pause_file):
                        if not self._paused:
                            self._paused = True
                            self._add_to_buffer("Screenshot capture paused.", "info")
                            self.logger.info("Screenshot capture paused during wait.")
                        break
                    time.sleep(0.1)

            except Exception as e:
                self.logger.error(f"Error in screenshot manager run loop: {e}", exc_info=True)
                self._add_to_buffer(f"ERROR in capture loop: {str(e)}", "error")
                if not stop_event.wait(1.0):
                    continue
                else:
                    break

        self._running = False
        self._paused = False
        self._add_to_buffer("Screenshot capture service stopped.", "info")
        self.logger.info("ScreenshotManager run method finished.")