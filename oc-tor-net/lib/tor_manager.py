"""
Tor hidden service management
"""
import os
import time
import atexit
import tempfile
from pathlib import Path
from typing import Optional
import stem.control
import stem.process



class TorManager:
    """Manages Tor process and hidden service"""
    
    def __init__(self, data_dir: str = None, service_port: int = 8765):
        if data_dir is None:
            data_dir = os.path.expanduser("~/.openclaw/p2p/tor")
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        
        self.service_port = service_port
        self.tor_process = None
        self.controller = None
        self._onion_address: Optional[str] = None
    
    def is_running(self) -> bool:
        """Check if Tor is already running for this data dir"""
        pid_file = self.data_dir / "tor.pid"
        if pid_file.exists():
            try:
                with open(pid_file) as f:
                    pid = int(f.read().strip())
                # Check if process exists
                os.kill(pid, 0)
                return True
            except (OSError, ValueError):
                return False
        return False
    
    def start(self, socks_port: int = 9060, control_port: int = 9061) -> str:
        """
        Start Tor with a hidden service.
        Returns the .onion address.
        """
        if self.is_running():
            # Connect to existing Tor
            self.controller = stem.control.Controller.from_port(port=control_port)
            self.controller.authenticate()
            return self.get_onion_address()
        
        # Create hidden service directory with correct permissions
        hidden_service_dir = self.data_dir / "hidden_service"
        hidden_service_dir.mkdir(exist_ok=True)
        # Tor requires specific permissions
        os.chmod(hidden_service_dir, 0o700)
        
        print(f"Starting Tor (this may take 30-60 seconds)...")
        print(f"Data directory: {self.data_dir}")
        
        # Start Tor process
        def print_tor_line(line):
            if isinstance(line, bytes):
                line = line.decode()
            if "Bootstrapped" in line:
                print(f"  {line.strip()}")
        
        config = {
            'SocksPort': str(socks_port),
            'ControlPort': str(control_port),
            'CookieAuthentication': '1',
            'HiddenServiceDir': str(hidden_service_dir),
            'HiddenServicePort': f'80 127.0.0.1:{self.service_port}',
        }
        
        self.tor_process = stem.process.launch_tor_with_config(
            config=config,
            init_msg_handler=print_tor_line,
            take_ownership=True
        )
        
        # Connect to controller
        self.controller = stem.control.Controller.from_port(port=control_port)
        self.controller.authenticate()
        
        # Wait for hidden service to be published
        print("Waiting for hidden service to be published...")
        time.sleep(5)
        
        # Save PID
        pid_file = self.data_dir / "tor.pid"
        with open(pid_file, 'w') as f:
            f.write(str(self.tor_process.pid))
        
        self._onion_address = self._read_hostname()
        print(f"Hidden service ready: {self._onion_address}")
        
        return self._onion_address
    
    def _read_hostname(self) -> str:
        """Read the .onion address from the hidden service directory"""
        hostname_file = self.data_dir / "hidden_service" / "hostname"
        # Wait for file to exist
        for _ in range(30):
            if hostname_file.exists():
                with open(hostname_file) as f:
                    return f.read().strip()
            time.sleep(1)
        raise RuntimeError("Hidden service hostname not created")
    
    def get_onion_address(self) -> Optional[str]:
        """Get the .onion address"""
        if self._onion_address:
            return self._onion_address
        try:
            return self._read_hostname()
        except RuntimeError:
            return None
    
    def get_socks_proxy(self) -> dict:
        """Get SOCKS proxy config for requests"""
        return {
            'http': 'socks5h://127.0.0.1:9060',
            'https': 'socks5h://127.0.0.1:9060'
        }
    
    def stop(self):
        """Stop Tor process"""
        if self.controller:
            try:
                self.controller.close()
            except:
                pass
            self.controller = None
        
        if self.tor_process:
            try:
                self.tor_process.terminate()
                self.tor_process.wait()
            except:
                pass
            self.tor_process = None
        
        # Clean up PID file
        pid_file = self.data_dir / "tor.pid"
        if pid_file.exists():
            pid_file.unlink()
    
    def __del__(self):
        self.stop()
