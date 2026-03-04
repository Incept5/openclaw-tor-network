#!/usr/bin/env python3
"""
Send a message to a peer
"""
import sys
import json

sys.path.insert(0, '../lib')
sys.path.insert(0, './lib')

try:
    from identity import Identity
    from peer import Peer, PeerManager
    from protocol import MessageProtocol
except ImportError as e:
    print(f"Error: {e}")
    sys.exit(1)


def main(peer_address: str, message_text: str):
    import os
    from pathlib import Path
    
    config_dir = Path.home() / ".openclaw/p2p"
    identity_file = config_dir / "identity.json"
    peers_file = config_dir / "peers.json"
    
    if not identity_file.exists():
        print("Error: No identity found. Run p2p_start.py first.")
        sys.exit(1)
    
    if not peers_file.exists():
        print("Error: No peers found. Run p2p_accept_invite.py first.")
        sys.exit(1)
    
    # Load identity
    identity = Identity(str(config_dir))
    
    # Load peer
    with open(peers_file) as f:
        peers_data = json.load(f)
    
    if peer_address not in peers_data:
        # Try to match by short prefix
        matches = [a for a in peers_data.keys() if a.startswith(peer_address)]
        if len(matches) == 1:
            peer_address = matches[0]
        elif len(matches) > 1:
            print(f"Error: Multiple peers match '{peer_address}':")
            for m in matches:
                print(f"  {m}")
            sys.exit(1)
        else:
            print(f"Error: Peer not found: {peer_address}")
            print(f"Known peers: {list(peers_data.keys())}")
            sys.exit(1)
    
    peer_info = peers_data[peer_address]
    
    # Create peer object
    peer = Peer(
        address=peer_address,
        onion=peer_info['onion'],
        port=peer_info['port'],
        public_key_b64=peer_info['public_key']
    )
    
    print(f"Sending to: {peer_address}")
    print(f"  Onion: {peer.onion}")
    print(f"  Message: {message_text}")
    print()
    
    # Create and encrypt message
    message = MessageProtocol.create_message('text', {
        'text': message_text
    })
    
    encrypted = MessageProtocol.encrypt_message(
        message,
        identity.signing_key,
        peer.public_key
    )
    
    # Send
    success = peer.send_message(encrypted)
    
    if success:
        print("Message sent successfully!")
    else:
        print("Failed to send message.")
        print("Is the peer online? Is Tor running on your machine?")
    
    return {
        "success": success,
        "peer": peer_address,
        "message": message_text
    }


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: p2p_send.py '<peer_address>' '<message>'")
        print()
        print("Example:")
        print("  python3 p2p_send.py '@abc123...ed25519' 'Hello from missy!'")
        print()
        print("You can use a prefix if it's unique:")
        print("  python3 p2p_send.py '@abc123' 'Hello!'")
        sys.exit(1)
    
    peer_address = sys.argv[1]
    message_text = sys.argv[2]
    
    result = main(peer_address, message_text)
    print("\n" + json.dumps(result))
