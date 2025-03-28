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
import logging  # Move logging import earlier
import argparse
from datetime import datetime
import asyncio
import socketio
from aiohttp import web
import atexit
import copy  # For deep copies
import threading  # Import threading

# --- Early Logging Setup ---
# Basic config for messages before full setup
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
early_logger = logging.getLogger('33ter-SocketIO-Startup')
early_logger.info("Server script started.")
# --- End Early Logging Setup ---

# Add app root to Python path if needed
app_root = str(Path(__file__).parent.parent.absolute())
if app_root not in sys.path:
    early_logger.info(f"Adding {app_root} to PYTHONPATH")
    sys.path.insert(0, app_root)

try:
    # Load config utility FIRST
    from utils.server_config import get_server_config, update_server_config, save_server_config, DEFAULT_CONFIG
    from utils.path_config import get_logs_dir
    # Change relative import to absolute import
    from socketio_server.discovery_manager import DiscoveryManager
    from utils.network_utils import get_local_ip
except ImportError as e:
    early_logger.error(f"Failed to import dependencies: {e}", exc_info=True)
    sys.exit(1)

# --- Load Configuration EARLY ---
# Load the configuration immediately after imports
try:
    config = get_server_config()
    # Ensure critical keys exist using defaults if necessary after loading
    if 'server' not in config or not isinstance(config.get('server'), dict):
        early_logger.warning("Config missing 'server' section, restoring from defaults.")
        config['server'] = copy.deepcopy(DEFAULT_CONFIG['server'])
        save_server_config(config)  # Attempt to save corrected config
    if 'host' not in config['server']:
        early_logger.warning("Config missing 'host', restoring from default.")
        config['server']['host'] = DEFAULT_CONFIG['server']['host']
        save_server_config(config)
    if 'port' not in config['server']:
        early_logger.warning("Config missing 'port', restoring from default.")
        config['server']['port'] = DEFAULT_CONFIG['server']['port']
        save_server_config(config)
    if 'cors_origins' not in config['server']:
        early_logger.warning("Config missing 'cors_origins', restoring from default.")
        config['server']['cors_origins'] = DEFAULT_CONFIG['server']['cors_origins']
        save_server_config(config)

except Exception as config_load_error:
    early_logger.error(f"CRITICAL: Failed to load initial configuration: {config_load_error}", exc_info=True)
    early_logger.warning("Falling back to hardcoded default configuration for server startup.")
    config = copy.deepcopy(DEFAULT_CONFIG)  # Use defaults as a last resort

# --- Full Logging Setup ---
def setup_logging(log_level: str = "INFO"):
    """Configure logging with the specified level."""
    log_file = os.path.join(get_logs_dir(), "socketio_server.log")
    # Use level from loaded config if available, otherwise use the function arg
    effective_log_level_str = config.get('server', {}).get('log_level', log_level).upper()
    log_level_enum = getattr(logging, effective_log_level_str, logging.INFO)

    # Remove basicConfig handlers if they exist
    for handler in logging.root.handlers[:]:
        logging.root.removeHandler(handler)

    # Ensure log directory exists before creating FileHandler
    try:
        os.makedirs(os.path.dirname(log_file), exist_ok=True)
    except OSError as e:
        early_logger.error(f"Failed to create log directory {os.path.dirname(log_file)}: {e}")
        pass

    log_handlers = [logging.StreamHandler(sys.stdout)]
    try:
        log_handlers.append(logging.FileHandler(log_file))
    except Exception as e:
        early_logger.error(f"Failed to create FileHandler for {log_file}: {e}. File logging disabled.")

    logging.basicConfig(
        level=log_level_enum,  # Use the determined level
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=log_handlers,
        force=True  # Try forcing reconfiguration
    )
    logging.getLogger('engineio.server').setLevel(logging.WARNING)
    logging.getLogger('socketio.server').setLevel(logging.WARNING)
    logging.getLogger('aiohttp.access').setLevel(logging.WARNING)

    logger_instance = logging.getLogger('33ter-SocketIO')
    logger_instance.propagate = False
    return logger_instance
# --- End Full Logging Setup ---

# --- Initialize Logger ---
# Initialize after loading config and setting up logging function
logger = setup_logging(config.get('server', {}).get('log_level', 'INFO'))

