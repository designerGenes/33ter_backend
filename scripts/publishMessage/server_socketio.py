import os
import sys
import json
import asyncio

# Add the root app directory to Python path for utils imports
app_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.append(app_root)

# Fallback path for utils if not found
utils_path = os.path.join(app_root, 'utils')
if utils_path not in sys.path:
    sys.path.append(utils_path)

from aiohttp import web
import socketio
import psutil
import argparse
import socket
from utils.socketio_utils import log_debug

# Set up Socket.IO server
sio = socketio.AsyncServer(cors_allowed_origins='*')
app = web.Application()
sio.attach(app)

# Constants
DEFAULT_ROOM = "33ter_room"
VALID_LOG_TYPES = ["Info", "Warning", "Prime"]

# Store connected clients and rooms
connected_clients = {}
rooms = {
    "33ter_room": {
        "clients": set(),
        "messages": []
    }
}

def get_local_ip():
    """Get the local IP address for the server."""
    ip = os.getenv("ADVERTISE_IP")
    if ip:
        return ip
    run_mode = os.getenv("RUN_MODE", "local").lower()
    if run_mode == "docker":
        try:
            return socket.gethostbyname('host.docker.internal')
        except:
            pass
    return socket.gethostbyname(socket.gethostname())

# Socket.IO Event Handlers
@sio.event
async def connect(sid, environ):
    """Handle client connection."""
    connected_clients[sid] = {"rooms": []}

@sio.event
async def join_room(sid, data):
    """Handle client joining a room."""
    room = data.get("room", DEFAULT_ROOM)
    if room not in rooms:
        rooms[room] = {"clients": set(), "messages": []}
    rooms[room]["clients"].add(sid)
    connected_clients[sid]["rooms"].append(room)
    await sio.enter_room(sid, room)

@sio.event
async def disconnect(sid):
    """Handle client disconnection."""
    if sid in connected_clients:
        for room in connected_clients[sid]["rooms"]:
            if room in rooms and sid in rooms[room]["clients"]:
                rooms[room]["clients"].remove(sid)
            await sio.leave_room(sid, room)
        del connected_clients[sid]

@sio.event
async def room_message(sid, data):
    """Handle message sent to a room."""
    room = data.get("room")
    message_data = data.get("data")
    if room and message_data:
        title = message_data.get("title")
        message = message_data.get("message")
        log_type = message_data.get("logType", "Info")
        
        if log_type not in VALID_LOG_TYPES:
            log_type = "Info"
        
        await sio.emit("room_message", {
            "data": {
                "title": title,
                "message": message,
                "logType": log_type
            }
        }, room=room)

# HTTP Endpoints
async def broadcast_handler(request):
    """Handle broadcast requests from HTTP endpoint."""
    try:
        data = await request.json()
        room = data.get("room", DEFAULT_ROOM)
        message_data = data.get("data")
        
        if message_data:
            title = message_data.get("title")
            message = message_data.get("message")
            log_type = message_data.get("logType", "Info")
            
            if log_type not in VALID_LOG_TYPES:
                log_type = "Info"
            
            if message:
                await sio.emit("room_message", {
                    "data": {
                        "title": title,
                        "message": message,
                        "logType": log_type
                    }
                }, room=room)
                return web.Response(text='Message broadcasted', status=200)
            
        return web.Response(text='No message provided', status=400)
    except Exception as e:
        return web.Response(text='Internal server error', status=500)

async def health_handler(request):
    """Health check endpoint."""
    return web.Response(text='OK')

def generate_server_config(ip, port, room):
    """Generate server configuration file."""
    config = {
        "ip": ip,
        "port": port,
        "room": room
    }
    with open("server_config.json", "w") as f:
        json.dump(config, f, indent=2)

async def start_server():
    """Start the Socket.IO server."""
    run_mode = os.getenv("RUN_MODE", "local").lower()
    bind_ip = "0.0.0.0"
    port = 5348
    
    app.router.add_get('/health', health_handler)
    app.router.add_post('/broadcast', broadcast_handler)

    advertise_ip = get_local_ip()
    generate_server_config(advertise_ip, port, DEFAULT_ROOM)
    
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, bind_ip, port)
    
    await site.start()
    print(f"Socket.IO server started on port {port}")
    
    try:
        while True:  # Keep the server running
            await asyncio.sleep(3600)  # Sleep for an hour
    finally:
        await runner.cleanup()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Socket.IO Server')
    parser.add_argument('--port', type=int, default=5348,
                       help='Port to run the server on')
    parser.add_argument('--room', type=str, default='33ter_room',
                       help='Default room name')
    args = parser.parse_args()

    port = args.port
    DEFAULT_ROOM = args.room

    try:
        asyncio.run(start_server())
    except KeyboardInterrupt:
        print("\nServer stopped by user")
    except Exception as e:
        print(f"Fatal error: {e}")
        sys.exit(1)