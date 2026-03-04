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
except ImportError as e:
    print(f"Error: {e}")
    sys.exit(1)


def check_tor_running():
    """Check if Tor process is running"""
    import subprocess
    try:
        result = subprocess.run(['pgrep', '-f', 'tor'], capture_output=True)
        return result.returncode == 0
    except:
        return False


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
    tor_hostname = config_dir / "tor" / "hidden_service" / "hostname"
    peers_file = config_dir / "peers.json"
    
    # Load identity
    if identity_file.exists():
        identity = Identity(str(config_dir))
        address = identity.get_address()
        display_name = identity.get_display_name()
        short_address = address[1:12] + "..." + address[-12:]
    else:
        print("Error: No identity found. Run oc-tor-net-start.py first.")
        sys.exit(1)
    
    # Get onion address
    onion = None
    if tor_hostname.exists():
        with open(tor_hostname) as f:
            onion = f.read().strip()
    
    # Get peer count
    peer_count = 0
    if peers_file.exists():
        with open(peers_file) as f:
            peers = json.load(f)
            peer_count = len(peers)
    
    # Check running status
    tor_running = check_tor_running()
    daemon_running = check_daemon_running()
    
    # Handle --invite flag
    if '--invite' in sys.argv:
        if onion:
            invite = identity.generate_invite(onion, port=80)
            invite_code = identity.encode_invite(invite)
            print(invite_code)
        else:
            print("Error: Tor not ready")
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
    if onion:
        print(f"  Onion:        {onion}")
    print()
    
    # Status
    print("Status:")
    print(f"  Tor daemon:     {'✅ Running' if tor_running else '❌ Not running'}")
    print(f"  P2P daemon:     {'✅ Running' if daemon_running else '❌ Not running'}")
    print(f"  Peers:          {peer_count}")
    print()
    
    # Invite code
    if onion:
        print("Your invite code (share this to let others connect):")
        print()
        invite = identity.generate_invite(onion, port=80)
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
        'onion': onion,
        'tor_running': tor_running,
        'daemon_running': daemon_running,
        'peer_count': peer_count
    }


if __name__ == "__main__":
    result = main()
    if result and '--invite' not in sys.argv and '--address' not in sys.argv:
        print("\n" + json.dumps(result, indent=2))
