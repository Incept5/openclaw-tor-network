"""
Main P2P agent coordinator
"""
import os
import json
from pathlib import Path
from typing import Optional

from identity import Identity
from tor_manager import TorManager
from server import MessageServer
from peer import PeerManager
from protocol import MessageProtocol
from webhook import OpenClawWebhook


class P2PAgent:
    """Main class coordinating P2P functionality"""
    
    def __init__(self, config_dir: str = None, service_port: int = 8765):
        if config_dir is None:
            config_dir = os.path.expanduser("~/.openclaw/p2p")
        self.config_dir = Path(config_dir)
        self.config_dir.mkdir(parents=True, exist_ok=True)
        
        self.service_port = service_port
        
        # Components
        self.identity: Optional[Identity] = None
        self.tor: Optional[TorManager] = None
        self.server: Optional[MessageServer] = None
        self.peers: Optional[PeerManager] = None
        
        self._onion_address: Optional[str] = None
        self._running = False
    
    def start(self) -> str:
        """
        Start the P2P agent.
        Returns the .onion address.
        """
        print("=== Starting P2P Agent ===")
        
        # 1. Load/create identity
        print("Loading identity...")
        self.identity = Identity(str(self.config_dir))
        print(f"  Address: {self.identity.get_address()}")
        
        # 2. Start message server (local HTTP endpoint)
        print(f"Starting message server on port {self.service_port}...")
        self.server = MessageServer(port=self.service_port, inbox_dir=str(self.config_dir / "inbox"))
        self.server.start(message_callback=self._on_message_received)
        
        # 3. Start Tor with hidden service
        print("Starting Tor hidden service...")
        self.tor = TorManager(str(self.config_dir / "tor"), service_port=self.service_port)
        self._onion_address = self.tor.start()
        
        # 4. Initialize peer manager
        print("Initializing peer manager...")
        self.peers = PeerManager(
            self.identity,
            data_dir=str(self.config_dir),
            socks_proxy=self.tor.get_socks_proxy()
        )
        
        # 5. Initialize webhook for OpenClaw notification
        print("Initializing OpenClaw webhook...")
        self.webhook = OpenClawWebhook()
        
        self._running = True
        
        print(f"\n=== P2P Agent Ready ===")
        print(f"Your address: {self.identity.get_address()}")
        print(f"Your .onion:  {self._onion_address}")
        print(f"\nTo connect, share your invite code:")
        print(f"  python3 tools/p2p_generate_invite.py")
        
        return self._onion_address
    
    def stop(self):
        """Stop the P2P agent"""
        print("\n=== Stopping P2P Agent ===")
        
        if self.server:
            self.server.stop()
            print("Message server stopped")
        
        if self.tor:
            self.tor.stop()
            print("Tor stopped")
        
        self._running = False
        print("P2P agent stopped")
    
    def generate_invite(self) -> str:
        """Generate an invite code for others to connect"""
        if not self._running:
            raise RuntimeError("P2P agent not started")
        
        invite = self.identity.generate_invite(self._onion_address, port=80)
        return self.identity.encode_invite(invite)
    
    def accept_invite(self, invite_code: str) -> bool:
        """Accept an invite and add peer"""
        if not self._running:
            raise RuntimeError("P2P agent not started")
        
        try:
            peer = self.peers.add_peer(invite_code)
            print(f"Added peer: {peer.address}")
            
            # Send handshake
            handshake = MessageProtocol.create_handshake(self.identity)
            success = self.peers.send_to_peer(peer.address, handshake)
            
            if success:
                print(f"Handshake sent to {peer.address}")
                peer.handshake_complete = True
            else:
                print(f"Failed to send handshake to {peer.address}")
            
            return success
            
        except Exception as e:
            print(f"Failed to accept invite: {e}")
            return False
    
    def send_message(self, peer_address: str, content: str, msg_type: str = "text") -> bool:
        """Send a message to a peer"""
        if not self._running:
            raise RuntimeError("P2P agent not started")
        
        message = MessageProtocol.create_message(msg_type, {
            'text': content
        })
        
        return self.peers.send_to_peer(peer_address, message)
    
    def list_peers(self):
        """List all connected peers"""
        if not self._running:
            raise RuntimeError("P2P agent not started")
        
        return self.peers.list_peers()
    
    def get_inbox(self):
        """Get received messages"""
        if not self.server:
            return []
        return self.server.get_inbox_messages()
    
    def _on_message_received(self, encrypted_message: dict):
        """Callback when a message is received"""
        print(f"\n[Received encrypted message]")
        
        # Get sender's public key from message
        sender_pubkey_b64 = encrypted_message.get('sender_pubkey')
        if not sender_pubkey_b64:
            print("  No sender pubkey, dropping")
            return
        
        # Find peer
        sender_address = f"@{sender_pubkey_b64}.ed25519"
        peer = self.peers.get_peer(sender_address)
        
        if not peer:
            print(f"  Unknown sender: {sender_address}")
            return
        
        # Decrypt
        from nacl.public import PrivateKey
        from nacl.signing import VerifyKey
        import base64
        
        # We need the private key for decryption - derive from signing key
        # This is a simplification - in practice you'd have a separate encryption keypair
        signing_key_bytes = bytes(self.identity.signing_key)
        # Use first 32 bytes as seed for encryption key
        encryption_private = PrivateKey(signing_key_bytes[:32])
        
        sender_verify_key = VerifyKey(base64.b64decode(sender_pubkey_b64))
        
        decrypted = MessageProtocol.decrypt_message(
            encrypted_message,
            encryption_private,
            sender_verify_key
        )
        
        if decrypted:
            print(f"  From: {sender_address}")
            print(f"  Type: {decrypted.get('type')}")
            print(f"  Content: {decrypted.get('content')}")
            
            # Notify OpenClaw via webhook
            print("  Notifying OpenClaw...")
            notified = self.webhook.notify_new_message(decrypted, sender_address)
            if notified:
                print("  ✓ OpenClaw notified")
            else:
                print("  ⚠ OpenClaw notification failed (message still saved)")
        else:
            print("  Failed to decrypt")
    
    def __enter__(self):
        self.start()
        return self
    
    def __exit__(self, *args):
        self.stop()
