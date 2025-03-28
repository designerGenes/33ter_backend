import socket
import logging
import atexit
import time
from typing import Optional

try:
    from zeroconf import ServiceInfo, Zeroconf
    zeroconf_available = True
except ImportError:
    zeroconf_available = False
    # Define dummy classes if zeroconf is not installed
    class Zeroconf: pass
    class ServiceInfo: pass

from utils.network_utils import get_local_ip

class DiscoveryManager:
    """Manages Bonjour (mDNS/Zeroconf) service discovery for the server."""

    def __init__(self, logger: logging.Logger):
        self.logger = logger
        self.zeroconf_instance: Optional[Zeroconf] = None
        self.service_info: Optional[ServiceInfo] = None
        self.registered = False

        if not zeroconf_available:
            self.logger.warning("The 'zeroconf' library is not installed. Bonjour discovery will be disabled.")
            self.logger.warning("Install it using: pip install zeroconf")

    def start_discovery(self,
                        port: int,
                        service_type: str = "_33ter-socketio._tcp.local.",
                        service_name: str = "33ter Backend"):
        """
        Starts advertising the service via Bonjour.

        Args:
            port (int): The port the service is running on.
            service_type (str): The Bonjour service type string.
            service_name (str): The name for this specific service instance.
        """
        if not zeroconf_available or self.registered:
            return

        local_ip = get_local_ip()
        if not local_ip:
            self.logger.error("Failed to determine local IP. Cannot start Bonjour discovery.")
            return

        try:
            self.zeroconf_instance = Zeroconf()
            # Ensure a unique name if multiple instances might run
            hostname = socket.gethostname().split('.')[0]
            full_service_name = f"{service_name} ({hostname}).{service_type}"

            self.service_info = ServiceInfo(
                type_=service_type,
                name=full_service_name,
                addresses=[socket.inet_aton(local_ip)],
                port=port,
                properties={}, # Optional: Add server version, etc.
                # server=f"{hostname}.local." # Optional: Specify server hostname
            )

            self.logger.info(f"Registering Bonjour service: {full_service_name} at {local_ip}:{port}")
            self.zeroconf_instance.register_service(self.service_info)
            self.registered = True
            self.logger.info("Bonjour service registered successfully.")

            # Ensure cleanup on exit
            atexit.register(self.stop_discovery)

        except Exception as e:
            self.logger.error(f"Failed to register Bonjour service: {e}", exc_info=True)
            if self.zeroconf_instance:
                self.zeroconf_instance.close()
            self.zeroconf_instance = None
            self.service_info = None

    def stop_discovery(self):
        """Stops advertising the service via Bonjour."""
        if not zeroconf_available or not self.registered or not self.zeroconf_instance:
            return

        self.logger.info("Unregistering Bonjour service...")
        try:
            if self.service_info:
                self.zeroconf_instance.unregister_service(self.service_info)
            self.zeroconf_instance.close()
            self.registered = False
            self.logger.info("Bonjour service unregistered.")
        except Exception as e:
            self.logger.error(f"Error unregistering Bonjour service: {e}", exc_info=True)
        finally:
            self.zeroconf_instance = None
            self.service_info = None
            # Attempt to remove from atexit to prevent multiple calls if stopped manually
            try:
                atexit.unregister(self.stop_discovery)
            except ValueError: # Already unregistered or never registered
                pass

