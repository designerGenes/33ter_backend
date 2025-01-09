import socketio
import eventlet
import logging
from flask import Flask
import socket
from dotenv import load_dotenv

load_dotenv(dotenv_path="../.env")

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Create a Socket.IO server
sio = socketio.Server(cors_allowed_origins='*')  # Allow all origins for simplicity
app = Flask(__name__)
app.wsgi_app = socketio.WSGIApp(sio, app.wsgi_app)

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
        return "127.0.0.1"  # Fallback to localhost

# Store connected clients and rooms
connected_clients = {}
rooms = {}

# Event: Client connects
@sio.event
def connect(sid, environ):
    logger.info(f"Client connected: {sid}")
    connected_clients[sid] = {"rooms": []}

# Event: Client disconnects
@sio.event
def disconnect(sid):
    logger.info(f"Client disconnected: {sid}")
    if sid in connected_clients:
        for room in connected_clients[sid]["rooms"]:
            sio.leave_room(sid, room)
            logger.info(f"Client {sid} left room {room}")
        del connected_clients[sid]

# Event: Client joins a room
@sio.event
def join_room(sid, data):
    room = data.get("room")
    if room:
        sio.enter_room(sid, room)
        connected_clients[sid]["rooms"].append(room)
        logger.info(f"Client {sid} joined room {room}")
        sio.emit("room_joined", {"room": room}, room=sid)  # Notify the client
    else:
        logger.warning(f"Client {sid} attempted to join a room without specifying a room name")

# Event: Client sends a message to a room
@sio.event
def room_message(sid, data):
    room = data.get("room")
    message = data.get("message")
    if room and message:
        logger.info(f"Client {sid} sent message to room {room}: {message}")
        sio.emit("room_message", {"message": message}, room=room)  # Broadcast to the room
    else:
        logger.warning(f"Client {sid} sent invalid room message: {data}")

# Run the server
if __name__ == "__main__":
    local_ip = get_local_ip()
    port = 3003  # Default port
    logger.info(f"Starting Socket.IO server on {local_ip}:{port}")
    eventlet.wsgi.server(eventlet.listen((local_ip, port)), app)