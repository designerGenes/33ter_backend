#!/bin/bash

# Define colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Default port
DEFAULT_PORT=5348
DEFAULT_ROOM="33ter_room"

# Parse command line arguments
port=$DEFAULT_PORT
room=$DEFAULT_ROOM
debug=false

print_help() {
    echo "33ter Startup Script"
    echo
    echo "Usage: $0 [options]"
    echo
    echo "Options:"
    echo "  -p, --port PORT       Socket.IO server port (default: $DEFAULT_PORT)"
    echo "  -r, --room ROOM       Socket.IO room name (default: $DEFAULT_ROOM)"
    echo "  -d, --debug           Enable debug mode (more verbose logging)"
    echo "  -h, --help            Show this help message"
    echo
}

while [[ $# -gt 0 ]]; do
    key="$1"
    case $key in
        -p|--port)
            port="$2"
            shift
            shift
            ;;
        -r|--room)
            room="$2"
            shift
            shift
            ;;
        -d|--debug)
            debug=true
            shift
            ;;
        -h|--help)
            print_help
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            print_help
            exit 1
            ;;
    esac
done

# Function to clean up background processes on exit
cleanup() {
    echo -e "${YELLOW}Shutting down services...${NC}"
    # Kill background processes by their group ID
    if [ ! -z "$SERVER_PID" ]; then
        echo "Stopping Socket.IO server (PID: $SERVER_PID)"
        pkill -TERM -P $SERVER_PID 2>/dev/null
        kill -TERM $SERVER_PID 2>/dev/null
    fi
    if [ ! -z "$CLIENT_PID" ]; then
        echo "Stopping Python client (PID: $CLIENT_PID)"
        pkill -TERM -P $CLIENT_PID 2>/dev/null
        kill -TERM $CLIENT_PID 2>/dev/null
    fi
    echo -e "${GREEN}All services stopped${NC}"
    exit 0
}

# Set up a trap to catch SIGINT and SIGTERM
trap cleanup SIGINT SIGTERM

# Check if Python is available
if ! command -v python3 &> /dev/null; then
    echo -e "${RED}Error: Python 3 is not installed or not in PATH${NC}"
    exit 1
fi

# Create necessary directories
mkdir -p screenshots logs .tmp

# Set debug flag for Python
if [ "$debug" = true ]; then
    export LOG_LEVEL=DEBUG
else
    export LOG_LEVEL=INFO
fi

echo -e "${BLUE}=== 33ter Application Startup ===${NC}"
echo -e "${GREEN}Starting Socket.IO server on port $port...${NC}"

# Start the Socket.IO server in the background
python3 socketio_server.py --port $port --room $room &
SERVER_PID=$!

# Wait for the server to start
sleep 2

# Check if the server started successfully
if ! ps -p $SERVER_PID > /dev/null; then
    echo -e "${RED}Error: Failed to start Socket.IO server${NC}"
    cleanup
    exit 1
fi

echo -e "${GREEN}Starting Python client...${NC}"

# Start the Python client in the background
python3 socketio_client.py &
CLIENT_PID=$!

# Wait for the client to start
sleep 2

# Check if the client started successfully
if ! ps -p $CLIENT_PID > /dev/null; then
    echo -e "${RED}Error: Failed to start Python client${NC}"
    cleanup
    exit 1
fi

echo -e "${GREEN}All services started successfully${NC}"
echo -e "${BLUE}Socket.IO server: localhost:$port${NC}"
echo -e "${YELLOW}Press Ctrl+C to stop all services${NC}"

# Wait for either process to exit or user interrupt
wait $SERVER_PID $CLIENT_PID

# Clean up if one of the processes exited on its own
cleanup