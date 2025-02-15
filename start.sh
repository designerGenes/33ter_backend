#!/bin/bash

# Function to check if a command exists
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# Detect Python command (prefer python3, fallback to python)
if command_exists python3; then
    PYTHON_CMD="python3"
elif command_exists python; then
    # Check if python is actually python3
    PYTHON_VER=$(python -c "import sys; print(sys.version_info[0])")
    if [ "$PYTHON_VER" -eq 3 ]; then
        PYTHON_CMD="python"
    else
        echo "Error: Python 3 is required but not found"
        exit 1
    fi
else
    echo "Error: Python 3 is required but not found"
    exit 1
fi

# Get the directory where the script is located
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

# Change to the app directory
cd "$DIR/app"

# Run the application
exec "$PYTHON_CMD" start_local_dev.py "$@"