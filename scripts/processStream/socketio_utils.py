import os
import json
import requests

#BAD

MAGIC_DEFAULT_PORT = 5348

# Global variables for server config
socketIO_server_host = None
socketIO_server_port = None

def discover_server_config():
    run_mode = os.getenv("RUN_MODE", "local").lower()
    server_config_path = "/app/server_config.json" if run_mode == "docker" else "server_config.json"
    default_host = "host.docker.internal" if run_mode == "docker" else "localhost"
    
    global socketIO_server_host
    global socketIO_server_port
    if (socketIO_server_host is not None and 
        socketIO_server_port is not None):
        return socketIO_server_host, socketIO_server_port
    try:
        with open(server_config_path, 'r') as f:
            config = json.load(f)
            socketIO_server_host = config.get('ip', default_host)
            socketIO_server_port = config.get('port', MAGIC_DEFAULT_PORT)
            return socketIO_server_host, socketIO_server_port
    except FileNotFoundError:
        print(f"Server config not found at {server_config_path}, using defaults")
        socketIO_server_host = default_host
        socketIO_server_port = os.getenv("SOCKETIO_PORT", MAGIC_DEFAULT_PORT)
        return socketIO_server_host, socketIO_server_port

def send_to_socketio(jsonObject, socketIO_server_host="localhost", socketIO_server_port=MAGIC_DEFAULT_PORT):
    try:
        if "data" in jsonObject:
            if "room" not in jsonObject:
                jsonObject["room"] = "33ter_room"
        
        response = requests.post(
            f'http://{socketIO_server_host}:{socketIO_server_port}/broadcast',
            json=jsonObject,
            timeout=5
        )
        if response.status_code >= 400 and response.status_code < 600:
            print(f"Failed to send to Socket.IO server. Status code: {response.status_code}")
    except requests.exceptions.ConnectionError as e:
        print(f"Failed to connect to Socket.IO server at {socketIO_server_host}:{socketIO_server_port}")
        print(f"Error: {e}")
    except requests.exceptions.Timeout:
        print("Request to Socket.IO server timed out")
    except Exception as e:
        print(f"Unexpected error sending solution: {e}")

def log_to_socketio(log_message, title=None, logType="info"):
    socketIO_server_host, socketIO_server_port = discover_server_config()
    if title is None:
        title = logType
    send_to_socketio({
                "room": "33ter_room",
                "data": {
                    "title": title,
                    "message": log_message,
                    "logType": logType
                }
            },
            socketIO_server_host,  # Use discovered host instead of hardcoded localhost
            socketIO_server_port)  # Use discovered port
    print(f"[{logType}]: \t {title}: \t {log_message}")