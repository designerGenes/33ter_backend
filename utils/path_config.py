"""Path configuration utilities for 33ter application."""
import os
import sys
from pathlib import Path

def get_app_root():
    """Get the root directory of the application."""
    return str(Path(__file__).parent.parent.absolute())

def get_config_dir():
    """Get the configuration directory path."""
    config_dir = os.path.join(get_app_root(), "config")
    os.makedirs(config_dir, exist_ok=True)
    return config_dir

def get_screenshots_dir():
    """Get the screenshots directory path."""
    screenshots_dir = os.path.join(get_app_root(), "screenshots")
    os.makedirs(screenshots_dir, exist_ok=True)
    return screenshots_dir

def get_logs_dir():
    """Get the logs directory path."""
    logs_dir = os.path.join(get_app_root(), "logs")
    os.makedirs(logs_dir, exist_ok=True)
    return logs_dir

def get_temp_dir():
    """Get the temporary directory path."""
    temp_dir = os.path.join(get_app_root(), ".tmp")
    os.makedirs(temp_dir, exist_ok=True)
    return temp_dir

def get_frequency_config_file():
    """Get the screenshot frequency configuration file path."""
    return os.path.join(get_config_dir(), "screenshot_frequency.json")