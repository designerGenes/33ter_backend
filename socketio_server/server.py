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
from .discovery_manager import DiscoveryManager
from utils.network_utils import get_local_ip

import logging
import argparse
from datetime import datetime
import asyncio
import socketio
from aiohttp import web
import atexit

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

# Global instance for discovery manager
discovery_manager = None

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
    })

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
        logger.warning(f"No room set for OCR result broadcast from {sid}")
        return

    logger.info(f"Received OCR result from {sid}, broadcasting as 'ocr_result' event to room {current_room}")

    try:
        # Assuming data is the list [{'text': ..., 'timestamp': ...}] sent by ProcessManager
        if not isinstance(data, list) or not data or not isinstance(data[0], dict):
             logger.error(f"Invalid ocr_result data format received from {sid}: {data}")
             # Optionally notify sender?
             return

        ocr_data = data[0]
        text = ocr_data.get('text', '')
        timestamp = ocr_data.get('timestamp', datetime.now().isoformat()) # Use provided or generate new

        # Prepare payload for broadcasting to room
        payload = {
            'text': text,
            'timestamp': timestamp,
            'from': 'localBackend' # Add source info
        }

        # Emit the specific 'ocr_result' event to the room
        await sio.emit('ocr_result', payload, room=current_room)
        logger.info(f"Broadcast 'ocr_result' event successful to room {current_room}: {len(text)} chars")

    except Exception as e:
        logger.error(f"Error broadcasting OCR result event: {e}", exc_info=True)
        # Emit an error message back to the room using generic 'message' for compatibility
        await sio.emit('message', {
            'messageType': 'warning',
            'value': 'Failed to process OCR result',
            'from': 'localBackend',
        }, room=current_room)

@sio.event
async def trigger_ocr(sid):
    """Handle OCR trigger request from iOS client."""
    if not current_room:
        logger.warning("No room set for OCR trigger")
        return
        
    logger.info(f"Broadcasting OCR trigger to room {current_room}")
    await sio.emit('trigger_ocr', {})
    logger.debug(f"Sent trigger_ocr to all clients")

@sio.event
async def heartbeat(sid, data):
    """Handle heartbeat messages."""
    logger.debug(f"Heartbeat received from {sid}")
    timestamp = data.get('timestamp')
    logger.info(f"Heartbeat received: {timestamp}") 
    await sio.emit('heartbeat_response', {
        'status': 'alive', 
        'timestamp': timestamp
    }, room=sid)

@sio.event
async def message(sid, data):
    """Handle custom messages."""
    try:
        if not isinstance(data, dict):
            error = "Invalid message format: not a dict"
            logger.error(f"{error} from {sid}")
            return error
            
        required_fields = ['messageType', 'from', 'value']
        missing = [field for field in required_fields if field not in data]
        if missing:
            error = f"Missing required fields: {', '.join(missing)}"
            logger.error(f"{error} from {sid}")
            return error
            
        logger.info(f"Message received: {data['messageType']} from {data['from']}")
        logger.debug(f"Message content: {data}")
        
        if current_room:
            logger.debug(f"Broadcasting message to room {current_room}")
            await sio.emit('message', data)
            logger.info(f"Message broadcast successful to all clients")
            return None
            
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
    
    server_updates = {
        'server': {
            'host': args.host,
            'port': args.port,
            'room': args.room,
            'log_level': args.log_level
        }
    }
    update_server_config(server_updates)
    
    if config['health_check']['enabled']:
        asyncio.create_task(health_check())
    
    return args.host, args.port

def main():
    """Main entry point."""
    global discovery_manager
    runner = None
    loop = None
    try:
        args = parse_args()
        
        logger.info(f"Starting Socket.IO server on {args.host}:{args.port}")
        
        discovery_manager = DiscoveryManager(logger)
        actual_ip = get_local_ip()
        if actual_ip:
            logger.info(f"Server should be accessible on local network at: {actual_ip}:{args.port}")
            discovery_manager.start_discovery(port=args.port)
        else:
            logger.warning("Could not determine local IP for Bonjour registration or logging.")
        
        app = web.Application()
        sio.attach(app)
        
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        runner = web.AppRunner(app)
        loop.run_until_complete(runner.setup())
        site = web.TCPSite(runner, args.host, args.port)
        loop.run_until_complete(site.start())

        # This is the line we will wait for in ProcessManager
        print(f"Running on http://{args.host}:{args.port}")
        sys.stdout.flush() # Ensure it's printed immediately

        loop.run_forever()
        
    except KeyboardInterrupt:
        logger.info("Shutdown requested by user (KeyboardInterrupt).")
    except Exception as e:
        logger.error(f"Failed to start or run server: {e}", exc_info=True)
        return 1
    finally:
        logger.info("Starting server shutdown...")
        if discovery_manager:
            discovery_manager.stop_discovery()
        
        if runner:
            if loop and loop.is_running():
                loop.run_until_complete(runner.cleanup())
            else:
                asyncio.run(runner.cleanup())
        
        if loop and not loop.is_closed():
            if loop.is_running():
                loop.stop()
            tasks = [task for task in asyncio.all_tasks(loop) if task is not asyncio.current_task(loop)]
            if tasks:
                logger.info(f"Waiting for {len(tasks)} background tasks to complete...")
                try:
                    loop.run_until_complete(asyncio.wait(tasks, timeout=5.0))
                except asyncio.TimeoutError:
                    logger.warning("Timeout waiting for background tasks. Forcing shutdown.")
                    for task in tasks:
                        if not task.done():
                            task.cancel()
                    loop.run_until_complete(asyncio.sleep(0))
            logger.info("Closing event loop.")
            loop.close()
        logger.info("Server shutdown complete.")
    
    return 0

if __name__ == '__main__':
    sys.exit(main())