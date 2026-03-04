#!/usr/bin/env python3
"""
List all known peers and their status
"""
import sys
import json
from pathlib import Path

sys.path.insert(0, '../lib')
sys.path.insert(0, './lib')


def main():
    config_dir = Path.home() / ".openclaw/p2p"
    peers_file = config_dir / "peers.json"
    
    if not peers_file.exists():
        print("No peers found. Run p2p_accept_invite.py to add peers.")
        return []
    
    with open(peers_file) as f:
        peers = json.load(f)
    
    if not peers:
        print("No peers found.")
        return []
    
    print("Known peers:")
    print("=" * 60)
    
    for address, info in peers.items():
        print(f"Address:    {address}")
        print(f"Onion:      {info['onion']}")
        print(f"Port:       {info['port']}")
        print(f"Added:      {info.get('added', 'unknown')}")
        print(f"Last seen:  {info.get('last_seen', 'never')}")
        print("-" * 60)
    
    print(f"\nTotal: {len(peers)} peer(s)")
    
    return list(peers.keys())


if __name__ == "__main__":
    peers = main()
    print("\n" + json.dumps({"peers": peers}))
