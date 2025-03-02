#!/usr/bin/env python3
import os
import sys
import subprocess
import shutil

def create_package_dirs(app_dir):
    """Create necessary package directories"""
    dirs = [
        os.path.join(app_dir, "socketio_server"),
        os.path.join(app_dir, "utils"),
        os.path.join(app_dir, "config"),
        os.path.join(app_dir, "logs"),
    ]
    for d in dirs:
        if not os.path.exists(d):
            os.makedirs(d)
        # Create __init__.py if it doesn't exist
        init_file = os.path.join(d, "__init__.py")
        if not os.path.exists(init_file):
            open(init_file, 'a').close()

def main():
    app_dir = os.path.dirname(os.path.abspath(__file__))
    venv_path = os.path.join(app_dir, "venv")

    # Remove existing venv if it exists
    if os.path.exists(venv_path):
        print(f"Removing existing virtual environment at {venv_path}")
        shutil.rmtree(venv_path)

    # Use system Python to create new venv
    base_python = '/usr/bin/python3'
    if not os.path.exists(base_python):
        print("Error: Could not find system Python. Please ensure Python 3 is installed.")
        sys.exit(1)

    print("Creating new virtual environment...")
    try:
        subprocess.run([base_python, "-m", "venv", venv_path], check=True)
    except subprocess.CalledProcessError as e:
        print(f"Error creating virtual environment: {e}")
        sys.exit(1)

    # Create package directories
    create_package_dirs(app_dir)

    # Get paths
    pip_path = os.path.join(venv_path, "bin", "pip")
    requirements_path = os.path.join(app_dir, "req", "requirements.txt")

    print("Installing dependencies...")
    try:
        # Upgrade pip
        subprocess.run([pip_path, "install", "--upgrade", "pip"], check=True)
        # Install requirements
        subprocess.run([pip_path, "install", "-r", requirements_path], check=True)
    except subprocess.CalledProcessError as e:
        print(f"Error installing dependencies: {e}")
        sys.exit(1)

    print("\nSetup complete! Now run:")
    print(f"source {venv_path}/bin/activate")
    print("export PYTHONPATH=$PYTHONPATH:/Users/jadennation/DEV/33ter/app")
    print("python3 socketio_server/client.py")

if __name__ == "__main__":
    main()