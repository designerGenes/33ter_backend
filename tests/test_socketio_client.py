"""Tests for the Socket.IO client component of 33ter."""
import pytest
import asyncio
from unittest.mock import Mock, patch
from datetime import datetime

from socketio_server.client import ScreenshotClient

pytestmark = pytest.mark.asyncio

@pytest.fixture
def mock_screenshot_manager():
    """Provide mock screenshot manager."""
    manager = Mock()
    manager.process_latest_screenshot.return_value = "Mock OCR Text"
    manager.is_capturing.return_value = False
    return manager

@pytest.fixture
async def screenshot_client(mock_screenshot_manager, test_config):
    """Provide configured screenshot client."""
    with patch('socketio_server.client.ScreenshotManager', return_value=mock_screenshot_manager):
        client = ScreenshotClient()
        client.config = test_config
        yield client
        if client.sio.connected:
            await client.disconnect()

async def test_client_initialization(screenshot_client):
    """Test client initialization and configuration."""
    client = await screenshot_client.__anext__()
    assert client.sio is not None
    assert client.config['server']['room'] == 'test_room'
    assert not client.sio.connected

async def test_client_connection(screenshot_client, server_app):
    """Test client connection to server."""
    client = await screenshot_client.__anext__()
    app, server_url = await server_app.__anext__()
    
    # Override server URL in client config
    client.config['server']['host'] = '0.0.0.0'
    client.config['server']['port'] = 5349
    
    # Test connection
    assert await client.connect_to_server()
    assert client.sio.connected
    
    # Test disconnection
    await client.disconnect()
    assert not client.sio.connected

async def test_room_join_on_connect(screenshot_client, server_app):
    """Test automatic room joining on connection."""
    client = await screenshot_client.__anext__()
    app, server_url = await server_app.__anext__()
    
    room_joined = False
    @client.sio.on('join_room')
    def on_join_room(data):
        nonlocal room_joined
        room_joined = data.get('room') == client.config['server']['room']
    
    await client.connect_to_server()
    await asyncio.sleep(0.1)
    
    assert room_joined

async def test_ocr_trigger_handling(screenshot_client, server_app, mock_screenshot_manager):
    """Test handling of OCR trigger events."""
    client = await screenshot_client.__anext__()
    app, server_url = await server_app.__anext__()
    await client.connect_to_server()
    
    # Simulate OCR trigger
    await client.sio.emit('trigger_ocr')
    await asyncio.sleep(0.1)
    
    # Verify screenshot processing was triggered
    mock_screenshot_manager.process_latest_screenshot.assert_called_once()

async def test_client_count_updates(screenshot_client, server_app):
    """Test handling of client count updates."""
    client = await screenshot_client.__anext__()
    app, server_url = await server_app.__anext__()
    received_counts = []
    
    @client.sio.on('client_count')
    def on_client_count(data):
        received_counts.append(data.get('count', 0))
    
    await client.connect_to_server()
    await asyncio.sleep(0.1)
    
    # Server should send initial count
    assert len(received_counts) > 0

async def test_ocr_result_sending(screenshot_client, server_app):
    """Test sending OCR results to server."""
    client = await screenshot_client.__anext__()
    app, server_url = await server_app.__anext__()
    await client.connect_to_server()
    
    # Create a mock result receiver
    results_received = []
    @client.sio.on('ocr_result')
    def on_ocr_result(data):
        results_received.append(data)
    
    # Process and send a screenshot
    await client.process_latest_screenshot()
    await asyncio.sleep(0.1)
    
    # Verify result was sent
    assert len(results_received) > 0
    assert 'Mock OCR Text' in str(results_received)

async def test_screenshot_manager_lifecycle(screenshot_client, server_app, mock_screenshot_manager):
    """Test screenshot manager start/stop on connection/disconnection."""
    client = await screenshot_client.__anext__()
    app, server_url = await server_app.__anext__()
    
    # Connect should start capturing
    await client.connect_to_server()
    await asyncio.sleep(0.1)
    mock_screenshot_manager.start_capturing.assert_called_once()
    
    # Disconnect should stop capturing
    await client.disconnect()
    await asyncio.sleep(0.1)
    mock_screenshot_manager.stop_capturing.assert_called_once()

async def test_error_handling(screenshot_client, server_app, mock_screenshot_manager):
    """Test error handling during OCR processing."""
    client = await screenshot_client.__anext__()
    app, server_url = await server_app.__anext__()
    await client.connect_to_server()
    
    # Simulate OCR processing error
    mock_screenshot_manager.process_latest_screenshot.side_effect = Exception("Mock OCR Error")
    
    # Attempt processing
    await client.process_latest_screenshot()
    await asyncio.sleep(0.1)
    
    # Should not crash and continue running
    assert client.sio.connected

async def test_connection_failure(screenshot_client):
    """Test handling of connection failures."""
    client = await screenshot_client.__anext__()
    
    # Configure invalid server URL
    client.config['server']['port'] = 9999
    
    # Attempt connection
    assert not await client.connect_to_server()
    assert not client.sio.connected