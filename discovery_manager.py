import socket
import logging
import atexit
import asyncio
from typing import Optional

try:
    from zeroconf import ServiceInfo, Zeroconf
    zeroconf_available = True
except ImportError:
    zeroconf_available = False
    # Define dummy classes if zeroconf is not installed
    class Zeroconf: pass
    class ServiceInfo: pass

from .network_utils import get_local_ip

class DiscoveryManager:
    """Manages Bonjour (mDNS/Zeroconf) service discovery for the server."""

    def __init__(self, logger: logging.Logger):
        self.logger = logger
        self.zeroconf_instance: Optional[Zeroconf] = None
        self.service_info: Optional[ServiceInfo] = None
        self.registered = False

        # CHANGE: Shorten service name to fit within 15 byte limit
        self.service_name = "t3t-io"  # Shortened from "Threethreeter-socketio"

        if not zeroconf_available:
            self.logger.warning("The 'zeroconf' library is not installed. Bonjour discovery will be disabled.")
            self.logger.warning("Install it using: pip install zeroconf")

    async def start_discovery(self,
                        port: int,
                        service_type: str = "_http._tcp.local."):
        """
        Starts advertising the service via Bonjour asynchronously.

        Args:
            port (int): The port the service is running on.
            service_type (str): The Bonjour service type string.
        """
        if not zeroconf_available or self.registered:
            return

        local_ip = get_local_ip() # This is synchronous, assumed fast enough
        if not local_ip:
            self.logger.error("Failed to determine local IP. Cannot start Bonjour discovery.")
            return

        try:
            # Run synchronous Zeroconf operations in a separate thread
            def _register():
                self.zeroconf_instance = Zeroconf()
                hostname = socket.gethostname().split('.')[0]
                full_service_name = f"{self.service_name} ({hostname}).{service_type}"

                self.service_info = ServiceInfo(
                    type_=service_type,
                    name=full_service_name,
                    addresses=[socket.inet_aton(local_ip)],
                    port=port,
                    properties={}, # Optional: Add server version, etc.
                )

                self.logger.info(f"Registering Bonjour service: {full_service_name} at {local_ip}:{port}")
                self.zeroconf_instance.register_service(self.service_info)
                self.registered = True
                self.logger.info("Bonjour service registered successfully.")
                # Ensure cleanup on exit - register synchronous version
                atexit.register(self._stop_discovery_sync)

            await asyncio.to_thread(_register)

        except Exception as e:
            self.logger.error(f"Failed to register Bonjour service: {e}", exc_info=True)
            # Cleanup if registration failed partway
            if self.zeroconf_instance:
                try:
                    await asyncio.to_thread(self.zeroconf_instance.close)
                except Exception as close_e:
                    self.logger.error(f"Error closing zeroconf instance during registration failure: {close_e}")
            self.zeroconf_instance = None
            self.service_info = None
            self.registered = False # Ensure registered is false on failure

    async def stop_discovery(self):
        """Stops advertising the service via Bonjour asynchronously."""
        if not zeroconf_available or not self.registered or not self.zeroconf_instance:
            return

        self.logger.info("Unregistering Bonjour service asynchronously...")
        try:
            # Run synchronous Zeroconf operations in a separate thread
            def _unregister():
                if self.service_info:
                    self.zeroconf_instance.unregister_service(self.service_info)
                self.zeroconf_instance.close()
                self.registered = False
                self.logger.info("Bonjour service unregistered.")
                # Attempt to remove from atexit
                try:
                    atexit.unregister(self._stop_discovery_sync)
                except ValueError:
                    pass # Already unregistered or never registered

            await asyncio.to_thread(_unregister)

        except Exception as e:
            self.logger.error(f"Error unregistering Bonjour service asynchronously: {e}", exc_info=True)
        finally:
            # Ensure state is reset even if thread fails
            self.zeroconf_instance = None
            self.service_info = None
            self.registered = False

    # Synchronous version for atexit
    def _stop_discovery_sync(self):
        """Synchronous version of stop_discovery for atexit handler."""
        if not zeroconf_available or not self.registered or not self.zeroconf_instance:
            return

        self.logger.info("Unregistering Bonjour service (atexit)...")
        try:
            if self.service_info:
                self.zeroconf_instance.unregister_service(self.service_info)
            self.zeroconf_instance.close()
            self.registered = False
            self.logger.info("Bonjour service unregistered (atexit).")
        except Exception as e:
            # Log error, but avoid raising exception in atexit
            self.logger.error(f"Error during atexit unregistration: {e}", exc_info=True)
        finally:
            self.zeroconf_instance = None
            self.service_info = None

