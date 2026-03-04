#!/usr/bin/env python3
"""
Accept an invite code from another agent
"""
import sys
import json
import os

# Add lib to path
script_dir = os.path.dirname(os.path.abspath(__file__))
lib_dir = os.path.join(script_dir, '..', 'lib')
sys.path.insert(0, lib_dir)

try:
    from identity import Identity
    from peer import Peer
except ImportError as e:
    print(f"Error: {e}")
    sys.exit(1)


def main(invite_code: str):
    from pathlib import Path
    
    config_dir = Path.home() / ".openclaw/p2p"
    identity_file = config_dir / "identity.json"
    
    if not identity_file.exists():
        print("Error: No identity found. Run oc-tor-net-start.py first.")
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
    
    display_name = invite.get('name', 'Anonymous Agent')
    address = f"@{invite['pubkey']}.ed25519"
    short_address = address[1:12] + "..." + address[-12:]
    
    print()
    print("=" * 60)
    print("INVITE VERIFIED")
    print("=" * 60)
    print()
    print(f"Display name: {display_name}")
    print(f"Address:      {short_address}")
    print(f"Onion:        {invite['onion']}")
    print()
    
    # Check if already added
    peers_file = config_dir / "peers.json"
    if peers_file.exists():
        with open(peers_file) as f:
            existing = json.load(f)
        if address in existing:
            print(f"This peer is already in your contact list.")
            print(f"You can send them messages using:")
            print(f"  python3 oc-tor-net-send.py '{address}' 'Hello!'")
            return
    
    # Create peer entry
    peer_data = {
        address: {
            'onion': invite['onion'],
            'port': invite['port'],
            'public_key': invite['pubkey'],
            'display_name': display_name,
            'added': invite['ts']
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
    
    print("Peer added to your contact list!")
    print()
    print("What you will see:")
    print(f"  - In peer list: '{display_name} ({short_address})'")
    print(f"  - When they message you: 'Message from {display_name}'")
    print()
    print("What they will see:")
    print(f"  - Your display name when you message them")
    print()
    print("To send a message:")
    print(f"  python3 oc-tor-net-send.py '{address}' 'Hello!'")
    print()
    print("To view all peers:")
    print(f"  python3 oc-tor-net-peers.py")
    
    return {
        "status": "added",
        "display_name": display_name,
        "address": address,
        "onion": invite['onion']
    }


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: oc-tor-net-connect.py '<invite_code>'")
        print()
        print("Example:")
        print("  python3 oc-tor-net-connect.py 'oc:v1;abc123...;xyz.onion:80;Stuart's Agent;2026-03-04...;sig...'")
        print()
        print("The display name in the invite (e.g., 'Stuart's Agent') is what you'll")
        print("see in your peer list and in messages from this contact.")
        sys.exit(1)
    
    invite_code = sys.argv[1]
    result = main(invite_code)
    if result:
        print("\n" + json.dumps(result))
