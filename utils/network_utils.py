import socket
import logging

logger = logging.getLogger('33ter-NetworkUtils')

def get_local_ip() -> str | None:
    """
    Attempts to determine the primary local IP address of the machine.

    Returns:
        str: The local IP address if found, otherwise None.
    """
    s = None
    try:
        # Connect to an external host (doesn't actually send data)
        # Using Google's public DNS server IP
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(0.1) # Prevent hanging if network is down
        s.connect(('8.8.8.8', 1))
        ip = s.getsockname()[0]
        logger.debug(f"Determined local IP: {ip}")
        return ip
    except Exception as e:
        logger.warning(f"Could not determine local IP address: {e}")
        # Fallback: try getting hostname then resolving it
        try:
            hostname = socket.gethostname()
            ip = socket.gethostbyname(hostname)
            if ip and not ip.startswith("127."):
                 logger.debug(f"Determined local IP via hostname: {ip}")
                 return ip
            else:
                 logger.warning(f"IP from hostname ({ip}) is loopback or invalid.")
        except Exception as host_e:
             logger.error(f"Could not determine local IP via hostname: {host_e}")
        return None
    finally:
        if s:
            s.close()

