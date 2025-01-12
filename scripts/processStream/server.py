import os
import time
from flask import Flask, request
from threading import Thread
import subprocess

app = Flask(__name__)

UPLOAD_DIR = "/app/screenshots"
SIGNAL_FILE = "/app/trigger.signal"
SERVER_PORT=os.getenv("SERVER_PORT")

# Ensure the upload directory exists
os.makedirs(UPLOAD_DIR, exist_ok=True)

def cleanup_old_files():
    """Delete files older than 5 minutes in the upload directory."""
    while True:
        current_time = time.time()
        for file_name in os.listdir(UPLOAD_DIR):
            file_path = os.path.join(UPLOAD_DIR, file_name)
            if os.path.isfile(file_path):
                file_age = current_time - os.path.getmtime(file_path)
                if file_age > 300:  # 5 minutes = 300 seconds
                    os.remove(file_path)
                    print(f"Deleted old file: {file_name}")
        time.sleep(60)  # Run every minute

@app.route('/upload', methods=['POST'])
def upload():
    """Handle file uploads from the host."""
    file = request.files.get('file')
    if not file:
        return "No file provided", 400

    file_path = os.path.join(UPLOAD_DIR, file.filename)
    file.save(file_path)
    print(f"Saved file: {file.filename}")
    return "File received", 200

@app.route('/signal', methods=['POST'])
def signal():
    """Handle signal to process the most recent file."""
    # Create a signal file to notify the main thread
    with open(SIGNAL_FILE, "w") as f:
        f.write("triggered")
    return "Signal received", 200

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint."""
    return "OK", 200

def wait_for_signal():
    """Monitor for the signal to process the most recent screenshot."""
    while True:
        if os.path.exists(SIGNAL_FILE):
            # Find the most recent screenshot
            files = [os.path.join(UPLOAD_DIR, f) for f in os.listdir(UPLOAD_DIR) if os.path.isfile(os.path.join(UPLOAD_DIR, f))]
            if files:
                most_recent_file = max(files, key=os.path.getmtime)
                print(f"Processing most recent file: {most_recent_file}")

                # Pass the file to the `submit_Azure.py` script
                subprocess.run(["python", "submit_Azure.py", most_recent_file])

            # Remove the signal file
            os.remove(SIGNAL_FILE)
        time.sleep(1)

if __name__ == '__main__':
    # Start the cleanup thread
    Thread(target=cleanup_old_files, daemon=True).start()

    # Start the signal watcher thread
    Thread(target=wait_for_signal, daemon=True).start()

    # Start the Flask server
    app.run(host='0.0.0.0', port=SERVER_PORT)