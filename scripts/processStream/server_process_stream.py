import os
import sys

# Add parent directory to Python path to find utils package
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import time
import re
from flask import Flask, request, jsonify
import requests
from threading import Thread, Lock
import subprocess
from dotenv import load_dotenv
import socket
import json
import datetime
import logging
from werkzeug.middleware.proxy_fix import ProxyFix
from werkzeug.serving import WSGIRequestHandler
from local_ocr import process_image
from utils.path_config import get_screenshots_dir, get_logs_dir, get_scripts_dir
from utils.socketio_utils import log_debug, log_to_socketio

# Disable default Werkzeug logging
WSGIRequestHandler.log = lambda *args, **kwargs: None

load_dotenv()

app = Flask(__name__)
app.wsgi_app = ProxyFix(app.wsgi_app)

# Global mute state
MUTE_PROCESS_MESSAGES = False
mute_lock = Lock()

# Completely disable Flask's default logging
logging.getLogger('werkzeug').disabled = True
app.logger.disabled = True

# Custom logging that respects muting
def should_log_message():
    """Check if we should log a message based on mute state."""
    global MUTE_PROCESS_MESSAGES
    with mute_lock:
        return not MUTE_PROCESS_MESSAGES

def log_network_message(message):
    """Log network-related messages respecting mute state."""
    if should_log_message() and isinstance(message, str):
        # Strip ANSI color codes and extra whitespace
        message = re.sub(r'\x1b\[[0-9;]*[a-zA-Z]', '', message).strip()
        if message:  # Only log non-empty messages
            print(f"[Process] {message}")

# Custom request logging middleware
class RequestLoggingMiddleware:
    def __init__(self, app):
        self._app = app

    def __call__(self, environ, start_response):
        path = environ.get('PATH_INFO', '')
        method = environ.get('REQUEST_METHOD', '')
        
        # Skip logging for certain paths
        skip_logging = (
            path == '/health' and method == 'GET'  # Skip frequent health checks
        )
        
        if not skip_logging and should_log_message():
            if method == 'POST' and path == '/upload':
                log_network_message(f"Screenshot upload received")
            else:
                log_network_message(f"{method} {path}")
        
        def custom_start_response(status, headers, exc_info=None):
            if not skip_logging and should_log_message():
                status_code = status.split()[0]
                if method == 'POST' and path == '/upload':
                    log_network_message(f"Upload complete: {status_code}")
            return start_response(status, headers, exc_info)
        
        return self._app(environ, custom_start_response)

# Add custom logging middleware
app.wsgi_app = RequestLoggingMiddleware(app.wsgi_app)

# Adjust paths based on run mode
run_mode = os.getenv("RUN_MODE", "local").lower()

UPLOAD_DIR = get_screenshots_dir()
LOGS_DIR = get_logs_dir()

if run_mode == "docker":
    SIGNAL_FILE = "/app/trigger.signal"
    submit_deepseek_script = "/app/submit_DeepSeek.py"
else:
    BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    SIGNAL_FILE = os.path.join(BASE_DIR, "trigger.signal")
    submit_deepseek_script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "submit_DeepSeek.py")

# Ensure required directories exist
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(LOGS_DIR, exist_ok=True)

# Configure DeepSeek script path
submit_deepseek_script = os.path.join(get_scripts_dir(), "processStream", "submit_DeepSeek.py")

def save_port_info(port):
    """Save the port number to a shared file."""
    port_file = os.path.join(os.path.dirname(__file__), 'process_stream_port.json')
    with open(port_file, 'w') as f:
        json.dump({'port': port}, f)
    print(f"Server port {port} saved to {port_file}")

def get_server_port():
    """Get the server port."""
    return 5347  # Fixed port for process stream server

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
                    if not MUTE_PROCESS_MESSAGES:
                        log_debug(f"Deleted old file: {file_name}")
        time.sleep(60)  # Run every minute

def submit_to_deepseek(ocr_result):
    """Submit OCR results to DeepSeek for processing."""
    try:
        # Save OCR results to a temporary file for logging
        timestamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
        temp_file = os.path.join(LOGS_DIR, f'{timestamp}_ocr_result.json')
        
        with open(temp_file, 'w') as f:
            json.dump(ocr_result, f, indent=2)
            f.flush()
            os.fsync(f.fileno())

        # Use dedicated DeepSeek client
        from deepseek_client import analyze_text
        
        log_debug("Sending text to DeepSeek for analysis...", "DeepSeek", "info")
        result = analyze_text(ocr_result.get("lines", []))
        
        if result["status"] == "success":
            # Send challenge text to socket if found
            if result["challenge"]:
                log_debug("Challenge text extracted successfully", "DeepSeek", "info")
                log_to_socketio(result["challenge"], "Challenge Detected", "info")
            else:
                log_debug("No challenge text found in extracted text", "DeepSeek", "warning")

            # Send solution to socket if found
            if result["solution"]:
                log_debug("Solution generated successfully", "DeepSeek", "info")
                log_to_socketio(result["solution"], "Solution Generated", "prime")
            else:
                log_debug("No solution generated", "DeepSeek", "warning")
                
            return True
        else:
            error_msg = result.get("error", "Unknown error in DeepSeek processing")
            log_debug(error_msg, "DeepSeek", "error")
            return False
            
    except Exception as e:
        log_debug(f"Error in DeepSeek processing: {str(e)}", "DeepSeek", "error")
        return False

