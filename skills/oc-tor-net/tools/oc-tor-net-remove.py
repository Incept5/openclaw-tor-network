#!/usr/bin/env python3
"""
Remove or block a peer

Usage:
  oc-tor-net-remove.py "Stuart"           # Remove by name
  oc-tor-net-remove.py "@evNG3V..."       # Remove by address
  oc-tor-net-remove.py "Stuart" --block   # Remove and block
"""
import sys
import json
from pathlib import Path
from datetime import datetime


def load_peers():
    """Load peers from disk"""
    config_dir = Path.home() / ".openclaw/p2p"
    peers_file = config_dir / "peers.json"
    blocked_file = config_dir / "blocked.json"
    
    peers = {}
    blocked = []
    
    if peers_file.exists():
        with open(peers_file) as f:
            peers = json.load(f)
    
    if blocked_file.exists():
        with open(blocked_file) as f:
            blocked = json.load(f)
    
    return peers, blocked


def save_peers(peers):
    """Save peers to disk"""
    config_dir = Path.home() / ".openclaw/p2p"
    peers_file = config_dir / "peers.json"
    
    with open(peers_file, 'w') as f:
        json.dump(peers, f, indent=2)


def save_blocked(blocked):
    """Save blocked list to disk"""
    config_dir = Path.home() / ".openclaw/p2p"
    blocked_file = config_dir / "blocked.json"
    
    with open(blocked_file, 'w') as f:
        json.dump(blocked, f, indent=2)


def find_peer(peers, query):
    """Find peer by name or address"""
    query_lower = query.lower()
    matches = []
    
    for address, info in peers.items():
        display_name = info.get('display_name', 'Anonymous Agent')
        
        if query_lower in display_name.lower():
            matches.append((address, info, 'name'))
        elif query_lower in address.lower():
            matches.append((address, info, 'address'))
    
    return matches


def main():
    if len(sys.argv) < 2:
        print("Usage: oc-tor-net-remove.py <name-or-address> [--block]")
        print("Example: oc-tor-net-remove.py 'Stuart'")
        print("Example: oc-tor-net-remove.py 'Stuart' --block")
        sys.exit(1)
    
    query = sys.argv[1]
    block = '--block' in sys.argv
    
    peers, blocked = load_peers()
    
    if not peers:
        print("No peers to remove.")
        return
    
    # Find matching peer
    matches = find_peer(peers, query)
    
    if not matches:
        print(f"❌ No peer found matching '{query}'")
        return
    
    if len(matches) > 1:
        print(f"⚠️  Multiple matches for '{query}':")
        for addr, info, _ in matches:
            print(f"   - {info.get('display_name', 'Unknown')} ({addr[:20]}...)")
        print("\nBe more specific.")
        return
    
    # Remove the peer
    address, info, match_type = matches[0]
    display_name = info.get('display_name', 'Unknown')
    
    print("=" * 70)
    print("REMOVE PEER")
    print("=" * 70)
    print()
    transport = info.get('transport', 'tor')
    network_addr = info.get('address', info.get('onion', ''))
    print(f"Name:      {display_name}")
    print(f"Address:   {address[:20]}...{address[-12:]}")
    print(f"Transport: {transport}")
    print(f"Network:   {network_addr}")
    print()
    
    if block:
        print("This will REMOVE the peer and BLOCK future contact.")
    else:
        print("This will REMOVE the peer. You can re-add them later.")
    
    confirm = input("\nConfirm? [y/N]: ").strip().lower()
    
    if confirm != 'y':
        print("Cancelled.")
        return
    
    # Remove from peers
    del peers[address]
    save_peers(peers)
    
    # Add to blocked if requested
    if block:
        blocked.append({
            'address': address,
            'display_name': display_name,
            'blocked_at': datetime.now().isoformat()
        })
        save_blocked(blocked)
        print(f"\n✅ {display_name} removed and blocked.")
    else:
        print(f"\n✅ {display_name} removed.")
    
    print("\nTo re-add them later, you'll need their invite code.")
    
    return {
        'removed': True,
        'blocked': block,
        'peer_name': display_name,
        'peer_address': address
    }


if __name__ == "__main__":
    result = main()
    if result:
        print("\n" + json.dumps(result, indent=2))
