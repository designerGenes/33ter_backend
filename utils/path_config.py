import os

def get_app_root():
    """Get the root directory of the application."""
    if os.getenv("RUN_MODE", "local").lower() == "docker":
        return "/app"
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def get_screenshots_dir():
    """Get the screenshots directory path."""
    return os.path.join(get_app_root(), "screenshots")

def get_logs_dir():
    """Get the logs directory path."""
    return os.path.join(get_app_root(), "logs")

def get_config_dir():
    """Get the config directory path."""
    return os.path.join(get_app_root(), "config")

def get_temp_dir():
    """Get the temporary directory path."""
    temp_dir = os.path.join(get_app_root(), ".tmp")
    os.makedirs(temp_dir, exist_ok=True)
    return temp_dir

def get_frequency_config_file():
    """Get the path to the screenshot frequency config file."""
    config_dir = os.path.join(get_app_root(), ".config")
    os.makedirs(config_dir, exist_ok=True)
    return os.path.join(config_dir, "screenshot_frequency.json")

def get_scripts_dir():
    """Get the scripts directory path."""
    return os.path.join(get_app_root(), "scripts")