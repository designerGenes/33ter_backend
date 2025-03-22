"""Tests for the Socket.IO server component of 33ter."""
import pytest
import asyncio
from datetime import datetime
from unittest.mock import Mock
import socketio 


pytestmark = pytest.mark.asyncio

# Add timeout constant for socket operations
SOCKET_TIMEOUT = 1.0

@pytest.fixture
async def multi_clients():
    """Fixture for testing multiple client scenarios."""
    clients = []
    try:
        for _ in range(2):
            client = socketio.AsyncClient()
            clients.append(client)
        yield clients
    finally:
        for client in clients:
            if client.connected:
                await client.disconnect()

async def test_client_connection(server_app, client_sio, test_config):
    """Test basic client connection and disconnection."""
    app, server_url = server_app   # Changed from await server_app.__anext__()
    client = client_sio            # Changed from await client_sio.__anext__()
    
    try:
        await asyncio.wait_for(client.connect(server_url), timeout=SOCKET_TIMEOUT)
        assert client.connected
        
        await asyncio.wait_for(client.disconnect(), timeout=SOCKET_TIMEOUT)
        assert not client.connected
    except asyncio.TimeoutError:
        pytest.fail("Socket operation timed out")

async def test_room_management(connected_client, test_config):
    """Test joining and leaving rooms."""
    client = connected_client  # Changed from await connected_client.__anext__()
    
    # Test joining room
    received_messages = []
    @client.on('message')
    def on_message(data):
        received_messages.append(data)
    
    await client.emit('join_room', {'room': test_config['server']['room']})
    await asyncio.sleep(0.1)  # Allow time for server processing
    
    # Verify welcome message was received
    assert len(received_messages) == 1
    assert received_messages[0]['type'] == 'info'
    assert test_config['server']['room'] in received_messages[0]['data']['message']
    
    # Test leaving room
    await client.emit('leave_room', {'room': test_config['server']['room']})
    await asyncio.sleep(0.1)

async def test_client_count_broadcast(server_app, multi_clients, test_config):
    """Test client count broadcasting."""
    app, server_url = server_app
    clients = await anext(multi_clients)
    client1, client2 = clients
    
    received_counts = []
    connection_event = asyncio.Event()
    
    @client1.on('client_count')
    def on_client_count(data):
        count = data.get('count', 0)
        received_counts.append(count)
        connection_event.set()
    
    try:
        # Connect first client
        await client1.connect(server_url)
        await asyncio.wait_for(connection_event.wait(), timeout=SOCKET_TIMEOUT)
        connection_event.clear()
        
        assert 1 in received_counts, "First client count not received"
        
        # Connect second client
        await client2.connect(server_url)
        await asyncio.wait_for(connection_event.wait(), timeout=SOCKET_TIMEOUT)
        connection_event.clear()
        
        assert 2 in received_counts, "Second client count not received"
        
        # Disconnect second client
        await client2.disconnect()
        await asyncio.wait_for(connection_event.wait(), timeout=SOCKET_TIMEOUT)
        
        assert 1 in received_counts, "Final client count not received"
        
    except asyncio.TimeoutError:
        pytest.fail("Socket operation timed out")
    except Exception as e:
        pytest.fail(f"Test failed: {str(e)}")
    finally:
        for client in [client1, client2]:
            if client.connected:
                await client.disconnect()

