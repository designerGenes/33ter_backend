import time
from io import BytesIO
import pyautogui
import requests
import logging
import signal
import sys
import os
import json
from dotenv import load_dotenv

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')

# Load environment variables
load_dotenv()

run_mode = os.getenv("RUN_MODE", "local").lower()
server_host = "localhost" if run_mode == "local" else "container1"
PROCESS_STREAM_PORT = 5347

running = True
paused = False
prev_pause_state = False  # Track previous pause state
screenshot_frequency = 4.0  # Default frequency in seconds
frequency_config_file = "./.config/screenshot_frequency.json"
last_screenshot_time = 0
last_frequency_check = 0  # Add timestamp for frequency checks

def ensure_config_dir():
    os.makedirs(os.path.dirname(frequency_config_file), exist_ok=True)

def load_frequency():
    global screenshot_frequency
    try:
        if os.path.exists(frequency_config_file):
            with open(frequency_config_file, 'r') as f:
                data = json.load(f)
                new_frequency = float(data.get('frequency', 4.0))
                if new_frequency != screenshot_frequency:
                    screenshot_frequency = new_frequency
                    logging.info(f"Updated screenshot frequency: {screenshot_frequency}s")
    except Exception as e:
        logging.error(f"Error loading frequency: {e}")
        screenshot_frequency = 4.0

def check_reload_frequency():
    global last_frequency_check
    current_time = time.time()
    
    # Check frequency file every 0.5 seconds
    if current_time - last_frequency_check >= 0.5:
        last_frequency_check = current_time
        reload_file = "./.tmp/reload_frequency"
        
        # Regular file check
        if os.path.exists(reload_file):
            os.remove(reload_file)
            load_frequency()
            return True
            
        # Also check frequency file directly for changes
        load_frequency()
    return False

def signal_handler(sig, frame):
    global running
    logging.info("Received termination signal. Stopping...")
    running = False

def check_pause_resume():
    pause_dir = "./.tmp/signal_pause_capture"
    resume_dir = "./.tmp/signal_resume_capture"
    
    if os.path.exists(pause_dir):
        return True
    elif os.path.exists(resume_dir):
        os.rmdir(resume_dir)  # Clean up resume signal
        return False
    return None  # No change

# Register signal handler for graceful shutdown
signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

# Ensure config directory exists and load saved frequency
ensure_config_dir()
load_frequency()

logging.info(f"Starting screenshot capture (frequency: {screenshot_frequency}s)...")

# Use fixed port instead of discovery
API_URL = f"http://{server_host}:{PROCESS_STREAM_PORT}/upload"
logging.info(f"Configured to connect to server at: {API_URL}")

while running:
    try:
        current_time = time.time()
        
        # Check for frequency reload signal
        check_reload_frequency()
        
        # Check for pause/resume signals
        pause_state = check_pause_resume()
        if pause_state is not None:
            paused = pause_state
            # Only log if state has changed
            if paused != prev_pause_state:
                if paused:
                    logging.info("Screenshot capture paused")
                else:
                    logging.info("Screenshot capture resumed")
                    last_screenshot_time = 0  # Reset timer on resume
                prev_pause_state = paused

        if not paused and (current_time - last_screenshot_time) >= screenshot_frequency:
            # Capture the screenshot
            screenshot = pyautogui.screenshot()

            # Save the screenshot to an in-memory buffer
            buffer = BytesIO()
            screenshot.save(buffer, format="PNG")
            buffer.seek(0)

            # Send the screenshot to the server
            file_name = f"{int(current_time)}_capture.png"
            response = requests.post(API_URL, files={"file": (file_name, buffer)})
            logging.info(f"Sent screenshot: {file_name}, Response: {response.status_code}")
            
            last_screenshot_time = current_time

        # Sleep for a short interval to prevent CPU spinning
        time.sleep(0.1)
            
    except Exception as e:
        logging.error(f"Error during screenshot capture or upload: {e}")

logging.info("Screenshot capture stopped.")
