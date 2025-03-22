"""Core functionality for the 33ter Python application.

This module provides the core components for screenshot capture, OCR processing,
and process management in the 33ter application.

Components:
- ProcessManager: Manages application services and inter-process communication
- ScreenshotManager: Handles continuous screenshot capture and cleanup
- TerminalUI: Provides the terminal-based user interface

#TODO:
- Add component dependency management
- Implement proper component lifecycle hooks
- Consider adding component health monitoring
- Add proper shutdown sequence handling
- Implement component recovery mechanisms
"""

from .process_manager import ProcessManager
from .screenshot_manager import ScreenshotManager
from .terminal_ui import TerminalUI

__all__ = ['ProcessManager', 'ScreenshotManager', 'TerminalUI']