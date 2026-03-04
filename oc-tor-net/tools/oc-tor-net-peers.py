#!/usr/bin/env python3
"""
List all known peers and their status
"""
import sys
import json
from pathlib import Path


def main():
    config_dir = Path.home() / ".openclaw/p2p"
    peers_file = config_dir / "peers.json"
    
    if not peers_file.exists():
        print("No peers found. Run oc-tor-net-connect.py to add peers.")
        return []
    
    with open(peers_file) as f:
        peers = json.load(f)
    
    if not peers:
        print("No peers found.")
        return []
    
    print("=" * 70)
    print("YOUR PEERS")
    print("=" * 70)
    print()
    
    for i, (address, info) in enumerate(peers.items(), 1):
        display_name = info.get('display_name', 'Anonymous Agent')
        short_address = address[1:12] + "..." + address[-12:]
        
        print(f"{i}. {display_name}")
        print(f"   Address:  {short_address}")
        print(f"   Onion:    {info['onion']}")
        print(f"   Added:    {info.get('added', 'unknown')}")
        if info.get('last_seen'):
            print(f"   Last seen: {info['last_seen']}")
        print()
    
    print("=" * 70)
    print(f"Total: {len(peers)} peer(s)")
    print()
    print("To send a message:")
    print("  python3 oc-tor-net-send.py '@address' 'Your message'")
    print()
    print("You can use a prefix if unique:")
    print("  python3 oc-tor-net-send.py '@abc123' 'Hello!'")
    
    return list(peers.keys())


if __name__ == "__main__":
    peers = main()
    print("\n" + json.dumps({"peers": peers}))
