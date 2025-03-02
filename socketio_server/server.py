#!/usr/bin/env python3
"""
33ter Socket.IO Server
Handles communication between the Python screenshot/OCR service and the iOS app.
"""
import os
import sys
import logging
import argparse
from datetime import datetime
import asyncio
import socketio
from aiohttp import web
from utils import get_server_config, update_server_config
from utils import get_logs_dir

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
        python_clients.add(sid)
        logger.info(f"Python client connected: {sid}")
    
    # Notify about iOS client count changes
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
    await sio.emit('client_count', {
        'count': get_client_count(),
        'timestamp': datetime.now().isoformat()
    }, room=current_room)

@sio.event
async def join_room(sid, data):
    """Handle room join requests."""
    global current_room
    
    if not isinstance(data, dict) or 'room' not in data:
        logger.error(f"Invalid join_room data from {sid}")
        return
    
    room = data['room']
    current_room = room
    sio.enter_room(sid, room)
    logger.info(f"Client {sid} joined room: {room}")
    
    # Send welcome and status
    if sid in ios_clients:
        await sio.emit('message', {
            'type': 'info',
            'data': {
                'message': f'Connected to 33ter server in room: {room}',
                'timestamp': datetime.now().isoformat()
            }
        }, room=sid)
    
    await broadcast_client_count()

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
    if sid not in python_clients:
        logger.warning(f"Unauthorized OCR result from {sid}")
        return
        
    if not current_room:
        logger.warning("No room set for OCR result broadcast")
        return
        
    logger.info(f"Broadcasting OCR result to room {current_room}")
    
    try:
        text = data[0].get('text', '')
        # Format message for iOS client
        message = {
            'type': 'prime',
            'data': {
                'text': text,
                'timestamp': datetime.now().isoformat()
            }
        }
        
        await sio.emit('message', message, room=current_room)
        logger.info(f"OCR result broadcast successful: {len(text)} chars")
        
    except Exception as e:
        logger.error(f"Error broadcasting OCR result: {e}")
        await sio.emit('message', {
            'type': 'error',
            'data': {
                'message': 'Failed to process OCR result',
                'timestamp': datetime.now().isoformat()
            }
        }, room=current_room)

@sio.event
async def trigger_ocr(sid):
    """Handle OCR trigger request from iOS client."""
    if sid not in ios_clients:
        logger.warning(f"Unauthorized OCR trigger from {sid}")
        return
        
    if not current_room:
        logger.warning("No room set for OCR trigger")
        return
        
    logger.info(f"Broadcasting OCR trigger to room {current_room}")
    await sio.emit('trigger_ocr', {}, room=current_room)

@sio.event
async def message(sid, data):
    """Handle custom messages."""
    if not isinstance(data, dict):
        return
    
    msg_type = data.get('type', 'info')
    if msg_type == 'custom':
        title = data.get('title', '')
        message = data.get('message', '')
        msg_level = data.get('msg_type', 'info')
        logger.info(f"Custom message: {title} ({msg_level})")
    
    if current_room:
        await sio.emit('message', data, room=current_room)

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
        logger.info(f"Default room: {args.room}")
        logger.info(f"Log level: {args.log_level}")
        
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
        global current_room
        current_room = args.room
        
        # Create event loop
        loop = asyncio.get_event_loop()
        
        # Start health check if enabled
        if config['health_check']['enabled']:
            loop.create_task(health_check())
        
        # Start server
        web.run_app(
            app,
            host=args.host,
            port=args.port
        )
        
    except Exception as e:
        logger.error(f"Failed to start server: {e}")
        return 1
        
    return 0

if __name__ == '__main__':
    sys.exit(main())