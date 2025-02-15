import subprocess
import sys
import os
import platform
import shutil
from typing import Tuple, List, Dict, Optional

def get_linux_distribution() -> Optional[str]:
    """Detect Linux distribution."""
    try:
        with open('/etc/os-release') as f:
            lines = f.readlines()
            info = dict(line.strip().split('=', 1) for line in lines if '=' in line)
            return info.get('ID', '').strip('"')
    except:
        return None

def get_package_manager() -> Optional[Dict[str, str]]:
    """Detect available package manager and return commands."""
    if platform.system() == 'Darwin':
        if shutil.which('brew'):
            return {
                'install': 'brew install',
                'update': 'brew update',
                'name': 'Homebrew'
            }
    elif platform.system() == 'Linux':
        distro = get_linux_distribution()
        if distro in ['ubuntu', 'debian', 'pop', 'mint']:
            return {
                'install': 'sudo apt-get install',
                'update': 'sudo apt-get update',
                'name': 'apt'
            }
        elif distro in ['fedora', 'rhel', 'centos']:
            return {
                'install': 'sudo dnf install',
                'update': 'sudo dnf update',
                'name': 'dnf'
            }
        elif distro == 'arch':
            return {
                'install': 'sudo pacman -S',
                'update': 'sudo pacman -Syu',
                'name': 'pacman'
            }
        elif shutil.which('apk'):  # Alpine Linux
            return {
                'install': 'sudo apk add',
                'update': 'sudo apk update',
                'name': 'apk'
            }
    return None

def check_python_version() -> Tuple[bool, str]:
    """Check if Python version meets requirements."""
    major, minor = sys.version_info[:2]
    if major < 3 or (major == 3 and minor < 8):
        return False, f"Python 3.8+ required, found {major}.{minor}"
    return True, f"Python version {major}.{minor} OK"

def check_pip() -> Tuple[bool, str]:
    """Check if pip is installed and install if missing."""
    try:
        subprocess.run([sys.executable, "-m", "pip", "--version"], 
                      capture_output=True, check=True)
        return True, "pip is installed"
    except subprocess.CalledProcessError:
        print("pip not found, attempting to install...")
        try:
            # Download get-pip.py
            subprocess.run(["curl", "https://bootstrap.pypa.io/get-pip.py", "-o", "get-pip.py"], 
                         check=True)
            # Install pip
            subprocess.run([sys.executable, "get-pip.py", "--user"], check=True)
            # Clean up
            os.remove("get-pip.py")
            return True, "pip successfully installed"
        except Exception as e:
            return False, f"Failed to install pip: {e}"

def check_venv_module() -> Tuple[bool, str]:
    """Check if venv module is available and install if missing."""
    try:
        import venv
        return True, "venv module is available"
    except ImportError:
        print("venv module not found, attempting to install...")
        try:
            subprocess.run([sys.executable, "-m", "pip", "install", "virtualenv"], 
                         check=True)
            return True, "virtualenv installed as fallback"
        except Exception as e:
            return False, f"Failed to install virtualenv: {e}"

def check_gui_dependencies() -> List[Tuple[bool, str]]:
    """Check GUI-related dependencies (for pyautogui)."""
    checks = []
    
    if platform.system() == 'Linux':
        pkg_mgr = get_package_manager()
        if not pkg_mgr:
            return [(False, "Unsupported Linux distribution")]

        # Check for X11/Wayland
        display = os.environ.get('DISPLAY') or os.environ.get('WAYLAND_DISPLAY')
        if not display:
            checks.append((False, "No display server detected (X11/Wayland)"))
        else:
            checks.append((True, f"Display server detected: {display}"))

        # Check Tkinter
        try:
            import tkinter
            checks.append(("Tkinter", (True, "Tkinter is installed")))
        except ImportError:
            msg = f"Missing Tkinter. Install using: {pkg_mgr['install']} "
            if pkg_mgr['name'] == 'apt':
                msg += "python3-tk"
            elif pkg_mgr['name'] == 'dnf':
                msg += "python3-tkinter"
            elif pkg_mgr['name'] == 'pacman':
                msg += "tk"
            elif pkg_mgr['name'] == 'apk':
                msg += "py3-tkinter"
            checks.append(("Tkinter", (False, msg)))

        # Check for Scrot (screenshot tool)
        if not shutil.which('scrot'):
            msg = f"Missing scrot. Install using: {pkg_mgr['install']} scrot"
            checks.append(("Scrot", (False, msg)))
        else:
            checks.append(("Scrot", (True, "Scrot is installed")))

    elif platform.system() == 'Darwin':
        # macOS specific checks
        try:
            import Quartz
            checks.append(("Quartz", (True, "Quartz is available")))
        except ImportError:
            checks.append(("Quartz", (False, "Install pyobjc-framework-Quartz for better screenshot support")))

    return checks

def check_system_dependencies() -> List[Tuple[str, Tuple[bool, str]]]:
    """Check all system dependencies and return status list."""
    checks = [
        ("Python Version", check_python_version()),
        ("pip", check_pip()),
        ("venv", check_venv_module())
    ]
    
    # Get system info
    system = platform.system()
    if system == "Linux":
        distro = get_linux_distribution()
        pkg_mgr = get_package_manager()
        if pkg_mgr:
            checks.append(("Package Manager", (True, f"Using {pkg_mgr['name']}")))
        else:
            checks.append(("Package Manager", (False, "No supported package manager found")))
    
    # Add GUI dependency checks
    checks.extend(check_gui_dependencies())
            
    return checks

def print_system_status():
    """Print system status in a user-friendly format."""
    print("\n=== System Requirements Check ===")
    print(f"OS: {platform.system()} {platform.release()}")
    
    if platform.system() == "Linux":
        distro = get_linux_distribution()
        if distro:
            print(f"Distribution: {distro}")
    
    checks = check_system_dependencies()
    all_passed = True
    warnings = []
    
    for name, (status, message) in checks:
        status_symbol = "✓" if status else "✗"
        print(f"{status_symbol} {name}: {message}")
        if not status:
            if "warning" in message.lower():
                warnings.append(message)
            else:
                all_passed = False
    
    if warnings:
        print("\n⚠️  Warnings:")
        for warning in warnings:
            print(f"  - {warning}")
    
    if not all_passed:
        print("\n❌ Please install missing dependencies before continuing.")
        sys.exit(1)
    
    print("\n✓ All system requirements met!")