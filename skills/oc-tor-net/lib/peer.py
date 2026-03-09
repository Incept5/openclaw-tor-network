"""
Peer connection management
"""
import json
import time
import base64
import requests
from pathlib import Path
from typing import Dict, Optional, List
from nacl.public import PublicKey
from nacl.signing import VerifyKey
from nacl.encoding import Base64Encoder

from identity import Identity
from protocol import MessageProtocol


def _default_socks_proxy() -> dict:
    """Read SOCKS proxy config from daemon.json, auto-detect transport type."""
    daemon_config = Path.home() / ".openclaw" / "p2p" / "daemon.json"
    socks_port = 9060  # Tor default
    if daemon_config.exists():
        try:
            with open(daemon_config) as f:
                config = json.load(f)
            transport = config.get('transport', 'tor')
            if transport == 'i2p':
                socks_port = config.get('socks_port', 4447)
            else:
                socks_port = config.get('socks_port', 9060)
        except (json.JSONDecodeError, OSError):
            pass
    return {
        'http': f'socks5h://127.0.0.1:{socks_port}',
        'https': f'socks5h://127.0.0.1:{socks_port}'
    }


class Peer:
    """Represents a connected peer"""

    def __init__(
        self,
        address: str,
        onion: str,
        port: int,
        public_key_b64: str,
        display_name: str = "Anonymous Agent",
        socks_proxy: dict = None,
        transport: str = "tor",
        transport_manager=None,
        full_destination: str = None
    ):
        self.address = address  # @pubkey.ed25519
        self.onion = onion  # Kept for backwards compat (also stores .b32.i2p)
        self.network_address = onion  # Generic name for the transport address
        self.port = port
        self.public_key_b64 = public_key_b64
        self.display_name = display_name
        self.transport = transport  # 'tor' or 'i2p'
        self.transport_manager = transport_manager  # Optional TransportManager for SAM-based sends
        self.full_destination = full_destination  # Full I2P base64 destination (for SAM)
        # Load Curve25519 public key directly (for encryption)
        self.public_key = PublicKey(base64.b64decode(public_key_b64))
        self.socks_proxy = socks_proxy or _default_socks_proxy()
        self.last_seen = None
        self.handshake_complete = False
    
    def get_display_label(self) -> str:
        """Get a human-readable label for this peer"""
        short_key = self.address[1:8] + "..." + self.address[-8:]
        return f"{self.display_name} ({short_key})"
    
    def get_url(self, path: str = '') -> str:
        """Get full URL for this peer (works for both .onion and .b32.i2p)"""
        return f"http://{self.network_address}:{self.port}{path}"
    
    def send_message(self, encrypted_payload: dict) -> bool:
        """Send encrypted message to peer via transport (SAM for I2P, SOCKS for Tor)"""
        try:
            url = self.get_url('/message')
            if self.transport_manager and hasattr(self.transport_manager, 'http_post'):
                status_code, _ = self.transport_manager.http_post(
                    url, encrypted_payload, timeout=60,
                    full_destination=self.full_destination
                )
            else:
                response = requests.post(
                    url, json=encrypted_payload, proxies=self.socks_proxy, timeout=30
                )
                status_code = response.status_code
            return status_code == 200
        except Exception as e:
            print(f"Failed to send to {self.address}: {e}")
            return False

    def health_check(self) -> bool:
        """Check if peer is reachable via transport"""
        try:
            url = self.get_url('/health')
            if self.transport_manager and hasattr(self.transport_manager, 'http_get'):
                status_code, _ = self.transport_manager.http_get(
                    url, timeout=30, full_destination=self.full_destination
                )
            else:
                response = requests.get(url, proxies=self.socks_proxy, timeout=10)
                status_code = response.status_code
            if status_code == 200:
                self.last_seen = time.time()
                return True
            return False
        except Exception:
            return False


