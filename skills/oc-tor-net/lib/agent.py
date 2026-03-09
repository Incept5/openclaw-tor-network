"""
Main P2P agent coordinator
"""
import os
import json
from pathlib import Path
from typing import Optional
from datetime import datetime

from identity import Identity
from transport import TransportFactory
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
    
    def __init__(self, config_dir: str = None, service_port: int = 8765,
                 transport: str = None):
        if config_dir is None:
            config_dir = os.path.expanduser("~/.openclaw/p2p")
        self.config_dir = Path(config_dir)
        self.config_dir.mkdir(parents=True, exist_ok=True)

        self.service_port = service_port
        # Determine transport type from config if not specified
        if transport is None:
            transport = TransportFactory.get_transport_type(str(self.config_dir))
        self.transport_type = transport

        # Components
        self.identity: Optional[Identity] = None
        self.transport = None  # TransportManager instance
        self.server: Optional[MessageServer] = None
        self.peers: Optional[PeerManager] = None

        self._network_address: Optional[str] = None  # .onion or .b32.i2p
        self._running = False
    
    def start(self) -> str:
        """
        Start the P2P agent.
        Returns the network address (.onion or .b32.i2p).
        """
        print(f"=== Starting P2P Agent (transport: {self.transport_type}) ===")

        # 1. Load/create identity
        print("Loading identity...")
        self.identity = Identity(str(self.config_dir))
        print(f"  Address: {self.identity.get_address()}")
        print(f"  Encryption pubkey: {self.identity.get_encryption_pubkey_b64()[:40]}...")

        # 2. Start message server (local HTTP endpoint)
        print(f"Starting message server on port {self.service_port}...")
        self.server = MessageServer(port=self.service_port, inbox_dir=str(self.config_dir / "inbox"))
        self.server.start(message_callback=self._on_message_received)

        # 3. Start transport (Tor or I2P)
        transport_label = 'Tor hidden service' if self.transport_type == 'tor' else 'I2P tunnel'
        print(f"Starting {transport_label}...")
        data_dir = str(self.config_dir / self.transport_type)
        self.transport = TransportFactory.create(
            self.transport_type, data_dir=data_dir, service_port=self.service_port
        )
        self._network_address = self.transport.start()

        # 4. Initialize peer manager
        print("Initializing peer manager...")
        self.peers = PeerManager(
            self.identity,
            data_dir=str(self.config_dir),
            socks_proxy=self.transport.get_proxy(),
            transport_manager=self.transport
        )
        # Store network address and transport type in peer manager for sender info
        self.peers.network_address = self._network_address
        self.peers.tor_onion = self._network_address  # Legacy compat
        self.peers.transport_type = self.transport_type

        # 5. Initialize webhook for OpenClaw notification
        print("Initializing OpenClaw webhook...")
        self.webhook = OpenClawWebhook()

        self._running = True

        addr_label = '.onion' if self.transport_type == 'tor' else '.b32.i2p'
        print(f"\n=== P2P Agent Ready ===")
        print(f"Transport:    {self.transport_type}")
        print(f"Your address: {self.identity.get_address()}")
        print(f"Your {addr_label}:  {self._network_address}")
        print(f"\nTo connect, share your invite code:")
        print(f"  python3 tools/oc-tor-net-invite.py")

        return self._network_address
    
    def stop(self):
        """Stop the P2P agent"""
        print("\n=== Stopping P2P Agent ===")

        if self.server:
            self.server.stop()
            print("Message server stopped")

        if self.transport:
            self.transport.stop()
            print(f"{self.transport_type.upper()} transport stopped")

        self._running = False
        print("P2P agent stopped")
    
    def generate_invite(self) -> str:
        """Generate an invite code for others to connect"""
        if not self._running:
            raise RuntimeError("P2P agent not started")

        # For I2P, include the full destination so peers can use SAM STREAM CONNECT
        full_dest = None
        if self.transport_type == 'i2p' and hasattr(self.transport, '_pub_dest'):
            full_dest = self.transport._pub_dest

        invite = self.identity.generate_invite(
            self._network_address, port=80, transport=self.transport_type,
            full_destination=full_dest
        )
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
                self._network_address,
                port=80,
                encryption_pubkey_b64=self.identity.get_encryption_pubkey_b64()
            )
            # Inject transport info (protocol.py is transport-agnostic)
            handshake['content']['transport'] = self.transport_type
            handshake['content']['address'] = self._network_address
            if self.transport_type == 'i2p' and hasattr(self.transport, '_pub_dest'):
                handshake['content']['full_destination'] = self.transport._pub_dest
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
        
        # Capture sender's encryption pubkey from envelope (for auto-add)
        import base64
        from nacl.signing import VerifyKey

        sender_encryption_pubkey_b64 = encrypted_message.get('sender_encryption_pubkey')

        # Decrypt using our Curve25519 encryption key
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
                        'onion': content.get('address', content.get('onion')),
                        'address': content.get('address', content.get('onion')),
                        'port': content.get('port', 80),
                        'transport': content.get('transport', 'tor'),
                        'encryption_pubkey': content.get('encryption_pubkey')
                    }

                display_name = sender_info.get('display_name', 'Anonymous Agent')
                network_addr = sender_info.get('address', sender_info.get('onion'))
                port = sender_info.get('port', 80)
                transport = sender_info.get('transport', 'tor')

                agent_log(f"Extracted: name={display_name}, address={network_addr}, port={port}, transport={transport}")

                if not network_addr:
                    agent_log("Cannot auto-add: no network address in message")
                    return

                # encryption_pubkey: prefer from sender_info (handshake content),
                # fall back to sender_encryption_pubkey from encrypted envelope
                enc_pubkey = sender_info.get('encryption_pubkey') or sender_encryption_pubkey_b64
                if not enc_pubkey:
                    agent_log("Cannot auto-add: no encryption pubkey in message or envelope")
                    return

                peer = self.peers.add_peer_from_handshake({
                    'display_name': display_name,
                    'onion': network_addr,
                    'address': network_addr,
                    'port': port,
                    'transport': transport,
                    'encryption_pubkey': enc_pubkey
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
                    self._network_address,
                    port=80,
                    encryption_pubkey_b64=self.identity.get_encryption_pubkey_b64()
                )
                response_handshake['content']['transport'] = self.transport_type
                response_handshake['content']['address'] = self._network_address
                if self.transport_type == 'i2p' and hasattr(self.transport, '_pub_dest'):
                    response_handshake['content']['full_destination'] = self.transport._pub_dest
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
        
        # For handshakes from existing peers, do NOT send a response — this
        # would create an infinite handshake loop (A responds to B, B responds
        # to A, forever), blocking the single-threaded HTTP server each time.
        # Handshake responses are only sent for NEW peers (auto-add above).
        if msg_type == 'handshake' and not is_new_peer:
            print(f"  Handshake from existing peer {peer.display_name} — acknowledged (no response needed)")
        
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
