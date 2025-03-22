"""UI components for the 33ter terminal interface."""

from .color_scheme import setup_colors, get_view_color
from .base_view import BaseView
from .status_view import StatusView
from .screenshot_view import ScreenshotView
from .debug_view import DebugView

__all__ = [
    'setup_colors',
    'get_view_color',
    'BaseView',
    'StatusView',
    'ScreenshotView',
    'DebugView'
]
