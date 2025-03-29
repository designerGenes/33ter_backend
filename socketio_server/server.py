#!/usr/bin/env python3
"""33ter Socket.IO Server

This module implements the Socket.IO server that handles communication between the Python
screenshot/OCR service and the iOS app. It manages client connections, rooms, and message
routing while providing health monitoring and connection status updates.

Key Features:
- Handles both iOS and Python client connections
- Manages client rooms for message isolation
- Provides health check functionality
- Handles custom message routing
- Maintains client connection counts

#TODO:
- Implement proper authentication and client validation
- Add rate limiting for message broadcasts
- Implement proper connection pooling
- Add support for multiple rooms with different purposes
- Consider adding message queuing for reliability
- Implement proper SSL/TLS support
"""
import os
import sys
from pathlib import Path
import logging  # Move logging import earlier
import argparse
from datetime import datetime
import asyncio
import socketio
from aiohttp import web
import atexit
import copy  # For deep copies
import threading  # Import threading
from typing import Dict, Optional, Any

# Ensure the project root is in the Python path
project_root = Path(__file__).resolve().parents[1]
if str(project_root) not in sys.path:
    sys.path.append(str(project_root))

# Import local modules after path adjustment
from utils.config_loader import config as config_manager  # Use the ConfigManager instance
from utils.message_utils import create_socket_message, create_client_count_message, create_welcome_message, create_joined_room_message, MessageType
from utils.event_utils import EventType
from core.ocr_processor import OCRProcessor  # Added import

# --- Globals ---
config_data = config_manager.config  # Get the loaded config dictionary
logger = logging.getLogger(__name__)  # Get logger instance, assumes setup elsewhere
sio = socketio.AsyncServer(async_mode='aiohttp', cors_allowed_origins='*')
app = web.Application()
sio.attach(app)

# Client tracking
connected_clients: Dict[str, Dict[str, Any]] = {}
current_room: Optional[str] = config_manager.get('server', 'room', default='33ter_room')
internal_client_sid: Optional[str] = None

# OCR Processor instance
ocr_processor = OCRProcessor()  # Added instance

# Health check related
health_check_task: Optional[asyncio.Task] = None
health_check_interval = config_manager.get('health_check', 'interval', default=60)

# --- Utility Functions ---

async def broadcast_client_count():
    """Broadcast current iOS client count to all clients."""
    ios_client_count = len(connected_clients.values())
    await sio.send(create_client_count_message(ios_client_count), room=current_room)
    logger.info(f"Broadcasted client count to room: {current_room}")

@sio.event
async def connect(sid: str, environ: Dict, auth: Optional[Dict] = None):
    """Handle new client connections."""
    client_ip = environ.get('REMOTE_ADDR', 'Unknown IP')
    client_type = auth.get('client', 'Unknown') if auth else 'Unknown'  # Check auth data for client type
    
    connected_clients[sid] = {
        "address": client_ip,
        "connect_time": datetime.now().isoformat(),
        "client_type": client_type
    }
    await sio.send(create_welcome_message(sid), room=sid)
    await broadcast_client_count()
    logger.info(f"Client connected: {sid} ({client_ip}) - Type: {client_type}")
    
    if current_room:
        await sio.enter_room(sid, current_room)
        logger.info(f"Client {sid} automatically joined room: {current_room}")
        join_confirm_message = create_socket_message(
            MessageType.INFO,
            f"You have joined room: {current_room}",
            sender="localBackend"
        )
        await sio.send(join_confirm_message, room=sid)
    else:
        logger.warning(f"No default room configured for client {sid} to join.")


