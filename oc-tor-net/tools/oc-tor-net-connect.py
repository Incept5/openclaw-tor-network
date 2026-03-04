#!/usr/bin/env python3
"""
Accept an invite code from another agent
"""
import sys
import json

sys.path.insert(0, '../lib')
sys.path.insert(0, './lib')

try:
    from agent import P2PAgent
    from identity import Identity
    from peer import PeerManager
except ImportError as e:
    print(f"Error: {e}")
    sys.exit(1)


def main(invite_code: str):
    import os
    from pathlib import Path
    
    config_dir = Path.home() / ".openclaw/p2p"
    identity_file = config_dir / "identity.json"
    
    if not identity_file.exists():
        print("Error: No identity found. Run p2p_start.py first.")
        sys.exit(1)
    
    # Load identity
    identity = Identity(str(config_dir))
    
    # Decode and verify invite
    print("Decoding invite...")
    try:
        invite = Identity.decode_invite(invite_code)
    except Exception as e:
        print(f"Error: Invalid invite format - {e}")
        sys.exit(1)
    
    print("Verifying signature...")
    if not Identity.verify_invite(invite):
        print("Error: Invalid invite signature")
        sys.exit(1)
    
    print(f"Invite valid!")
    print(f"  Public key: {invite['pubkey'][:20]}...")
    print(f"  Onion: {invite['onion']}")
    print(f"  Port: {invite['port']}")
    
    # Create peer manager (without full agent - we just need to store the peer)
    # But we need Tor SOCKS proxy... let's check if Tor is running
    
    from peer import Peer
    
    address = f"@{invite['pubkey']}.ed25519"
    
    # Check if already added
    peers_file = config_dir / "peers.json"
    if peers_file.exists():
        with open(peers_file) as f:
            existing = json.load(f)
        if address in existing:
            print(f"\nPeer already added: {address}")
            print("Use p2p_send.py to send them a message.")
            return
    
    # Create peer entry
    peer_data = {
        address: {
            'onion': invite['onion'],
            'port': invite['port'],
            'public_key': invite['pubkey'],
            'added': json.dumps(json.loads(json.dumps(invite['ts'])))
        }
    }
    
    # Merge with existing peers
    if peers_file.exists():
        with open(peers_file) as f:
            existing = json.load(f)
        existing.update(peer_data)
        peer_data = existing
    
    # Save
    with open(peers_file, 'w') as f:
        json.dump(peer_data, f, indent=2)
    
    print(f"\nPeer added: {address}")
    print()
    print("To send a message (after starting p2p_start.py):")
    print(f"  python3 p2p_send.py '{address}' 'Hello!'")
    
    return {
        "status": "added",
        "address": address,
        "onion": invite['onion']
    }


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: p2p_accept_invite.py '<invite_code>'")
        print()
        print("Example:")
        print("  python3 p2p_accept_invite.py 'oc:v1;abc123...;xyz.onion:80;2026-03-04...;sig...'")
        sys.exit(1)
    
    invite_code = sys.argv[1]
    result = main(invite_code)
    if result:
        print("\n" + json.dumps(result))
