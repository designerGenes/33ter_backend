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

# Add app root to Python path if needed
app_root = str(Path(__file__).parent.parent.absolute())
if app_root not in sys.path:
    sys.path.insert(0, app_root)

from utils.server_config import get_server_config, update_server_config
from utils.path_config import get_logs_dir

import logging
import argparse
from datetime import datetime
import asyncio
import socketio
from aiohttp import web

def setup_logging(log_level: str = "INFO"):
    """Configure logging with the specified level."""
    log_file = os.path.join(get_logs_dir(), "socketio_server.log")
    
    logging.basicConfig(
        level=getattr(logging, log_level.upper()),
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_file),
            logging.StreamHandler()
        ]
    )
    return logging.getLogger('33ter-SocketIO')

# Load configuration
config = get_server_config()
logger = setup_logging(config['server']['log_level'])

# Create Socket.IO server with reduced logging
sio = socketio.AsyncServer(
    async_mode='aiohttp',
    cors_allowed_origins=config['server']['cors_origins'],
    logger=False,  # Disable default logging
    engineio_logger=False  # Disable engineio logging
)

# Create web application
app = web.Application()
sio.attach(app)

# Keep track of clients by type
ios_clients = set()
python_clients = set()
current_room = config['server']['room']

def get_client_count():
    """Get current iOS client count."""
    return len(ios_clients)

# Event handlers
@sio.event
async def connect(sid, environ):
    """Handle client connection."""
    user_agent = environ.get('HTTP_USER_AGENT', '').lower()
    
    if 'ios' in user_agent or 'iphone' in user_agent or 'ipad' in user_agent:
        ios_clients.add(sid)
        logger.info(f"iOS client connected: {sid}")
    else:
        # For testing purposes, treat Python clients as both iOS and Python clients
        ios_clients.add(sid)
        python_clients.add(sid)
        logger.info(f"Python client connected (treated as both): {sid}")
    
    await broadcast_client_count()

@sio.event
async def disconnect(sid):
    """Handle client disconnection."""
    was_ios = sid in ios_clients
    ios_clients.discard(sid)
    python_clients.discard(sid)
    
    if was_ios:
        logger.info(f"iOS client disconnected: {sid}")
        await broadcast_client_count()
    else:
        logger.info(f"Python client disconnected: {sid}")

async def broadcast_client_count():
    """Broadcast current iOS client count to all clients."""
    count = get_client_count()
    logger.debug(f"Broadcasting client count: {count}")
    await sio.emit('client_count', {
        'count': count,
        'timestamp': datetime.now().isoformat()
    })  # Removed room restriction to ensure all clients receive the count

@sio.event
async def join_room(sid, data):
    """Handle room join requests."""
    global current_room
    
    if not isinstance(data, dict) or 'room' not in data:
        logger.error(f"Invalid join_room data from {sid}")
        return False
    
    room = data['room']
    if not room:
        logger.error(f"Empty room name from {sid}")
        return False
        
    current_room = room
    sio.enter_room(sid, room)
    logger.info(f"Client {sid} joined room: {room}")
    
    # Send welcome message to all clients (removed iOS check)
    await sio.emit('message', {
        'messageType': 'info',
        'value': f'Connected to 33ter server in room: {room}',
        'from': 'localBackend',
    }, room=sid)
    
    await broadcast_client_count()
    return True

@sio.event
async def leave_room(sid, data):
    """Handle room leave requests."""
    if not isinstance(data, dict) or 'room' not in data:
        return
        
    room = data['room']
    sio.leave_room(sid, room)
    logger.info(f"Client {sid} left room: {room}")

@sio.event
async def ocr_result(sid, data):
    """Handle OCR results from Python client and broadcast to room."""
    if not current_room:
        logger.warning("No room set for OCR result broadcast")
        return
        
    logger.info(f"Broadcasting OCR result to room {current_room}")
    
    try:
        text = data[0].get('text', '')
        
        # Create a preview with just the first two lines
        lines = text.splitlines()
        preview_lines = lines[:2]
        preview_text = '\n'.join(preview_lines)
        
        # Add an indicator if there's more text
        if len(lines) > 2:
            preview_text += "\n[...more lines not shown...]"
        
        message = {
            'type': 'codeSolution',
            'data': {
                'text': preview_text,
                'fullText': text,  # Include the full text as well
                'timestamp': datetime.now().isoformat()
            }
        }
        
        # Broadcast to sender's room and current room
        await sio.emit('message', message)  # Changed to broadcast to all
        logger.info(f"OCR result preview broadcast successful: {len(preview_text)}/{len(text)} chars")
        
    except Exception as e:
        logger.error(f"Error broadcasting OCR result: {e}")
        await sio.emit('message', {
            'messageType': 'warning',
            'value': 'Failed to process OCR result',
            'from': 'localBackend',
        })

