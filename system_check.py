"""System check utilities for Threethreeter application.

This module provides comprehensive system validation and requirement checking for the Threethreeter
application. It ensures all required dependencies, directories, and configurations are
available and properly set up before the application starts.

Key Features:
- Python version validation
- Tesseract OCR installation check
- Socket.IO dependency validation
- Directory permissions verification
- System information reporting

#TODO:
- Add disk space verification for screenshot storage
- Implement memory requirement validation
- Add GPU availability check for potential future features
- Consider adding network connectivity tests
- Add validation of system locale settings for OCR
- Implement dependency version compatibility matrix
"""

import os
import sys
import shutil
import platform
import subprocess
from typing import List, Tuple

def check_python_version() -> Tuple[bool, str]:
    """Check if Python version meets requirements."""
    major, minor = sys.version_info[:2]
    required = (3, 9)
    if (major, minor) >= required:
        return True, f"Python {major}.{minor} (✓)"
    return False, f"Python {major}.{minor} (✗) - Requires 3.9+"

def check_tesseract() -> Tuple[bool, str]:
    """Check if Tesseract OCR is installed."""
    tesseract_path = shutil.which('tesseract')
    if tesseract_path:
        try:
            version = subprocess.check_output([tesseract_path, '--version'], 
                                           stderr=subprocess.STDOUT,
                                           text=True).split()[1]
            return True, f"Tesseract {version} (✓)"
        except:
            return True, "Tesseract installed (✓)"
    return False, "Tesseract not found (✗)"

def check_socketio() -> Tuple[bool, str]:
    """Check if Socket.IO is available."""
    try:
        import socketio
        version = 1
        return True, f"Socket.IO {version} (✓)"
    except ImportError:
        return False, "Socket.IO not found (✗)"

def check_directories() -> List[Tuple[str, bool, str]]:
    """Check required directories exist and are writable."""
    from path_config import (
        get_project_root,
        get_screenshots_dir,
        get_logs_dir,
        get_temp_dir,
        get_config_dir
    )
    
    dirs = [
        ("App Root", get_project_root()),
        ("Config", get_config_dir()),
        ("Screenshots", get_screenshots_dir()),
        ("Logs", get_logs_dir()),
        ("Temp", get_temp_dir())
    ]
    
    results = []
    for name, path in dirs:
        exists = os.path.exists(path)
        writable = os.access(path, os.W_OK) if exists else False
        status = "(✓)" if exists and writable else "(✗)"
        results.append((name, exists and writable, f"{path} {status}"))
    
    return results

def print_system_status():
    """Print a formatted report of system status."""
    # Get terminal width
    try:
        width = os.get_terminal_size().columns
    except:
        width = 80
    
    # Print header
    print("=" * width)
    print("Threethreeter System Check".center(width))
    print("=" * width)
    
    # Check Python and core dependencies
    checks = [
        ("Python Version", check_python_version()),
        ("Tesseract OCR", check_tesseract()),
        ("Socket.IO", check_socketio())
    ]
    
    print("\nCore Dependencies:")
    print("-" * width)
    for name, (status, message) in checks:
        print(f"{name:<15} {message}")
    
    # Check directories
    print("\nDirectory Access:")
    print("-" * width)
    for name, status, message in check_directories():
        print(f"{name:<15} {message}")
    
    print("\nSystem Information:")
    print("-" * width)
    print(f"{'OS:':<15} {platform.system()} {platform.release()}")
    print(f"{'Platform:':<15} {platform.platform()}")
    print("=" * width)
    print()
    
    # Check if any critical components are missing
    critical_failures = [
        not status for name, (status, msg) in checks
        if name in ("Python Version", "Tesseract OCR")
    ]
    
    dir_failures = [
        not status for name, status, msg in check_directories()
    ]
    
    if any(critical_failures) or any(dir_failures):
        print("WARNING: Some critical components are missing or inaccessible!")
        print("Please address the issues marked with (✗) above.")
        print()
        return False
        
    return True

if __name__ == "__main__":
    print_system_status()