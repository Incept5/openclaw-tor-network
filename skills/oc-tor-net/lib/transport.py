"""
Abstract transport layer for P2P communication.
Supports Tor and I2P as pluggable transports.
"""
import json
import os
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional


class TransportManager(ABC):
    """Abstract base class for transport managers (Tor, I2P, etc.)"""

    @abstractmethod
    def start(self) -> str:
        """Start the transport and return the reachable address (.onion or .b32.i2p)."""

    @abstractmethod
    def stop(self):
        """Stop the transport."""

    @abstractmethod
    def is_running(self) -> bool:
        """Check if the transport is currently running."""

    @abstractmethod
    def get_proxy(self) -> dict:
        """Get SOCKS proxy config dict for the requests library."""

    @abstractmethod
    def get_address(self) -> Optional[str]:
        """Get the reachable address for this transport."""

    def http_post(self, url: str, json_data: dict, timeout: int = 30) -> tuple:
        """Send an HTTP POST to a peer via the transport.
        Returns (status_code, response_body) or raises on failure.
        Default implementation uses requests + SOCKS proxy."""
        import requests
        response = requests.post(url, json=json_data, proxies=self.get_proxy(), timeout=timeout)
        return response.status_code, response.text

    def http_get(self, url: str, timeout: int = 10) -> tuple:
        """Send an HTTP GET to a peer via the transport.
        Returns (status_code, response_body) or raises on failure.
        Default implementation uses requests + SOCKS proxy."""
        import requests
        response = requests.get(url, proxies=self.get_proxy(), timeout=timeout)
        return response.status_code, response.text

    @staticmethod
    @abstractmethod
    def check_daemon(config_dir: str = None) -> dict:
        """Check if the daemon is running. Returns status dict."""


class TransportFactory:
    """Creates the appropriate TransportManager based on config."""

    @staticmethod
    def get_transport_type(config_dir: str = None) -> str:
        """Read transport preference from config. Defaults to 'tor'."""
        if config_dir is None:
            config_dir = os.path.expanduser("~/.openclaw/p2p")
        config_file = Path(config_dir) / "config.json"
        if config_file.exists():
            try:
                with open(config_file) as f:
                    config = json.load(f)
                return config.get('transport', 'tor')
            except (json.JSONDecodeError, OSError):
                pass
        return 'tor'

    @staticmethod
    def create(transport_type: str = None, data_dir: str = None,
               service_port: int = 8765) -> TransportManager:
        """Create a TransportManager for the given transport type."""
        if transport_type is None:
            transport_type = TransportFactory.get_transport_type()

        transport_type = transport_type.lower()

        if transport_type == 'tor':
            from tor_manager import TorManager
            return TorManager(data_dir=data_dir, service_port=service_port)
        elif transport_type == 'i2p':
            from i2p_manager import I2PManager
            return I2PManager(data_dir=data_dir, service_port=service_port)
        else:
            raise ValueError(f"Unknown transport type: {transport_type}. Use 'tor' or 'i2p'.")

    @staticmethod
    def check_daemon(config_dir: str = None) -> dict:
        """Check daemon status, auto-detecting transport from daemon.json."""
        if config_dir is None:
            config_dir = os.path.expanduser("~/.openclaw/p2p")
        config_file = Path(config_dir) / "daemon.json"
        if not config_file.exists():
            return {'running': False, 'error': 'No daemon.json found. Run oc-tor-net-start.py first.'}
        try:
            with open(config_file) as f:
                config = json.load(f)
            pid = config.get('pid')
            if pid:
                os.kill(pid, 0)
            return {'running': True, **config}
        except (OSError, ProcessLookupError):
            return {'running': False, 'error': 'Daemon process is not running. Restart with oc-tor-net-start.py.'}
        except (json.JSONDecodeError, KeyError) as e:
            return {'running': False, 'error': f'Corrupt daemon.json: {e}'}
