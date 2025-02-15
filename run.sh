#!/bin/bash

# Store the script's directory
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

# Deactivate any active conda environment
conda deactivate 2>/dev/null || true

# Remove existing venv if it exists
if [ -d "$SCRIPT_DIR/venv" ]; then
    echo "Removing existing virtual environment..."
    rm -rf "$SCRIPT_DIR/venv"
fi

# Create new venv using system Python
echo "Creating new virtual environment..."
/usr/bin/python3 -m venv "$SCRIPT_DIR/venv"

# Activate the new venv
source "$SCRIPT_DIR/venv/bin/activate"

# Upgrade pip and install requirements
echo "Installing dependencies..."
pip install --upgrade pip
pip install -r "$SCRIPT_DIR/req/requirements.txt"

# Run the main script
echo "Starting 33ter Process Manager..."
python3 "$SCRIPT_DIR/start_local_dev.py"