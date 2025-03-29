class EventType(enum.Enum):
    """Enumerates the types of events triggered in Socket.IO."""
    JOINED_ROOM = "joined_room"
    EXITED_ROOM = "exited_room"
    CAPTURED_SCREENSHOT = "captured_screenshot"
    FAILED_SCREENSHOT_CAPTURE = "failed_screenshot_capture"
    PROCESSED_SCREENSHOT = "processed_screenshot"
    TRIGGERED_OCR = "triggered_ocr"
    UPDATED_CLIENT_COUNT = "updated_client_count"
    RECEIVED_CODE_SOLUTION = "received_code_solution"
    
