"""Message system for 33ter application.

This module provides a centralized messaging system with structured message
representation, thread-safe buffering, and consistent formatting for UI display.
"""
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from enum import Enum
import time
import threading
from collections import deque


class MessageLevel(Enum):
    """Message severity levels."""
    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CODESOLUTION = "codeSolution"


class MessageCategory(Enum):
    """Message category types."""
    SOCKET = "socket"
    SCREENSHOT = "screenshot"
    SYSTEM = "system"
    DEBUG = "debug"
    OCR = "ocr"


@dataclass
class Message:
    """Structured message for the 33ter application."""
    timestamp: float = field(default_factory=time.time)
    level: MessageLevel = MessageLevel.INFO
    category: MessageCategory = MessageCategory.SYSTEM
    content: str = ""
    source: str = "system"
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    @property
    def formatted_timestamp(self) -> str:
        """Get formatted timestamp string."""
        return time.strftime("%H:%M:%S", time.localtime(self.timestamp))
    
    @property
    def emoji(self) -> str:
        """Get appropriate emoji based on message properties."""
        # Category-based emojis
        if self.category == MessageCategory.SOCKET:
            if "sending" in self.content.lower():
                return "📤"
            elif "received" in self.content.lower():
                return "📥"
            return "📱"
        elif self.category == MessageCategory.SCREENSHOT:
            if "captured" in self.content.lower():
                return "📸"
            elif "deleted" in self.content.lower():
                return "🗑️"
            return "🖼️"
        elif self.category == MessageCategory.OCR:
            return "📝"
            
        # Level-based emojis
        if self.level == MessageLevel.ERROR:
            return "❌"
        elif self.level == MessageLevel.WARNING:
            return "⚠️"
        elif self.level == MessageLevel.INFO:
            return "ℹ️"
        elif self.level == MessageLevel.CODESOLUTION:
            return "✨"
        elif self.level == MessageLevel.DEBUG:
            return "🔍"
            
        return "📱"  # Default


class MessageBuffer:
    """Thread-safe buffer for storing and retrieving messages."""
    def __init__(self, max_size: int = 1000):
        self.buffer = deque(maxlen=max_size)
        self.lock = threading.RLock()
        
    def add(self, message: Message) -> None:
        """Add a message to the buffer."""
        with self.lock:
            self.buffer.append(message)
    
    def get_all(self) -> List[Message]:
        """Get all messages in the buffer."""
        with self.lock:
            return list(self.buffer)
    
    def get_by_category(self, category: MessageCategory) -> List[Message]:
        """Get messages filtered by category."""
        with self.lock:
            return [msg for msg in self.buffer if msg.category == category]
    
    def get_by_level(self, level: MessageLevel) -> List[Message]:
        """Get messages filtered by level."""
        with self.lock:
            return [msg for msg in self.buffer if msg.level == level]
    
    def get_by_source(self, source: str) -> List[Message]:
        """Get messages filtered by source."""
        with self.lock:
            return [msg for msg in self.buffer if msg.source == source]
    
    def clear(self) -> None:
        """Clear all messages from the buffer."""
        with self.lock:
            self.buffer.clear()


class MessageFormatter:
    """Formats messages for different UI contexts."""
    
    @staticmethod
    def format_for_curses(message: Message) -> Dict[str, Any]:
        """Format a message for curses display."""
        return {
            "timestamp": message.formatted_timestamp,
            "emoji": message.emoji,
            "content": message.content,
            "level": message.level.value,
            "category": message.category.value,
            "raw_message": message
        }
    
    @staticmethod
    def format_for_log(message: Message) -> str:
        """Format a message for log file."""
        return f"[{message.formatted_timestamp}] [{message.level.value.upper()}] {message.content}"
    
    @staticmethod
    def format_legacy(message: Message) -> str:
        """Format a message in the legacy string format for backward compatibility."""
        timestamp = message.formatted_timestamp
        emoji = message.emoji
        content = message.content
        level = message.level.value
        return f"{timestamp} {emoji} {content} ({level})"
        
    @staticmethod
    def format_json_like(message: Message) -> str:
        """Format a message in a JSON-like format for debug view."""
        timestamp = message.formatted_timestamp
        
        # For error messages
        if message.level == MessageLevel.ERROR:
            return f"{timestamp}: {{\n    ERROR: {message.content}\n}}"
            
        # For regular messages
        metadata = message.metadata
        msg_type = metadata.get("type", "unknown")
        msg_value = metadata.get("value", "")
        msg_from = message.source
        
        return f"{timestamp}: {{\n    type: {msg_type},\n    value: {msg_value},\n    from: {msg_from}\n}}"


