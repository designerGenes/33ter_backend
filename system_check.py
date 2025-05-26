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
        version = socketio.__version__ if hasattr(socketio, '__version__') else "unknown"
        return True, f"Socket.IO {version} (✓)"
    except ImportError:
        return False, "Socket.IO not found (✗)"

def check_directories() -> List[Tuple[str, bool, str]]:
    """Check if required directories exist or can be created."""
    from .path_config import get_temp_dir, get_logs_dir, get_screenshots_dir
    
    directories = [
        ("Temp directory", get_temp_dir()),
        ("Logs directory", get_logs_dir()),
        ("Screenshots directory", get_screenshots_dir())
    ]
    
    results = []
    for name, path in directories:
        try:
            if not os.path.exists(path):
                os.makedirs(path, exist_ok=True)
            
            # Test write permissions
            test_file = os.path.join(path, ".test_write")
            with open(test_file, 'w') as f:
                f.write("test")
            os.remove(test_file)
            
            results.append((name, True, f"{path} (✓)"))
        except Exception as e:
            results.append((name, False, f"{path} - Error: {e} (✗)"))
    
    return results

def check_system_requirements_silent() -> bool:
    """Check system requirements without producing output. Returns True if all checks pass."""
    try:
        # Check Python version
        python_ok, _ = check_python_version()
        if not python_ok:
            return False
        
        # Check Tesseract
        tesseract_ok, _ = check_tesseract()
        if not tesseract_ok:
            return False
        
        # Check Socket.IO
        socketio_ok, _ = check_socketio()
        # Socket.IO is not critical for silent mode startup
        
        # Check directories
        dir_results = check_directories()
        for name, status, message in dir_results:
            if not status:
                return False
        
        return True
    except Exception:
        return False

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