@sio.event
async def disconnect(sid: str):
    """Handle client disconnections."""
    if sid in connected_clients:
        client_info = connected_clients.pop(sid)
        logger.info(f"Client disconnected: {sid} ({client_info.get('address', 'Unknown IP')})")
        
        # If the internal client disconnects, clear its SID
        global internal_client_sid
        if sid == internal_client_sid:
            logger.warning("Internal macOS client disconnected.")
            internal_client_sid = None
            
        # Leave the known default room if it exists
        if current_room:
            try:
                await sio.leave_room(sid, current_room)
                logger.info(f"Client {sid} left room: {current_room}")
            except Exception as e:
                logger.error(f"Error removing {sid} from room {current_room}: {e}")

        # Broadcast updated client count
        await broadcast_client_count()
    else:
        logger.warning(f"Disconnect event received for unknown SID: {sid}")

@sio.event
async def join_room(sid, data):
    """Handle room join requests."""
    room_name = data.get('room')
    if not room_name:
        logger.error(f"Client {sid} sent join_room request without specifying room name.")
        error_message = create_socket_message(MessageType.ERROR, "Room name is required.", sender="localBackend")
        await sio.emit('message', error_message, room=sid)
        return

    await sio.enter_room(sid, room_name)
    logger.info(f"Client {sid} joined room: {room_name}")
    
    # Confirm joining the room
    join_confirm_message = create_socket_message(
        MessageType.INFO,
        f"Someone joined room: {room_name}",
        sender="localBackend"
    )
    await sio.emit('message', join_confirm_message, room=sid)
    
    # Broadcast updated client count for the specific room joined
    await broadcast_client_count()

@sio.event
async def leave_room(sid, data):
    """Handle room leave requests."""
    room_name = data.get('room')
    if not room_name:
        logger.error(f"Client {sid} sent leave_room request without specifying room name.")
        error_message = create_socket_message(MessageType.ERROR, "Room name is required.", sender="localBackend")
        await sio.emit('message', error_message, room=sid)
        return

    if room_name in sio.rooms(sid):
        await sio.leave_room(sid, room_name)
        logger.info(f"Client {sid} left room: {room_name}")
        # Confirm leaving the room
        leave_confirm_message = create_socket_message(
            MessageType.INFO,
            f"You have left room: {room_name}",
            sender="localBackend"
        )
        await sio.emit('message', leave_confirm_message, room=sid)
        # Broadcast updated client count
        await broadcast_client_count()
    else:
        logger.warning(f"Client {sid} tried to leave room '{room_name}' but was not in it.")
        error_message = create_socket_message(MessageType.WARNING, f"You are not in room: {room_name}", sender="localBackend")
        await sio.emit('message', error_message, room=sid)

@sio.event
async def register_internal_client(sid: str, data: Optional[Dict] = None):
    """Allows the macOS agent to identify itself as the internal client."""
    global internal_client_sid
    # FIX: Corrected variable name in the check
    if internal_client_sid and internal_client_sid != sid:
        logger.warning(f"Another internal client {sid} tried to register while {internal_client_sid} is active.")
        internal_client_sid = sid  # Allow new client to take over for now
        if sid in connected_clients:
            connected_clients[sid]['client_type'] = 'Internal'  # Update type if known
        logger.info(f"Internal macOS client re-registered with SID: {sid} (previous: {internal_client_sid})")
    else:
        internal_client_sid = sid
        if sid in connected_clients:
            connected_clients[sid]['client_type'] = 'Internal'
        logger.info(f"Internal macOS client registered with SID: {sid}")
        confirm_message = create_socket_message(MessageType.INFO, "Internal client registration confirmed.", sender="localBackend")
        await sio.emit('message', confirm_message, room=sid)
        # Ensure the client is in the main room (should be from connect handler, but belt-and-suspenders)
        if current_room:
            await sio.enter_room(sid, current_room)
            logger.debug(f"Ensured internal client {sid} is in room {current_room}")

