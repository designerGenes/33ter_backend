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
    CODE_SOLUTION = "codeSolution" # Renamed from ocrResult
    CLIENT_COUNT = "clientCount"
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
    sender: str = "server",
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

# Example Usage (for testing this module directly)
if __name__ == "__main__":
    info_msg = create_socket_message(MessageType.INFO, "Server started successfully.", sender="server")
    print(f"Info Message: {info_msg}")

    solution_data = {"text": "print('Hello')", "language": "python"}
    solution_msg = create_socket_message(MessageType.CODE_SOLUTION, solution_data, sender="ocr_service")
    print(f"Code Solution Message: {solution_msg}")

    count_data = {"count": 3}
    count_msg = create_socket_message(MessageType.CLIENT_COUNT, count_data, sender="server", timestamp=False)
    print(f"Client Count Message: {count_msg}")
