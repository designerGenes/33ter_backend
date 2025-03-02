# 33ter Python Client

This is the Python client component for the 33ter application, which captures screenshots, performs OCR, and communicates with the iOS app via Socket.IO.

## Overview

The Python client consists of two main components:

1. **Socket.IO Server**: Acts as a communication bridge between the Python client and iOS app.
2. **Python Client**: Captures screenshots continuously, performs OCR when triggered by the iOS app, and sends results via Socket.IO.

## Features

- Automatic screenshot capture at configurable intervals
- Local OCR processing using Tesseract
- Direct communication with iOS app via Socket.IO
- Pause/resume screenshot capture
- Automatic cleanup of old screenshots
- Support for both local and Docker environments

## Requirements

- Python 3.9 or higher
- Tesseract OCR
- Dependencies in `requirements.txt`

## Installation

### Install Tesseract OCR

#### On macOS:
```bash
brew install tesseract
```

#### On Ubuntu/Debian:
```bash
sudo apt-get update
sudo apt-get install tesseract-ocr libtesseract-dev
```

#### On Windows:
Download and install from [Tesseract GitHub](https://github.com/UB-Mannheim/tesseract/wiki).

### Install Python Dependencies
```bash
pip install -r requirements.txt
```

## Running the Application

### Using the Startup Script (Recommended)

The start.sh script launches both the Socket.IO server and Python client:

```bash
chmod +x start.sh  # Make executable (first time only)
./start.sh
```

Options:
- `-p, --port PORT`: Socket.IO server port (default: 5348)
- `-r, --room ROOM`: Socket.IO room name (default: 33ter_room)
- `-d, --debug`: Enable debug mode (more verbose logging)
- `-h, --help`: Show help message

### Running Components Separately

1. Start the Socket.IO server:
```bash
python socketio_server.py
```

2. Start the Python client in another terminal:
```bash
python socketio_client.py
```

## Using Docker

1. Build and start both services:
```bash
docker-compose up -d
```

2. Check logs:
```bash
docker-compose logs -f
```

3. Stop services:
```bash
docker-compose down
```

## Configuration

The `server_config.json` file contains configuration for both the server and client:

```json
{
  "ip": "localhost",
  "port": 5348,
  "room": "33ter_room"
}
```

- `ip`: IP address of the Socket.IO server
- `port`: Port to run the Socket.IO server on
- `room`: Default room name for Socket.IO communication

## iOS App Integration

The iOS app connects to the Socket.IO server and can:

1. Receive screenshots and OCR results from the Python client
2. Trigger OCR processing on the most recent screenshot
3. Control screenshot capture (pause/resume)

## Communication Protocol

The Socket.IO server handles the following events:

- `connect`: Client connection event
- `disconnect`: Client disconnection event
- `join_room`: Client joining a room
- `trigger_ocr`: iOS app triggers OCR on the latest screenshot
- `ocr_result`: Python client sends OCR results
- `ocr_error`: Python client sends OCR error
- `message`: General messaging

## Directory Structure

- `screenshots/`: Stores captured screenshots
- `logs/`: Contains log files
- `.tmp/`: Temporary files and signals
- `utils/`: Utility modules
- `Dockerfiles/`: Docker configuration files

## Troubleshooting

### Common Issues

1. **Socket.IO connection issues**:
   - Verify the server IP in `server_config.json` is correct
   - Ensure the port is available (default: 5348)

2. **OCR not working**:
   - Verify Tesseract is installed and in PATH
   - Check logs for specific errors

3. **Screenshots not being captured**:
   - Verify the Python client has permission to capture screenshots
   - On macOS, ensure Screen Recording permission is granted

## Support

For assistance, file an issue in the project repository.