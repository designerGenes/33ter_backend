import socketio
import asyncio
import logging
from aiohttp import web, web_runner  
import socket
from zeroconf import ServiceInfo, IPVersion  
from zeroconf.asyncio import AsyncZeroconf
import json 
import os, sys 
import psutil 
import argparse 

# Set up logging to file only
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Clear any existing handlers
logger.handlers.clear()

# Determine logs directory based on RUN_MODE
run_mode = os.getenv("RUN_MODE", "local").lower()
if run_mode == "docker":
    logs_dir = "/app/logs"
else:
    logs_dir = os.path.join(os.getcwd(), "logs")
os.makedirs(logs_dir, exist_ok=True)

# Set up file handler for debug logging
file_handler = logging.FileHandler(os.path.join(logs_dir, "socketio.log"))
file_handler.setLevel(logging.DEBUG)
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
file_handler.setFormatter(formatter)
logger.addHandler(file_handler)

# Create a Socket.IO server
sio = socketio.AsyncServer(cors_allowed_origins='*')
app = web.Application()
sio.attach(app)

# Constants
SERVICE_TYPE = "_socketio._tcp.local."
SERVICE_NAME = "33terServer"
DEFAULT_ROOM = "33ter_room"

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
        logger.info(f"Using ADVERTISE_IP: {ip}")
        return ip
    run_mode = os.getenv("RUN_MODE", "local").lower()
    if run_mode == "docker":
        try:
            docker_host = socket.gethostbyname('host.docker.internal')
            logger.info(f"Running in Docker mode; using Docker host IP: {docker_host}")
            return docker_host
        except Exception as e:
            logger.error(f"Running in Docker mode but failed to get Docker host IP: {e}")
    fallback_ip = socket.gethostbyname(socket.gethostname())
    logger.info(f"Using local IP: {fallback_ip}")
    return fallback_ip

# Socket.IO Event Handlers
@sio.event
async def connect(sid, environ):
    """Handle client connection."""
    logger.info(f"Client connected: {sid}")
    connected_clients[sid] = {"rooms": []}
    await join_room(sid, {"room": DEFAULT_ROOM})

@sio.event
async def get_rooms(sid):
    """Return list of available rooms."""
    available_rooms = list(rooms.keys())
    await sio.emit("available_rooms", {"rooms": available_rooms}, room=sid)

@sio.event
async def join_room(sid, data):
    """Handle client joining a room."""
    room = data.get("room")
    if room:
        if room not in rooms:
            rooms[room] = {"clients": set(), "messages": []}
        await sio.enter_room(sid, room)
        connected_clients[sid]["rooms"].append(room)
        rooms[room]["clients"].add(sid)
        logger.info(f"Client {sid} joined room {room}")
        await sio.emit("room_joined", {
            "room": room,
            "client_count": len(rooms[room]["clients"])
        }, room=sid)
    else:
        logger.warning(f"Client {sid} attempted to join without room name")

@sio.event
async def disconnect(sid):
    """Handle client disconnection."""
    logger.info(f"Client disconnected: {sid}")
    if sid in connected_clients:
        for room in connected_clients[sid]["rooms"]:
            if room in rooms and sid in rooms[room]["clients"]:
                rooms[room]["clients"].remove(sid)
            await sio.leave_room(sid, room)
            logger.info(f"Client {sid} left room {room}")
        del connected_clients[sid]

@sio.event
async def room_message(sid, data):
    """Handle message sent to a room."""
    room = data.get("room")
    message_data = data.get("data")
    if room and message_data:
        title = message_data.get("title")
        message = message_data.get("message")
        log_type = message_data.get("logType", "info")
        logger.info(f"Message sent to room {room}")
        await sio.emit("room_message", {
            "data": {
                "title": title,
                "message": message,
                "logType": log_type
            }
        }, room=room)
    else:
        logger.warning(f"Invalid room message data")

async def broadcast_handler(request):
    """Handle broadcast requests from HTTP endpoint."""
    try:
        data = await request.json()
        room = data.get("room", DEFAULT_ROOM)
        message_data = data.get("data")
        
        if message_data:
            title = message_data.get("title")
            message = message_data.get("message")
            log_type = message_data.get("logType", "info")
            
            if message:
                logger.info(f"Broadcasting to room {room}")
                await sio.emit("room_message", {
                    "data": {
                        "title": title,
                        "message": message,
                        "logType": log_type
                    }
                }, room=room)
                return web.Response(text='Message broadcasted', status=200)
            else:
                logger.warning("No message provided")
                return web.Response(text='No message provided', status=400)
        else:
            logger.warning("No data provided")
            return web.Response(text='No data provided', status=400)
    except Exception as e:
        logger.error(f"Broadcast error: {e}")
        return web.Response(text='Internal server error', status=500)

async def health_handler(request):
    """Health check endpoint."""
    return web.Response(text='healthy', status=200)

# Server startup and configuration
def generate_server_config(ip, port, room):
    """Generate server configuration file."""
    run_mode = os.getenv("RUN_MODE", "local").lower()
    config_file = "/app/server_config.json" if run_mode == "docker" else os.path.join(os.getcwd(), "server_config.json")
    config = {
        "ip": ip,
        "port": port,
        "room": room
    }
    with open(config_file, "w") as f:
        json.dump(config, f, indent=4)
    logger.info(f"Generated server config at {config_file}")

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
    
    try:
        await site.start()
        logger.info(f"Socket.IO server started on port {port}")
        while True:
            await asyncio.sleep(3600)
    except Exception as e:
        logger.error(f"Server error: {e}")
        raise
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
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        sys.exit(1)