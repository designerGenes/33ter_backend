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

# Remove get_process_stream_port and wait_for_server_port functions since we're using a fixed port

run_mode = os.getenv("RUN_MODE", "local").lower()
server_host = "localhost" if run_mode == "local" else "container1"
PROCESS_STREAM_PORT = 5347  # Fixed port matching server_process_stream.py

running = True
PAUSE_FILE = "./.tmp/signal_pause_capture"
RESUME_FILE = "./.tmp/signal_resume_capture"

def signal_handler(sig, frame):
    global running
    logging.info("Received termination signal. Stopping...")
    running = False

def get_latest_file(directory, prefix):
    files = [f for f in os.listdir(directory) if f.startswith(prefix)]
    if not files:
        return None
    latest_file = max(files, key=lambda f: os.path.getctime(os.path.join(directory, f)))
    return os.path.join(directory, latest_file)

def get_latest_directory(directory, prefix):
    dirs = [d for d in os.listdir(directory) if d.startswith(prefix) and os.path.isdir(os.path.join(directory, d))]
    if not dirs:
        return None
    latest_dir = max(dirs, key=lambda d: os.path.getctime(os.path.join(directory, d)))
    return os.path.join(directory, latest_dir)

def check_pause_resume():
    pause_dir = get_latest_directory("./.tmp", "signal_pause_capture")
    resume_dir = get_latest_directory("./.tmp", "signal_resume_capture")

    if pause_dir:
        logging.info("Pause signal detected. Pausing screenshot capture...")
        while not resume_dir:
            time.sleep(1)
            resume_dir = get_latest_directory("./.tmp", "signal_resume_capture")
        logging.info("Resume signal detected. Resuming screenshot capture...")

    # Clean up all pause and resume directories
    for d in os.listdir("./.tmp"):
        if d.startswith("signal_pause_capture") or d.startswith("signal_resume_capture"):
            os.rmdir(os.path.join("./.tmp", d))

# Register signal handler for graceful shutdown
signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

logging.info("Starting screenshot capture...")

# Use fixed port instead of discovery
API_URL = f"http://{server_host}:{PROCESS_STREAM_PORT}/upload"
logging.info(f"Configured to connect to server at: {API_URL}")

while running:
    try:
        check_pause_resume()
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
