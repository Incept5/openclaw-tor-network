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


class Peer:
    """Represents a connected peer"""
    
    def __init__(
        self,
        address: str,
        onion: str,
        port: int,
        public_key_b64: str,
        display_name: str = "Anonymous Agent",
        socks_proxy: dict = None
    ):
        self.address = address  # @pubkey.ed25519
        self.onion = onion
        self.port = port
        self.public_key_b64 = public_key_b64
        self.display_name = display_name
        # Load Curve25519 public key directly (for encryption)
        self.public_key = PublicKey(base64.b64decode(public_key_b64))
        self.socks_proxy = socks_proxy or {
            'http': 'socks5h://127.0.0.1:9050',
            'https': 'socks5h://127.0.0.1:9050'
        }
        self.last_seen = None
        self.handshake_complete = False
    
    def get_display_label(self) -> str:
        """Get a human-readable label for this peer"""
        short_key = self.address[1:8] + "..." + self.address[-8:]
        return f"{self.display_name} ({short_key})"
    
    def get_url(self, path: str = '') -> str:
        """Get full URL for this peer"""
        return f"http://{self.onion}:{self.port}{path}"
    
    def send_message(self, encrypted_payload: dict) -> bool:
        """Send encrypted message to peer"""
        try:
            url = self.get_url('/message')
            response = requests.post(
                url,
                json=encrypted_payload,
                proxies=self.socks_proxy,
                timeout=30
            )
            return response.status_code == 200
        except Exception as e:
            print(f"Failed to send to {self.address}: {e}")
            return False
    
    def health_check(self) -> bool:
        """Check if peer is reachable"""
        try:
            url = self.get_url('/health')
            response = requests.get(
                url,
                proxies=self.socks_proxy,
                timeout=10
            )
            if response.status_code == 200:
                self.last_seen = time.time()
                return True
            return False
        except Exception:
            return False


class PeerManager:
    """Manages all peer connections"""
    
    def __init__(self, identity: Identity, data_dir: str = None, socks_proxy: dict = None):
        self.identity = identity
        
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
                self.peers[addr] = Peer(
                    address=addr,
                    onion=info['onion'],
                    port=info['port'],
                    public_key_b64=info['public_key'],
                    socks_proxy=self.socks_proxy
                )
    
    def _save_peers(self):
        """Save peers to disk"""
        data = {}
        for addr, peer in self.peers.items():
            data[addr] = {
                'onion': peer.onion,
                'port': peer.port,
                'public_key': peer.public_key_b64,
                'display_name': peer.display_name,
                'last_seen': peer.last_seen
            }
        with open(self.peers_file, 'w') as f:
            json.dump(data, f, indent=2)
    
    def add_peer(self, invite_code: str) -> Optional[Peer]:
        """Add a peer from an invite code"""
        from .identity import Identity
        
        # Decode and verify invite
        invite = Identity.decode_invite(invite_code)
        if not Identity.verify_invite(invite):
            raise ValueError("Invalid invite signature")
        
        address = f"@{invite['pubkey']}.ed25519"
        
        # Check if already added
        if address in self.peers:
            return self.peers[address]
        
        # Create peer
        peer = Peer(
            address=address,
            onion=invite['onion'],
            port=invite['port'],
            public_key_b64=invite['pubkey'],
            display_name=invite.get('name', 'Anonymous Agent'),
            socks_proxy=self.socks_proxy
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

        # Extract info from handshake
        onion = handshake_data.get('onion')
        port = handshake_data.get('port', 80)
        display_name = handshake_data.get('display_name', 'Anonymous Agent')

        if not onion:
            raise ValueError("Handshake missing onion address")

        # Use encryption_pubkey from handshake if available, otherwise fall back to derivation
        encryption_pubkey_b64 = handshake_data.get('encryption_pubkey', sender_pubkey_b64)
        
        print(f"  [DEBUG] add_peer_from_handshake: sender_pubkey={sender_pubkey_b64[:20]}...")
        print(f"  [DEBUG] add_peer_from_handshake: encryption_pubkey={encryption_pubkey_b64[:20]}...")
        print(f"  [DEBUG] Using encryption_pubkey from handshake: {'encryption_pubkey' in handshake_data}")

        # Create peer
        peer = Peer(
            address=address,
            onion=onion,
            port=port,
            public_key_b64=encryption_pubkey_b64,
            display_name=display_name,
            socks_proxy=self.socks_proxy
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
            message['sender_info'] = {
                'display_name': self.identity.get_display_name(),
                'onion': self.tor_onion if hasattr(self, 'tor_onion') else None,
                'port': 80,
                'address': self.identity.get_address()
            }
        
        # Encrypt message
        encrypted = MessageProtocol.encrypt_message(
            message,
            self.identity.signing_key,
            peer.public_key
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