class MessageManager:
    """Central manager for all application messages."""
    _instance = None
    _initialized = False
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(MessageManager, cls).__new__(cls)
        return cls._instance
    
    def __init__(self):
        if not self._initialized:
            self.buffers = {
                "main": MessageBuffer(),
                "screenshot": MessageBuffer(),
                "socket": MessageBuffer(),
                "debug": MessageBuffer()
            }
            self._initialized = True
    
    def add_message(self, 
                   content: str, 
                   level: MessageLevel = MessageLevel.INFO,
                   category: MessageCategory = MessageCategory.SYSTEM,
                   source: str = "system",
                   buffer_name: str = "main",
                   metadata: Optional[Dict[str, Any]] = None) -> Message:
        """
        Add a message to the specified buffer.
        Returns the created message.
        """
        if metadata is None:
            metadata = {}
            
        message = Message(
            content=content,
            level=level,
            category=category,
            source=source,
            metadata=metadata
        )
        
        # Add to specified buffer
        if buffer_name in self.buffers:
            self.buffers[buffer_name].add(message)
        
        # Always add to main buffer if it's not the target
        if buffer_name != "main":
            self.buffers["main"].add(message)
            
        return message
    
    def get_messages(self, buffer_name: str) -> List[Message]:
        """Get all messages from the specified buffer."""
        if buffer_name in self.buffers:
            return self.buffers[buffer_name].get_all()
        return []
    
    def get_formatted_messages(self, buffer_name: str, format_type: str = "legacy") -> List[str]:
        """Get formatted messages from the specified buffer."""
        messages = self.get_messages(buffer_name)
        
        if format_type == "legacy":
            return [MessageFormatter.format_legacy(msg) for msg in messages]
        elif format_type == "json":
            return [MessageFormatter.format_json_like(msg) for msg in messages]
        else:
            return [MessageFormatter.format_for_curses(msg) for msg in messages]
    
    def clear_buffer(self, buffer_name: str) -> None:
        """Clear a specific message buffer."""
        if buffer_name in self.buffers:
            self.buffers[buffer_name].clear()

    def parse_legacy_message(self, message: str, buffer_name: str = "main"):
        """
        Parse a legacy format message string and add it to the system.
        Format expected: "timestamp emoji message (level)"
        """
        try:
            parts = message.split(" ", 2)
            if len(parts) >= 3:
                timestamp_str = parts[0]
                emoji = parts[1]
                rest = parts[2]
                
                # Extract level from parentheses at the end
                level_start = rest.rfind("(")
                level_end = rest.rfind(")")
                
                if level_start > 0 and level_end > level_start:
                    content = rest[:level_start].strip()
                    level_str = rest[level_start+1:level_end].strip().lower()
                    
                    # Map to MessageLevel
                    try:
                        level = MessageLevel(level_str)
                    except ValueError:
                        level = MessageLevel.INFO
                    
                    # Determine category based on buffer and content
                    if buffer_name == "screenshot":
                        category = MessageCategory.SCREENSHOT
                    elif buffer_name == "debug":
                        category = MessageCategory.DEBUG
                    elif "socket" in content.lower():
                        category = MessageCategory.SOCKET
                    elif "ocr" in content.lower():
                        category = MessageCategory.OCR
                    else:
                        category = MessageCategory.SYSTEM
                    
                    # Add the structured message
                    return self.add_message(
                        content=content,
                        level=level,
                        category=category,
                        buffer_name=buffer_name
                    )
        except Exception:
            # If parsing fails, add as-is with default values
            return self.add_message(
                content=message,
                buffer_name=buffer_name
            )
        
        # Fallback for unparseable messages
        return self.add_message(
            content=message,
            buffer_name=buffer_name
        )
