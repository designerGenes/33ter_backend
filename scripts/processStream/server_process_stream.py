import os
import sys

# Add parent directory to Python path to find utils package
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import time
import re
from flask import Flask, request, jsonify, json
import requests
from threading import Thread, Lock
import subprocess
from dotenv import load_dotenv
import socket
import json
import datetime
import logging
import asyncio
# import JSONEncoder from Flask

# from flask.json.provider import JSONProvider, JSONEncoder
from asgiref.wsgi import WsgiToAsgi
from hypercorn.config import Config
from hypercorn.asyncio import serve
from werkzeug.middleware.proxy_fix import ProxyFix
from werkzeug.serving import WSGIRequestHandler
from local_ocr import process_image
from utils.path_config import get_screenshots_dir, get_logs_dir, get_scripts_dir
from utils.socketio_utils import log_debug, log_to_socketio

# Completely disable Flask's default logging
logging.getLogger('werkzeug').disabled = True
log = logging.getLogger('werkzeug')
log.disabled = True

# Ensure Flask's built-in logging is also disabled
class CustomFlask(Flask):
    def log_exception(self, exc_info):
        """Override to prevent Flask from logging exceptions to stderr"""
        pass

app = CustomFlask(__name__)
app.logger.disabled = True
asgi_app = WsgiToAsgi(app)

# Disable Werkzeug's default request logging
WSGIRequestHandler.log = lambda *args, **kwargs: None

load_dotenv()

app.wsgi_app = ProxyFix(app.wsgi_app)

# Global mute state
MUTE_PROCESS_MESSAGES = False
mute_lock = Lock()

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
        
        # Skip logging for internal paths
        skip_logging = (
            path == '/health' or  # Skip health checks
            path == '/broadcast' or  # Skip SocketIO broadcasts
            (path == '/upload' and not MUTE_PROCESS_MESSAGES)  # Only log uploads if not muted
        )
        
        if not skip_logging:
            log_debug(f"Received {method} {path}", "Process", "info")
        
        def custom_start_response(status, headers, exc_info=None):
            if not skip_logging:
                status_code = status.split()[0]
                log_debug(f"Response: {status_code}", "Process", "info")
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

async def submit_to_deepseek(ocr_result):
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
        
        result = await analyze_text(ocr_result.get("lines", []))
        
        if result["status"] == "success":
            # Only process challenge if one was actually found
            if result["challenge"] is not None:
                log_debug("Challenge found, sending to UI", "DeepSeek", "info")
                challenge_message = (
                    "📝 Challenge Description:\n\n"
                    f"{result['challenge']}\n\n"
                    "Generating solution..."
                )
                log_to_socketio(challenge_message, "Challenge", "Info")

                # Only attempt solution if we had a real challenge
                if result["solution"]:
                    log_debug("Solution generated, sending to UI", "DeepSeek", "info")
                    solution_message = (
                        "Here's a solution to the challenge:\n\n"
                        f"{result['solution']}\n\n"
                        "This solution emphasizes:\n"
                        "• Clean, maintainable code\n"
                        "• Optimal time/space complexity\n"
                        "• Language-specific best practices"
                    )
                    log_to_socketio(solution_message, "Solution", "Prime")
                else:
                    log_debug("No solution generated for challenge", "DeepSeek", "warning")
                    log_to_socketio(
                        "I found a coding challenge but couldn't generate a solution.\n"
                        "This might be due to:\n"
                        "• Complex or ambiguous requirements\n"
                        "• Missing test cases or constraints\n"
                        "• Incomplete challenge description\n\n"
                        "Try capturing a clearer screenshot of the challenge.", 
                        "Processing Status", 
                        "Warning"
                    )
            else:
                # No challenge was found - this is normal and should be a warning
                log_debug("No coding challenge found in text", "DeepSeek", "info")
                log_to_socketio(
                    "No coding challenge was found in this screenshot.\n\n"
                    "I analyzed the text but didn't find anything that looks like a programming challenge.\n\n"
                    "Make sure:\n"
                    "• The challenge text is clearly visible\n"
                    "• The screenshot includes actual programming problem statements\n"
                    "• The text isn't just general documentation or discussion\n\n"
                    "Try taking another screenshot focusing on the challenge description.",
                    "Analysis Result",
                    "Warning"
                )
                
            return True
        else:
            error_msg = result.get("error", "Unknown error in DeepSeek processing")
            log_debug(error_msg, "DeepSeek", "error")
            log_to_socketio(
                "Failed to process the screenshot with DeepSeek.\n\n"
                "Possible issues:\n"
                "• OCR text might be unclear\n"
                "• Screenshot might be incomplete\n"
                "• Connection problems with DeepSeek\n\n"
                "Check the Process screen for detailed error information.",
                "Processing Error", 
                "error"
            )
            return False
            
    except Exception as e:
        error_msg = f"Error in DeepSeek processing: {str(e)}"
        log_debug(error_msg, "DeepSeek", "error")
        log_to_socketio(
            "An unexpected error occurred.\n\n"
            "This might be due to:\n"
            "• Network connectivity issues\n"
            "• Server resource constraints\n"
            "• Internal processing errors\n\n"
            "Please try again in a few moments.",
            "System Error",
            "error"
        )
        return False

