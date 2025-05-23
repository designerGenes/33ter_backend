#!/usr/bin/env python3
"""Configuration loader for the Threethreeter application.

This module provides a centralized configuration management system for the Threethreeter application.
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
                "room": "Threethreeter_room"
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
            
        # Handle the case where frequency is None or not a number
        frequency = config.get("frequency")
        if frequency is None:
            config["frequency"] = 4.0  # Default value if None
            return
            
        try:
            frequency_value = float(frequency)
            if not (0.1 <= frequency_value <= 60.0):
                logging.warning(f"Screenshot frequency {frequency_value} out of range (0.1-60.0), setting to default.")
                config["frequency"] = 4.0
        except (TypeError, ValueError):
            logging.warning(f"Invalid frequency value: {frequency}, setting to default.")
            config["frequency"] = 4.0
    
    def _validate_server_config(self, config: Dict[str, Any]) -> None:
        """Validate server configuration"""
        if 'server' not in config:
            raise ValueError("Missing 'server' section in server_config.json")
        
        server_config = config['server']
        required = {"host", "port"}
        if not all(k in server_config for k in required):
            raise ValueError(f"Missing required server config keys under 'server': {required - set(server_config.keys())}")
            
        port = server_config.get("port")
        if port is None:
            server_config["port"] = 5348  # Default port if None
            return
            
        if not isinstance(port, int):
            try:
                server_config["port"] = int(port)
            except (TypeError, ValueError):
                logging.warning(f"Invalid port value: {port}, setting to default.")
                server_config["port"] = 5348
    
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
            # First try to get the value from the config
            value = self._config[section][key]
            # Check if value is None and a default is provided
            if value is None and default is not None:
                return default
            return value
        except (KeyError, TypeError):
            # Return default if section or key doesn't exist
            return default
    
    def get_config(self) -> Dict[str, Any]:
        """Get the complete configuration dictionary."""
        return self._config.copy()
    
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