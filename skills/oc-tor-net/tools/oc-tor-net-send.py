#!/usr/bin/env python3
"""
Send a message to a peer.
Requires the P2P daemon (oc-tor-net-start.py) to be running for connectivity.
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
    from peer import Peer, PeerManager
    from protocol import MessageProtocol
    from transport import TransportFactory
except ImportError as e:
    print(f"Error: {e}")
    sys.exit(1)


def main(peer_address: str, message_text: str):
    from pathlib import Path

    config_dir = Path.home() / ".openclaw/p2p"
    identity_file = config_dir / "identity.json"
    peers_file = config_dir / "peers.json"

    if not identity_file.exists():
        print("Error: No identity found. Run oc-tor-net-start.py first.")
        sys.exit(1)

    if not peers_file.exists():
        print("Error: No peers found. Run oc-tor-net-connect.py first.")
        sys.exit(1)

    # Check daemon is running (needed for SOCKS proxy)
    daemon_status = TransportFactory.check_daemon(str(config_dir))
    if not daemon_status['running']:
        print(f"Error: {daemon_status['error']}")
        print("The daemon must be running to send messages (provides network connectivity).")
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

    # Use SOCKS port from daemon config
    socks_port = daemon_status.get('socks_port', 9060)
    socks_proxy = {
        'http': f'socks5h://127.0.0.1:{socks_port}',
        'https': f'socks5h://127.0.0.1:{socks_port}'
    }

    transport = peer_info.get('transport', daemon_status.get('transport', 'tor'))
    network_addr = peer_info.get('address', peer_info.get('onion', ''))

    # Create peer object
    peer = Peer(
        address=peer_address,
        onion=network_addr,
        port=peer_info['port'],
        public_key_b64=peer_info['public_key'],
        socks_proxy=socks_proxy,
        transport=transport
    )

    print(f"Sending to: {peer_address}")
    print(f"  Address: {peer.network_address}")
    print(f"  Message: {message_text}")
    print()

    # Create and encrypt message, including our encryption pubkey for peer discovery
    message = MessageProtocol.create_message('text', {
        'text': message_text
    })

    encrypted = MessageProtocol.encrypt_message(
        message,
        identity.signing_key,
        peer.public_key,
        sender_encryption_pubkey=identity.encryption_key.public_key
    )

    # Send
    success = peer.send_message(encrypted)

    if success:
        print("Message sent successfully!")
    else:
        print("Failed to send message.")
        print("Is the peer online? Is the daemon running?")

    return {
        "success": success,
        "peer": peer_address,
        "message": message_text
    }


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: oc-tor-net-send.py '<peer_address>' '<message>'")
        print()
        print("Example:")
        print("  python3 oc-tor-net-send.py '@abc123...ed25519' 'Hello!'")
        print()
        print("You can use a prefix if it's unique:")
        print("  python3 oc-tor-net-send.py '@abc123' 'Hello!'")
        print()
        print("IMPORTANT: The P2P daemon (oc-tor-net-start.py) must be running.")
        sys.exit(1)

    peer_address = sys.argv[1]
    message_text = sys.argv[2]

    result = main(peer_address, message_text)
    print("\n" + json.dumps(result))
