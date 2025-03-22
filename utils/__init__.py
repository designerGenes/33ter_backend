"""Utility functions and helpers for the 33ter Python application.

This package provides utility functions for configuration management, path handling,
system checks, and server configuration. It serves as the foundation for the application's
infrastructure needs.

Components:
- path_config: Path management and directory structure utilities
- server_config: Server configuration management
- system_check: System requirement validation
- config_loader: Configuration file handling and validation
- check_config: Configuration verification tools

#TODO:
- Add utility function test coverage
- Implement proper error handling strategies
- Consider adding logging utilities
- Add proper type hints throughout
- Implement proper security measures
"""

from .path_config import (
    get_app_root,
    get_config_dir,
    get_screenshots_dir,
    get_logs_dir,
    get_temp_dir,
    get_frequency_config_file,
    get_server_config_file
)
from .server_config import get_server_config, update_server_config

__all__ = [
    'get_app_root',
    'get_config_dir',
    'get_screenshots_dir',
    'get_logs_dir',
    'get_temp_dir',
    'get_frequency_config_file',
    'get_server_config_file',
    'get_server_config',
    'update_server_config'
]