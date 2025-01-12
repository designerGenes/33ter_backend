import socketio
import asyncio
import logging
from aiohttp import web
import socket
from zeroconf import ServiceInfo, IPVersion
from zeroconf.asyncio import AsyncZeroconf
import json  # Add this import

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Create a Socket.IO server
sio = socketio.AsyncServer(cors_allowed_origins='*')  # Allow all origins for simplicity
app = web.Application()
sio.attach(app)

# Get the local IP address dynamically
def get_local_ip():
    try:
        # Create a socket to get the local IP address
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))  # Connect to a public DNS server
        local_ip = s.getsockname()[0]
        s.close()
        return local_ip
    except Exception as e:
        logger.error(f"Could not determine local IP address: {e}")
        return "0.0.0.0"  # Fallback to all interfaces

# Store connected clients and rooms
connected_clients = {}
rooms = {
    "chatRoom": {  # Default room
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
    await join_room(sid, {"room": "chatRoom"})

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
    message = data.get("message")
    if room and message:
        logger.info(f"Client {sid} sent message to room {room}: {message}")
        # Forward the message structure as-is
        await sio.emit("room_message", {"message": message}, room=room)
    else:
        logger.warning(f"Client {sid} sent invalid room message: {data}")

# Broadcast server details using mDNS
async def broadcast_mdns(ip, port):
    service_name = "SocketIO Server._socketio._tcp.local."
    service_info = ServiceInfo(
        "_socketio._tcp.local.",
        service_name,
        addresses=[socket.inet_aton(ip)],
        port=port,
        properties={"room": "chatRoom"},  # Optional: Include additional metadata
    )
    zeroconf = AsyncZeroconf(ip_version=IPVersion.V4Only)
    await zeroconf.async_register_service(service_info)
    logger.info(f"Broadcasting mDNS service: {service_name} at {ip}:{port}")
    return zeroconf, service_info  # Return both zeroconf and service_info

# Generate server_config.json
def generate_server_config(ip, port, room):
    config = {
        "ip": ip,
        "port": port,
        "room": room
    }
    with open("/app/server_config.json", "w") as f:
        json.dump(config, f, indent=4)
    logger.info(f"Generated server_config.json with IP: {ip}, Port: {port}, Room: {room}")

# Replace Flask-style route with aiohttp route
async def health_handler(request):
    return web.Response(text='healthy', status=200)

# Run the server
async def start_server():
    local_ip = get_local_ip()
    port = os.getenv("SOCKETIO_PORT", 5347)  # Default to 5347 if not set

    # Add routes to the app
    app.router.add_get('/health', health_handler)

    # Generate the server_config.json file
    generate_server_config(local_ip, port, "chatRoom")

    # Broadcast server details using mDNS
    zeroconf, service_info = await broadcast_mdns(local_ip, port)  # Unpack the returned values

    logger.info(f"Starting Socket.IO server on {local_ip}:{port}")
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, local_ip, port)
    await site.start()

    try:
        while True:
            await asyncio.sleep(3600)  # Keep the server running
    except asyncio.CancelledError:
        pass
    finally:
        # Clean up mDNS when the server stops
        await zeroconf.async_unregister_service(service_info)
        await zeroconf.async_close()

if __name__ == "__main__":
    try:
        asyncio.run(start_server())
    except Exception as e:
        logger.error(f"Server error: {e}")
        sys.exit(1)