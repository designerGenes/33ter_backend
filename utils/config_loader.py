#!/usr/bin/env python3
"""Configuration loader for the 33ter application.

This module provides a centralized configuration management system for the 33ter application.
It handles loading, merging, and validating configurations from multiple sources, with support
for default values and runtime updates.

Key Features:
- Hierarchical configuration management
- Default configuration values
- JSON file-based configuration
- Deep merging of configuration updates
- Configuration validation
- Runtime configuration updates

#TODO:
- Add support for environment variable overrides
- Implement configuration schema validation
- Add support for hot reloading of configuration files
- Consider adding encryption for sensitive configuration values
- Implement configuration versioning and migration
- Add configuration backup and restore functionality
"""
import os
import json
import logging
from typing import Any, Dict, Optional
from .path_config import get_config_dir

class ConfigManager:
    def __init__(self):
        """Initialize the configuration manager."""
        self._config: Dict[str, Any] = {}
        self._load_defaults()
        self._load_config_files()
    
    def _load_defaults(self) -> None:
        """Load default configuration values."""
        self._config = {
            "logging": {
                "level": "INFO",
                "format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
            },
            "server": {
                "host": "0.0.0.0",
                "port": 5348,
                "room": "33ter_room"
            },
            "screenshot": {
                "frequency": 4.0,
                "cleanup_age": 180
            },
            "health_check": {
                "enabled": True,
                "interval": 60
            }
        }
    
    def _load_config_files(self) -> None:
        """Load configuration from JSON files in the config directory."""
        config_files = [
            "server_config.json",
            "screenshot_frequency.json"
        ]
        
        for filename in config_files:
            filepath = os.path.join(get_config_dir(), filename)
            try:
                if os.path.exists(filepath):
                    with open(filepath, 'r') as f:
                        file_config = json.load(f)
                        # Merge configuration recursively
                        self._merge_config(self._config, file_config)
                        self._validate_config(filename, file_config)
            except Exception as e:
                logging.error(f"Error loading config file {filename}: {e}")
    
    def _merge_config(self, base: Dict, update: Dict) -> None:
        """
        Recursively merge two configuration dictionaries.
        Args:
            base: Base configuration dictionary
            update: Dictionary with updates to merge
        """
        for key, value in update.items():
            if (
                key in base and 
                isinstance(base[key], dict) and 
                isinstance(value, dict)
            ):
                self._merge_config(base[key], value)
            else:
                base[key] = value
    
    def _validate_config(self, filename: str, config: Dict[str, Any]) -> None:
        """Validate configuration based on the filename."""
        if filename == "screenshot_frequency.json":
            self._validate_frequency_config(config)
        elif filename == "server_config.json":
            self._validate_server_config(config)
    
    def _validate_frequency_config(self, config: Dict[str, Any]) -> None:
        """Validate screenshot frequency configuration"""
        required = {"frequency", "min_frequency", "max_frequency", "max_age"}
        if not all(k in config for k in required):
            raise ValueError(f"Missing required frequency config keys: {required}")
            
        if not (0.1 <= config["frequency"] <= 60.0):
            raise ValueError("Screenshot frequency must be between 0.1 and 60 seconds")
            
    def _validate_server_config(self, config: Dict[str, Any]) -> None:
        """Validate server configuration"""
        required = {"host", "port"}
        if not all(k in config for k in required):
            raise ValueError(f"Missing required server config keys: {required}")
            
        if not isinstance(config["port"], int):
            raise ValueError("Server port must be an integer")
    
    def get(self, section: str, key: str, default: Any = None) -> Any:
        """
        Get a configuration value.
        Args:
            section: Configuration section
            key: Configuration key
            default: Default value if not found
        Returns:
            Configuration value or default
        """
        try:
            return self._config[section][key]
        except KeyError:
            return default
    
    def set(self, section: str, key: str, value: Any) -> None:
        """
        Set a configuration value.
        Args:
            section: Configuration section
            key: Configuration key
            value: Value to set
        """
        if section not in self._config:
            self._config[section] = {}
        self._config[section][key] = value
    
    def save(self, filename: str) -> bool:
        """
        Save current configuration to a file.
        Args:
            filename: Name of the file to save to
        Returns:
            bool: True if save was successful, False otherwise
        """
        try:
            filepath = os.path.join(get_config_dir(), filename)
            os.makedirs(os.path.dirname(filepath), exist_ok=True)
            
            with open(filepath, 'w') as f:
                json.dump(self._config, f, indent=2)
            return True
        except Exception as e:
            logging.error(f"Error saving config to {filename}: {e}")
            return False
    
    @property
    def config(self) -> Dict[str, Any]:
        """Get the complete configuration dictionary."""
        return self._config.copy()

# Create a global configuration instance
config = ConfigManager()