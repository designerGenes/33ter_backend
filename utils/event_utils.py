import enum # Ensure enum is imported

class EventType(enum.Enum):
    """
    Enumerates the types of events emitted by the Socket.IO server or clients.
    Events signify that something *has happened*. Payloads provide context.
    """
    # Server Lifecycle
    SERVER_STARTED = "server_started" # Payload: {}

    # Client Lifecycle / Room Management
    CLIENT_CONNECTED = "client_connected" # Payload: {"sid": str, "address": str, "client_type": str}
    CLIENT_DISCONNECTED = "client_disconnected" # Payload: {"sid": str}
    CLIENT_JOINED_ROOM = "client_joined_room" # Payload: {"sid": str, "room": str}
    CLIENT_LEFT_ROOM = "client_left_room" # Payload: {"sid": str, "room": str}
    UPDATED_CLIENT_COUNT = "updated_client_count" # Payload: {"count": int} # Renamed for clarity

    # Screenshot / OCR Process (Internal Client / Server)
    CAPTURED_SCREENSHOT = "captured_screenshot" # Payload: {"filepath": str}
    FAILED_SCREENSHOT_CAPTURE = "failed_screenshot_capture" # Payload: {"error": str}
    OCR_PROCESSING_STARTED = "ocr_processing_started" # Payload: {"requester_sid": str}
    OCR_PROCESSING_COMPLETED = "ocr_processing_completed" # Payload: {"requester_sid": str, "success": bool, "error": Optional[str]}
    PROCESSED_SCREENSHOT = "processed_screenshot" # Payload: {"success": bool, "text_preview": Optional[str], "error": Optional[str]}

    # Potentially from iOS Client (if needed for logging/UI)
    RECEIVED_CODE_SOLUTION = "received_code_solution" # Payload: {"request_id": str, "success": bool}

    # Removed TRIGGERED_OCR as OCR_PROCESSING_STARTED covers the start
    # Removed JOINED_ROOM/EXITED_ROOM in favor of CLIENT_JOINED_ROOM/CLIENT_LEFT_ROOM

