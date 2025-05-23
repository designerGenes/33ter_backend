#!/usr/bin/env python3
"""Configuration checker for the Threethreeter application.

This module provides utilities for validating and troubleshooting configuration files
and settings. It helps identify missing or invalid configuration entries and provides
detailed feedback about the configuration state.

Key Features:
- Configuration path validation
- JSON syntax validation
- Required key verification
- Configuration content display
- Cross-reference validation

#TODO:
- Add configuration format versioning
- Implement configuration dependency checking
- Add value range validation
- Consider adding configuration repair suggestions
- Implement configuration backup before changes
- Add configuration migration support
"""

import os
import sys
import json

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from .path_config import get_server_config_file, get_config_dir
from .server_config import get_server_config

def check_config_paths():
    """Check configuration paths and files."""
    print("Checking configuration paths:")
    
    config_dir = get_config_dir()
    print(f"Config directory: {config_dir}")
    print(f"  Exists: {os.path.exists(config_dir)}")
    
    server_config_file = get_server_config_file()
    print(f"Server config file: {server_config_file}")
    print(f"  Exists: {os.path.exists(server_config_file)}")
    
    if os.path.exists(server_config_file):
        try:
            with open(server_config_file, 'r') as f:
                data = json.load(f)
                print(f"  Valid JSON: Yes")
                print(f"  Contents: {json.dumps(data, indent=2)}")
        except Exception as e:
            print(f"  Valid JSON: No - {e}")

def check_server_config():
    """Check server configuration loading."""
    print("\nChecking server configuration:")
    
    try:
        config = get_server_config()
        print(f"Server config loaded: {'Yes' if config else 'No'}")
        print(f"Contents: {json.dumps(config, indent=2)}")
        
        # Check required keys
        if 'server' in config:
            server = config['server']
            required = ['host', 'port', 'room']
            for key in required:
                print(f"  '{key}' present: {key in server}")
        else:
            print("  'server' section missing")
            
    except Exception as e:
        print(f"Error loading server config: {e}")

def main():
    """Main entry point."""
    check_config_paths()
    check_server_config()

if __name__ == "__main__":
    main()
