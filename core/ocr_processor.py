"""OCR processing module for 33ter application."""
import os
import logging
from datetime import datetime
import pytesseract
from PIL import ImageGrab

from utils import get_screenshots_dir, get_logs_dir

class OCRProcessor:
    """Handles screenshot capture and OCR processing."""
    
    def __init__(self):
        self.screenshots_dir = get_screenshots_dir()
        self.logger = self._setup_logging()
    
    def _setup_logging(self):
        """Configure OCR processor logging."""
        log_file = os.path.join(get_logs_dir(), "ocr_processor.log")
        
        logger = logging.getLogger('33ter-OCR')
        logger.setLevel(logging.INFO)
        
        if not logger.handlers:
            handler = logging.FileHandler(log_file)
            formatter = logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            )
            handler.setFormatter(formatter)
            logger.addHandler(handler)
        
        return logger

    def capture_screenshot(self):
        """Capture a screenshot and save it."""
        try:
            timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            filename = f"screenshot_{timestamp}.png"
            filepath = os.path.join(self.screenshots_dir, filename)
            
            # Capture the screenshot
            screenshot = ImageGrab.grab()
            screenshot.save(filepath)
            
            self.logger.debug(f"Screenshot saved: {filename}")
            return filepath
        except Exception as e:
            self.logger.error(f"Screenshot capture failed: {e}")
            return None

    def get_latest_screenshot(self):
        """Get the path of the most recent screenshot."""
        try:
            files = [f for f in os.listdir(self.screenshots_dir) 
                    if f.startswith("screenshot_") and f.endswith(".png")]
            if not files:
                return None
                
            files.sort(reverse=True)
            return os.path.join(self.screenshots_dir, files[0])
        except Exception as e:
            self.logger.error(f"Error getting latest screenshot: {e}")
            return None

    def process_screenshot(self, filepath):
        """Process a screenshot with OCR."""
        try:
            # Extract text using Tesseract
            text = pytesseract.image_to_string(filepath)
            
            if not text.strip():
                self.logger.warning("No text found in screenshot")
                return None
            
            # Format OCR result
            result = [{
                'text': text.strip(),
                'timestamp': datetime.now().isoformat()
            }]
            
            return result
        except Exception as e:
            self.logger.error(f"OCR processing failed: {e}")
            return None

    def cleanup_old_screenshots(self, max_age=180):
        """Delete screenshots older than max_age seconds."""
        try:
            from datetime import datetime, timedelta
            cutoff = datetime.now() - timedelta(seconds=max_age)
            
            for filename in os.listdir(self.screenshots_dir):
                if not filename.startswith("screenshot_"):
                    continue
                    
                filepath = os.path.join(self.screenshots_dir, filename)
                modified_time = datetime.fromtimestamp(os.path.getmtime(filepath))
                
                if modified_time < cutoff:
                    os.remove(filepath)
                    self.logger.debug(f"Deleted old screenshot: {filename}")
        except Exception as e:
            self.logger.error(f"Error during cleanup: {e}")

    def process_latest_screenshot(self):
        """Process the most recent screenshot and return results."""
        latest = self.get_latest_screenshot()
        if not latest:
            self.logger.error("No screenshots available")
            return None
            
        return self.process_screenshot(latest)