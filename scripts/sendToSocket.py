#!/usr/bin/env python3
"""Utility script for sending messages to the 33ter Socket.IO server."""

import os
import sys
import socketio
import json
import argparse
import time
import threading
import traceback
from pathlib import Path

# Add app root to Python path
app_root = str(Path(__file__).parent.parent.absolute())
if app_root not in sys.path:
    sys.path.insert(0, app_root)

from utils import get_server_config

def send_message(value: str, message_type: str = "info", from_source: str = "commandLine") -> None:
    """Send a message to the Socket.IO server."""
    try:
        config = get_server_config()
        sio = socketio.Client(logger=True, engineio_logger=False)  # Enable logger to debug
        
        # Get room name from config
        room_name = config.get('server', {}).get('room', '33ter_room')
        host = '0.0.0.0'  # Default to localhost
        port = 5348  # Default port
        
        # Track connection and message status
        connected = False
        message_sent = False
        room_joined = False
        
        # Add a unique ID to the message to help track it
        unique_id = int(time.time() * 1000)  # Millisecond timestamp
        
        @sio.event
        def connect():
            nonlocal connected
            connected = True
            print("Connected to server")
            
            # Join the room first
            sio.emit('join_room', {'room': room_name}, callback=join_room_callback)
        
        def join_room_callback(success):
            nonlocal room_joined
            if success:
                room_joined = True
                print(f"Successfully joined room: {room_name}")
                # Send message now that we're in the room
                send_message_to_room()
            else:
                print(f"Failed to join room: {room_name}")
                sio.disconnect()
        
        def send_message_to_room():
            nonlocal message_sent
            # Format message to match expected structure EXACTLY
            message = {
                "messageType": message_type,
                "from": from_source,
                "value": value 
            }
            
            print(f"Sending message: {json.dumps(message, indent=2)}")
            
            # Send message to the room explicitly
            sio.emit('message', message)
            message_sent = True
            print(f"Sent message to room {room_name}")
            
            # Wait longer to ensure message is delivered and processed
            print("Keeping connection open for 3 seconds to ensure message delivery...")
            time.sleep(3)  # Increased from 5 to 10 seconds
            print("Disconnecting...")
            sio.disconnect()
        
        @sio.event
        def disconnect():
            nonlocal connected
            connected = False
            print("Disconnected from server")
        
        @sio.on('message')
        def on_message(data):
            print(f"Received response message: {data}")
            # Check if this is our own message echoed back
            if isinstance(data, dict) and data.get('from') == from_source and f"[ID:{unique_id}]" in str(data.get('value', '')):
                print("Confirmed our message was received and echoed back!")
        
        # Connect to server with proper headers that identify as an iOS client
        url = f"http://{host}:{port}"
        print(f"Connecting to {url}...")
        headers = {
            'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 15_0 like Mac OS X)',
            'X-Client-Type': 'iOS'  # Add custom header for client identification
        }
        
        print(f"Using room: {room_name}")
        sio.connect(url, headers=headers, wait_timeout=10)
        
        # Wait for whole process to complete
        timeout = time.time() + 20  # Increased from 15 to 20 seconds
        while connected and time.time() < timeout:
            time.sleep(0.1)
            
        if time.time() >= timeout:
            print("Operation timed out")
            if sio.connected:
                sio.disconnect()
        
        # Report final status
        if message_sent:
            print("Message delivery completed successfully")
        else:
            print("Message was not confirmed sent - check server logs")
        
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        traceback.print_exc()
        sys.exit(1)

def main():
    parser = argparse.ArgumentParser(description='Send message to 33ter Socket.IO server')
    parser.add_argument('value', help='Message value to send')
    parser.add_argument('--type', choices=['info', 'warning', 'trigger', 'ocrResult'], 
                       default='info', help='Message type')
    parser.add_argument('--from', dest='from_source', default='commandLine',
                       help='Source of the message')
    
    args = parser.parse_args()
    send_message(args.value, args.type, args.from_source)

if __name__ == '__main__':
    main()
