#!/usr/bin/env python3
"""
33ter Socket.IO Server
Handles communication between the Python screenshot/OCR service and the iOS app.
"""
import os
import sys
import json
import logging
import argparse
from datetime import datetime
import asyncio
import socketio
from aiohttp import web

from utils.server_config import get_server_config, update_server_config
from utils.path_config import get_logs_dir

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

# Create Socket.IO server
sio = socketio.AsyncServer(
    async_mode='aiohttp',
    cors_allowed_origins=config['server']['cors_origins'],
    logger=True,
    engineio_logger=True
)

# Create web application
app = web.Application()
sio.attach(app)

# Keep track of connected clients
connected_clients = set()
current_room = config['server']['room']

# Event handlers
@sio.event
async def connect(sid, environ):
    """Handle client connection."""
    logger.info(f"Client connected: {sid}")
    connected_clients.add(sid)
    
    # Emit welcome message
    await sio.emit('message', {
        'type': 'info',
        'data': {
            'message': 'Connected to 33ter Socket.IO server',
            'timestamp': datetime.now().isoformat()
        }
    }, room=sid)

@sio.event
async def disconnect(sid):
    """Handle client disconnection."""
    logger.info(f"Client disconnected: {sid}")
    if sid in connected_clients:
        connected_clients.remove(sid)

@sio.event
async def join_room(sid, data):
    """Handle room join requests."""
    global current_room
    
    if not isinstance(data, dict) or 'room' not in data:
        logger.error(f"Invalid join_room data from {sid}: {data}")
        return
    
    room = data['room']
    current_room = room
    sio.enter_room(sid, room)
    logger.info(f"Client {sid} joined room: {room}")
    
    await sio.emit('message', {
        'type': 'info',
        'data': {
            'message': f'Joined room: {room}',
            'timestamp': datetime.now().isoformat()
        }
    }, room=sid)

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
        # Format message for iOS client
        message = {
            'type': 'prime',
            'data': {
                'text': data[0].get('text', ''),
                'timestamp': datetime.now().isoformat()
            }
        }
        
        await sio.emit('message', message, room=current_room)
        logger.debug(f"OCR result broadcast successful: {len(data[0].get('text', ''))} chars")
        
    except Exception as e:
        logger.error(f"Error broadcasting OCR result: {e}")
        # Send error message to room
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
    if not current_room:
        logger.warning("No room set for OCR trigger")
        return
        
    logger.info(f"Broadcasting OCR trigger to room {current_room}")
    await sio.emit('trigger_ocr', {}, room=current_room)

@sio.event
async def message(sid, data):
    """Handle generic messages."""
    if not isinstance(data, dict):
        return
        
    msg_type = data.get('type', 'info')
    msg_data = data.get('data', {})
    
    if current_room:
        await sio.emit('message', {
            'type': msg_type,
            'data': {
                'message': msg_data.get('message', ''),
                'timestamp': datetime.now().isoformat()
            }
        }, room=current_room)

async def health_check():
    """Periodic health check and status broadcast."""
    if not config['health_check']['enabled']:
        return
        
    interval = config['health_check']['interval']
    
    while True:
        if current_room:
            try:
                await sio.emit('server_status', {
                    'status': 'healthy',
                    'clients': len(connected_clients),
                    'timestamp': datetime.now().isoformat()
                }, room=current_room)
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
        
        # Create event loop
        loop = asyncio.get_event_loop()
        
        # Start server
        web.run_app(
            app,
            host=args.host,
            port=args.port,
            loop=loop
        )
        
    except Exception as e:
        logger.error(f"Failed to start server: {e}")
        return 1
        
    return 0

if __name__ == '__main__':
    sys.exit(main())