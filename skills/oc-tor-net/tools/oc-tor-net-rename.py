#!/usr/bin/env python3
"""
Rename a peer (local nickname)

Usage:
  oc-tor-net-rename.py "Stuart" "Stuart Work"   # Rename Stuart to "Stuart Work"
"""
import sys
import json
from pathlib import Path


def load_peers():
    """Load peers from disk"""
    config_dir = Path.home() / ".openclaw/p2p"
    peers_file = config_dir / "peers.json"
    
    if peers_file.exists():
        with open(peers_file) as f:
            return json.load(f)
    return {}


def save_peers(peers):
    """Save peers to disk"""
    config_dir = Path.home() / ".openclaw/p2p"
    peers_file = config_dir / "peers.json"
    
    with open(peers_file, 'w') as f:
        json.dump(peers, f, indent=2)


def find_peer(peers, query):
    """Find peer by name or address"""
    query_lower = query.lower()
    matches = []
    
    for address, info in peers.items():
        display_name = info.get('display_name', 'Anonymous Agent')
        
        if query_lower in display_name.lower():
            matches.append((address, info))
        elif query_lower in address.lower():
            matches.append((address, info))
    
    return matches


def main():
    if len(sys.argv) < 3:
        print("Usage: oc-tor-net-rename.py <current-name> <new-name>")
        print("Example: oc-tor-net-rename.py 'Stuart' 'Stuart Work'")
        sys.exit(1)
    
    current_name = sys.argv[1]
    new_name = sys.argv[2]
    
    peers = load_peers()
    
    if not peers:
        print("No peers to rename.")
        return
    
    # Find matching peer
    matches = find_peer(peers, current_name)
    
    if not matches:
        print(f"❌ No peer found matching '{current_name}'")
        return
    
    if len(matches) > 1:
        print(f"⚠️  Multiple matches for '{current_name}':")
        for addr, info in matches:
            print(f"   - {info.get('display_name', 'Unknown')} ({addr[:20]}...)")
        print("\nBe more specific.")
        return
    
    # Rename the peer
    address, info = matches[0]
    old_name = info.get('display_name', 'Unknown')
    
    print(f"Renaming '{old_name}' to '{new_name}'")
    
    info['display_name'] = new_name
    info['original_name'] = old_name  # Keep track of original
    peers[address] = info
    save_peers(peers)
    
    print(f"✅ Renamed. You will now see '{new_name}' in your peer list.")
    print(f"   (Their actual display name is still '{old_name}')")
    
    return {
        'renamed': True,
        'old_name': old_name,
        'new_name': new_name,
        'address': address
    }


if __name__ == "__main__":
    result = main()
    if result:
        print("\n" + json.dumps(result, indent=2))
