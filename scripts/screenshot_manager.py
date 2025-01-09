# scripts/screenshot_manager.py
import os
import time
from datetime import datetime, timedelta
import subprocess
import glob

class ScreenshotManager:
    def __init__(self, screenshot_dir="/app/screenshots", max_age_minutes=5):
        self.screenshot_dir = screenshot_dir
        self.max_age_minutes = max_age_minutes
        os.makedirs(screenshot_dir, exist_ok=True)
        self.retry_delay = 2  # Changed to 2 seconds
        self.max_retries = 3  # Maximum number of retry attempts

    def capture_screenshot(self):
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        output_path = f"{self.screenshot_dir}/screenshot_{timestamp}.jpg"
        
        try:
            result = subprocess.run([
                'ffmpeg',
                '-y',  # Overwrite output files
                '-loglevel', 'error',  # Only show errors
                '-i', 'rtmp://localhost:1935/live/stream',
                '-vframes', '1',  # Capture single frame
                '-update', '1',  # Update mode
                '-q:v', '2',     # High quality
                output_path
            ], check=True, capture_output=True)
            print(f"Screenshot captured: {output_path}")
            return True
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
            print(f"Screenshot failed: {str(e)}")
            return False

    def cleanup_old_screenshots(self):
        cutoff_time = datetime.now() - timedelta(minutes=self.max_age_minutes)
        
        for screenshot in glob.glob(f"{self.screenshot_dir}/screenshot_*.jpg"):
            try:
                file_time = os.path.getmtime(screenshot)
                if datetime.fromtimestamp(file_time) < cutoff_time:
                    os.remove(screenshot)
            except OSError as e:
                print(f"Error cleaning up {screenshot}: {e}")

    def run(self):
        print("Starting screenshot manager...")
        while True:
            self.capture_screenshot()
            self.cleanup_old_screenshots()
            time.sleep(2)  # Wait 2 seconds before next capture

if __name__ == "__main__":
    manager = ScreenshotManager()
    manager.run()