async def process_latest_screenshot():
    """Process the most recent screenshot file."""
    try:
        files = [os.path.join(UPLOAD_DIR, f) for f in os.listdir(UPLOAD_DIR) 
                if os.path.isfile(os.path.join(UPLOAD_DIR, f))]
        if not files:
            return "No screenshot found", 404
            
        most_recent_file = max(files, key=os.path.getmtime)
        filename = os.path.basename(most_recent_file)
        
        # Add longer delay to ensure file write is complete
        time.sleep(0.5)  # Increased from 0.1 to 0.5 seconds
        
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

            # Display extracted text with relative positioning
            log_debug("\n===============================", "Process", "info")
            log_debug("       Extracted Text:", "Process", "info")
            log_debug("===============================", "Process", "info")
            
            # Get image dimensions from OCR result
            img_width = result.get("image_width", 0)
            img_height = result.get("image_height", 0)
            
            if img_width and img_height:
                # Create a relative spatial representation
                lines = result.get("lines", [])
                
                # Sort lines by vertical position
                sorted_lines = sorted(lines, key=lambda x: x.get("bbox", [0,0,0,0])[1])
                
                # Group lines by vertical position (within 20px threshold)
                vertical_groups = []
                current_group = []
                last_y = -float('inf')
                
                for line in sorted_lines:
                    bbox = line.get("bbox", [0,0,0,0])
                    x, y = bbox[0], bbox[1]
                    
                    # Start new group if y-coordinate differs significantly
                    if abs(y - last_y) > 20:
                        if current_group:
                            vertical_groups.append(sorted(current_group, key=lambda x: x[0]))
                        current_group = []
                        last_y = y
                    
                    # Calculate relative x position (0-100)
                    rel_x = min(100, max(0, int((x / img_width) * 100)))
                    current_group.append((rel_x, line.get("text", "")))
                
                if current_group:
                    vertical_groups.append(sorted(current_group, key=lambda x: x[0]))

                # Display text with proportional spacing
                for group in vertical_groups:
                    line = ""
                    last_x = 0
                    for rel_x, text in group:
                        # Add proportional spacing
                        spaces = max(1, min(15, int((rel_x - last_x) / 7)))
                        line += " " * spaces + text
                        last_x = rel_x
                    log_debug(line.lstrip(), "Process", "info")
                    
            else:
                # Fallback to simple list if dimensions aren't available
                for line in result.get("lines", []):
                    log_debug(line.get("text", ""), "Process", "info")

            log_debug("===============================\n", "Process", "info")
            
            # Start DeepSeek processing
            log_debug("Sending to DeepSeek... away we go!", "Process", "info")
            success = await submit_to_deepseek(result)
            
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
        
        # Verify file was written correctly with multiple retries
        max_retries = 3
        retry_delay = 0.1
        success = False
        
        for attempt in range(max_retries):
            try:
                # Force sync to filesystem
                with open(file_path, 'rb') as f:
                    # For PNG files, verify the header
                    if file_path.lower().endswith('.png'):
                        png_signature = b'\x89PNG\r\n\x1a\n'
                        file_signature = f.read(8)
                        if file_signature != png_signature:
                            if attempt < max_retries - 1:
                                time.sleep(retry_delay)
                                continue
                            raise IOError("Invalid PNG signature")
                    
                    # Read the rest to verify complete file and get size
                    f.seek(0)
                    content = f.read()
                    if len(content) < 100:  # Basic sanity check for minimum file size
                        if attempt < max_retries - 1:
                            time.sleep(retry_delay)
                            continue
                        raise IOError("File too small - likely corrupted")
                    
                    os.fsync(f.fileno())
                    success = True
                    break
            except Exception:
                if attempt == max_retries - 1:
                    raise
                time.sleep(retry_delay)
                continue
        
        if not success:
            raise IOError("Failed to verify file integrity after multiple attempts")
                
        if not MUTE_PROCESS_MESSAGES:
            log_debug(f"Saved and verified screenshot: {file.filename}", "Process", "info")
        return "File received", 200
    except Exception as e:
        log_debug(f"Error saving file: {str(e)}", "Process", "error")
        # Try to clean up corrupted file
        try:
            if os.path.exists(file_path):
                os.remove(file_path)
        except:
            pass
        return str(e), 500

@app.route('/trigger', methods=['POST'])
async def trigger():
    """Handle manual trigger to process the most recent file."""
    log_debug("Manual trigger received - starting processing workflow", "Process", "info")
    result, status_code = await process_latest_screenshot()
    if status_code != 200:
        log_debug(f"Processing workflow failed: {result}", "Process", "error")
    return "", 204  # Return immediately

@app.route('/signal', methods=['POST'])
async def signal():
    """Handle signal to process the most recent file immediately."""
    log_debug("Signal received - processing latest screenshot", "Process", "info")
    result, status_code = await process_latest_screenshot()
    if status_code != 200:
        log_debug(f"Processing failed: {result}", "Process", "error")
    else:
        log_debug("Processing completed successfully", "Process", "info")
    return "", 204

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

    # Start the Flask server with fixed port using Hypercorn
    port = get_server_port()
    print(f"Starting server on port {port}")
    save_port_info(port)
    
    config = Config()
    config.bind = [f"0.0.0.0:{port}"]
    asyncio.run(serve(asgi_app, config))