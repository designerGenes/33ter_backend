"""Screenshot management module for 33ter application."""
import os
import time
import json
import logging
import threading
from datetime import datetime

from utils import get_config_dir, get_temp_dir, get_logs_dir
from .ocr_processor import OCRProcessor

class ScreenshotManager:
    """Manages continuous screenshot capture and cleanup."""
    
    def __init__(self):
        self.ocr_processor = OCRProcessor()
        self.capturing = False
        self.capture_thread = None
        self.logger = self._setup_logging()
        self.screenshot_interval = 4.0
        self.load_screenshot_config()
        self.output_buffer = []
        
    def _setup_logging(self):
        """Configure screenshot manager logging."""
        log_file = os.path.join(get_logs_dir(), "screenshot_manager.log")
        
        logger = logging.getLogger('33ter-Screenshot')
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
            config_file = os.path.join(get_config_dir(), "screenshot_frequency.json")
            if os.path.exists(config_file):
                with open(config_file) as f:
                    self.screenshot_interval = float(json.load(f).get('frequency', 4.0))
                    self._add_to_buffer(f"Screenshot frequency set to {self.screenshot_interval}s")
        except Exception as e:
            self.logger.error(f"Error loading screenshot config: {e}")

    def _add_to_buffer(self, message, level="info"):
        """Add a message to the output buffer with timestamp."""
        timestamp = time.strftime("%H:%M:%S")
        emoji = "📸" if "screenshot" in message.lower() else "🗑️" if "deleted" in message.lower() else "ℹ️"
        self.output_buffer.append(f"{timestamp} {emoji} {message} ({level})")
        
        # Keep buffer size manageable
        if len(self.output_buffer) > 1000:
            self.output_buffer.pop(0)

    def _capture_loop(self):
        """Main screenshot capture loop."""
        self.logger.info("Starting screenshot capture loop")
        self._add_to_buffer("Screenshot capture started")
        
        while self.capturing:
            try:
                # Check for pause signal
                pause_file = os.path.join(get_temp_dir(), "signal_pause_capture")
                if os.path.exists(pause_file):
                    time.sleep(1)  # Sleep briefly while paused
                    continue
                
                # Capture screenshot
                filepath = self.ocr_processor.capture_screenshot()
                if filepath:
                    filename = os.path.basename(filepath)
                    self._add_to_buffer(f"Captured: {filename}")
                
                # Clean up old screenshots
                deleted = self.ocr_processor.cleanup_old_screenshots()
                if deleted:
                    self._add_to_buffer(f"Cleaned up {deleted} old screenshots", "info")
                
                # Check for frequency changes
                reload_file = os.path.join(get_temp_dir(), "reload_frequency")
                if os.path.exists(reload_file):
                    self.load_screenshot_config()
                    try:
                        os.remove(reload_file)
                    except:
                        pass
                
                # Wait for next capture
                time.sleep(self.screenshot_interval)
                
            except Exception as e:
                self.logger.error(f"Error in capture loop: {e}")
                self._add_to_buffer(f"Error: {str(e)}", "warning")
                time.sleep(1)  # Brief sleep on error before retry

    def start_capturing(self):
        """Start the screenshot capture process."""
        if self.capturing:
            return
            
        self.capturing = True
        self.capture_thread = threading.Thread(target=self._capture_loop)
        self.capture_thread.daemon = True  # Thread will exit when main process exits
        self.capture_thread.start()
        self._add_to_buffer("Screenshot service started")
        self.logger.info("Screenshot capture started")

    def stop_capturing(self):
        """Stop the screenshot capture process."""
        self.capturing = False
        if self.capture_thread:
            self.capture_thread.join()
            self.capture_thread = None
        self._add_to_buffer("Screenshot service stopped")
        self.logger.info("Screenshot capture stopped")

    def process_latest_screenshot(self):
        """Process the most recent screenshot."""
        result = self.ocr_processor.process_latest_screenshot()
        if result:
            self._add_to_buffer("OCR processing successful", "info")
        return result

    def is_capturing(self):
        """Check if screenshot capture is active."""
        return self.capturing and (self.capture_thread is not None and self.capture_thread.is_alive())

    def get_output(self):
        """Get the current output buffer."""
        return self.output_buffer.copy()