# --- Socket.IO Server Setup ---
# Use the 'config' loaded earlier
cors_origins = config.get('server', {}).get('cors_origins', DEFAULT_CONFIG['server']['cors_origins'])
logger.info(f"Initializing Socket.IO server with CORS origins: {cors_origins}")
sio = socketio.AsyncServer(
    async_mode='aiohttp',
    cors_allowed_origins=cors_origins,  # Use the loaded origins
    logger=False,  # Use our own logger
    engineio_logger=False  # Use our own logger
)
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
    await sio.enter_room(sid, room)
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
        logger.error(f"Invalid leave_room data from {sid}: {data}")  # Log invalid data
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
        if not isinstance(data, list) or not data or not isinstance(data[0], dict):
            logger.error(f"Invalid ocr_result data format received from {sid}: {data}")
            return

        ocr_data = data[0]
        text = ocr_data.get('text', '')
        timestamp = ocr_data.get('timestamp', datetime.now().isoformat())

        payload = {
            'text': text,
            'timestamp': timestamp,
            'from': 'localBackend'
        }

        await sio.emit('ocr_result', payload, room=current_room)
        logger.info(f"Broadcast 'ocr_result' event successful to room {current_room}: {len(text)} chars")

    except Exception as e:
        logger.error(f"Error broadcasting OCR result event: {e}", exc_info=True)
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

# --- Health Check ---
async def health_check():
    """Periodic health check and status broadcast."""
    # Use loaded config
    health_config = config.get('health_check', DEFAULT_CONFIG['health_check'])
    if not health_config.get('enabled', False):
        logger.info("Health check disabled in configuration.")
        return

    interval = health_config.get('interval', 30)
    logger.info(f"Health check enabled with interval: {interval}s")

    while True:
        if current_room:
            try:
                await broadcast_client_count()
            except Exception as e:
                logger.error(f"Health check broadcast failed: {e}")
        await asyncio.sleep(interval)

# --- Argument Parsing ---
def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description='33ter Socket.IO Server')
    # Use defaults directly from the *already loaded* config dictionary
    server_cfg = config.get('server', DEFAULT_CONFIG['server'])  # Safely get server config

    parser.add_argument('--host',
                        default=server_cfg.get('host', DEFAULT_CONFIG['server']['host']),
                        help='Host to bind to')
    parser.add_argument('--port',
                        type=int,
                        default=server_cfg.get('port', DEFAULT_CONFIG['server']['port']),
                        help='Port to listen on')
    parser.add_argument('--room',
                        default=server_cfg.get('room', DEFAULT_CONFIG['server']['room']),
                        help='Default room name')
    parser.add_argument('--log-level',
                        default=server_cfg.get('log_level', DEFAULT_CONFIG['server']['log_level']),
                        choices=['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'],  # Add CRITICAL
                        help='Logging level')
    return parser.parse_args()

# --- Application Initialization ---
async def init_app():
    """Initialize the application."""
    global config  # Declare config as global at the function scope
    global logger  # Declare logger as global if it might be reassigned

    args = parse_args()  # Parse args using loaded config defaults

    # Update config based on command-line args ONLY if they differ from loaded config
    server_updates = {}
    # Safely access nested keys, providing empty dict as default
    current_server_config = config.get('server', {})
    if args.host != current_server_config.get('host'):
        server_updates['host'] = args.host
    if args.port != current_server_config.get('port'):
        server_updates['port'] = args.port
    if args.room != current_server_config.get('room'):
        server_updates['room'] = args.room
    if args.log_level != current_server_config.get('log_level'):
        server_updates['log_level'] = args.log_level

    if server_updates:
        logger.info(f"Updating server config with command-line arguments: {server_updates}")
        # Use the update function which handles saving
        # config is already declared global, so we just assign to it
        config = update_server_config({'server': server_updates})
        # Re-setup logging if level changed
        if 'log_level' in server_updates:
            logger.info(f"Log level changed to {args.log_level}, reconfiguring logger.")
            # logger is already declared global, so we just assign to it
            logger = setup_logging(args.log_level)
            # Ensure the logger instance level is also updated
            try:
                logger.setLevel(getattr(logging, args.log_level.upper()))
                logger.info(f"Logger level set to {args.log_level}")
            except Exception as e:
                 logger.error(f"Failed to set logger level after update: {e}")


    # Use the potentially updated config for health check check
    # Safely access nested keys
    health_cfg = config.get('health_check', DEFAULT_CONFIG['health_check'])
    if health_cfg.get('enabled'):
        logger.info("Creating health check task.")
        asyncio.create_task(health_check())
    else:
        logger.info("Health check disabled.")

    # Return the host/port that will actually be used
    # Safely access nested keys
    final_host = config.get('server', {}).get('host', DEFAULT_CONFIG['server']['host'])
    final_port = config.get('server', {}).get('port', DEFAULT_CONFIG['server']['port'])
    return final_host, final_port

