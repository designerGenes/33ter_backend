"""Server configuration utilities for Threethreeter Socket.IO server.

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

import sys
import json
import logging
from pathlib import Path
from typing import Dict, Any, Optional
import copy

# Explicitly get the logger for this module's name
logger = logging.getLogger(__name__)

# --- Add a basic handler IF NONE EXIST ---
if not logger.hasHandlers():
    handler = logging.StreamHandler(sys.stderr)
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    # Set a default level for this logger if run standalone or before main config
    # Avoid setting propagate=False unless you are sure
    logger.setLevel(logging.INFO)


# Define the configuration directory relative to this file
CONFIG_DIR = Path(__file__).parent.parent / 'config'
SERVER_CONFIG_FILE = CONFIG_DIR / 'server_config.json'

# Default configuration structure
DEFAULT_CONFIG: Dict[str, Any] = {
    "server": {
        "host": "0.0.0.0",
        "port": 5348,
        "room": "Threethreeter_room",
        "cors_origins": ["*"],
        "log_level": "INFO"
    },
    "health_check": {
        "enabled": True,
        "interval": 30
    }
}

# In-memory cache for the configuration
_config_cache: Optional[Dict[str, Any]] = None

def _deep_merge_dicts(source: Dict[str, Any], destination: Dict[str, Any]) -> Dict[str, Any]:
    """Recursively merge source dict into destination dict."""
    for key, value in source.items():
        if isinstance(value, dict):
            # Get node or create one
            node = destination.setdefault(key, {})
            _deep_merge_dicts(value, node)
        else:
            destination[key] = value
    return destination

def _load_config() -> Dict[str, Any]:
    """Loads configuration from file, merges with defaults, handles errors."""
    global _config_cache
    config = copy.deepcopy(DEFAULT_CONFIG) # Start with defaults

    if SERVER_CONFIG_FILE.exists():
        try:
            with open(SERVER_CONFIG_FILE, 'r') as f:
                loaded_config = json.load(f)
                logger.debug(f"Raw config loaded from {SERVER_CONFIG_FILE}: {loaded_config}") # Added logging
                if isinstance(loaded_config, dict):
                    config = _deep_merge_dicts(loaded_config, config)
                else:
                    logger.error(f"Invalid config format in {SERVER_CONFIG_FILE}. Expected a dictionary, got {type(loaded_config)}. Using defaults.")
                    # Reset to defaults if file format is wrong
                    config = copy.deepcopy(DEFAULT_CONFIG)
        except json.JSONDecodeError as e:
            logger.error(f"Error decoding JSON from {SERVER_CONFIG_FILE}: {e}. Using default configuration.")
            # Reset to defaults on JSON error
            config = copy.deepcopy(DEFAULT_CONFIG)
        except Exception as e:
            logger.error(f"Unexpected error loading config from {SERVER_CONFIG_FILE}: {e}. Using default configuration.")
            # Reset to defaults on other errors
            config = copy.deepcopy(DEFAULT_CONFIG)
    else:
        logger.warning(f"Configuration file not found at {SERVER_CONFIG_FILE}. Creating with default settings.")
        save_server_config(config) # Save defaults if file doesn't exist

    _config_cache = config
    logger.debug(f"Final merged config: {_config_cache}") # Added logging
    return _config_cache

def get_server_config() -> Dict[str, Any]:
    """Returns the current server configuration, loading if necessary."""
    # Always reload from file for now to ensure freshness during debugging
    # if _config_cache is None:
    #     _load_config()
    # return _config_cache if _config_cache is not None else copy.deepcopy(DEFAULT_CONFIG)
    return _load_config() # Force reload on each call during debugging

def save_server_config(config_data: Dict[str, Any]) -> bool:
    """Saves the configuration data to the file."""
    global _config_cache
    try:
        # Ensure the config directory exists
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        with open(SERVER_CONFIG_FILE, 'w') as f:
            json.dump(config_data, f, indent=2)
        _config_cache = copy.deepcopy(config_data) # Update cache after successful save
        logger.info(f"Server configuration saved to {SERVER_CONFIG_FILE}")
        return True
    except Exception as e:
        logger.error(f"Failed to save server configuration to {SERVER_CONFIG_FILE}: {e}")
        return False

def update_config_value(key_path: str, value: Any) -> bool:
    """Updates a specific configuration value using a dot-separated path."""
    config = get_server_config()
    keys = key_path.split('.')
    current_level = config
    try:
        for i, key in enumerate(keys):
            if i == len(keys) - 1:
                current_level[key] = value
            else:
                current_level = current_level.setdefault(key, {})
                if not isinstance(current_level, dict):
                    logger.error(f"Invalid path for update: '{key}' in '{key_path}' is not a dictionary.")
                    return False
        return save_server_config(config)
    except KeyError:
        logger.error(f"Invalid key path for update: '{key_path}'")
        return False
    except Exception as e:
        logger.error(f"Error updating config value for '{key_path}': {e}")
        return False

# Example usage (optional, for testing)
if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG) # Enable debug logging for testing
    logger.info("Testing server_config module...")
    initial_config = get_server_config()
    logger.info(f"Initial config: {json.dumps(initial_config, indent=2)}")

    # Test update
    # update_success = update_config_value("server.port", 5349)
    # logger.info(f"Update port success: {update_success}")
    # updated_config = get_server_config()
    # logger.info(f"Updated config: {json.dumps(updated_config, indent=2)}")

    # # Revert update
    # revert_success = update_config_value("server.port", 5348)
    # logger.info(f"Revert port success: {revert_success}")
    # reverted_config = get_server_config()
    # logger.info(f"Reverted config: {json.dumps(reverted_config, indent=2)}")

    # Test non-existent key
    # update_fail = update_config_value("server.non_existent.key", "test")
    # logger.info(f"Update non-existent key success: {update_fail}")