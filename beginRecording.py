import time
from io import BytesIO
import pyautogui
import requests
import logging
import signal
import sys

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

API_URL = "http://localhost:5346/upload"
running = True

def signal_handler(sig, frame):
    global running
    logging.info("Received termination signal. Stopping...")
    running = False

# Register signal handler for graceful shutdown
signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

logging.info("Starting screenshot capture...")

while running:
    try:
        # Capture the screenshot
        screenshot = pyautogui.screenshot()

        # Save the screenshot to an in-memory buffer
        buffer = BytesIO()
        screenshot.save(buffer, format="PNG")
        buffer.seek(0)

        # Send the screenshot to the server
        file_name = f"{int(time.time())}_capture.png"
        response = requests.post(API_URL, files={"file": (file_name, buffer)})
        logging.info(f"Sent screenshot: {file_name}, Response: {response.status_code}")

        # Wait before the next capture
        time.sleep(1)
    except Exception as e:
        logging.error(f"Error during screenshot capture or upload: {e}")

logging.info("Screenshot capture stopped.")
