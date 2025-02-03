import os
import json
import pytest
from unittest.mock import Mock, patch
import sys

# Add the parent directory to the Python path so we can import submit_DeepSeek
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from submit_DeepSeek import submit_for_code_solution, log_to_socketio, send_to_socketio, discover_server_config

# Load test data
@pytest.fixture
def test_data():
    current_dir = os.path.dirname(os.path.abspath(__file__))
    with open(os.path.join(current_dir, 'test_raw_data.json'), 'r') as f:
        return json.load(f)

# Mock responses
@pytest.fixture
def mock_deepseek_response():
    return Mock(choices=[
        Mock(
            message=Mock(
                content="""
<CHALLENGE>
Given an integer array nums, find the subarray with the largest sum, and return its sum.
Example 1:
Input: nums = [-2,1,-3,4,-1,2,1,-5,4]
Output: 6
Explanation: The subarray [4,-1,2,1] has the largest sum 6.
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
    ])

@pytest.fixture(autouse=True)
def setup_global_client():
    """Setup the global client for all tests"""
    import submit_DeepSeek
    submit_DeepSeek.client = Mock()
    yield
    submit_DeepSeek.client = None

@pytest.mark.parametrize("run_mode", ["local", "docker"])
def test_discover_server_config(run_mode):
    with patch.dict('os.environ', {'RUN_MODE': run_mode}):
        host, port = discover_server_config()
        assert isinstance(host, str)
        assert isinstance(port, (int, str))
        if run_mode == "docker":
            assert host == "publish-message"
        else:
            assert host == "localhost"

@patch('requests.post')
def test_send_to_socketio(mock_post):
    mock_post.return_value = Mock(status_code=200, text="Success")
    test_message = {"data": {"title": "test", "message": "test message"}}
    
    send_to_socketio(test_message, "localhost", 5347)
    mock_post.assert_called_once()
    assert mock_post.call_args[1]['json'] == test_message

@patch('submit_DeepSeek.client')
def test_submit_for_code_solution(mock_client, test_data, mock_deepseek_response):
    mock_client.chat.completions.create.return_value = mock_deepseek_response
    
    with patch('submit_DeepSeek.log_to_socketio') as mock_log:
        submit_for_code_solution(test_data)
        
        # Verify logging calls
        assert mock_log.call_count >= 2  # Should have at least challenge and solution logs
        
        # Verify DeepSeek API call
        mock_client.chat.completions.create.assert_called_once()
        call_args = mock_client.chat.completions.create.call_args[1]
        assert call_args['model'] == "deepseek-chat"
        assert call_args['temperature'] == 0.1
        assert len(call_args['messages']) == 2

@patch('submit_DeepSeek.send_to_socketio')
def test_log_to_socketio(mock_send):
    test_message = "Test log message"
    log_to_socketio(test_message, title="Test", logType="info")
    
    mock_send.assert_called_once()
    call_args = mock_send.call_args[0][0]
    assert call_args['data']['title'] == "Test"
    assert call_args['data']['logType'] == "info"

def test_error_handling(test_data):
    with patch('submit_DeepSeek.client') as mock_client:
        mock_client.chat.completions.create.side_effect = Exception("API Error")
        
        with patch('submit_DeepSeek.log_to_socketio') as mock_log:
            result = submit_for_code_solution(test_data)
            assert result is None

if __name__ == '__main__':
    pytest.main([__file__])