def process_latest_screenshot():
    """Process the most recent screenshot file."""
    try:
        files = [os.path.join(UPLOAD_DIR, f) for f in os.listdir(UPLOAD_DIR) 
                if os.path.isfile(os.path.join(UPLOAD_DIR, f))]
        if not files:
            return "No screenshot found", 404
            
        most_recent_file = max(files, key=os.path.getmtime)
        filename = os.path.basename(most_recent_file)
        
        # Add small delay to ensure file write is complete
        time.sleep(0.1)
        
        # Process with local OCR
        log_debug("Starting OCR processing...", "Process", "info")
        result = process_image(most_recent_file)
        
        if result["status"] == "success":
            # Save OCR result to logs
            timestamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
            result_file = os.path.join(LOGS_DIR, f'{timestamp}_local_ocr_response.json')
            with open(result_file, 'w') as f:
                json.dump(result, f, indent=2)
                f.flush()
                os.fsync(f.fileno())

            # Start DeepSeek processing
            log_debug("Starting DeepSeek analysis...", "Process", "info")
            success = submit_to_deepseek(result)
            
            if success:
                log_debug("Processing workflow completed successfully", "Process", "info")
            else:
                log_debug("Processing completed with some errors", "Process", "warning")
                
            return "Processing complete", 200
        else:
            error_msg = result.get("error", "Unknown error during OCR")
            log_debug(error_msg, "Process", "error")
            return error_msg, 500
            
    except Exception as e:
        error_msg = f"Error processing {filename if 'filename' in locals() else 'unknown file'}: {str(e)}"
        log_debug(error_msg, "Process", "error")
        return error_msg, 500

@app.route('/upload', methods=['POST'])
def upload():
    """Handle file uploads from the host."""
    file = request.files.get('file')
    if not file:
        return "No file provided", 400

    file_path = os.path.join(UPLOAD_DIR, file.filename)
    
    # Save file with explicit flush and sync
    try:
        file.save(file_path)
        # Force sync to filesystem
        with open(file_path, 'rb') as f:
            os.fsync(f.fileno())
        if not MUTE_PROCESS_MESSAGES:
            log_debug(f"Saved screenshot: {file.filename}", "Process", "info")
        return "File received", 200
    except Exception as e:
        log_debug(f"Error saving file: {str(e)}", "Process", "error")
        return str(e), 500

@app.route('/trigger', methods=['POST'])
def trigger():
    """Handle manual trigger to process the most recent file."""
    def process_async():
        log_debug("Manual trigger received - starting processing workflow", "Process", "info")
        result, status_code = process_latest_screenshot()
        if status_code != 200:
            log_debug(f"Processing workflow failed: {result}", "Process", "error")
    
    # Start processing in background thread
    Thread(target=process_async, daemon=True).start()
    return "", 204  # Return immediately to prevent UI lockup

@app.route('/signal', methods=['POST'])
def signal():
    """Handle signal to process the most recent file immediately."""
    def process_async():
        log_debug("Signal received - processing latest screenshot", "Process", "info")
        result, status_code = process_latest_screenshot()
        if status_code != 200:
            log_debug(f"Processing failed: {result}", "Process", "error")
        else:
            log_debug("Processing completed successfully", "Process", "info")
    
    # Start processing in background
    Thread(target=process_async, daemon=True).start()
    return "", 204  # Return immediately

@app.route('/mute', methods=['POST'])
def toggle_mute():
    """Toggle the mute state for Process screen messages."""
    global MUTE_PROCESS_MESSAGES
    
    with mute_lock:
        MUTE_PROCESS_MESSAGES = not MUTE_PROCESS_MESSAGES
        status = "muted" if MUTE_PROCESS_MESSAGES else "unmuted"
        if not MUTE_PROCESS_MESSAGES:
            log_debug(f"Process messages {status}", "Process", "info")
        return jsonify({"status": status}), 200

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint."""
    log_network_message("Health check OK")
    return "OK", 200

if __name__ == '__main__':
    # Start the cleanup thread
    Thread(target=cleanup_old_files, daemon=True).start()

    # Start the Flask server with fixed port
    port = get_server_port()
    print(f"Starting server on port {port}")
    save_port_info(port)
    app.run(host='0.0.0.0', port=port, use_reloader=False)