# --- Main Execution ---
def main():
    """Main entry point."""
    loop = None  # Initialize loop variable
    runner = None  # Initialize runner variable
    site = None  # Initialize site variable
    try:
        # Get or create an event loop for the main thread
        try:
            # Try getting the loop associated with the current OS thread
            loop = asyncio.get_event_loop_policy().get_event_loop()
            if loop.is_running():
                logger.warning("Event loop is already running in main thread. Attempting to use it.")
            else:
                logger.info("Using existing event loop for main thread.")
        except RuntimeError:
            logger.info("Creating new event loop for main thread.")
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        # Run init_app within the managed loop
        host, port = loop.run_until_complete(init_app())
        logger.info(f"Configuration loaded. Preparing to run server on {host}:{port}")

        # Bonjour/Zeroconf setup
        # Initialize DiscoveryManager here if needed, or ensure it's handled elsewhere
        global discovery_manager
        try:
            discovery_manager = DiscoveryManager()
            logger.info("DiscoveryManager initialized.")
        except Exception as disc_err:
            logger.error(f"Failed to initialize DiscoveryManager: {disc_err}", exc_info=True)
            discovery_manager = None  # Ensure it's None if init fails

        local_ip = get_local_ip()
        if discovery_manager and local_ip:
            service_name = f"33ter Backend ({local_ip}:{port})"
            logger.info(f"Starting Bonjour discovery service: {service_name}")
            # Assuming start_discovery is synchronous or handled internally
            discovery_manager.start_discovery(port=port, service_name=service_name)
        elif not local_ip:
            logger.warning("Could not determine local IP for Bonjour registration or logging.")

        # Setup and run the web server
        logger.info("Setting up AIOHTTP AppRunner...")
        runner = web.AppRunner(app)
        loop.run_until_complete(runner.setup())
        logger.info("AppRunner setup complete.")
        site = web.TCPSite(runner, host, port)
        loop.run_until_complete(site.start())
        logger.info(f"TCPSite started on http://{host}:{port}")

        startup_msg = f"Running on http://{host}:{port}"
        logger.info(f"SERVER IS LIVE: {startup_msg}")
        print(startup_msg, flush=True)  # Print startup message for ProcessManager

        logger.info("Entering main event loop (run_forever).")
        loop.run_forever()  # This blocks until loop.stop() is called

    except KeyboardInterrupt:
        logger.info("KeyboardInterrupt received, shutting down.")
    except Exception as e:
        logger.critical(f"Unhandled exception in main execution: {e}", exc_info=True)
    finally:
        logger.info("Starting server shutdown sequence.")

        # --- Graceful Shutdown ---
        # Use the loop variable captured in the try block
        if loop and loop.is_running():
            logger.info("Event loop is running, attempting graceful shutdown.")
            # Schedule cleanup tasks to run on the loop
            async def shutdown_tasks():
                nonlocal site, runner  # Allow modification of outer scope variables if needed
                if site:
                    logger.info("Stopping TCPSite...")
                    await site.stop()
                    logger.info("TCPSite stopped.")
                if runner:
                    logger.info("Cleaning up AppRunner...")
                    await runner.cleanup()
                    logger.info("AppRunner cleaned up.")
                # Cancel other pending tasks (excluding self)
                tasks = [t for t in asyncio.all_tasks(loop) if t is not asyncio.current_task(loop)]
                if tasks:
                    logger.info(f"Cancelling {len(tasks)} outstanding tasks.")
                    [task.cancel() for task in tasks]
                    await asyncio.gather(*tasks, return_exceptions=True)
                    logger.info("Outstanding tasks cancelled.")

            # Run the shutdown tasks and then stop the loop
            loop.run_until_complete(shutdown_tasks())
            loop.stop()
            logger.info("Event loop stopped.")

        elif loop and not loop.is_running():
            logger.info("Event loop was found but is not running. Minimal cleanup.")
            # Perform non-async cleanup if needed
            if discovery_manager:
                logger.info("Stopping Bonjour discovery (non-async).")
                discovery_manager.stop_discovery()
        else:
            logger.info("No running event loop found. Minimal cleanup.")
            # Perform non-async cleanup if needed
            if discovery_manager:
                logger.info("Stopping Bonjour discovery (non-async).")
                discovery_manager.stop_discovery()

        logger.info("Server shutdown sequence complete.")

    return 0

if __name__ == '__main__':
    # Ensure logs directory exists before anything else
    try:
        os.makedirs(get_logs_dir(), exist_ok=True)
    except Exception as e:
        print(f"CRITICAL: Failed to create logs directory {get_logs_dir()}: {e}", file=sys.stderr)

    sys.exit(main())