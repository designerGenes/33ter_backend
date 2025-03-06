import pytest
from unittest.mock import Mock, patch, mock_open
import os
from typing import Tuple
from app.socket.socketio_utils import (
    discover_server_config,
    send_to_socketio,
    log_to_socketio,
    MAGIC_DEFAULT_PORT
)

@pytest.mark.parametrize("run_mode", ["local", "docker"])
def test_discover_server_config(run_mode: str) -> Tuple[str, int]:
    mock_config = {
        'local': '{"ip": "localhost", "port": 5348}',
        'docker': '{"ip": "host.docker.internal", "port": 5348}'
    }
    
    with patch.dict('os.environ', {'RUN_MODE': run_mode}):
        with patch('builtins.open', mock_open(read_data=mock_config[run_mode])):
            host, port = discover_server_config()
            assert isinstance(host, str)
            assert isinstance(port, (int, str))
            if run_mode == "docker":
                assert host == "host.docker.internal"
            else:
                assert host == "localhost"

@patch('requests.post')
def test_send_to_socketio(mock_post: Mock) -> None:
    mock_post.return_value = Mock(status_code=200, text="Success")
    test_message = {"data": {"title": "test", "message": "test message"}}
    
    send_to_socketio(test_message, "localhost", 5348)
    mock_post.assert_called_once()
    assert mock_post.call_args[1]['json'] == test_message

@patch('app.socket.socketio_utils.send_to_socketio')
def test_log_to_socketio(mock_send: Mock) -> None:
    test_message = "Test log message"
    log_to_socketio(test_message, title="Test", logType="info")
    
    mock_send.assert_called_once()
    call_args = mock_send.call_args[0][0]
    assert call_args['data']['title'] == "Test"
    assert call_args['data']['logType'] == "info"