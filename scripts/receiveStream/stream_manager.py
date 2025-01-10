import os
import time
import threading
import subprocess
from flask import Flask, request, jsonify
from datetime import datetime, timedelta
import requests  # Add this import

# Initialize Flask app
app = Flask(__name__)

# Configuration
SCREENSHOT_DIR = "/app/screenshots"
SCREENSHOT_RETENTION = 60  # Delete screenshots older than 60 seconds
FFMPEG_INPUT_URL = "udp://0.0.0.0:1234"  # Replace with your FFmpeg input URL
SCREENSHOT_INTERVAL = 1  # Take a screenshot every 1 second
CONTAINER_2_URL = "http://container2:5001/process"  # URL of Container #2

# Ensure the screenshot directory exists
os.makedirs(SCREENSHOT_DIR, exist_ok=True)

# Global variable to store the most recent screenshot
most_recent_screenshot = None

def capture_screenshots():
    """
    Continuously capture screenshots from the FFmpeg stream.
    """
    global most_recent_screenshot

    while True:
        # Generate a unique filename for the screenshot
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        screenshot_path = os.path.join(SCREENSHOT_DIR, f"screenshot_{timestamp}.jpg")

        # Use FFmpeg to capture a frame and save it as a screenshot
        command = [
            "ffmpeg",
            "-i", FFMPEG_INPUT_URL,  # Input stream URL
            "-vf", "fps=1",          # Capture 1 frame per second
            "-frames:v", "1",        # Capture only 1 frame
            "-q:v", "2",             # Quality of the screenshot (1=best, 31=worst)
            screenshot_path
        ]

        try:
            subprocess.run(command, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            print(f"Saved screenshot: {screenshot_path}")
            most_recent_screenshot = screenshot_path
        except subprocess.CalledProcessError as e:
            print(f"Failed to capture screenshot: {e}")

        # Sleep for the specified interval
        time.sleep(SCREENSHOT_INTERVAL)

def cleanup_old_screenshots():
    """
    Delete screenshots older than the retention period.
    """
    while True:
        now = datetime.now()
        for filename in os.listdir(SCREENSHOT_DIR):
            file_path = os.path.join(SCREENSHOT_DIR, filename)
            if os.path.isfile(file_path):
                file_creation_time = datetime.fromtimestamp(os.path.getctime(file_path))
                if now - file_creation_time > timedelta(seconds=SCREENSHOT_RETENTION):
                    os.remove(file_path)
                    print(f"Deleted old screenshot: {file_path}")

        # Sleep for a while before checking again
        time.sleep(10)

@app.route("/get_latest_screenshot", methods=["GET"])
def get_latest_screenshot():
    """
    Endpoint to return the most recent screenshot.
    """
    global most_recent_screenshot

    if most_recent_screenshot and os.path.exists(most_recent_screenshot):
        # Send the screenshot to Container #2
        with open(most_recent_screenshot, "rb") as f:
            files = {"file": f}
            response = requests.post(CONTAINER_2_URL, files=files)
            if response.status_code == 200:
                return jsonify({"status": "success", "message": "Screenshot sent to Container #2"}), 200
            else:
                return jsonify({"status": "error", "message": "Failed to send screenshot to Container #2"}), 500
    else:
        return jsonify({"error": "No screenshot available"}), 404

@app.route("/health", methods=["GET"])
def health_check():
    """
    Health check endpoint.
    """
    return jsonify({"status": "healthy"}), 200

if __name__ == "__main__":
    # Start the screenshot capture thread
    capture_thread = threading.Thread(target=capture_screenshots, daemon=True)
    capture_thread.start()

    # Start the cleanup thread
    cleanup_thread = threading.Thread(target=cleanup_old_screenshots, daemon=True)
    cleanup_thread.start()

    # Run the Flask app
    app.run(host="0.0.0.0", port=5000)