import os
import time
from flask import Flask, request
from threading import Thread
import subprocess
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

# Add run mode check
run_mode = os.getenv("RUN_MODE", "local").lower()

# Adjust paths based on run mode
if run_mode == "docker":
    UPLOAD_DIR = "/app/screenshots"
    SIGNAL_FILE = "/app/trigger.signal"
else:
    UPLOAD_DIR = os.path.join(os.getcwd(), "screenshots")
    SIGNAL_FILE = os.path.join(os.getcwd(), "trigger.signal")

SERVER_PORT = os.getenv("SERVER_PORT")

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
    """Handle signal to process the most recent file immediately via GET."""
    files = [os.path.join(UPLOAD_DIR, f) for f in os.listdir(UPLOAD_DIR) if os.path.isfile(os.path.join(UPLOAD_DIR, f))]
    if not files:
        return "No screenshot found", 404
    most_recent_file = max(files, key=os.path.getmtime)
    print(f"Processing most recent file: {most_recent_file}")
    
    # Get the absolute path to the script directory
    current_dir = os.path.dirname(os.path.abspath(__file__))
    
    # Adjust script path based on run mode
    if run_mode == "docker":
        submit_azure_script = "/app/submit_Azure.py"
    else:
        submit_azure_script = os.path.join(current_dir, "submit_Azure.py")
    
    subprocess.run(["python", submit_azure_script, most_recent_file])
    return "Screenshot submitted for OCR", 200

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint."""
    return "OK", 200

if __name__ == '__main__':
    # Start the cleanup thread
    Thread(target=cleanup_old_files, daemon=True).start()

    # Start the Flask server
    app.run(host='0.0.0.0', port=SERVER_PORT)