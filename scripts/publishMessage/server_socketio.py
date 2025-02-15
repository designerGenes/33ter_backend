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

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Determine logs directory based on RUN_MODE
run_mode = os.getenv("RUN_MODE", "local").lower()
if run_mode == "docker":
    logs_dir = "/app/logs"
else:
    logs_dir = os.path.join(os.getcwd(), "logs")
os.makedirs(logs_dir, exist_ok=True)
file_handler = logging.FileHandler(os.path.join(logs_dir, "socketio.log"))
file_handler.setLevel(logging.DEBUG)
logger.addHandler(file_handler)

# Create a Socket.IO server
sio = socketio.AsyncServer(cors_allowed_origins='*')  # Allow all origins for simplicity
app = web.Application()
sio.attach(app)

# Add constants after the existing imports
SERVICE_TYPE = "_socketio._tcp.local."
SERVICE_NAME = "33terServer"
DEFAULT_ROOM = "33ter_room"

# Modify get_local_ip to prefer non-loopback interfaces
def get_local_ip():
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

# Store connected clients and rooms
connected_clients = {}
rooms = {
    "33ter_room": {  # Default room
        "clients": set(),
        "messages": []
    }
}

# Event: Client connects
@sio.event
async def connect(sid, environ):
    logger.info(f"Client connected: {sid}")
    connected_clients[sid] = {"rooms": []}
    # Auto-join the default room
    await join_room(sid, {"room": "33ter_room"})

@sio.event
async def get_rooms(sid):
    """Return list of available rooms"""
    available_rooms = list(rooms.keys())
    await sio.emit("available_rooms", {"rooms": available_rooms}, room=sid)

# Event: Client joins a room
@sio.event
async def join_room(sid, data):
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
        logger.warning(f"Client {sid} attempted to join a room without specifying a room name")

# Event: Client disconnects
@sio.event
async def disconnect(sid):
    logger.info(f"Client disconnected: {sid}")
    if sid in connected_clients:
        for room in connected_clients[sid]["rooms"]:
            if room in rooms and sid in rooms[room]["clients"]:
                rooms[room]["clients"].remove(sid)
            await sio.leave_room(sid, room)
            logger.info(f"Client {sid} left room {room}")
        del connected_clients[sid]

# Event: Client sends a message to a room
@sio.event
async def room_message(sid, data):
    room = data.get("room")
    message_data = data.get("data")
    if room and message_data:
        title = message_data.get("title")
        message = message_data.get("message")
        log_type = message_data.get("logType", "prime")  # Default to "prime" if not specified
        logger.info(f"Client {sid} sent message to room {room}: {message} (logType: {log_type})")
        await sio.emit("room_message", {
            "data": {
                "title": title,
                "message": message,
                "logType": log_type
            }
        }, room=room)
    else:
        logger.warning(f"Client {sid} sent invalid room message: {data}")

# Broadcast server details using mDNS
async def broadcast_mdns(ip, port):
    run_mode = os.getenv("RUN_MODE", "local").lower()
    if run_mode == "local":
        logger.info("Skipping mDNS setup in local environment")
        return None, None
        
    try:
        host_ip = get_local_ip()
        
        # Enhanced service properties
        service_info = ServiceInfo(
            SERVICE_TYPE,
            f"{SERVICE_NAME}.{SERVICE_TYPE}",
            addresses=[socket.inet_aton(host_ip)],
            port=port,
            properties={
                'path': '/',
                'room': DEFAULT_ROOM,
                'server': 'socketio',
                'version': '1.0',
                'protocol': 'socketio',
                'host': host_ip
            },
            server=f"{SERVICE_NAME}.local."
        )
        
        # Initialize Zeroconf with error handling
        try:
            zeroconf = AsyncZeroconf(ip_version=IPVersion.V4Only)
            await zeroconf.async_register_service(service_info)
            logger.info(f"Successfully registered mDNS service: {SERVICE_NAME}")
            logger.info(f"Service details: {host_ip}:{port} ({SERVICE_TYPE})")
            return zeroconf, service_info
            
        except Exception as e:
            logger.error(f"Failed to register mDNS service: {e}")
            if zeroconf:
                await zeroconf.async_close()
            return None, None
            
    except Exception as e:
        logger.error(f"Failed to setup mDNS: {e}")
        return None, None

