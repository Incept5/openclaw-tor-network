"""
I2P transport management via SAM v3.3 protocol.
Direct SAM protocol implementation — no external library dependency.
Requires i2pd running with SAM bridge enabled (default port 7656).
"""
import os
import json
import time
import asyncio
import base64
import hashlib
import threading
from pathlib import Path
from typing import Optional, Tuple

from transport import TransportManager


class SAMError(Exception):
    """SAM protocol error"""
    pass


class SAMClient:
    """Minimal SAM v3.3 protocol client — no external dependencies."""

    def __init__(self, sam_host: str = '127.0.0.1', sam_port: int = 7656):
        self.sam_host = sam_host
        self.sam_port = sam_port

    async def _connect(self) -> Tuple[asyncio.StreamReader, asyncio.StreamWriter]:
        """Open a connection to the SAM bridge."""
        reader, writer = await asyncio.open_connection(self.sam_host, self.sam_port)
        return reader, writer

    async def _hello(self, reader, writer) -> str:
        """SAM HELLO handshake. Returns the SAM version."""
        writer.write(b'HELLO VERSION MIN=3.1 MAX=3.3\n')
        await writer.drain()
        reply = await reader.readline()
        reply_str = reply.decode().strip()
        if 'RESULT=OK' not in reply_str:
            raise SAMError(f'HELLO failed: {reply_str}')
        # Extract version
        for part in reply_str.split():
            if part.startswith('VERSION='):
                return part.split('=', 1)[1]
        return '3.1'

    async def generate_destination(self) -> str:
        """Generate a new I2P destination keypair. Returns base64 private+public keys."""
        reader, writer = await self._connect()
        try:
            await self._hello(reader, writer)
            writer.write(b'DEST GENERATE\n')
            await writer.drain()
            reply = (await reader.readline()).decode().strip()
            # Response: DEST REPLY PUB=<base64> PRIV=<base64>
            parts = {}
            for token in reply.split():
                if '=' in token:
                    k, v = token.split('=', 1)
                    parts[k] = v
            if 'PRIV' not in parts:
                raise SAMError(f'DEST GENERATE failed: {reply}')
            return parts['PUB'], parts['PRIV']
        finally:
            writer.close()

    async def create_session(self, session_id: str, private_keys: str,
                              style: str = 'STREAM') -> str:
        """Create a SAM session. Returns the destination base64."""
        reader, writer = await self._connect()
        try:
            await self._hello(reader, writer)
            cmd = f'SESSION CREATE STYLE={style} ID={session_id} DESTINATION={private_keys}\n'
            writer.write(cmd.encode())
            await writer.drain()
            reply = (await reader.readline()).decode().strip()
            if 'RESULT=OK' not in reply:
                raise SAMError(f'SESSION CREATE failed: {reply}')
            # Extract DESTINATION from reply
            for token in reply.split():
                if token.startswith('DESTINATION='):
                    return token.split('=', 1)[1]
            return private_keys
        finally:
            # Don't close — session lives for the lifetime of this connection
            # Actually for SAM, the session is tied to this socket
            # We need to keep it open. Return the reader/writer.
            pass

    async def create_session_persistent(self, session_id: str, private_keys: str,
                                         style: str = 'STREAM'):
        """Create a SAM session and return the open reader/writer (session dies when socket closes)."""
        reader, writer = await self._connect()
        await self._hello(reader, writer)
        cmd = f'SESSION CREATE STYLE={style} ID={session_id} DESTINATION={private_keys}\n'
        writer.write(cmd.encode())
        await writer.drain()
        reply = (await reader.readline()).decode().strip()
        if 'RESULT=OK' not in reply:
            writer.close()
            raise SAMError(f'SESSION CREATE failed: {reply}')
        return reader, writer

    async def stream_accept(self, session_id: str):
        """Accept an incoming stream connection. Returns (reader, writer)."""
        reader, writer = await self._connect()
        await self._hello(reader, writer)
        cmd = f'STREAM ACCEPT ID={session_id} SILENT=false\n'
        writer.write(cmd.encode())
        await writer.drain()
        reply = (await reader.readline()).decode().strip()
        if 'RESULT=OK' not in reply:
            writer.close()
            raise SAMError(f'STREAM ACCEPT failed: {reply}')
        # After RESULT=OK, the next line contains the remote destination
        # Then the socket becomes a raw data stream
        return reader, writer

    async def stream_connect(self, session_id: str, destination: str):
        """Connect to a remote I2P destination. Returns (reader, writer)."""
        reader, writer = await self._connect()
        await self._hello(reader, writer)
        cmd = f'STREAM CONNECT ID={session_id} DESTINATION={destination} SILENT=false\n'
        writer.write(cmd.encode())
        await writer.drain()
        reply = (await reader.readline()).decode().strip()
        if 'RESULT=OK' not in reply:
            writer.close()
            raise SAMError(f'STREAM CONNECT failed: {reply}')
        return reader, writer

    @staticmethod
    def compute_b32_address(pub_b64: str) -> str:
        """Compute .b32.i2p address from public destination base64.
        I2P uses modified base64: - instead of +, ~ instead of /
        """
        # Convert I2P base64 to standard base64
        std_b64 = pub_b64.replace('-', '+').replace('~', '/')
        # Add padding
        padding = 4 - (len(std_b64) % 4)
        if padding < 4:
            std_b64 += '=' * padding
        dest_raw = base64.b64decode(std_b64)
        # b32 address = base32(SHA-256(destination))
        sha = hashlib.sha256(dest_raw).digest()
        b32 = base64.b32encode(sha).decode().lower().rstrip('=')
        return f"{b32}.b32.i2p"


