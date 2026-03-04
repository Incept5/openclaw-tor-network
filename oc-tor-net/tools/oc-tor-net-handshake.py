#!/usr/bin/env python3
"""
Send a handshake to a peer (for initial pairing)
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


def main(peer_address: str):
    import os
    from pathlib import Path
    
    config_dir = Path.home() / ".openclaw/p2p"
    identity_file = config_dir / "identity.json"
    peers_file = config_dir / "peers.json"
    
    if not identity_file.exists():
        print("Error: No identity found. Run oc-tor-net-start.py first.")
        sys.exit(1)
    
    # Load identity
    identity = Identity(str(config_dir))
    
    # Get our onion address
    tor_hostname = config_dir / 'tor' / 'hidden_service' / 'hostname'
    if not tor_hostname.exists():
        print("Error: No Tor hidden service found. Is the daemon running?")
        sys.exit(1)
    
    with open(tor_hostname) as f:
        onion = f.read().strip()
    
    # Load peer
    if not peers_file.exists():
        print(f"Error: No peers found. Add peer first with oc-tor-net-connect.py")
        sys.exit(1)
    
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
    
    print(f"Sending handshake to: {peer_address}")
    print(f"  Onion: {peer.onion}")
    print(f"  My onion: {onion}")
    print()
    
    # Create handshake message
    handshake = MessageProtocol.create_handshake(
        identity,
        onion,
        port=80,
        encryption_pubkey_b64=identity.get_encryption_pubkey_b64()
    )
    
    # Encrypt and send
    encrypted = MessageProtocol.encrypt_message(
        handshake,
        identity.signing_key,
        peer.public_key
    )
    
    # Send
    success = peer.send_message(encrypted)
    
    if success:
        print("Handshake sent successfully!")
        print("The peer should auto-add you when they receive it.")
    else:
        print("Failed to send handshake.")
        print("Is the peer online? Is Tor running on your machine?")
    
    return {"success": success, "peer": peer_address}


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: oc-tor-net-handshake.py '<peer_address>'")
        print()
        print("Example:")
        print("  python3 oc-tor-net-handshake.py '@abc123...ed25519'")
        print()
        print("Sends a handshake message to establish bidirectional communication.")
        sys.exit(1)
    
    peer_address = sys.argv[1]
    result = main(peer_address)
    print("\n" + json.dumps(result))
