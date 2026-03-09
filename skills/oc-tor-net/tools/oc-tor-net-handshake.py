#!/usr/bin/env python3
"""
Send a handshake to a peer (for initial pairing)
"""
import sys
import json
import os

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


def main(peer_address: str):
    import os
    from pathlib import Path
    
    config_dir = Path.home() / ".openclaw/p2p"
    identity_file = config_dir / "identity.json"
    peers_file = config_dir / "peers.json"
    
    if not identity_file.exists():
        print("Error: No identity found. Run oc-tor-net-start.py first.")
        sys.exit(1)

    # Check daemon is running
    daemon_status = TransportFactory.check_daemon(str(config_dir))
    if not daemon_status['running']:
        print(f"Error: {daemon_status['error']}")
        sys.exit(1)

    # Load identity
    identity = Identity(str(config_dir))

    # Get our network address from daemon config
    our_transport = daemon_status.get('transport', 'tor')
    our_address = daemon_status.get('address', daemon_status.get('onion_address'))
    if not our_address and our_transport == 'tor':
        tor_hostname = config_dir / 'tor' / 'hidden_service' / 'hostname'
        if not tor_hostname.exists():
            print("Error: No hidden service found. Is the daemon running?")
            sys.exit(1)
        with open(tor_hostname) as f:
            our_address = f.read().strip()
    
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
    
    # Create peer object with daemon's SOCKS port
    socks_port = daemon_status.get('socks_port', 9060)
    socks_proxy = {
        'http': f'socks5h://127.0.0.1:{socks_port}',
        'https': f'socks5h://127.0.0.1:{socks_port}'
    }
    peer_transport = peer_info.get('transport', 'tor')
    peer_network_addr = peer_info.get('address', peer_info.get('onion', ''))

    peer = Peer(
        address=peer_address,
        onion=peer_network_addr,
        port=peer_info['port'],
        public_key_b64=peer_info['public_key'],
        socks_proxy=socks_proxy,
        transport=peer_transport
    )

    print(f"Sending handshake to: {peer_address}")
    print(f"  Address: {peer.network_address}")
    print(f"  My address: {our_address}")
    print()

    # Create handshake message
    handshake = MessageProtocol.create_handshake(
        identity,
        our_address,
        port=80,
        encryption_pubkey_b64=identity.get_encryption_pubkey_b64()
    )
    # Inject transport info (protocol.py is transport-agnostic)
    handshake['content']['transport'] = our_transport
    handshake['content']['address'] = our_address
    
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
        print("Is the peer online? Is the daemon running?")
    
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