@sio.event
async def trigger_ocr(sid):
    """Handle OCR trigger request from iOS client."""
    logger.info(f"Received trigger_ocr from client {sid}")

    if not current_room:
        logger.warning(f"No room set for OCR trigger from {sid}")
        warning_msg = create_socket_message(MessageType.WARNING, "Server error: No processing room configured.", sender="localBackend")
        await sio.emit('message', warning_msg, room=sid)
        return

    try:
        loop = asyncio.get_running_loop()
        if hasattr(ocr_processor, 'process_latest_screenshot'):
            ocr_text = await loop.run_in_executor(None, ocr_processor.process_latest_screenshot)
        else:
            logger.error("OCRProcessor object or process_latest_screenshot method not found!")
            ocr_text = None

        if ocr_text and ocr_text.strip():
            logger.info(f"OCR successful for {sid}. Emitting ocr_result.")
            ocr_data = {"text": ocr_text, "source": "manual_trigger"}
            await sio.emit('ocr_result', ocr_data, room=sid)
        else:
            logger.warning(f"OCR for {sid} returned no text.")
            warning_msg = create_socket_message(MessageType.WARNING, "OCR processing returned no text.", sender="localBackend")
            await sio.emit('message', warning_msg, room=sid)

    except Exception as e:
        logger.error(f"Error processing OCR for {sid}: {e}", exc_info=True)
        error_msg = create_socket_message(MessageType.ERROR, "Server error during OCR processing.", sender="localBackend")
        await sio.emit('message', error_msg, room=sid)

@sio.event
async def heartbeat(sid, data):
    """Handle heartbeat messages."""
    timestamp = data.get('timestamp')
    await sio.emit('heartbeat_response', {
        'status': 'alive',
        'timestamp': timestamp
    }, room=sid)

@sio.event
async def message(sid, data):
    """Handle custom messages."""
    logger.debug(f"Received generic message from {sid}: {data}")
    pass

# --- Health Check ---
async def health_check():
    """Periodic health check and status broadcast."""
    while True:
        await asyncio.sleep(health_check_interval)
        logger.info("Performing periodic health check...")
        logger.info(f"Connected clients ({len(connected_clients)}): {list(connected_clients.keys())}")
        availability_message = create_socket_message(
            MessageType.INFO, 
            {"status": "available", "timestamp": datetime.now().isoformat()}, 
            sender="localBackend"
        )
        await sio.emit('server_available', availability_message, room=current_room)

# --- Argument Parsing ---
def parse_args():
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description="33ter Socket.IO Server")
    parser.add_argument('--host', type=str, default=config_manager.get('server', 'host', default='0.0.0.0'),
                        help='Host IP address to bind the server to.')
    parser.add_argument('--port', type=int, default=config_manager.get('server', 'port', default=5348),
                        help='Port number to bind the server to.')
    return parser.parse_args()

# --- Server Lifecycle ---

async def start_server(host: str, port: int):
    """Starts the Socket.IO server and related tasks."""
    global health_check_task
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host, port)
    
    logger.info(f"Starting Socket.IO server on {host}:{port}")
    await site.start()
    
    health_check_task = asyncio.create_task(health_check())
    logger.info(f"Health check started with interval: {health_check_interval}s")
    
    await asyncio.Event().wait()

async def stop_server():
    """Stops the Socket.IO server and cleans up."""
    logger.info("Stopping Socket.IO server...")
    if health_check_task and not health_check_task.done():
        health_check_task.cancel()
        try:
            await health_check_task
        except asyncio.CancelledError:
            logger.info("Health check task cancelled.")

def cleanup_on_exit():
    """Perform cleanup actions when the server exits."""
    logger.info("Performing cleanup on exit...")

atexit.register(cleanup_on_exit)

# --- Main Execution ---

if __name__ == '__main__':
    args = parse_args()
    
    try:
        asyncio.run(start_server(args.host, args.port))
    except KeyboardInterrupt:
        logger.info("Server stopped by user (KeyboardInterrupt).")
    except Exception as e:
        logger.critical(f"Server encountered critical error: {e}", exc_info=True)
    finally:
        logger.info("Server shutdown complete.")