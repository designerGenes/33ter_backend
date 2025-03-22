#!/usr/bin/env python3
"""Utility script for sending messages to the 33ter Socket.IO server."""

import os
import sys
import socketio
import json
import argparse
import time
from pathlib import Path

# Add app root to Python path
app_root = str(Path(__file__).parent.parent.absolute())
if app_root not in sys.path:
    sys.path.insert(0, app_root)

from utils.server_config import get_server_config

def send_message(text: str, msg_type: str = "info") -> None:
    """Send a message to the Socket.IO server."""
    try:
        config = get_server_config()
        sio = socketio.Client(logger=False)
        
        @sio.event
        def connect():
            print("Connected to server")
            # Format message to match expected structure
            message = {
                "type": "custom",
                "data": {
                    "title": "CLI Message",
                    "message": text,
                    "msg_type": msg_type,
                    "timestamp": time.time()
                }
            }
            # Send message
            sio.emit('message', message, room=config.get('room', '33ter_room'))
            print(f"Sent message: {text}")
            # Disconnect after sending
            sio.disconnect()
        
        # Connect to server
        url = f"http://{config['host']}:{config['port']}"
        print(f"Connecting to {url}...")
        sio.connect(url, wait_timeout=5)
        
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

def main():
    parser = argparse.ArgumentParser(description='Send message to 33ter Socket.IO server')
    parser.add_argument('message', help='Message to send')
    parser.add_argument('--type', choices=['info', 'prime', 'warning'], 
                       default='info', help='Message type')
    
    args = parser.parse_args()
    send_message(args.message, args.type)

if __name__ == '__main__':
    main()
