"""Utilities for creating and handling standardized Socket.IO messages."""

import enum
import time
from typing import Dict, Any, Union, Optional
from datetime import datetime, timezone

# Define standard message types used across client/server
class MessageType(enum.Enum):
    """
    Enumerates the types of messages exchanged via Socket.IO.
    Messages are typically requests for action or data payloads.
    """
    # General Purpose
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"

    # Client -> Server
    TRIGGER_OCR = "trigger_ocr" # Request from iOS to start OCR

    # Server -> Internal Client
    PERFORM_OCR_REQUEST = "perform_ocr_request" # Server asks internal client to do OCR

    # Internal Client -> Server
    OCR_RESULT = "ocr_result" # Internal client sends result *back to server*
    OCR_ERROR = "ocr_error"   # Internal client sends error *back to server*

    # Server -> Client(s)
    CLIENT_COUNT = "client_count" # Periodic broadcast of client count
    # OCR_RESULT is also used Server -> iOS Client (but targeted, not broadcast)

    # Removed TRIGGER (renamed to TRIGGER_OCR)
    # Removed PING, PONG, HEARTBEAT, HEARTBEAT_RESPONSE (assuming not used or handled differently)


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
    timestamp: bool = True,
    target_sid: Optional[str] = None
) -> Dict[str, Any]:
    """
    Creates a standardized dictionary object for Socket.IO messages.

    Args:
        message_type: The type of the message (from MessageType enum).
        value: The payload of the message (string or dictionary).
        sender: The source of the message (e.g., "server", "client", "ui").
        timestamp: Whether to include an ISO 8601 timestamp.
        target_sid: Optional SID this message is intended for (for logging/context).

    Returns:
        A dictionary representing the structured message.
    """
    message = {
        "messageType": message_type.value,
        "value": value,
        "from": sender,
    }
    if timestamp:
        message["timestamp"] = datetime.now(timezone.utc).isoformat()
    if target_sid:
        message["target_sid"] = target_sid # Add if provided

    return message

### Message Utility functions

# Updated: Now sends a message with type CLIENT_COUNT
def create_client_count_message(count: int) -> Dict[str, Any]:
    """Creates a client count message."""
    return create_socket_message(
        MessageType.CLIENT_COUNT,
        {"count": count},
        sender="localBackend" # Server sends this
    )

# Updated: Now creates the OCR_RESULT message payload (used Server -> iOS)
def create_ocr_result_message(text: str, source: str = "manual_trigger") -> Dict[str, Any]:
    """Creates an OCR result message payload for sending to the iOS client."""
    # This function now just creates the *value* part of the message
    # The actual sending logic in server.py will wrap this using create_socket_message
    # and target the specific iOS client SID.
    return {
        "text": text,
        "source": source # Indicate if it was manually triggered or automatic
    }

# Kept for server sending welcome message directly to new client
def create_welcome_message(sid: str) -> Dict[str, Any]:
    """Creates a welcome message."""
    return create_socket_message(
        MessageType.INFO,
        f"Welcome! You are connected with SID: {sid}",
        sender="localBackend",
        target_sid=sid # Explicitly target the new client
    )

# Kept for server sending confirmation messages directly to specific clients
def create_join_leave_message(sid: str, room_name: str, joined: bool) -> Dict[str, Any]:
    """Creates a message confirming joining or leaving a room."""
    action = "joined" if joined else "left"
    return create_socket_message(
        MessageType.INFO,
        f"You have {action} room: {room_name}",
        sender="localBackend",
        target_sid=sid # Target the specific client
    )