async def test_ocr_result_handling(connected_client, test_config):
    """Test OCR result transmission and reception."""
    client = connected_client
    
    message_received = asyncio.Event()
    received_messages = []
    
    @client.on('message')
    def on_message(data):
        print(f"Received message: {data}")  # Add debug logging
        received_messages.append(data)
        message_received.set()
    
    try:
        # Join test room
        await asyncio.wait_for(
            client.emit('join_room', {'room': test_config['server']['room']}),
            timeout=SOCKET_TIMEOUT * 2
        )
        await asyncio.wait_for(message_received.wait(), timeout=SOCKET_TIMEOUT * 2)
        message_received.clear()
        
        # Wait a bit after joining room
        await asyncio.sleep(0.1)
        
        # Send test OCR result
        test_text = "def test_function():\\n    pass"
        await asyncio.wait_for(
            client.emit('ocr_result', [{
                'text': test_text,
                'timestamp': datetime.now().isoformat()
            }]),
            timeout=SOCKET_TIMEOUT * 2
        )
        
        # Wait for response with increased timeout
        try:
            await asyncio.wait_for(message_received.wait(), timeout=SOCKET_TIMEOUT * 4)
        except asyncio.TimeoutError:
            print(f"Received messages so far: {received_messages}")  # Add debug logging
            raise
            
        messages = [msg for msg in received_messages if msg['type'] == 'prime']
        assert len(messages) > 0, "No OCR result message received"
        assert messages[-1]['data']['text'] == test_text
        
    except asyncio.TimeoutError:
        pytest.fail("Socket operation timed out")
    finally:
        if client.connected:
            await client.disconnect()

async def test_trigger_ocr(connected_client, test_config):
    """Test OCR trigger functionality."""
    client = connected_client  # Changed from await connected_client.__anext__()
    
    trigger_received = False
    @client.on('trigger_ocr')
    def on_trigger():
        nonlocal trigger_received
        trigger_received = True
    
    # Join test room
    await client.emit('join_room', {'room': test_config['server']['room']})
    await asyncio.sleep(0.1)
    
    # Trigger OCR
    await client.emit('trigger_ocr')
    await asyncio.sleep(0.1)
    
    assert trigger_received

async def test_custom_message_handling(connected_client, test_config):
    """Test custom message handling."""
    client = await connected_client.__anext__()
    
    received_messages = []
    @client.on('message')
    def on_message(data):
        received_messages.append(data)
    
    # Join test room
    await client.emit('join_room', {'room': test_config['server']['room']})
    await asyncio.sleep(0.1)
    
    # Send custom message
    test_message = {
        'type': 'custom',
        'title': 'Test Title',
        'message': 'Test Message',
        'msg_type': 'info'
    }
    await client.emit('message', test_message)
    await asyncio.sleep(0.1)
    
    # Verify message was received
    assert any(msg == test_message for msg in received_messages)

async def test_invalid_room_join(connected_client):
    """Test handling of invalid room join attempts."""
    client = await connected_client.__anext__()
    
    received_messages = []
    @client.on('message')
    def on_message(data):
        received_messages.append(data)
    
    # Test with missing room field
    await client.emit('join_room', {})
    await asyncio.sleep(0.1)
    
    # Test with invalid data type
    await client.emit('join_room', 'invalid')
    await asyncio.sleep(0.1)
    
    # Test with empty room name
    await client.emit('join_room', {'room': ''})
    await asyncio.sleep(0.1)
    
    # No welcome messages should be received for invalid attempts
    assert not any(
        msg['type'] == 'info' and 'Connected to 33ter server' in msg.get('data', {}).get('message', '')
        for msg in received_messages
    )

# Add test for concurrent room operations
async def test_concurrent_room_joins(multi_clients, test_config):
    """Test concurrent room join operations."""
    client1, client2 = await multi_clients.__anext__()
    
    received_messages1 = []
    received_messages2 = []
    
    @client1.on('message')
    def on_message1(data):
        received_messages1.append(data)
        
    @client2.on('message')
    def on_message2(data):
        received_messages2.append(data)
    
    # Join same room concurrently
    await asyncio.gather(
        client1.emit('join_room', {'room': test_config['server']['room']}),
        client2.emit('join_room', {'room': test_config['server']['room']})
    )
    await asyncio.sleep(0.1)
    
    # Both clients should receive welcome messages
    assert any('Connected to 33ter server' in msg.get('data', {}).get('message', '')
              for msg in received_messages1)
    assert any('Connected to 33ter server' in msg.get('data', {}).get('message', '')
              for msg in received_messages2)