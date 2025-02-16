import os
import json
import requests
import logging

def get_socket_config():
    """Get Socket.IO server configuration from config file."""
    try:
        config_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'config', 'config.json')
        with open(config_path) as f:
            config = json.load(f)
        return config['services']['publishMessage']
    except Exception as e:
        logging.error(f"Error loading socket config: {e}")
        return None

def log_debug(message, source="Process", level="info"):
    """Log a debug message - goes to Process screen output."""
    print(f"[{source}] {message}")

def log_to_socketio(message, title="Message", log_type="info"):
    """Send a message to the Socket.IO server for iOS app consumption only."""
    try:
        config = get_socket_config()
        if not config:
            return
        
        socket_port = config['port']
        socket_room = config['room']
        
        payload = {
            "room": socket_room,
            "data": {
                "title": title,
                "message": message,
                "logType": log_type
            }
        }
        
        response = requests.post(
            f"http://localhost:{socket_port}/broadcast",
            json=payload
        )
        
        if response.status_code != 200:
            logging.error(f"Error sending message to Socket.IO server: {response.status_code}")
            
    except Exception as e:
        logging.error(f"Error in log_to_socketio: {e}")