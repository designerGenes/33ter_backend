import os
import json
import requests
import logging
from datetime import datetime
from typing import Optional

def get_socket_config() -> Optional[dict]:
    """Get Socket.IO server configuration from config file."""
    try:
        config_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'config', 'config.json')
        with open(config_path) as f:
            config = json.load(f)
        return config['services']['publishMessage']
    except Exception as e:
        logging.error(f"Error loading socket config: {e}")
        return None

def log_debug(message: str, source: str = "Process", level: str = "info") -> None:
    """Log a debug message to the Process screen."""
    print(f"[{source}] {message}")

def format_socket_message(title: str, message: str, log_type: str = "info") -> str:
    """Format a message in the style it will be sent to SocketIO."""
    timestamp = datetime.now().strftime("%H:%M:%S")
    separator = "=" * 50
    
    # Enhanced type indicators with descriptive emojis
    type_indicator = {
        "info": "ℹ️",
        "prime": "🌟",
        "warning": "⚠️",
        "error": "❌",
        "success": "✅",
        "progress": "⏳",
        "challenge": "🎯",
        "solution": "💡"
    }.get(log_type.lower(), "ℹ️")
    
    formatted = f"\n{separator}\n"
    formatted += f"{timestamp} {type_indicator} {title}\n"
    formatted += f"{separator}\n\n"
    
    # Format the message body with proper line breaks and indentation
    message_lines = message.strip().split('\n')
    
    # Detect if this is a multi-line message
    if len(message_lines) == 1:
        # Single line messages get simple formatting
        formatted += f"  {message_lines[0]}"
    else:
        # Track code block state
        in_code_block = False
        code_block_lines = []
        text_block_lines = []
        
        for line in message_lines:
            # Detect code blocks by looking at indentation and code-like patterns
            is_code_line = (
                line.startswith('    ') or 
                line.startswith('\t') or
                line.strip().startswith('def ') or
                line.strip().startswith('class ') or
                line.strip().startswith('func ') or
                line.strip().startswith('var ') or
                line.strip().startswith('let ') or
                any(line.strip().endswith(x) for x in ['{', '}', ');', '};', '];', ':'])
            )
            
            if is_code_line:
                if not in_code_block:
                    # Flush any pending text block
                    if text_block_lines:
                        formatted += '\n'.join(f"  {line}" for line in text_block_lines if line.strip())
                        formatted += "\n\n"
                        text_block_lines = []
                    in_code_block = True
                code_block_lines.append(line)
            else:
                if in_code_block:
                    # Flush code block
                    if code_block_lines:
                        formatted += "  Code:\n"
                        formatted += '\n'.join(f"    {line}" for line in code_block_lines)
                        formatted += "\n\n"
                        code_block_lines = []
                    in_code_block = False
                if line.strip():
                    text_block_lines.append(line)
                elif text_block_lines:
                    # Add empty line between text blocks
                    text_block_lines.append('')
        
        # Flush any remaining blocks
        if code_block_lines:
            formatted += "  Code:\n"
            formatted += '\n'.join(f"    {line}" for line in code_block_lines)
            formatted += "\n"
        if text_block_lines:
            if code_block_lines:  # Add extra newline if coming after code
                formatted += "\n"
            formatted += '\n'.join(f"  {line}" for line in text_block_lines if line.strip())
    
    formatted += f"\n\n{separator}\n"
    return formatted

def send_socket_message(title: str, message: str, log_type: str = "info", config: Optional[dict] = None) -> bool:
    """Send a message to the Socket.IO server."""
    try:
        if config is None:
            config = get_socket_config()
        if not config:
            return False
            
        socket_port = config['port']
        socket_room = config['room']
        
        payload = {
            "room": socket_room,
            "data": {
                "title": title,
                "message": message,
                "logType": log_type
            }
        }
        
        response = requests.post(
            f"http://localhost:{socket_port}/broadcast",
            json=payload,
            timeout=5
        )
        
        return response.status_code == 200
        
    except Exception as e:
        logging.error(f"Error sending message to Socket.IO server: {e}")
        return False

def log_to_socketio(message: str, title: str = "Message", log_type: str = "info") -> None:
    """Send a message to the Socket.IO server and format for Socket screen."""
    try:
        # Map common titles to appropriate log types if not explicitly set
        title_type_mapping = {
            "Challenge Found": "challenge",
            "Challenge Detected": "challenge",
            "Solution Ready": "solution",
            "Solution Generated": "solution",
            "Processing Status": "progress",
            "Analysis Result": "info",
            "Processing Error": "error",
            "System Error": "error"
        }
        
        # Use mapped log_type if available, otherwise keep the provided one
        effective_log_type = title_type_mapping.get(title, log_type)
        
        # Get socket config once
        config = get_socket_config()
        if not config:
            return
            
        # Print formatted message to Socket screen first
        print(format_socket_message(title, message, effective_log_type))
        
        # Then send to SocketIO server using shared config
        if not send_socket_message(title, message, effective_log_type, config):
            logging.error("Failed to send message to Socket.IO server")
            
    except Exception as e:
        logging.error(f"Error in log_to_socketio: {e}")