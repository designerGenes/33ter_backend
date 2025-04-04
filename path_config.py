"""Path configuration utilities for the Threethreeter application.

Provides functions to get standardized paths for various application directories
like logs, configuration, temporary files, and screenshots. Ensures consistency
across different modules.

#TODO:
- Add validation for path existence/permissions where necessary
- Consider platform-specific path handling improvements
- Add function to get path relative to project root
"""

import os
from pathlib import Path

# --- Project Root ---
def get_project_root() -> str:
    """Get the absolute path to the Threethreeter package directory."""
    # Returns the directory containing this file.
    return str(Path(__file__).parent.absolute())

# --- Configuration Directory ---
def get_config_dir() -> str:
    """Get the configuration directory path."""
    return os.path.join(get_project_root(), "config")

# --- Logs Directory ---
def get_logs_dir() -> str:
    """Get the logs directory path."""
    return os.path.join(get_project_root(), "logs")

# --- Temporary Directory ---
def get_temp_dir() -> str:
    """Get the temporary files directory path."""
    temp_dir = os.path.join(get_project_root(), "temp")
    os.makedirs(temp_dir, exist_ok=True) # Ensure it exists
    return temp_dir

# --- Screenshots Directory ---
def get_screenshots_dir() -> str:
    """Get the screenshots directory path."""
    screenshots_dir = os.path.join(get_project_root(), "screenshots")
    os.makedirs(screenshots_dir, exist_ok=True) # Ensure it exists
    return screenshots_dir

# --- Specific Config Files ---
def get_main_config_file():
    """Get the main configuration file path.≈"""
    return os.path.join(get_config_dir(), "config.json")

def get_server_config_file():
    """Get the server configuration file path."""
    return os.path.join(get_config_dir(), "server_config.json")

def get_frequency_config_file():
    """Get the screenshot frequency configuration file path."""
    return os.path.join(get_config_dir(), "screenshot_frequency.json")

# --- Tesseract Data Path ---
def get_tessdata_prefix() -> str:
    """Get the TESSDATA_PREFIX path."""
    # This might need adjustment based on actual install location
    # Common location for Homebrew on Apple Silicon
    default_path = "/opt/homebrew/share/tessdata/"
    # Allow overriding via environment variable
    return os.environ.get("TESSDATA_PREFIX", default_path)