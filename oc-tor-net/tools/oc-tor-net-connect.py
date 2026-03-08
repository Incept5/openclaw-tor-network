#!/usr/bin/env python3
"""
Accept an invite code from another agent.
Adds the peer and sends a handshake so both sides can communicate.
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
    from protocol import MessageProtocol
    from tor_manager import TorManager
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

    # Check daemon is running (needed for Tor SOCKS proxy and handshake)
    daemon_status = TorManager.check_daemon(str(config_dir))
    if not daemon_status['running']:
        print(f"Error: {daemon_status['error']}")
        print("The daemon must be running to connect to peers.")
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

    # Require encryption_pubkey -- Ed25519 signing key is NOT compatible with NaCl box
    encryption_pubkey = invite.get('encryption_pubkey')
    if not encryption_pubkey:
        print("Error: Invite is missing encryption_pubkey (Curve25519 key).")
        print("This may be a legacy v1 invite. Ask the peer to regenerate their invite.")
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

    # Create peer entry with Curve25519 encryption key
    peer_data = {
        address: {
            'onion': invite['onion'],
            'port': invite['port'],
            'public_key': encryption_pubkey,
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

    # Send handshake so the remote peer can auto-add us
    print("Sending handshake to peer...")
    socks_port = daemon_status.get('socks_port', 9060)
    socks_proxy = {
        'http': f'socks5h://127.0.0.1:{socks_port}',
        'https': f'socks5h://127.0.0.1:{socks_port}'
    }

    peer = Peer(
        address=address,
        onion=invite['onion'],
        port=invite['port'],
        public_key_b64=encryption_pubkey,
        display_name=display_name,
        socks_proxy=socks_proxy
    )

    # Read our onion address from daemon config
    our_onion = daemon_status.get('onion_address')
    if not our_onion:
        tor_hostname = config_dir / 'tor' / 'hidden_service' / 'hostname'
        if tor_hostname.exists():
            with open(tor_hostname) as f:
                our_onion = f.read().strip()

    if our_onion:
        handshake = MessageProtocol.create_handshake(
            identity,
            our_onion,
            port=80,
            encryption_pubkey_b64=identity.get_encryption_pubkey_b64()
        )
        encrypted = MessageProtocol.encrypt_message(
            handshake,
            identity.signing_key,
            peer.public_key,
            sender_encryption_pubkey=identity.encryption_key.public_key
        )
        success = peer.send_message(encrypted)
        if success:
            print("  Handshake sent! The peer will auto-add you.")
        else:
            print("  Warning: Failed to send handshake. The peer may not be online.")
            print("  They will auto-add you when you send your first message.")
    else:
        print("  Warning: Could not determine our .onion address for handshake.")
        print("  The peer will need to add you manually.")

    print()
    print(f"To send a message:")
    print(f"  python3 oc-tor-net-send.py '{address}' 'Hello!'")
    print()
    print(f"To view all peers:")
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
        print("IMPORTANT: The P2P daemon (oc-tor-net-start.py) must be running.")
        print("The display name in the invite is what you'll see in your peer list.")
        sys.exit(1)

    invite_code = sys.argv[1]
    result = main(invite_code)
    if result:
        print("\n" + json.dumps(result))
