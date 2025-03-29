"""Utilities for creating and handling standardized Socket.IO messages."""

import enum
import time
from typing import Dict, Any, Union

# Define standard message types used across client/server
class MessageType(enum.Enum):
    """Enumerates the types of messages exchanged via Socket.IO."""
    INFO = "info"
    WARNING = "warning"
    ERROR = "error" # Added for completeness
    TRIGGER = "trigger"
    PING = "ping"
    PONG = "pong"
    HEARTBEAT = "heartbeat"
    HEARTBEAT_RESPONSE = "heartbeatResponse"
    # Add other types as needed

# Define possible structures for the 'value' field based on MessageType
# This is more illustrative; actual validation might be more complex
class SocketMessageValue:
    """Namespace for potential value structures (can be simple types or dicts)."""
    # Examples - adjust based on actual needs
    CodeSolution = Dict[str, Any]  # e.g., {"text": "...", "language": "..."}
    ClientCount = Dict[str, int]   # e.g., {"count": 5}
    Timestamp = Dict[str, float]   # e.g., {"timestamp": 1678886400.0}
    Text = str

def create_socket_message(
    message_type: MessageType,
    value: Union[str, Dict[str, Any]],
    sender: str = "localBackend",
    timestamp: bool = True
) -> Dict[str, Any]:
    """
    Creates a standardized dictionary object for Socket.IO messages.

    Args:
        message_type: The type of the message (from MessageType enum).
        value: The payload of the message (string or dictionary).
        sender: The source of the message (e.g., "server", "client", "ui").
        timestamp: Whether to include an ISO 8601 timestamp.

    Returns:
        A dictionary representing the structured message.
    """
    message = {
        "messageType": message_type.value,
        "value": value,
        "from": sender,
    }
    if timestamp:
        # Use time.time() for a simple epoch timestamp, or datetime for ISO format
        # message["timestamp"] = time.time()
        # Using ISO format as seen in some logs/examples
        from datetime import datetime, timezone
        message["timestamp"] = datetime.now(timezone.utc).isoformat()

    return message

### Message Utility functions
def create_client_count_message(count: int) -> Dict[str, Any]:
    """Creates a client count message."""
    return create_socket_message(
        MessageType.CLIENT_COUNT,
        {"count": count},    # note to self: should we standardize this or use dictionaries / strings here?        
    )

def create_ocr_result_message(result: str) -> Dict[str, Any]:
    """Creates an OCR result message."""
    return create_socket_message(
        MessageType.INFO,
        {"text": result},
    )

def create_welcome_message(sid: str) -> Dict[str, Any]:
    """Creates a welcome message."""
    return create_socket_message(
        MessageType.INFO,
        f"Welcome! You are connected with SID: {sid}",
    )

def create_joined_room_message(sid: str, room_name: str) -> Dict[str, Any]:
    """Creates a message for when a client joins a room."""
    return create_socket_message(
        MessageType.INFO,
        f"Client {sid} has joined room: {room_name}",
    )