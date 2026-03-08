"""
Main P2P agent coordinator
"""
import os
import json
from pathlib import Path
from typing import Optional
from datetime import datetime

from identity import Identity
from tor_manager import TorManager
from server import MessageServer
from peer import PeerManager
from protocol import MessageProtocol
from webhook import OpenClawWebhook


def agent_log(msg):
    """Write directly to log file"""
    try:
        log_file = Path.home() / ".openclaw" / "p2p" / "daemon.log"
        with open(log_file, 'a') as f:
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            f.write(f"[{timestamp}] [AGENT] {msg}\n")
    except:
        pass


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
        print(f"  Encryption pubkey: {self.identity.get_encryption_pubkey_b64()[:40]}...")
        
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
        # Store onion address in peer manager for sender info
        self.peers.tor_onion = self._onion_address
        
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
            
            # Send handshake with full identity info for auto-add
            handshake = MessageProtocol.create_handshake(
                self.identity,
                self._onion_address,
                port=80,
                encryption_pubkey_b64=self.identity.get_encryption_pubkey_b64()
            )
            success = self.peers.send_to_peer(peer.address, handshake)
            
            if success:
                print(f"Handshake sent to {peer.address}")
                peer.handshake_complete = True
                
                # Notify user that pairing is complete (initiator side)
                print("Notifying user of successful pairing...")
                notified = self.webhook.notify_pairing_complete(
                    peer.display_name,
                    peer.address,
                    is_initiator=True
                )
                if notified:
                    print(f"  ✓ User notified: Connected to {peer.display_name}")
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
        agent_log("_on_message_received called")
        agent_log(f"Message keys: {list(encrypted_message.keys())}")
        agent_log(f"Has sender_pubkey: {'sender_pubkey' in encrypted_message}")
        
        # Get sender's public key from message
        sender_pubkey_b64 = encrypted_message.get('sender_pubkey')
        if not sender_pubkey_b64:
            print("  No sender pubkey, dropping")
            return
        
        # Find peer
        sender_address = f"@{sender_pubkey_b64}.ed25519"
        peer = self.peers.get_peer(sender_address)
        
        is_new_peer = False
        if not peer:
            print(f"  Unknown sender: {sender_address}")
            print("  Will attempt auto-add from handshake content")
        
        # Decrypt using our Curve25519 encryption key
        import base64
        from nacl.signing import VerifyKey

        encryption_private = self.identity.encryption_key
        sender_verify_key = VerifyKey(base64.b64decode(sender_pubkey_b64))
        
        agent_log("Attempting decryption...")
        
        # Decrypt using our encryption private key and the ephemeral key in the message.
        # Note: the sender_encryption_pubkey from the envelope is NOT needed for
        # decryption -- NaCl box uses (our_private, ephemeral_public) which are both
        # already available. The envelope key is only useful for peer discovery.
        decrypted = MessageProtocol.decrypt_message(
            encrypted_message,
            encryption_private,
            sender_verify_key
        )
        
        if not decrypted:
            agent_log("Decryption FAILED - keys don't match")
            return
        
        agent_log("Decryption SUCCESS")
        msg_type = decrypted.get('type')
        content = decrypted.get('content', {})
        agent_log(f"Decrypted msg_type={msg_type}, content_keys={list(content.keys())}")
        
        # Auto-add peer on any valid message from unknown sender
        agent_log(f"Checking auto-add: peer={peer is not None}, msg_type={msg_type}")
        if not peer:
            try:
                agent_log("Auto-adding peer from message...")
                
                # Get sender info from message (all messages now include this)
                sender_info = content.get('sender_info', {})
                agent_log(f"sender_info from content: {bool(sender_info)}")
                
                # If not in content, check if it's a handshake
                if not sender_info and msg_type == 'handshake':
                    agent_log("Extracting from handshake content")
                    sender_info = {
                        'display_name': content.get('display_name', 'Anonymous Agent'),
                        'onion': content.get('onion'),
                        'port': content.get('port', 80),
                        'encryption_pubkey': content.get('encryption_pubkey')  # Include encryption key from handshake
                    }
                
                display_name = sender_info.get('display_name', 'Anonymous Agent')
                onion = sender_info.get('onion')
                port = sender_info.get('port', 80)
                
                agent_log(f"Extracted: name={display_name}, onion={onion}, port={port}")
                
                if not onion:
                    agent_log("Cannot auto-add: no onion address in message")
                    return
                
                peer = self.peers.add_peer_from_handshake({
                    'display_name': display_name,
                    'onion': onion,
                    'port': port,
                    'encryption_pubkey': sender_info.get('encryption_pubkey')
                }, sender_pubkey_b64)
                is_new_peer = True
                agent_log(f"Added peer: {peer.get_display_label()}")
                
                # Notify user that pairing is complete (recipient side)
                print("  Notifying user of new peer...")
                notified = self.webhook.notify_pairing_complete(
                    peer.display_name,
                    peer.address,
                    is_initiator=False
                )
                if notified:
                    print(f"  ✓ User notified: New peer {peer.display_name}")
                
                # Send handshake back so they can add us too
                print(f"  Sending handshake response...")
                response_handshake = MessageProtocol.create_handshake(
                    self.identity,
                    self._onion_address,
                    port=80,
                    encryption_pubkey_b64=self.identity.get_encryption_pubkey_b64()
                )
                success = self.peers.send_to_peer(peer.address, response_handshake)
                if success:
                    print(f"  ✓ Handshake response sent")
            except Exception as e:
                agent_log(f"Failed to auto-add: {e}")
                import traceback
                agent_log(traceback.format_exc())
                return
        
        if not peer:
            print(f"  Cannot process: unknown sender and not a handshake")
            return
        
        print(f"  From: {peer.get_display_label()}")
        print(f"  Type: {msg_type}")
        print(f"  Content: {content}")
        
        # If it's a handshake from an existing peer, send handshake back
        # This ensures both sides have each other's info
        if msg_type == 'handshake' and not is_new_peer:
            print(f"  Handshake from existing peer, sending response...")
            response_handshake = MessageProtocol.create_handshake(
                self.identity,
                self._onion_address,
                port=80,
                encryption_pubkey_b64=self.identity.get_encryption_pubkey_b64()
            )
            success = self.peers.send_to_peer(peer.address, response_handshake)
            if success:
                print(f"  ✓ Handshake response sent to {peer.display_name}")
            else:
                print(f"  ⚠ Failed to send handshake response")
        
        if is_new_peer:
            print(f"  🎉 New peer! You can now reply to {peer.display_name}")
        
        # Notify OpenClaw via webhook
        print("  Notifying OpenClaw...")
        notified = self.webhook.notify_new_message(decrypted, sender_address)
        if notified:
            print("  ✓ OpenClaw notified")
        else:
            print("  ⚠ OpenClaw notification failed (message still saved)")
    
    def __enter__(self):
        self.start()
        return self
    
    def __exit__(self, *args):
        self.stop()
