import time
import signal
import sys
import threading
from screenshot_manager import ScreenshotManager

def signal_handler(sig, frame):
    print('Shutting down gracefully...')
    sys.exit(0)

def main():
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    print("Container started successfully")
    
    # Start screenshot manager in a separate thread
    screenshot_manager = ScreenshotManager()
    screenshot_thread = threading.Thread(target=screenshot_manager.run, daemon=True)
    screenshot_thread.start()
    
    try:
        while True:
            time.sleep(1)
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    print("beginning main.py")
    main()