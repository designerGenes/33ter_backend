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
import json
from pathlib import Path
from typing import Dict, Any, Optional

from .path_config import get_config_dir

DEFAULT_CONFIG = {
    "server": {
        "host": "127.0.0.1",
        "port": 5348,
        "room": "33ter_room",
        "cors_origins": ["127.0.0.1:*", "0.0.0.0:*", "localhost:*"],
        "log_level": "INFO"
    },
    "health_check": {
        "enabled": True,
        "interval": 30
    }
}

def load_server_config() -> Dict[str, Any]:
    """Load server configuration from file, using defaults if not found."""
    config_file = os.path.join(get_config_dir(), "server_config.json")
    
    try:
        if os.path.exists(config_file):
            with open(config_file, 'r') as f:
                user_config = json.load(f)
                # Deep merge with defaults
                return _deep_merge(DEFAULT_CONFIG, user_config)
    except Exception as e:
        print(f"Error loading server config: {e}")
        print("Using default configuration")
    
    return DEFAULT_CONFIG.copy()

def save_server_config(config: Dict[str, Any]) -> bool:
    """Save server configuration to file."""
    config_file = os.path.join(get_config_dir(), "server_config.json")
    
    try:
        # Ensure config directory exists
        os.makedirs(os.path.dirname(config_file), exist_ok=True)
        
        with open(config_file, 'w') as f:
            json.dump(config, f, indent=2)
        return True
    except Exception as e:
        print(f"Error saving server config: {e}")
        return False

def _deep_merge(default: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    """Recursively merge two configuration dictionaries."""
    result = default.copy()
    
    for key, value in override.items():
        if (
            key in result and 
            isinstance(result[key], dict) and 
            isinstance(value, dict)
        ):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
            
    return result

def get_server_config() -> Dict[str, Any]:
    """Get the current server configuration."""
    return load_server_config()

def update_server_config(updates: Dict[str, Any]) -> bool:
    """Update specific server configuration values."""
    current_config = load_server_config()
    new_config = _deep_merge(current_config, updates)
    return save_server_config(new_config)