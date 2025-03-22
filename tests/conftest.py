"""Test configuration and fixtures for 33ter Socket.IO tests."""
import os
import sys
import pytest
import socketio
import asyncio
import pytest_asyncio
from aiohttp import web
from unittest.mock import Mock, patch
from typing import AsyncGenerator, Tuple

# Add application root to Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Mock pytesseract and other OCR-related imports
sys.modules['pytesseract'] = Mock()
sys.modules['PIL'] = Mock()
sys.modules['PIL.ImageGrab'] = Mock()

from socketio_server.server import sio as server_sio
from utils.server_config import DEFAULT_CONFIG

@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for each test case."""
    policy = asyncio.get_event_loop_policy()
    loop = policy.new_event_loop()
    yield loop
    loop.close()

@pytest.fixture
def test_config():
    """Provide test configuration."""
    return {
        "server": {
            "host": "127.0.0.1",
            "port": 5349,  # Different port for testing
            "room": "test_room",
            "cors_origins": "*",
            "log_level": "DEBUG"
        },
        "health_check": {
            "enabled": False
        }
    }

@pytest_asyncio.fixture
async def server_app(event_loop, test_config):
    """Provide test server application."""
    app = web.Application()
    server_sio.attach(app)
    
    runner = None
    try:
        # Configure test server
        server_url = f"http://{test_config['server']['host']}:{test_config['server']['port']}"
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, test_config['server']['host'], test_config['server']['port'])
        await site.start()
        
        yield app, server_url
    finally:
        if runner:
            await runner.cleanup()

@pytest_asyncio.fixture
async def client_sio():
    """Provide test Socket.IO client."""
    client = socketio.AsyncClient(logger=False, engineio_logger=False)
    yield client
    if client.connected:
        await client.disconnect()

@pytest_asyncio.fixture
async def connected_client(server_app, client_sio):
    """Provide connected test client."""
    app, server_url = server_app
    try:
        await client_sio.connect(server_url)
        yield client_sio
    finally:
        if client_sio.connected:
            await client_sio.disconnect()

@pytest_asyncio.fixture
async def screenshot_client(mock_screenshot_manager, test_config):
    """Provide configured screenshot client."""
    with patch('socketio_server.client.ScreenshotManager', return_value=mock_screenshot_manager):
        from socketio_server.client import ScreenshotClient
        client = ScreenshotClient()
        client.config = test_config
        yield client
        if hasattr(client, 'sio') and client.sio.connected:
            await client.disconnect()

@pytest.fixture
def mock_screenshot_manager():
    """Provide mock screenshot manager."""
    manager = Mock()
    manager.process_latest_screenshot.return_value = "Mock OCR Text"
    manager.is_capturing.return_value = False
    return manager