class PeerManager:
    """Manages all peer connections"""
    
    def __init__(self, identity: Identity, data_dir: str = None, socks_proxy: dict = None,
                 transport_manager=None):
        self.identity = identity
        self.transport_manager = transport_manager

        if data_dir is None:
            data_dir = Path.home() / ".openclaw/p2p"
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        
        self.peers_file = self.data_dir / "peers.json"
        self.peers: Dict[str, Peer] = {}
        self.socks_proxy = socks_proxy
        
        self._load_peers()
    
    def _load_peers(self):
        """Load peers from disk"""
        if self.peers_file.exists():
            with open(self.peers_file) as f:
                data = json.load(f)
            for addr, info in data.items():
                # Backwards compat: default to 'tor' if transport missing
                transport = info.get('transport', 'tor')
                # Support both 'onion' and 'address' keys
                network_addr = info.get('address', info.get('onion', ''))
                self.peers[addr] = Peer(
                    address=addr,
                    onion=network_addr,
                    port=info['port'],
                    public_key_b64=info['public_key'],
                    display_name=info.get('display_name', 'Anonymous Agent'),
                    socks_proxy=self.socks_proxy,
                    transport=transport,
                    transport_manager=self.transport_manager,
                    full_destination=info.get('full_destination')
                )
    
    def _save_peers(self):
        """Save peers to disk"""
        data = {}
        for addr, peer in self.peers.items():
            entry = {
                'onion': peer.onion,
                'address': peer.network_address,
                'port': peer.port,
                'public_key': peer.public_key_b64,
                'display_name': peer.display_name,
                'transport': peer.transport,
                'last_seen': peer.last_seen
            }
            if peer.full_destination:
                entry['full_destination'] = peer.full_destination
            data[addr] = entry
        with open(self.peers_file, 'w') as f:
            json.dump(data, f, indent=2)
    
    def add_peer(self, invite_code: str) -> Optional[Peer]:
        """Add a peer from an invite code"""
        from identity import Identity
        
        # Decode and verify invite
        invite = Identity.decode_invite(invite_code)
        if not Identity.verify_invite(invite):
            raise ValueError("Invalid invite signature")
        
        address = f"@{invite['pubkey']}.ed25519"
        
        # Check if already added
        if address in self.peers:
            return self.peers[address]
        
        # Use encryption_pubkey from invite -- this MUST be a Curve25519 key.
        # The signing pubkey (Ed25519) is NOT compatible with NaCl box encryption.
        encryption_pubkey = invite.get('encryption_pubkey')
        if not encryption_pubkey:
            raise ValueError(
                "Invite is missing encryption_pubkey (Curve25519 key). "
                "This may be a legacy v1 invite. Ask the peer to regenerate their invite."
            )
        
        # Create peer with transport info
        transport = invite.get('transport', 'tor')
        peer = Peer(
            address=address,
            onion=invite['onion'],
            port=invite['port'],
            public_key_b64=encryption_pubkey,
            display_name=invite.get('name', 'Anonymous Agent'),
            socks_proxy=self.socks_proxy,
            transport=transport,
            transport_manager=self.transport_manager,
            full_destination=invite.get('dest')
        )
        
        self.peers[address] = peer
        self._save_peers()
        
        return peer
    
    def get_peer(self, address: str) -> Optional[Peer]:
        """Get a peer by address"""
        return self.peers.get(address)

    def add_peer_from_handshake(self, handshake_data: dict, sender_pubkey_b64: str) -> Peer:
        """Add a peer from a handshake message (auto-add on first contact)"""
        address = f"@{sender_pubkey_b64}.ed25519"

        # Check if already added
        if address in self.peers:
            return self.peers[address]

        # Extract info from handshake — support both 'onion' and 'address' keys
        network_addr = handshake_data.get('address', handshake_data.get('onion'))
        # Fall back to legacy 'onion' key
        if not network_addr:
            network_addr = handshake_data.get('onion')
        port = handshake_data.get('port', 80)
        display_name = handshake_data.get('display_name', 'Anonymous Agent')
        transport = handshake_data.get('transport', 'tor')

        if not network_addr:
            raise ValueError("Handshake missing network address")

        # Use encryption_pubkey from handshake -- this MUST be a Curve25519 key.
        # The sender_pubkey_b64 is Ed25519 (signing) and NOT compatible with NaCl box.
        encryption_pubkey_b64 = handshake_data.get('encryption_pubkey')
        if not encryption_pubkey_b64:
            raise ValueError(
                "Handshake is missing encryption_pubkey (Curve25519 key). "
                "The peer may be running an outdated version."
            )

        # Debug logging
        from pathlib import Path
        from datetime import datetime
        try:
            with open(Path.home() / '.openclaw' / 'p2p' / 'daemon.log', 'a') as f:
                ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                f.write(f"[{ts}] [PEER] sender_pubkey={sender_pubkey_b64[:30]}...\n")
                f.write(f"[{ts}] [PEER] encryption_pubkey={encryption_pubkey_b64[:30]}...\n")
                f.write(f"[{ts}] [PEER] transport={transport}\n")
        except:
            pass

        # Create peer
        peer = Peer(
            address=address,
            onion=network_addr,
            port=port,
            public_key_b64=encryption_pubkey_b64,
            display_name=display_name,
            socks_proxy=self.socks_proxy,
            transport=transport,
            transport_manager=self.transport_manager,
            full_destination=handshake_data.get('full_destination')
        )

        self.peers[address] = peer
        self._save_peers()

        return peer
    
    def list_peers(self) -> List[Peer]:
        """List all peers"""
        return list(self.peers.values())
    
    def send_to_peer(self, address: str, message: dict, include_sender_info: bool = True) -> bool:
        """Send a message to a specific peer"""
        peer = self.get_peer(address)
        if not peer:
            print(f"Unknown peer: {address}")
            return False
        
        # Add sender info for auto-add capability (unless it's already a handshake)
        if include_sender_info and message.get('type') != 'handshake':
            # network_address is set by agent.py after transport starts
            network_addr = getattr(self, 'network_address', None)
            transport = getattr(self, 'transport_type', 'tor')
            message['sender_info'] = {
                'display_name': self.identity.get_display_name(),
                'onion': network_addr,
                'address': network_addr,
                'port': 80,
                'transport': transport,
                'identity_address': self.identity.get_address()
            }
        
        # Block cross-transport sends — Tor SOCKS can't resolve .b32.i2p and vice versa
        our_transport = getattr(self, 'transport_type', 'tor')
        if peer.transport != our_transport:
            print(f"❌ Cross-transport messaging not supported: "
                  f"we are on {our_transport}, peer {peer.display_name} is on {peer.transport}. "
                  f"Both agents must use the same transport to communicate.")
            return False

        # Encrypt message — include our encryption pubkey so receiver can auto-add us
        encrypted = MessageProtocol.encrypt_message(
            message,
            self.identity.signing_key,
            peer.public_key,
            sender_encryption_pubkey=self.identity.encryption_key.public_key
        )
        
        # Send
        return peer.send_message(encrypted)
    
    def broadcast(self, message: dict) -> Dict[str, bool]:
        """Broadcast message to all peers"""
        results = {}
        for address, peer in self.peers.items():
            results[address] = self.send_to_peer(address, message)
        return results
    
    def check_all_health(self) -> Dict[str, bool]:
        """Check health of all peers"""
        results = {}
        for address, peer in self.peers.items():
            results[address] = peer.health_check()
        self._save_peers()
        return results
