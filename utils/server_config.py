"""Server configuration utilities for 33ter Socket.IO server.

This module manages server-specific configuration settings, providing defaults and handling
updates for the Socket.IO server component. It supports dynamic configuration updates
and maintains backward compatibility with existing configurations.

Key Features:
- Default server configuration
- Configuration file management
- Deep configuration merging
- Dynamic configuration updates
- Cross-instance configuration synchronization

#TODO:
- Add configuration validation schema
- Implement configuration change notifications
- Add support for multiple server profiles
- Consider adding configuration versioning
- Implement configuration rollback support
- Add configuration export/import functionality
"""

import os
import sys  # Import sys for stderr stream handler
import json
import logging
from pathlib import Path
from typing import Dict, Any, Optional
import copy

# Explicitly get the logger for this module's name
logger = logging.getLogger(__name__)  # Ensures logger name is 'utils.server_config'

# --- Add a basic handler IF NONE EXIST ---
# This ensures that if this module is imported and used BEFORE
# the main application's logging is configured, its messages
# still go somewhere (stderr) and are identifiable.
if not logger.hasHandlers():
    handler = logging.StreamHandler(sys.stderr)
    formatter = logging.Formatter('%(name)s:%(levelname)s:%(message)s')  # Simple format
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    # Set a default level for this early handler if needed, e.g., WARNING or INFO
    # logger.setLevel(logging.INFO)  # Uncomment if you want early INFO messages too
    logger.propagate = False  # Prevent messages from going to root logger if it's configured later

# Now import other local modules AFTER setting up the logger handler
try:
    from .path_config import get_config_dir
except ImportError as e:
    # Log import error using the logger we just configured
    logger.critical(f"Failed to import path_config: {e}. Server config paths will be incorrect.", exc_info=True)
    # Define a fallback if path_config is critical
    def get_config_dir():
        logger.error("Using fallback config directory path due to import error.")
        # Provide a sensible fallback, e.g., relative path
        return os.path.join(os.path.dirname(__file__), '..', 'config')


DEFAULT_CONFIG = {
    "server": {
        "host": "0.0.0.0",
        "port": 5348,
        "room": "33ter_room",
        # More specific defaults might be safer than "*" if "*" causes issues
        "cors_origins": ["http://localhost:5348", "http://0.0.0.0:5348", "*"],
        "log_level": "INFO"
    },
    "health_check": {
        "enabled": True,
        "interval": 30
    }
}

# --- Configuration Loading ---
def get_server_config() -> Dict[str, Any]:
    """Load server configuration from file, merging with defaults."""
    config_file = os.path.join(get_config_dir(), "server_config.json")
    # Start with a deep copy of defaults
    loaded_config = copy.deepcopy(DEFAULT_CONFIG)
    logger.debug(f"Attempting to load server config from: {config_file}")  # Use named logger

    if os.path.exists(config_file):
        try:
            with open(config_file, 'r') as f:
                user_config = json.load(f)
                logger.debug(f"Successfully loaded user config from {config_file}")
                # Deep merge user config into defaults
                _deep_merge(loaded_config, user_config)
        except json.JSONDecodeError as e:
            # Use the explicitly named logger
            logger.error(f"Error decoding JSON from {config_file}: {e}. Using default config.", exc_info=True)
            return copy.deepcopy(DEFAULT_CONFIG)
        except Exception as e:
            # Use the explicitly named logger
            logger.error(f"Error reading config file {config_file}: {e}. Using default config.", exc_info=True)
            return copy.deepcopy(DEFAULT_CONFIG)
    else:
        # Use the explicitly named logger
        logger.warning(f"Config file not found at {config_file}. Using default config and attempting to save it.")
        try:
            save_server_config(loaded_config)  # Save defaults if file doesn't exist
        except Exception as e:
            # Use the explicitly named logger
            logger.error(f"Failed to save default config to {config_file}: {e}", exc_info=True)

    # --- Validation ---
    # Ensure critical keys exist after merge, falling back to defaults if necessary
    if 'server' not in loaded_config:
        # Use the explicitly named logger
        logger.warning("Missing 'server' section in config, restoring from defaults.")
        loaded_config['server'] = copy.deepcopy(DEFAULT_CONFIG['server'])
    # Ensure 'server' is a dict before accessing subkeys
    server_dict = loaded_config.get('server', {})
    if not isinstance(server_dict, dict):
        logger.warning("'server' key exists but is not a dictionary, restoring from defaults.")
        loaded_config['server'] = copy.deepcopy(DEFAULT_CONFIG['server'])
        server_dict = loaded_config['server']  # Update local reference

    if 'host' not in server_dict:
        # Use the explicitly named logger
        logger.warning("Missing 'host' in server config, restoring from default.")
        loaded_config['server']['host'] = DEFAULT_CONFIG['server']['host']
    if 'port' not in server_dict:
        # Use the explicitly named logger
        logger.warning("Missing 'port' in server config, restoring from default.")
        loaded_config['server']['port'] = DEFAULT_CONFIG['server']['port']
    if 'cors_origins' not in server_dict:
        # Use the explicitly named logger
        logger.warning("Missing 'cors_origins' in server config, restoring from default.")
        loaded_config['server']['cors_origins'] = DEFAULT_CONFIG['server']['cors_origins']

    logger.debug(f"Final loaded config: {json.dumps(loaded_config, indent=2)}")
    return loaded_config

# --- Configuration Saving ---
def save_server_config(config_data: Dict[str, Any]) -> bool:
    """Save server configuration to file."""
    config_file = os.path.join(get_config_dir(), "server_config.json")
    try:
        os.makedirs(os.path.dirname(config_file), exist_ok=True)
        with open(config_file, 'w') as f:
            json.dump(config_data, f, indent=2)
        # Use the explicitly named logger
        logger.info(f"Server configuration saved to {config_file}")
        return True
    except Exception as e:
        # Use the explicitly named logger
        logger.error(f"Error saving config file {config_file}: {e}", exc_info=True)
        return False

# --- Configuration Update ---
def update_server_config(updates: Dict[str, Any]) -> Dict[str, Any]:
    """Update the server configuration file with new values."""
    current_config = get_server_config()
    _deep_merge(current_config, updates)
    if save_server_config(current_config):
        return current_config
    else:
        # Use the explicitly named logger
        logger.error("Failed to save updated configuration, returning previous state.")
        return get_server_config()

# --- Helper for deep merging dictionaries ---
def _deep_merge(source: Dict, destination: Dict):
    """
    Deep merge `destination` dict into `source` dict.
    Modifies `source` in place.
    """
    for key, value in destination.items():
        if isinstance(value, dict):
            node = source.setdefault(key, {})
            # Ensure node is a dict before merging into it
            if isinstance(node, dict):
                _deep_merge(node, value)
            else:
                # Handle case where source has a non-dict value at the key
                logger.warning(f"Overwriting non-dict value at key '{key}' during deep merge.")
                source[key] = value  # Overwrite with the new dict
        else:
            source[key] = value
    return source