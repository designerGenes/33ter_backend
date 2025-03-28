"""Network diagnostics utilities for 33ter.

This module provides diagnostic tools for network configuration and connection issues.
It helps identify common Socket.IO connection problems by analyzing network interfaces,
checking port availability, and testing connectivity.
"""

import os
import socket
import subprocess
import platform
import logging
import json
from typing import Dict, List, Tuple, Optional, Any
import time

logger = logging.getLogger(__name__)

def check_host_resolution(host: str) -> bool:
    """Check if a hostname can be resolved to an IP address."""
    try:
        socket.gethostbyname(host)
        return True
    except socket.gaierror:
        return False

def check_port_availability(host: str, port: int) -> Tuple[bool, str]:
    """Check if a given port is available/in use."""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(2)
        result = sock.connect_ex((host, port))
        sock.close()
        
        if result == 0:
            return True, f"Port {port} is open on {host}"
        else:
            return False, f"Port {port} is not accessible on {host} (error: {result})"
    except Exception as e:
        return False, f"Error checking port {port} on {host}: {e}"

def get_network_interfaces() -> List[Dict[str, str]]:
    """Get all network interfaces and their IP addresses."""
    interfaces = []
    
    if platform.system() == "Darwin" or platform.system() == "Linux":
        try:
            # Use ifconfig on macOS/Linux
            if platform.system() == "Darwin":
                output = subprocess.check_output(["ifconfig"], text=True)
            else:
                output = subprocess.check_output(["ifconfig", "-a"], text=True)
                
            interface = None
            ip_address = None
            
            for line in output.split('\n'):
                if ': ' in line and not line.startswith('\t') and not line.startswith(' '):
                    # This is an interface line
                    if interface and ip_address:
                        interfaces.append({'name': interface, 'ip': ip_address})
                    
                    interface = line.split(': ')[0]
                    ip_address = None
                elif 'inet ' in line and interface:
                    # This is an IP address line
                    parts = line.strip().split()
                    idx = parts.index('inet')
                    if idx + 1 < len(parts):
                        ip_address = parts[idx + 1]
                        if '%' in ip_address:  # Handle macOS format with %interface suffix
                            ip_address = ip_address.split('%')[0]
                        
                        interfaces.append({'name': interface, 'ip': ip_address})
        except Exception as e:
            logger.error(f"Error getting network interfaces: {e}")
    elif platform.system() == "Windows":
        try:
            # Use ipconfig on Windows
            output = subprocess.check_output(["ipconfig"], text=True)
            interface = None
            for line in output.split('\n'):
                line = line.strip()
                if line and line[-1] == ':':
                    interface = line[:-1]
                elif 'IPv4 Address' in line and interface:
                    ip_address = line.split(':')[1].strip()
                    interfaces.append({'name': interface, 'ip': ip_address})
        except Exception as e:
            logger.error(f"Error getting network interfaces: {e}")
    
    return interfaces

def test_loopback_connectivity() -> Tuple[bool, str]:
    """Test if loopback connectivity is working properly."""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(2)
        
        # Try to bind to loopback address
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
        sock.listen(1)
        
        # Try to connect to it
        client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        client.settimeout(2)
        client.connect(('127.0.0.1', port))
        
        # Send data
        msg = b'test'
        client.sendall(msg)
        
        # Accept connection and receive data
        conn, addr = sock.accept()
        data = conn.recv(len(msg))
        
        # Cleanup
        client.close()
        conn.close()
        sock.close()
        
        if data == msg:
            return True, "Loopback connectivity test passed"
        else:
            return False, f"Loopback data corrupted: sent {msg}, received {data}"
    except Exception as e:
        return False, f"Loopback connectivity test failed: {e}"

def test_socket_server(host: str, port: int) -> Tuple[bool, str]:
    """Test if a Socket.IO server is responding correctly."""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(2)
        sock.connect((host, port))
        sock.close()
        return True, f"Socket.IO server at {host}:{port} is responding correctly"
    except Exception as e:
        return False, f"Socket.IO server test failed for {host}:{port}: {e}"

def run_diagnostics(host: str, port: int) -> Dict[str, Any]:
    """Run comprehensive network diagnostics and return results."""
    logger.info(f"Running network diagnostics for {host}:{port}")
    
    results = {
        "timestamp": time.time(),
        "host": host,
        "port": port,
        "tests": {}
    }
    
    # Test host resolution
    host_resolvable = check_host_resolution(host)
    results["tests"]["host_resolution"] = {
        "success": host_resolvable,
        "message": f"Host {host} is {'resolvable' if host_resolvable else 'not resolvable'}"
    }
    logger.info(f"Host resolution: {results['tests']['host_resolution']['message']}")
    
    # Test port availability
    port_available, port_message = check_port_availability(host, port)
    results["tests"]["port_availability"] = {
        "success": port_available,
        "message": port_message
    }
    logger.info(f"Port availability: {port_message}")
    
    # Test loopback connectivity
    loopback_ok, loopback_message = test_loopback_connectivity()
    results["tests"]["loopback_connectivity"] = {
        "success": loopback_ok,
        "message": loopback_message
    }
    logger.info(f"Loopback connectivity: {loopback_message}")
    
    # Test Socket.IO server
    socketio_ok, socketio_message = test_socket_server(host, port)
    results["tests"]["socketio_server"] = {
        "success": socketio_ok,
        "message": socketio_message
    }
    logger.info(f"Socket.IO server test: {socketio_message}")
    
    # Get network interfaces
    interfaces = get_network_interfaces()
    results["interfaces"] = interfaces
    logger.info(f"Network interfaces: {json.dumps(interfaces)}")
    
    # Overall assessment
    if not host_resolvable:
        results["assessment"] = "Host resolution failure. Check hostname or DNS configuration."
    elif not port_available:
        results["assessment"] = "Port not accessible. Check if server is running and firewall settings."
    elif not loopback_ok and (host == "localhost" or host == "127.0.0.1"):
        results["assessment"] = "Loopback connectivity issue. Check network stack configuration."
    elif not socketio_ok:
        results["assessment"] = "Socket.IO server not responding correctly. Check server process."
    else:
        results["assessment"] = "All basic connectivity tests passed."
    
    logger.info(f"Diagnostic assessment: {results['assessment']}")
    return results

if __name__ == "__main__":
    # Simple command-line usage
    import sys
    
    logging.basicConfig(level=logging.INFO)
    
    if len(sys.argv) >= 3:
        host = sys.argv[1]
        port = int(sys.argv[2])
    else:
        host = "127.0.0.1"
        port = 5348
    
    results = run_diagnostics(host, port)
    print(json.dumps(results, indent=2))
