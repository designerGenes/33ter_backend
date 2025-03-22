import pytest
import asyncio
import socketio

pytestmark = pytest.mark.asyncio

async def test_server_app_fixture(server_app):
    """Test the server_app fixture to ensure the test server starts correctly."""
    app, server_url = server_app  # Unpack the fixture result

    # Verify the server URL is correctly formatted
    assert server_url.startswith("http://"), "Server URL must start with http://"
    assert ":" in server_url, "Server URL must include a port"

    # Create a test client to connect to the server
    client = socketio.AsyncClient(logger=False, engineio_logger=False)
    try:
        # Connect to the server
        await client.connect(server_url, transports=["polling"], wait_timeout=5)
        assert client.connected, "Client should successfully connect to the server"

        # Disconnect from the server
        await client.disconnect()
        assert not client.connected, "Client should successfully disconnect from the server"
    finally:
        if client.connected:
            await client.disconnect()
