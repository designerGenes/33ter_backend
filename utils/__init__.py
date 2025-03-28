"""Utility functions and helpers for the 33ter Python application"""
from .path_config import (
    get_project_root, # Changed from get_project_root
    get_config_dir,
    get_screenshots_dir,
    get_logs_dir,
    get_temp_dir,
    get_frequency_config_file,
    get_server_config_file
)
# Remove update_server_config from this import as it doesn't exist
from .server_config import get_server_config, save_server_config, update_config_value, DEFAULT_CONFIG

__all__ = [
    'get_project_root', # Changed from get_project_root
    'get_config_dir',
    'get_screenshots_dir',
    'get_logs_dir',
    'get_temp_dir',
    'get_frequency_config_file',
    'get_server_config_file',
    'get_server_config',
    'save_server_config', # Add save_server_config if needed externally
    'update_config_value', # Add update_config_value if needed externally
    'DEFAULT_CONFIG' # Add DEFAULT_CONFIG if needed externally
    # Remove update_server_config from the export list
]