#!/usr/bin/env python3
"""
Show P2P agent status and info

Usage:
  oc-tor-net-status.py          # Show full status
  oc-tor-net-status.py --invite # Show invite code only
  oc-tor-net-status.py --address # Show address only
"""
import sys
import json
import os
from pathlib import Path

# Add lib to path
script_dir = os.path.dirname(os.path.abspath(__file__))
lib_dir = os.path.join(script_dir, '..', 'lib')
sys.path.insert(0, lib_dir)

try:
    from identity import Identity
    from transport import TransportFactory
except ImportError as e:
    print(f"Error: {e}")
    sys.exit(1)


def check_daemon_running():
    """Check if P2P daemon is running"""
    import subprocess
    try:
        result = subprocess.run(['pgrep', '-f', 'oc-tor-net-start'], capture_output=True)
        return result.returncode == 0
    except:
        return False


def main():
    config_dir = Path.home() / ".openclaw/p2p"
    identity_file = config_dir / "identity.json"
    peers_file = config_dir / "peers.json"
    daemon_json = config_dir / "daemon.json"

    # Load identity
    if identity_file.exists():
        identity = Identity(str(config_dir))
        address = identity.get_address()
        display_name = identity.get_display_name()
        short_address = address[1:12] + "..." + address[-12:]
    else:
        print("Error: No identity found. Run oc-tor-net-start.py first.")
        sys.exit(1)

    # Detect transport and network address from daemon.json
    transport = 'tor'
    network_address = None
    if daemon_json.exists():
        try:
            with open(daemon_json) as f:
                daemon_config = json.load(f)
            transport = daemon_config.get('transport', 'tor')
            network_address = daemon_config.get('address', daemon_config.get('onion_address'))
        except (json.JSONDecodeError, OSError):
            pass

    # Fallback: read Tor hostname file for backwards compat
    if not network_address and transport == 'tor':
        tor_hostname = config_dir / "tor" / "hidden_service" / "hostname"
        if tor_hostname.exists():
            with open(tor_hostname) as f:
                network_address = f.read().strip()

    # Get peer count
    peer_count = 0
    if peers_file.exists():
        with open(peers_file) as f:
            peers = json.load(f)
            peer_count = len(peers)

    # Check running status
    daemon_status = TransportFactory.check_daemon(str(config_dir))
    daemon_running = daemon_status.get('running', False)

    # Handle --invite flag
    if '--invite' in sys.argv:
        if network_address:
            # Include full I2P destination for SAM routing
            full_dest = None
            if transport == 'i2p':
                dest_keys_file = config_dir / "i2p" / "destination_keys.json"
                if dest_keys_file.exists():
                    try:
                        with open(dest_keys_file) as f:
                            full_dest = json.load(f).get('pub')
                    except (json.JSONDecodeError, OSError):
                        pass
            invite = identity.generate_invite(
                network_address, port=80, transport=transport,
                full_destination=full_dest
            )
            invite_code = identity.encode_invite(invite)
            print(invite_code)
        else:
            print(f"Error: Transport ({transport}) not ready")
            sys.exit(1)
        return

    # Handle --address flag
    if '--address' in sys.argv:
        print(address)
        return

    # Full status display
    print("=" * 70)
    print("P2P AGENT STATUS")
    print("=" * 70)
    print()

    # Identity
    print("Identity:")
    print(f"  Display name: {display_name}")
    print(f"  Address:      {short_address}")
    if network_address:
        addr_label = '.onion' if transport == 'tor' else '.b32.i2p'
        print(f"  {addr_label.lstrip('.')}:  {network_address}")
    print()

    # Check transport-specific status
    tor_running = False
    i2pd_running = False
    if transport == 'tor':
        import subprocess
        try:
            result = subprocess.run(['pgrep', '-f', 'tor.*SocksPort'], capture_output=True)
            tor_running = result.returncode == 0
        except:
            tor_running = daemon_running  # Fall back to daemon check
    elif transport == 'i2p':
        import subprocess
        try:
            result = subprocess.run(['pgrep', '-f', 'i2pd'], capture_output=True)
            i2pd_running = result.returncode == 0
        except:
            i2pd_running = daemon_running

    # Status
    transport_label = 'Tor' if transport == 'tor' else 'I2P'
    print("Status:")
    print(f"  Transport:      {transport_label}")
    if transport == 'tor':
        print(f"  Tor process:    {'Running' if tor_running else 'Not running'}")
    else:
        print(f"  i2pd process:   {'Running' if i2pd_running else 'Not running'}")
    print(f"  P2P daemon:     {'Running' if daemon_running else 'Not running'}")
    print(f"  Peers:          {peer_count}")
    print()

    # Invite code
    if network_address:
        print("Your invite code (share this to let others connect):")
        print()
        full_dest = None
        if transport == 'i2p':
            dest_keys_file = config_dir / "i2p" / "destination_keys.json"
            if dest_keys_file.exists():
                try:
                    with open(dest_keys_file) as f:
                        full_dest = json.load(f).get('pub')
                except (json.JSONDecodeError, OSError):
                    pass
        invite = identity.generate_invite(
            network_address, port=80, transport=transport,
            full_destination=full_dest
        )
        invite_code = identity.encode_invite(invite)
        print(f"  {invite_code}")
        print()

    # Quick commands
    print("Quick commands:")
    print(f"  oc-tor-net-peers.py              # List {peer_count} peer(s)")
    print(f"  oc-tor-net-messages.py           # Check for messages")
    print(f"  oc-tor-net-status.py --invite    # Show invite code")
    print()

    return {
        'display_name': display_name,
        'address': address,
        'network_address': network_address,
        'transport': transport,
        'daemon_running': daemon_running,
        'peer_count': peer_count
    }


if __name__ == "__main__":
    result = main()
    if result and '--invite' not in sys.argv and '--address' not in sys.argv:
        print("\n" + json.dumps(result, indent=2))
