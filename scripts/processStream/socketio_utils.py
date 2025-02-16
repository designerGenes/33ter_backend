import os
import requests
import json
import time
from typing import Optional, Literal

LogType = Literal["Info", "Warning", "Prime"]

def log_to_socketio(message: str, title: str = "Message", logType: LogType = "Info") -> None:
    """Send a log message to the Socket.IO server."""
    try:
        run_mode = os.getenv("RUN_MODE", "local").lower()
        host = "127.0.0.1" if run_mode == "local" else "host.docker.internal"
        socketio_url = f"http://{host}:5348/broadcast"
        
        payload = {
            "data": {
                "title": title,
                "message": message,
                "logType": logType
            }
        }
        
        # Add a small delay between messages to ensure proper order
        if title == "Process":
            time.sleep(0.1)
        
        headers = {'Content-Type': 'application/json'}
        response = requests.post(socketio_url, json=payload, headers=headers, timeout=5)
        
        if response.status_code != 200:
            print(f"Failed to send socket message. Status code: {response.status_code}")
            
    except Exception as e:
        print(f"Error sending socket message: {str(e)}")