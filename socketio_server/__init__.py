"""SocketIO server package for 33ter.

This package provides the Socket.IO server and client implementations for real-time
communication between the Python screenshot service and iOS app.

Components:
- server: Socket.IO server implementation with room management and message routing
- client: Socket.IO client for sending OCR results and handling screenshot triggers

#TODO:
- Add proper connection pooling
- Implement message queuing for reliability
- Consider adding protocol versioning
- Add proper connection state recovery
- Implement proper authentication system
"""

import client 
import server

__all__ = [
    client,
    server
]