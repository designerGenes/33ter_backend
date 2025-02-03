import os
import json
import pytest
from unittest.mock import Mock, patch, mock_open
import sys

# Add the parent directory to the Python path so we can import submit_DeepSeek
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from submit_DeepSeek import (
    submit_for_code_solution, 
    log_to_socketio, 
    send_to_socketio, 
    discover_server_config,
    setup_logs_dir,
    DEEPSEEK_SYSTEM_MESSAGE
)

# Load test data
@pytest.fixture
def test_data():
    current_dir = os.path.dirname(os.path.abspath(__file__))
    with open(os.path.join(current_dir, 'test_raw_data.json'), 'r') as f:
        return json.load(f)

@pytest.fixture
def mock_deepseek_api():
    return Mock(
        chat_completion=Mock(
            return_value="""
<CHALLENGE>
Given an integer array nums, find the subarray with the largest sum, and return its sum.
</CHALLENGE>
<SOLUTION>
func maxSubArray(_ nums: [Int]) -> Int {
    var currentSum = nums[0]
    var maxSum = nums[0]
    for i in 1..<nums.count {
        currentSum = max(nums[i], currentSum + nums[i])
        maxSum = max(maxSum, currentSum)
    }
    return maxSum
}
</SOLUTION>
"""
        )
    )

@pytest.fixture(autouse=True)
def setup_global_client():
    """Setup the global DeepSeek client for all tests"""
    import submit_DeepSeek
    submit_DeepSeek.deepseek_client = Mock()
    yield
    submit_DeepSeek.deepseek_client = None

@pytest.mark.parametrize("run_mode", ["local", "docker"])
def test_discover_server_config(run_mode):
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
def test_send_to_socketio(mock_post):
    mock_post.return_value = Mock(status_code=200, text="Success")
    test_message = {"data": {"title": "test", "message": "test message"}}
    
    send_to_socketio(test_message, "localhost", 5348)
    mock_post.assert_called_once()
    assert mock_post.call_args[1]['json'] == test_message

def test_setup_logs_dir():
    with patch('os.makedirs') as mock_makedirs:
        with patch.dict('os.environ', {'RUN_MODE': 'local'}):
            logs_dir = setup_logs_dir()
            assert logs_dir.endswith('logs')
            mock_makedirs.assert_called_once_with(logs_dir, exist_ok=True)

        mock_makedirs.reset_mock()
        with patch.dict('os.environ', {'RUN_MODE': 'docker'}):
            logs_dir = setup_logs_dir()
            assert logs_dir == '/app/logs'
            mock_makedirs.assert_called_once_with('/app/logs', exist_ok=True)

@patch('submit_DeepSeek.deepseek_client')
def test_submit_for_code_solution(mock_client, test_data, mock_deepseek_api):
    mock_client.chat_completion.return_value = mock_deepseek_api.chat_completion()
    
    with patch('submit_DeepSeek.log_to_socketio') as mock_log:
        submit_for_code_solution(test_data)
        
        # Verify logging calls
        assert mock_log.call_count >= 2
        
        # Verify DeepSeek API call
        mock_client.chat_completion.assert_called_once()
        call_args = mock_client.chat_completion.call_args[1]
        assert call_args['temperature'] == 0.1
        assert DEEPSEEK_SYSTEM_MESSAGE in call_args['prompt_sys']
        assert isinstance(call_args['prompt'], str)

@patch('submit_DeepSeek.send_to_socketio')
def test_log_to_socketio(mock_send):
    test_message = "Test log message"
    log_to_socketio(test_message, title="Test", logType="info")
    
    mock_send.assert_called_once()
    call_args = mock_send.call_args[0][0]
    assert call_args['data']['title'] == "Test"
    assert call_args['data']['logType'] == "info"

def test_error_handling(test_data):
    with patch('submit_DeepSeek.deepseek_client') as mock_client:
        mock_client.chat_completion.side_effect = Exception("API Error")
        
        with patch('submit_DeepSeek.log_to_socketio') as mock_log:
            result = submit_for_code_solution(test_data)
            assert result is None

if __name__ == '__main__':
    pytest.main([__file__])