class I2PManager(TransportManager):
    """Manages I2P session via SAM bridge for P2P communication"""

    DEFAULT_SAM_HOST = '127.0.0.1'
    DEFAULT_SAM_PORT = 7656
    DEFAULT_SOCKS_PORT = 4447

    def __init__(self, data_dir: str = None, service_port: int = 8765):
        if data_dir is None:
            data_dir = os.path.expanduser("~/.openclaw/p2p/i2p")
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)

        self.service_port = service_port
        self._address: Optional[str] = None  # .b32.i2p address
        self._pub_dest: Optional[str] = None  # Public destination base64
        self._priv_dest: Optional[str] = None  # Private destination base64
        self._session_reader = None
        self._session_writer = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._thread: Optional[threading.Thread] = None
        self._accept_task: Optional[asyncio.Task] = None
        self._running = False
        self._pid = os.getpid()

    def is_running(self) -> bool:
        """Check if I2P session is active"""
        pid_file = self.data_dir / "i2p.pid"
        if pid_file.exists():
            try:
                with open(pid_file) as f:
                    pid = int(f.read().strip())
                os.kill(pid, 0)
                return True
            except (OSError, ValueError):
                return False
        return False

    def start(self, sam_port: int = None, socks_port: int = None) -> str:
        """
        Start I2P transport via SAM bridge.
        Creates a SAM session and returns the .b32.i2p address.
        """
        if sam_port is None:
            sam_port = self.DEFAULT_SAM_PORT
        if socks_port is None:
            socks_port = self.DEFAULT_SOCKS_PORT

        self._socks_port = socks_port
        self._sam_port = sam_port

        print("Starting I2P transport (this may take 2-5 minutes for tunnel building)...")
        print(f"Data directory: {self.data_dir}")
        print(f"SAM bridge: {self.DEFAULT_SAM_HOST}:{sam_port}")

        # Load or create destination keys
        saved_keys = self._load_destination_keys()

        # Run the async SAM session setup in a background thread
        self._loop = asyncio.new_event_loop()
        setup_done = threading.Event()
        setup_error = [None]

        def run_loop():
            asyncio.set_event_loop(self._loop)
            try:
                self._loop.run_until_complete(
                    self._setup_sam_session(sam_port, saved_keys, setup_done, setup_error)
                )
            except Exception as e:
                setup_error[0] = e
                setup_done.set()

        self._thread = threading.Thread(target=run_loop, daemon=True)
        self._thread.start()

        # Wait for session to be established (with progress)
        print("Connecting to SAM bridge...")
        elapsed = 0
        while not setup_done.wait(timeout=5):
            elapsed += 5
            if elapsed <= 120:
                print(f"  Building I2P tunnels... ({elapsed}s elapsed)")
            else:
                print(f"  Still building tunnels... ({elapsed}s elapsed, I2P can take up to 5 minutes)")

        if setup_error[0]:
            raise RuntimeError(f"Failed to start I2P session: {setup_error[0]}")

        print(f"I2P tunnels ready: {self._address}")

        # Save PID
        pid_file = self.data_dir / "i2p.pid"
        with open(pid_file, 'w') as f:
            f.write(str(self._pid))

        # Write daemon config
        self._write_daemon_config(socks_port, sam_port)

        self._running = True
        return self._address

    async def _setup_sam_session(self, sam_port: int, saved_keys: Optional[dict],
                                  setup_done: threading.Event,
                                  setup_error: list):
        """Set up SAM session asynchronously using raw SAM protocol."""
        try:
            sam = SAMClient(self.DEFAULT_SAM_HOST, sam_port)

            if saved_keys:
                pub_b64 = saved_keys['pub']
                priv_b64 = saved_keys['priv']
                print("  Restored I2P destination from saved keys")
            else:
                # Generate new destination via SAM
                pub_b64, priv_b64 = await sam.generate_destination()
                self._save_destination_keys(pub_b64, priv_b64)
                print("  Generated new I2P destination")

            self._pub_dest = pub_b64
            self._priv_dest = priv_b64

            # Compute .b32.i2p address
            self._address = SAMClient.compute_b32_address(pub_b64)

            # Create SAM session (keeps socket open — session dies when socket closes)
            session_name = f"oc-tor-net-{self._pid}"
            self._session_reader, self._session_writer = await sam.create_session_persistent(
                session_name, priv_b64, style="STREAM"
            )

            print(f"  SAM session '{session_name}' created")
            print(f"  Destination: {self._address}")

            setup_done.set()

            # Accept and forward incoming I2P streams to local HTTP server
            self._accept_task = asyncio.ensure_future(
                self._accept_loop(session_name, sam_port)
            )
            await self._accept_task

        except ConnectionRefusedError:
            setup_error[0] = (
                f"Cannot connect to SAM bridge at {self.DEFAULT_SAM_HOST}:{sam_port}.\n"
                "Ensure i2pd is running with SAM enabled:\n"
                "  sudo apt install i2pd\n"
                "  # Enable SAM in /etc/i2pd/i2pd.conf: [sam] enabled = true"
            )
            setup_done.set()
        except Exception as e:
            setup_error[0] = e
            setup_done.set()

    async def _accept_loop(self, session_name: str, sam_port: int):
        """Accept incoming I2P streams and forward to local HTTP server."""
        sam = SAMClient(self.DEFAULT_SAM_HOST, sam_port)
        while True:
            try:
                reader, writer = await sam.stream_accept(session_name)
                asyncio.ensure_future(
                    self._forward_stream(reader, writer, '127.0.0.1', self.service_port)
                )
            except asyncio.CancelledError:
                break
            except Exception as e:
                try:
                    log_file = Path.home() / ".openclaw" / "p2p" / "daemon.log"
                    with open(log_file, 'a') as f:
                        f.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] [I2P] stream_accept error: {e}\n")
                except:
                    pass
                await asyncio.sleep(1)

    @staticmethod
    async def _forward_stream(i2p_reader, i2p_writer, local_host: str, local_port: int):
        """Forward an incoming I2P stream to the local HTTP server and relay the response back."""
        try:
            local_reader, local_writer = await asyncio.open_connection(local_host, local_port)

            async def pipe(src, dst):
                try:
                    while True:
                        data = await src.read(4096)
                        if not data:
                            break
                        dst.write(data)
                        await dst.drain()
                except (asyncio.CancelledError, ConnectionError, OSError):
                    pass
                finally:
                    try:
                        dst.close()
                    except:
                        pass

            # Bidirectional pipe: I2P stream <-> local HTTP server
            await asyncio.gather(
                pipe(i2p_reader, local_writer),
                pipe(local_reader, i2p_writer)
            )
        except Exception as e:
            try:
                log_file = Path.home() / ".openclaw" / "p2p" / "daemon.log"
                with open(log_file, 'a') as f:
                    f.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] [I2P] forward error: {e}\n")
            except:
                pass

    def _load_destination_keys(self) -> Optional[dict]:
        """Load saved I2P destination keys for persistent identity"""
        keys_file = self.data_dir / "destination_keys.json"
        if keys_file.exists():
            try:
                with open(keys_file, 'r') as f:
                    return json.load(f)
            except (OSError, json.JSONDecodeError):
                return None
        return None

    def _save_destination_keys(self, pub_b64: str, priv_b64: str):
        """Save I2P destination keys for persistent identity"""
        keys_file = self.data_dir / "destination_keys.json"
        with open(keys_file, 'w') as f:
            json.dump({'pub': pub_b64, 'priv': priv_b64}, f)
        os.chmod(keys_file, 0o600)

    def get_address(self) -> Optional[str]:
        """Get the .b32.i2p address"""
        return self._address

    def get_proxy(self) -> dict:
        """Get SOCKS proxy config for requests (I2P SOCKS proxy)"""
        port = getattr(self, '_socks_port', self.DEFAULT_SOCKS_PORT)
        return {
            'http': f'socks5h://127.0.0.1:{port}',
            'https': f'socks5h://127.0.0.1:{port}'
        }

    # Legacy alias
    def get_socks_proxy(self) -> dict:
        return self.get_proxy()

    def _write_daemon_config(self, socks_port: int, sam_port: int):
        """Write daemon.json so CLI tools can discover config."""
        config_file = self.data_dir.parent / "daemon.json"
        config = {
            'transport': 'i2p',
            'socks_port': socks_port,
            'sam_port': sam_port,
            'service_port': self.service_port,
            'address': self._address,
            'destination': self._pub_dest[:80] + '...' if self._pub_dest else None,
            'pid': self._pid,
            'data_dir': str(self.data_dir)
        }
        with open(config_file, 'w') as f:
            json.dump(config, f, indent=2)

    def _remove_daemon_config(self):
        """Remove daemon.json on shutdown."""
        config_file = self.data_dir.parent / "daemon.json"
        if config_file.exists():
            try:
                config_file.unlink()
            except OSError:
                pass

    @staticmethod
    def check_daemon(config_dir: str = None) -> dict:
        """Check if the I2P daemon is running."""
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

    def stop(self):
        """Stop I2P session"""
        self._running = False
        self._remove_daemon_config()

        # Cancel async accept loop
        if self._loop and self._accept_task:
            self._loop.call_soon_threadsafe(self._accept_task.cancel)

        # Stop the event loop
        if self._loop:
            self._loop.call_soon_threadsafe(self._loop.stop)

        if self._thread:
            self._thread.join(timeout=5)
            self._thread = None

        self._loop = None

        # Close session socket (kills the SAM session)
        if self._session_writer:
            try:
                self._session_writer.close()
            except:
                pass
            self._session_writer = None
            self._session_reader = None

        # Clean up PID file
        pid_file = self.data_dir / "i2p.pid"
        if pid_file.exists():
            try:
                pid_file.unlink()
            except OSError:
                pass

    def __del__(self):
        self.stop()