@sio.event
async def trigger_ocr(sid):
    """Handle OCR trigger request from iOS client."""
    # Remove iOS client check since we're treating all test clients as both types
    if not current_room:
        logger.warning("No room set for OCR trigger")
        return
        
    logger.info(f"Broadcasting OCR trigger to room {current_room}")
    await sio.emit('trigger_ocr', {})  # Emit to all clients
    logger.debug(f"Sent trigger_ocr to all clients")

@sio.event
async def message(sid, data):
    """Handle custom messages."""
    try:
        if not isinstance(data, dict):
            error = "Invalid message format: not a dict"
            logger.error(f"{error} from {sid}")
            return error
            
        # Validate required fields
        required_fields = ['messageType', 'from', 'value']
        missing = [field for field in required_fields if field not in data]
        if missing:
            error = f"Missing required fields: {', '.join(missing)}"
            logger.error(f"{error} from {sid}")
            return error
            
        logger.info(f"Message received: {data['messageType']} from {data['from']}")
        logger.debug(f"Message content: {data}")
        
        # Broadcast to room
        if current_room:
            logger.debug(f"Broadcasting message to room {current_room}")
            # Make sure it's sent to EVERYONE in the room, including the original sender
            await sio.emit('message', data)  # Broadcast to all clients, not just room members
            logger.info(f"Message broadcast successful to all clients")
            return None  # Success case
            
        error = "No room set for message broadcast"
        logger.warning(error)
        return error
        
    except Exception as e:
        error = f"Error processing message: {str(e)}"
        logger.error(error)
        return error

async def health_check():
    """Periodic health check and status broadcast."""
    if not config['health_check']['enabled']:
        return
        
    interval = config['health_check']['interval']
    
    while True:
        if current_room:
            try:
                await broadcast_client_count()
            except Exception as e:
                logger.error(f"Health check broadcast failed: {e}")
        await asyncio.sleep(interval)

def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description='33ter Socket.IO Server')
    parser.add_argument('--host', 
                       default=config['server']['host'],
                       help='Host to bind to')
    parser.add_argument('--port', 
                       type=int,
                       default=config['server']['port'],
                       help='Port to listen on')
    parser.add_argument('--room',
                       default=config['server']['room'],
                       help='Default room name')
    parser.add_argument('--log-level',
                       default=config['server']['log_level'],
                       choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'],
                       help='Logging level')
    return parser.parse_args()

async def init_app():
    """Initialize the application."""
    args = parse_args()
    
    # Update config with any command line overrides
    server_updates = {
        'server': {
            'host': args.host,
            'port': args.port,
            'room': args.room,
            'log_level': args.log_level
        }
    }
    update_server_config(server_updates)
    
    # Start health check if enabled
    if config['health_check']['enabled']:
        asyncio.create_task(health_check())
    
    return args.host, args.port

def main():
    """Main entry point."""
    try:
        args = parse_args()
        
        # Log startup
        logger.info(f"Starting Socket.IO server on {args.host}:{args.port}")
        
        # Create web app and attach Socket.IO
        app = web.Application()
        sio.attach(app)
        
        # Create event loop
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        # Start server
        runner = web.AppRunner(app)
        loop.run_until_complete(runner.setup())
        site = web.TCPSite(runner, args.host, args.port)
        loop.run_until_complete(site.start())
        
        print(f"Running on http://{args.host}:{args.port}")
        sys.stdout.flush()
        
        # Run forever
        loop.run_forever()
        
    except Exception as e:
        logger.error(f"Failed to start server: {e}")
        return 1
    finally:
        if 'runner' in locals():
            loop.run_until_complete(runner.cleanup())
        if 'loop' in locals():
            loop.close()
    
    return 0

if __name__ == '__main__':
    sys.exit(main())