"""Configuration management utilities for the 33ter application."""
import os
import json
from typing import Any, Dict, Optional
from .path_config import get_config_dir

DEFAULT_CONFIG = {
    "services": {
        "socket": {
            "port": 5348,
            "room": "33ter_room"
        },
        "screenshot": {
            "frequency": 4.0,
            "max_age": 180
        }
    },
    "logging": {
        "level": "INFO",
        "max_files": 5,
        "max_size": "10M"
    }
}

class ConfigManager:
    """Manages application configuration loading and saving."""
    
    def __init__(self):
        self.config_file = os.path.join(get_config_dir(), "config.json")
        self._config = self.load_config()
    
    def load_config(self) -> Dict[str, Any]:
        """Load configuration from file, creating default if not exists."""
        try:
            if os.path.exists(self.config_file):
                with open(self.config_file, 'r') as f:
                    loaded_config = json.load(f)
                    # Merge with defaults to ensure all required keys exist
                    return self._merge_configs(DEFAULT_CONFIG, loaded_config)
        except Exception as e:
            print(f"Error loading config: {e}")
        
        # Save and return default config if loading fails
        self.save_config(DEFAULT_CONFIG)
        return DEFAULT_CONFIG.copy()
    
    def save_config(self, config: Dict[str, Any]) -> bool:
        """Save configuration to file."""
        try:
            with open(self.config_file, 'w') as f:
                json.dump(config, f, indent=2)
            return True
        except Exception as e:
            print(f"Error saving config: {e}")
            return False
    
    def _merge_configs(self, default: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
        """Recursively merge two configuration dictionaries."""
        result = default.copy()
        
        for key, value in override.items():
            if (
                key in result and 
                isinstance(result[key], dict) and 
                isinstance(value, dict)
            ):
                result[key] = self._merge_configs(result[key], value)
            else:
                result[key] = value
                
        return result
    
    def get(self, *keys: str, default: Any = None) -> Any:
        """Get a configuration value by key path."""
        current = self._config
        for key in keys:
            if isinstance(current, dict) and key in current:
                current = current[key]
            else:
                return default
        return current
    
    def set(self, *keys: str, value: Any) -> bool:
        """Set a configuration value by key path."""
        if not keys:
            return False
            
        current = self._config
        for key in keys[:-1]:
            if key not in current:
                current[key] = {}
            elif not isinstance(current[key], dict):
                return False
            current = current[key]
            
        current[keys[-1]] = value
        return self.save_config(self._config)
    
    def reload(self) -> None:
        """Reload configuration from disk."""
        self._config = self.load_config()
    
    @property
    def config(self) -> Dict[str, Any]:
        """Get the current configuration."""
        return self._config.copy()

# Global configuration instance
config = ConfigManager()