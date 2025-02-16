import os
import time
from flask import Flask, request, jsonify
import requests  # Add this import
from threading import Thread
import subprocess
from dotenv import load_dotenv
import socket
import json
import datetime
from local_ocr import process_image
from socketio_utils import log_to_socketio

load_dotenv()

app = Flask(__name__)

# Add run mode check
run_mode = os.getenv("RUN_MODE", "local").lower()

# Adjust paths based on run mode
if run_mode == "docker":
    UPLOAD_DIR = "/app/screenshots"
    SIGNAL_FILE = "/app/trigger.signal"
    submit_azure_script = "/app/submit_Azure.py"
else:
    UPLOAD_DIR = os.path.join(os.getcwd(), "screenshots")
    SIGNAL_FILE = os.path.join(os.getcwd(), "trigger.signal")
    submit_azure_script = os.path.join(os.path.dirname(__file__), "submit_Azure.py")

def save_port_info(port):
    """Save the port number to a shared file."""
    port_file = os.path.join(os.path.dirname(__file__), 'process_stream_port.json')
    with open(port_file, 'w') as f:
        json.dump({'port': port}, f)
    print(f"Server port {port} saved to {port_file}")

def get_server_port():
    """Get the server port."""
    return 5347  # Fixed port for process stream server

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

def send_socket_message(title, message):
    """Send a message to the Socket.IO server's broadcast endpoint."""
    try:
        # Determine the Socket.IO server address
        host = "127.0.0.1" if run_mode == "local" else "host.docker.internal"
        socketio_url = f"http://{host}:5348/broadcast"
        
        payload = {
            "data": {
                "title": title,
                "message": message
            }
        }
        
        print(f"Sending message to Socket.IO server at {socketio_url}")
        print(f"Payload: {json.dumps(payload, indent=2)}")
        
        headers = {'Content-Type': 'application/json'}
        response = requests.post(socketio_url, json=payload, headers=headers, timeout=5)
        
        if response.status_code != 200:
            print(f"Failed to send socket message. Status code: {response.status_code}")
            print(f"Response text: {response.text}")
        else:
            print(f"Successfully sent message to Socket.IO server")
            
    except Exception as e:
        print(f"Error sending socket message: {str(e)}")
        if hasattr(e, 'response'):
            print(f"Response status: {e.response.status_code}")
            print(f"Response text: {e.response.text}")

def process_latest_screenshot():
    """Process the most recent screenshot file."""
    files = [os.path.join(UPLOAD_DIR, f) for f in os.listdir(UPLOAD_DIR) if os.path.isfile(os.path.join(UPLOAD_DIR, f))]
    if not files:
        return "No screenshot found", 404
    
    most_recent_file = max(files, key=os.path.getmtime)
    filename = os.path.basename(most_recent_file)
    
    send_socket_message(
        "Manual Trigger",
        f"Processing screenshot: {filename}"
    )
    
    try:
        # Process with local OCR
        result = process_image(most_recent_file)
        
        # Save result to logs
        timestamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
        if not os.path.exists('logs'):
            os.makedirs('logs')
            
        result_file = os.path.join('logs', f'{timestamp}_local_ocr_response.json')
        with open(result_file, 'w') as f:
            json.dump(result, f, indent=2)

        if result["status"] == "success":
            log_to_socketio("✓ OCR completed successfully", title="OCR", logType="success")
            return "Screenshot processed by local OCR", 200
        else:
            error_msg = result.get("error", "Unknown error during OCR")
            log_to_socketio(f"Error: {error_msg}", title="OCR", logType="error")
            return error_msg, 500
        
    except Exception as e:
        error_msg = f"Error processing {filename}: {str(e)}"
        log_to_socketio(f"Error: {error_msg}", title="OCR", logType="error")
        return error_msg, 500

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

@app.route('/trigger', methods=['POST'])
def trigger():
    """Handle manual trigger to process the most recent file."""
    result, status_code = process_latest_screenshot()
    return jsonify({"message": result}), status_code

@app.route('/signal', methods=['POST'])
def signal():
    """Handle signal to process the most recent file immediately."""
    result, status_code = process_latest_screenshot()
    return jsonify({"message": result}), status_code

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint."""
    return "OK", 200

if __name__ == '__main__':
    # Start the cleanup thread
    Thread(target=cleanup_old_files, daemon=True).start()

    # Start the Flask server with fixed port
    port = get_server_port()
    print(f"Starting server on port {port}")
    save_port_info(port)  # Still save the port info for other processes
    app.run(host='0.0.0.0', port=port)