# Generate server_config.json
def generate_server_config(ip, port, room):
    run_mode = os.getenv("RUN_MODE", "local").lower()
    if run_mode == "docker":
        config_file = "/app/server_config.json"
    else:
        config_file = os.path.join(os.getcwd(), "server_config.json")
    config = {
        "ip": ip,
        "port": port,
        "room": room
    }
    with open(config_file, "w") as f:
        json.dump(config, f, indent=4)
    logger.info(f"Generated server_config.json at {config_file} with IP: {ip}, Port: {port}, Room: {room}")

async def health_handler(request):
    return web.Response(text='healthy', status=200)

# This is the most important part of the script
async def broadcast_handler(request):
    try:
        data = await request.json()
        room = data.get("room", "33ter_room")  # Default to 33ter_room if not specified
        message_data = data.get("data")
        
        if message_data:
            title = message_data.get("title")
            message = message_data.get("message")
            log_type = message_data.get("logType", "info")  # Default to "prime" if not specified
            
            if message:
                logger.info(f"Broadcasting message: {title}: {message} (logType: {log_type})")
                await sio.emit("room_message", {
                    "data": {
                        "title": title,
                        "message": message,
                        "logType": log_type
                    }
                }, room=room)
                return web.Response(text='Message broadcasted', status=200)
            else:
                logger.warning("Received broadcast request without a message")
                return web.Response(text='No message provided', status=400)
        else:
            logger.warning("Received broadcast request without data")
            return web.Response(text='No data provided', status=400)
    except Exception as e:
        logger.error(f"Error handling broadcast request: {e}")
        return web.Response(text='Internal server error', status=500)

# Run the server
async def start_server():
    run_mode = os.getenv("RUN_MODE", "local").lower()
    bind_ip = "0.0.0.0"  # Always bind to all interfaces to allow external connections
    port = 5348  # Fixed port for socket.io server
    
    # Add routes to the app
    app.router.add_get('/health', health_handler)
    app.router.add_post('/broadcast', broadcast_handler)

    # Get host IP for config and mDNS
    advertise_ip = get_local_ip()
    
    # Generate the server_config.json file with the host IP
    generate_server_config(advertise_ip, port, "33ter_room")

    # Broadcast server details using mDNS
    zeroconf, service_info = await broadcast_mdns(advertise_ip, port)

    # Define cleanup handler
    async def cleanup(app):
        if zeroconf and service_info:
            try:
                logger.info("Unregistering mDNS service...")
                await zeroconf.async_unregister_service(service_info)
                await zeroconf.async_close()
                logger.info("mDNS service unregistered")
            except Exception as e:
                logger.error(f"Error unregistering mDNS service: {e}")

    # Register cleanup handler before starting the server
    app.on_cleanup.append(cleanup)

    # Start the server bound to all interfaces
    logger.info(f"Starting Socket.IO server on {bind_ip}:{port}")
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, bind_ip, port)
    
    try:
        await site.start()
        while True:
            await asyncio.sleep(3600)
    except Exception as e:
        logger.error(f"Server error: {e}")
        raise
    finally:
        await runner.cleanup()

def find_and_kill_server():
    """Find and kill any running instances of this script"""
    current_pid = os.getpid()
    current_script = os.path.abspath(__file__)
    killed_count = 0
    
    for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
        try:
            # Check if this is a Python process
            if proc.info['name'] == 'python' or proc.info['name'] == 'python3':
                cmdline = proc.info['cmdline']
                if cmdline and current_script in cmdline:
                    # Don't kill ourselves
                    if proc.pid != current_pid:
                        logger.info(f"Killing server process: {proc.pid}")
                        proc.kill()
                        killed_count += 1
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            pass
    
    return killed_count

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Socket.IO Server')
    parser.add_argument('-k', '--kill', action='store_true', 
                       help='Kill any running instances of the server')
    parser.add_argument('--port', type=int, default=5348,
                       help='Port to run the server on')
    parser.add_argument('--room', type=str, default='33ter_room',
                       help='Default room name')
    args = parser.parse_args()

    if args.kill:
        killed = find_and_kill_server()
        logger.info(f"Killed {killed} server instance(s)")
        sys.exit(0)

    # Update port and room from arguments
    port = args.port
    DEFAULT_ROOM = args.room

    try:
        asyncio.run(start_server())
    except Exception as e:
        logger.error(f"Server error: {e}")
        sys.exit(1)