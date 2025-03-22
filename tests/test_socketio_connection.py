#!/usr/bin/env python3
"""Test suite for Socket.IO server connection verification."""

import os
import sys
import time
import pytest
import socketio
import subprocess
from pathlib import Path
import select

# Add app root to Python path
app_root = str(Path(__file__).parent.parent.absolute())
if app_root not in sys.path:
    sys.path.insert(0, app_root)

def read_process_output(process, timeout=0.1):
    """Read from process stdout/stderr with timeout."""
    reads = [process.stdout, process.stderr]
    ret = select.select(reads, [], [], timeout)
    
    if not ret[0]:
        return None
        
    for pipe in ret[0]:
        line = pipe.readline()
        if line:
            return line.decode().strip()
    return None

def test_socketio_server_connection():
    """Test direct Socket.IO server startup and connection."""
    
    # Get path to server script
    server_script = os.path.join(app_root, 'socketio_server', 'server.py')
    assert os.path.exists(server_script), f"Server script not found at {server_script}"
    
    # Create environment with proper Python path
    env = os.environ.copy()
    env['PYTHONPATH'] = app_root
    
    # Start server process with output capture
    host = '127.0.0.1'
    port = 5348
    
    # Create process with both stdout and stderr pipes
    process = subprocess.Popen([
        sys.executable,
        '-u',  # Unbuffered output
        server_script,
        '--host', host,
        '--port', str(port),
        '--room', 'test_room',
        '--log-level', 'DEBUG'
    ], stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env)
    
    try:
        # Wait and check for server startup
        start_time = time.time()
        server_started = False
        error_output = []
        
        while time.time() - start_time < 10:  # 10 second timeout
            if process.poll() is not None:
                # Process terminated, collect error output
                error = process.stderr.read().decode()
                raise Exception(f"Server process terminated unexpectedly\nError output:\n{error}")
            
            line = read_process_output(process)
            if line:
                print(f"Server output: {line}")
                error_output.append(line)
                if "Running on" in line:
                    server_started = True
                    print("Server started successfully")
                    break
            time.sleep(0.1)
        
        if not server_started:
            raise Exception(f"Server failed to start\nOutput:\n" + "\n".join(error_output))
        
        # Create client
        sio = socketio.Client(logger=True)
        connected = False
        
        @sio.event
        def connect():
            nonlocal connected
            print("Connected to server!")
            connected = True
        
        @sio.event
        def connect_error(data):
            print(f"Connection error: {data}")
        
        # Try to connect
        url = f"http://{host}:{port}"
        print(f"Attempting to connect to {url}")
        sio.connect(url, wait_timeout=5)
        
        # Wait briefly for connection events
        time.sleep(1)
        assert connected, "Failed to establish Socket.IO connection"
        
    except Exception as e:
        print("\nServer Error Output:")
        print(process.stderr.read().decode())
        raise
        
    finally:
        # Cleanup
        if 'sio' in locals():
            try:
                sio.disconnect()
            except:
                pass
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()

if __name__ == '__main__':
    pytest.main([__file__, '-v'])
