import requests
import json
import sys
import os 

# Load server details from the config file
def load_server_details():
    try:
        run_mode = os.getenv("RUN_MODE", "local").lower()
        if run_mode == "docker":
            config_path = "/app/server_config.json"
        else:
            config_path = os.path.join(os.getcwd(), "server_config.json")
        
        if not os.path.exists(config_path):
            # Fallback for docker mode: try using the current working directory
            if run_mode == "docker":
                alt_config_path = os.path.join(os.getcwd(), "server_config.json")
                if os.path.exists(alt_config_path):
                    config_path = alt_config_path
                else:
                    raise FileNotFoundError(f"Config file not found at {config_path} or {alt_config_path}")
            else:
                raise FileNotFoundError(f"Config file not found at {config_path}")
                
        with open(config_path, "r") as f:
            config = json.load(f)
            ip = config["ip"] or "localhost"
            port = 5348 #config["port"] or 5348
            room = config["room"] or "33ter_room"
            return ip, port, room
    except Exception as e:
        print(f"Error loading server details: {e}")
        exit(1)

def send_data(ip, port, room, message, logType="info"):
    try:
        # Prepare the message in the correct format
        message_data = {
            "room": room,
            "data": {
                "title": "coding challenge",
                "message": message,
                "logType": logType
            }  
        }

        # Send using REST API
        url = f"http://{ip}:{port}/broadcast"
        response = requests.post(url, json=message_data, timeout=5)
        
        if response.status_code == 200:
            print(f"Successfully sent message to {url}")
            print(f"Message: {json.dumps(message_data, indent=2)}")
        else:
            print(f"Failed to send message. Status code: {response.status_code}")

    except Exception as e:
        print(f"Unexpected error: {e}")
        exit(1)

if __name__ == "__main__":
    # Load server details from the config file
    ip, port, room = load_server_details()
    print(f"sending message to room: {room} on server at http://{ip}:{port}")

    # Get the message from the command line
    if len(sys.argv) < 2:
        print("Usage: python3 publish_socketio.py <message>")
        exit(1)
    message = sys.argv[1]
    logType = sys.argv[2] if len(sys.argv) > 2 else "info"

    # Send the message
    send_data(ip, port, room, message, logType)