import os
import time
from flask import Flask, request
from threading import Thread
import subprocess
from dotenv import load_dotenv
import socket
import json

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

# Add port management functions
def find_available_port(start_port=5000, max_port=5100):
    """Find an available port starting from start_port."""
    for port in range(start_port, max_port):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(('', port))
                return port
            except OSError:
                continue
    raise RuntimeError(f"No available ports found between {start_port} and {max_port}")

def save_port_info(port):
    """Save the port number to a shared file."""
    port_file = os.path.join(os.path.dirname(__file__), 'process_stream_port.json')
    with open(port_file, 'w') as f:
        json.dump({'port': port}, f)
    print(f"Server port {port} saved to {port_file}")

def get_server_port():
    """Get the server port, finding an available one if necessary."""
    try:
        default_port = int(os.getenv("SERVER_PORT", "5000"))
        port = find_available_port(start_port=default_port)
        save_port_info(port)
        return port
    except Exception as e:
        print(f"Error setting up port: {e}")
        raise

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

    # Start the Flask server with dynamic port
    port = get_server_port()
    print(f"Starting server on port {port}")
    app.run(host='0.0.0.0', port=port)