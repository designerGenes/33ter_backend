#!/usr/bin/env python3
"""Threethreeter Socket.IO Server

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
import sys
from pathlib import Path
import logging  # Move logging import earlier
import argparse
from datetime import datetime
import asyncio
import socketio
from aiohttp import web
import atexit
from typing import Dict, Optional, Any

# Ensure the project root is in the Python path
project_root = Path(__file__).resolve().parents[1]
if str(project_root) not in sys.path:
    sys.path.append(str(project_root))

# Import local modules using absolute paths from the package root (Threethreeter)
from Threethreeter.config_loader import config as config_manager
from Threethreeter.message_utils import (
    create_socket_message, create_client_count_message,
    create_welcome_message, create_join_leave_message, MessageType
)
from Threethreeter.event_utils import EventType
from Threethreeter.discovery_manager import DiscoveryManager

# --- Globals ---
config_data = config_manager.config  # Get the loaded config dictionary
logger = logging.getLogger(__name__)  # Get logger instance, assumes setup elsewhere
sio = socketio.AsyncServer(async_mode='aiohttp', cors_allowed_origins='*')
app = web.Application()
sio.attach(app)

# Client tracking
connected_clients: Dict[str, Dict[str, Any]] = {}
current_room: Optional[str] = config_manager.get('server', 'room', default='Threethreeter_room')
internal_client_sid: Optional[str] = None

# Health check related
health_check_task: Optional[asyncio.Task] = None
# Use a dedicated config key or default for health check interval
health_check_interval = config_manager.get('server', 'health_check_interval', default=30) # Example: Check every 30s

# Discovery Manager Instance
discovery_manager: Optional[DiscoveryManager] = None

# --- Utility Functions ---

async def emit_client_count_update():
    """Emits an event with the current client count."""
    # Exclude internal client from count if desired, or count all connections
    # Counting only non-internal clients for iOS count:
    ios_client_count = sum(1 for sid, info in connected_clients.items() if info.get('client_type') != 'Internal')
    # Or count all clients: ios_client_count = len(connected_clients)

    count_payload = {"count": ios_client_count}
    logger.info(f"Emitting {EventType.UPDATED_CLIENT_COUNT.value} event with payload: {count_payload}")
    await sio.emit(EventType.UPDATED_CLIENT_COUNT.value, count_payload, room=current_room)

# --- EVENTS ---
@sio.on('*')
async def any_event(event, sid, data):
    """Catch-all handler to log any event received by the server."""
    # Avoid logging excessively for built-in connect/disconnect
    if event not in ['connect', 'disconnect']:
        logger.info(f"SERVER_ANY_EVENT: Received event '{event}' from SID {sid}. Data: {data}")
        sys.stdout.flush() # Explicitly flush stdout


@sio.event
async def connect(sid: str, environ: Dict, auth: Optional[Dict] = None):
    """Handle new client connections."""
    client_ip = environ.get('REMOTE_ADDR', 'Unknown IP')
    # Log connection attempt *before* processing
    logger.info(f"Connection attempt received from SID: {sid}, IP: {client_ip}")
    # Infer client type from auth or headers (example)
    client_type = 'Unknown'
    if auth and 'client_type' in auth:
        client_type = auth['client_type']
    elif 'HTTP_USER_AGENT' in environ:
        if 'Python/Threethreeter-Client' in environ['HTTP_USER_AGENT']:
            client_type = 'Internal' # Identify internal client by User-Agent
        elif 'iOS' in environ['HTTP_USER_AGENT']: # Example heuristic
             client_type = 'iOS'

    connect_time = datetime.now().isoformat()
    connected_clients[sid] = {
        "address": client_ip,
        "connect_time": connect_time,
        "client_type": client_type
    }

    # --- Log before sending welcome message TO ROOM ---
    welcome_msg = create_welcome_message(sid)
    logger.info(f"SERVER_EMIT_DEBUG: Attempting to emit welcome message to room {current_room}: {welcome_msg}")
    # Emit as a 'message' event to the room instead of sending privately
    await sio.emit('message', welcome_msg, room=current_room)
    logger.info(f"SERVER_EMIT_DEBUG: Welcome message emitted to room {current_room}.")
    # --- End log ---

    # Emit connection event to the room
    connect_event_payload = {
        "sid": sid,
        "address": client_ip,
        "client_type": client_type,
        "connect_time": connect_time
    }
    await sio.emit(EventType.CLIENT_CONNECTED.value, connect_event_payload, room=current_room)

    # Automatically join the default room and emit events
    if current_room:
        await sio.enter_room(sid, current_room)
        logger.info(f"Client {sid} automatically joined room: {current_room}")

        # Send join confirmation message TO ROOM
        join_confirm_msg = create_join_leave_message(sid, current_room, joined=True)
        # --- Log before emitting join confirmation TO ROOM ---
        logger.info(f"SERVER_EMIT_DEBUG: Attempting to emit join confirmation to room {current_room}: {join_confirm_msg}")
        # Emit as a 'message' event to the room instead of sending privately
        await sio.emit('message', join_confirm_msg, room=current_room)
        logger.info(f"SERVER_EMIT_DEBUG: Join confirmation emitted to room {current_room}.")
        # --- End log ---

        # Emit joined room event
        join_event_payload = {"sid": sid, "room": current_room}
        await sio.emit(EventType.CLIENT_JOINED_ROOM.value, join_event_payload, room=current_room)
    else:
        logger.warning(f"No default room configured for client {sid} to join.")

    # Emit updated client count event
    await emit_client_count_update()

    # If the connecting client is identified as Internal, register it
    if client_type == 'Internal':
        await register_internal_client(sid, {}) # Call registration logic


@sio.event
async def disconnect(sid: str):
    """Handle client disconnections."""
    if sid in connected_clients:
        client_info = connected_clients.pop(sid)
        logger.info(f"Client disconnected: {sid} ({client_info.get('address', 'Unknown IP')}) - Type: {client_info.get('client_type')}")

        # Emit disconnect event
        disconnect_event_payload = {"sid": sid, "client_type": client_info.get('client_type')}
        await sio.emit(EventType.CLIENT_DISCONNECTED.value, disconnect_event_payload, room=current_room)

        # If the internal client disconnects, clear its SID
        global internal_client_sid
        if sid == internal_client_sid:
            logger.warning("Internal macOS client disconnected.")
            internal_client_sid = None

        # Leave the known default room if it exists (Socket.IO might handle this automatically, but explicit is okay)
        # No need to emit CLIENT_LEFT_ROOM here, disconnect implies leaving all rooms.

        # Emit updated client count event
        await emit_client_count_update()
    else:
        logger.warning(f"Disconnect event received for unknown SID: {sid}")

@sio.event
async def join_room(sid, data):
    """Handle explicit room join requests (if needed beyond auto-join)."""
    room_name = data.get('room')
    if not room_name:
        # Send private error message
        error_message = create_socket_message(MessageType.ERROR, "Room name is required.", sender="localBackend", target_sid=sid)
        await sio.emit('message', error_message, room=sid)
        return

    await sio.enter_room(sid, room_name)
    logger.info(f"Client {sid} joined room: {room_name}")

    # Emit join confirmation message TO ROOM
    join_confirm_msg = create_join_leave_message(sid, room_name, joined=True)
    # --- Log before emitting join confirmation TO ROOM ---
    logger.info(f"SERVER_EMIT_DEBUG: Attempting to emit join confirmation to room {current_room}: {join_confirm_msg}")
    # Emit as a 'message' event to the room instead of sending privately
    await sio.emit('message', join_confirm_msg, room=current_room)
    logger.info(f"SERVER_EMIT_DEBUG: Join confirmation emitted to room {current_room}.")
    # --- End log ---

    # Emit joined room event
    join_event_payload = {"sid": sid, "room": room_name}
    await sio.emit(EventType.CLIENT_JOINED_ROOM.value, join_event_payload, room=current_room) # Emit to main room

    # Emit updated client count event (if joining affects the count logic)
    await emit_client_count_update()


@sio.event
async def leave_room(sid, data):
    """Handle explicit room leave requests."""
    room_name = data.get('room')
    if not room_name:
        # Send private error message
        error_message = create_socket_message(MessageType.ERROR, "Room name is required.", sender="localBackend", target_sid=sid)
        await sio.emit('message', error_message, room=sid)
        return

    if room_name in sio.rooms(sid):
        await sio.leave_room(sid, room_name)
        logger.info(f"Client {sid} left room: {room_name}")
        
        # Emit leave confirmation message TO ROOM
        leave_confirm_msg = create_join_leave_message(sid, room_name, joined=False)
        # --- Log before emitting leave confirmation TO ROOM ---
        logger.info(f"SERVER_EMIT_DEBUG: Attempting to emit leave confirmation to room {current_room}: {leave_confirm_msg}")
        # Emit as a 'message' event to the room instead of sending privately
        await sio.emit('message', leave_confirm_msg, room=current_room)
        logger.info(f"SERVER_EMIT_DEBUG: Leave confirmation emitted to room {current_room}.")
        # --- End log ---

        # Emit left room event
        leave_event_payload = {"sid": sid, "room": room_name}
        await sio.emit(EventType.CLIENT_LEFT_ROOM.value, leave_event_payload, room=current_room) # Emit to main room

        # Emit updated client count event (if leaving affects the count logic)
        await emit_client_count_update()
    else:
        logger.warning(f"Client {sid} tried to leave room '{room_name}' but was not in it.")
        
        # Emit warning message TO ROOM
        warning_message = create_socket_message(MessageType.WARNING, f"Client {sid} tried to leave room '{room_name}' but was not in it.", sender="localBackend")
        # --- Log before emitting leave warning TO ROOM ---
        logger.info(f"SERVER_EMIT_DEBUG: Attempting to emit leave warning to room {current_room}: {warning_message}")
        # Emit as a 'message' event to the room instead of sending privately
        await sio.emit('message', warning_message, room=current_room)
        logger.info(f"SERVER_EMIT_DEBUG: Leave warning emitted to room {current_room}.")
        # --- End log ---

# Explicitly handle the event named 'message'
@sio.on('message')
async def handle_default_message(sid, data):
    """Handle generic messages sent with the default 'message' event.
    Acts on trigger_ocr, otherwise rebroadcasts to the room.
    Uses logger for output.
    """
    # Use INFO level for initial reception log
    logger.info(f"Received generic 'message' event from {sid}. Data: {data}")
    sys.stdout.flush() # Explicitly flush stdout
    msg_type = data.get('messageType')

    # Handle trigger_ocr message type within the generic message handler
    if msg_type and msg_type.lower() == "trigger_ocr":
        logger.info(f"Received 'trigger_ocr' messageType via generic message event from {sid}")
        sys.stdout.flush() # Explicitly flush stdout
        # Ensure handle_ocr_trigger exists and is called correctly
        if 'handle_ocr_trigger' in globals() and callable(globals()['handle_ocr_trigger']):
             await handle_ocr_trigger(sid)
        else:
             # Use ERROR level for errors
             logger.error(f"handle_ocr_trigger function not found or not callable when processing trigger_ocr message from {sid}")
             sys.stderr.flush() # Explicitly flush stderr
        return # Stop processing here for trigger_ocr

    # --- ADD REBROADCAST LOGIC --- 
    # For any other message type received via the default 'message' event,
    # rebroadcast it to the room, skipping the original sender.
    logger.info(f"Rebroadcasting generic message from {sid} (Type: '{msg_type}') to room {current_room}.")
    sys.stdout.flush()
    try:
        # --- Log before rebroadcasting message ---
        logger.info(f"SERVER_EMIT_DEBUG: Attempting to rebroadcast message to room {current_room} (skip {sid}): {data}")
        await sio.emit('message', data, room=current_room, skip_sid=sid)
        logger.info(f"SERVER_EMIT_DEBUG: Message rebroadcast complete to room {current_room}.")
        sys.stdout.flush()
        # --- End log ---
    except Exception as e:
        logger.error(f"Error rebroadcasting message from {sid}: {e}", exc_info=True)
        sys.stderr.flush()
    # --- END REBROADCAST LOGIC ---

@sio.event
async def register_internal_client(sid: str, data: Optional[Dict] = None):
    """Allows the macOS agent to identify itself as the internal client."""
    global internal_client_sid
    previous_internal_sid = internal_client_sid

    if internal_client_sid and internal_client_sid != sid:
        logger.warning(f"Another internal client {sid} tried to register while {previous_internal_sid} is active. Overwriting.")
    elif not internal_client_sid:
         logger.info(f"Internal macOS client registered with SID: {sid}")
    # Else: Re-registering the same client, which is fine.

    internal_client_sid = sid
    if sid in connected_clients:
        connected_clients[sid]['client_type'] = 'Internal' # Ensure type is set

    # Send private confirmation message
    confirm_message = create_socket_message(MessageType.INFO, "Internal client registration confirmed.", sender="localBackend", target_sid=sid)
    await sio.emit('message', confirm_message, room=sid)

    # Ensure the client is in the main room (should be from connect handler, but belt-and-suspenders)
    if current_room and current_room not in sio.rooms(sid):
        await sio.enter_room(sid, current_room)
        logger.debug(f"Ensured internal client {sid} is in room {current_room}")
        # Emit joined room event if it wasn't already in
        join_event_payload = {"sid": sid, "room": current_room}
        await sio.emit(EventType.CLIENT_JOINED_ROOM.value, join_event_payload, room=current_room)
        await emit_client_count_update() # Update count if type changed or room joined

# Renamed from trigger_ocr to handle the message type
@sio.on(MessageType.TRIGGER_OCR.value)
async def on_trigger_ocr_message(sid: str, data: Any): # Add data parameter
    # Log both the library-provided SID and the received data
    logger.info(f"Received '{MessageType.TRIGGER_OCR.value}' message from client SID: {sid}. Data received: {data}")
    
    # Use the library-provided SID as the requester ID
    requester_sid = sid 
    logger.info(f"Handling OCR trigger for requester_sid: {requester_sid}")
    
    # Emit event indicating processing has started
    start_event_payload = {"requester_sid": requester_sid}
    await sio.emit(EventType.OCR_PROCESSING_STARTED.value, start_event_payload, room=current_room)

    # Check if internal client is connected and ready
    if internal_client_sid and internal_client_sid in connected_clients:
        logger.info(f"Forwarding OCR request directly to internal client: {internal_client_sid}")
        # Send targeted message to internal client SID
        request_payload = {"requester_sid": requester_sid} # Pass original requester SID
        # Emit directly to the internal client's SID, not the room
        await sio.emit(MessageType.PERFORM_OCR_REQUEST.value, request_payload, room=internal_client_sid)
        return True
    else:
        logger.warning(f"Cannot process OCR trigger from {requester_sid}: Internal client not registered or connected.")
        # Send error message TO ROOM
        error_message = create_socket_message(
            MessageType.ERROR,
            f"Cannot process OCR trigger from {requester_sid}: Internal processing client not available.", # Include requester SID in message
            sender="localBackend"
            # Removed target_sid
        )
        # --- Log before emitting error message TO ROOM ---
        logger.info(f"SERVER_EMIT_DEBUG: Attempting to emit error message to room {current_room}: {error_message}")
        await sio.emit('message', error_message, room=current_room)
        logger.info(f"SERVER_EMIT_DEBUG: Error message emitted to room {current_room}.")
        # --- End log ---
        return False


# Handler for results coming FROM the internal client
@sio.on(MessageType.OCR_RESULT.value)
async def on_internal_ocr_result(sid, data):
    """Handles OCR_RESULT message FROM the internal client."""
    if sid != internal_client_sid:
        logger.warning(f"Received '{MessageType.OCR_RESULT.value}' from non-internal client {sid}. Ignoring.")
        return

    original_requester_sid = data.get('requester_sid')
    ocr_text = data.get('text')
    # logger.info(f"Received OCR result from internal client for requester {original_requester_sid}.")

    if ocr_text is None:
        logger.error(f"Invalid OCR result payload from internal client: {data}")
        # Optionally notify the internal client?
        return

    # Emit completion event (success)
    completion_payload = {"requester_sid": original_requester_sid, "success": True}
    await sio.emit(EventType.OCR_PROCESSING_COMPLETED.value, completion_payload, room=current_room)

    # Emit processed screenshot event with preview
    preview = (ocr_text[:50] + '...') if len(ocr_text) > 50 else ocr_text
    processed_payload = {"success": True, "text_preview": preview}
    await sio.emit(EventType.PROCESSED_SCREENSHOT.value, processed_payload, room=current_room)

    # Send a formatted ocr_result message to the chat room
    room_ocr_result = {
        "messageType": "ocr_result",
        "value": ocr_text,
        "from": "localBackend"
    }
    logger.info(f"Broadcasting OCR result to room {current_room}")
    # --- Log before emitting OCR result to room ---
    logger.info(f"SERVER_EMIT_DEBUG: Attempting to emit OCR result message to room {current_room}: {room_ocr_result}")
    await sio.emit('message', room_ocr_result, room=current_room)
    logger.info(f"SERVER_EMIT_DEBUG: OCR result message emitted to room {current_room}.")
    # --- End log ---

# --- Health Check / Periodic Tasks ---
async def periodic_tasks():
    """Run periodic tasks like broadcasting client count."""
    while True:
        await asyncio.sleep(health_check_interval) # Use configured interval
        if current_room:
            try:
                # Send CLIENT_COUNT message
                ios_client_count = sum(1 for sid, info in connected_clients.items() if info.get('client_type') != 'Internal')
                count_message = create_client_count_message(ios_client_count)
                logger.info(f"Sending periodic client count message: {count_message}")
                await sio.emit('message', count_message, room=current_room)

                # Log general status
                logger.info(f"Periodic check: Connected clients ({len(connected_clients)}): {list(connected_clients.keys())}")
                logger.info(f"Internal client SID: {internal_client_sid}")

            except Exception as e:
                logger.error(f"Error during periodic tasks: {e}", exc_info=True)
        else:
            logger.warning("Periodic tasks skipped: No current_room configured.")


# --- Argument Parsing ---
def parse_args():
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description="Threethreeter Socket.IO Server")
    parser.add_argument('--host', type=str, default=config_manager.get('server', 'host', default='0.0.0.0'),
                        help='Host IP address to bind the server to.')
    parser.add_argument('--port', type=int, default=config_manager.get('server', 'port', default=5348),
                        help='Port number to bind the server to.')
    return parser.parse_args()

# --- Server Lifecycle ---

async def start_server(host: str, port: int):
    """Starts the Socket.IO server and related tasks."""
    global health_check_task, discovery_manager
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host, port)

    logger.info(f"Attempting to start Socket.IO server on {host}:{port}")
    try:
        await site.start()
        # Log *after* successful start
        logger.info(f"✅ Socket.IO server successfully listening on {host}:{port}")
        logger.info(f"   Default room: {current_room}")
    except Exception as e:
        logger.critical(f"❌ Failed to start web server on {host}:{port}: {e}", exc_info=True)
        # Optionally re-raise or handle differently
        raise

    # Emit SERVER_STARTED event
    if current_room:
        await sio.emit(EventType.SERVER_STARTED.value, {}, room=current_room)

    # Start periodic tasks
    health_check_task = asyncio.create_task(periodic_tasks())
    logger.info(f"Periodic tasks started with interval: {health_check_interval}s")

    # Start Bonjour/Zeroconf discovery (now async)
    logger.info("Initializing and starting Bonjour discovery...")
    discovery_manager = DiscoveryManager(logger)
    await discovery_manager.start_discovery(port=port) # <-- Await the async call

    # Keep server running
    logger.info("Server startup complete. Waiting for connections...")
    await asyncio.Event().wait()


async def stop_server():
    """Stops the Socket.IO server and cleans up."""
    logger.info("Stopping Socket.IO server...")
    if health_check_task and not health_check_task.done():
        health_check_task.cancel()
        try:
            await health_check_task
        except asyncio.CancelledError:
            logger.info("Periodic tasks task cancelled.")

    # Stop Bonjour discovery (now async)
    if discovery_manager:
        logger.info("Stopping Bonjour discovery...")
        await discovery_manager.stop_discovery() # <-- Await the async call
        logger.info("Bonjour discovery stopped.")

    # Add any other specific cleanup needed for sio or app
    # await app.shutdown() # Example if needed
    # await app.cleanup()  # Example if needed
    # await sio.shutdown() # Example if needed

def cleanup_on_exit():
    """Perform cleanup actions when the server exits."""
    logger.info("Performing cleanup on exit...")
    # Discovery manager cleanup is handled by its own atexit registration
    # or the explicit call in stop_server if the loop is running.

atexit.register(cleanup_on_exit)

# --- Main Execution ---

if __name__ == '__main__':
    args = parse_args()
    # Setup basic logging if running standalone
    if not logging.getLogger().hasHandlers():
         # Explicitly set the stream to sys.stdout
         logging.basicConfig(level=logging.INFO,
                             format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                             stream=sys.stdout)

    try:
        asyncio.run(start_server(args.host, args.port))
    except KeyboardInterrupt:
        logger.info("Server stopped by user (KeyboardInterrupt).")
    except Exception as e:
        logger.critical(f"Server encountered critical error: {e}", exc_info=True)
    finally:
        # Ensure stop_server is called if asyncio loop is available
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                loop.run_until_complete(stop_server())
            else:
                # Fallback if loop already stopped or not running
                logger.info("Asyncio loop not running, skipping async stop_server.")
        except Exception as e:
            logger.error(f"Error during final cleanup: {e}")

        logger.info("Server shutdown complete.")