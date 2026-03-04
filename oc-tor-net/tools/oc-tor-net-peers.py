#!/usr/bin/env python3
"""
List and query paired peers

Usage:
  oc-tor-net-peers.py                    # List all peers
  oc-tor-net-peers.py --check "Stuart"   # Check if paired with Stuart
  oc-tor-net-peers.py --check "@evNG3V"  # Check by address prefix
"""
import sys
import json
from pathlib import Path


def load_peers():
    """Load peers from disk"""
    config_dir = Path.home() / ".openclaw/p2p"
    peers_file = config_dir / "peers.json"
    
    if not peers_file.exists():
        return {}
    
    with open(peers_file) as f:
        return json.load(f)


def list_all_peers(peers):
    """Display all peers in a formatted list"""
    if not peers:
        print("No peers found. Run oc-tor-net-connect.py to add peers.")
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


def check_peer(peers, query):
    """Check if a specific peer exists (by name or address)"""
    query_lower = query.lower()
    matches = []
    
    for address, info in peers.items():
        display_name = info.get('display_name', 'Anonymous Agent')
        short_address = address[1:12] + "..." + address[-12:]
        
        # Check if query matches display name (case insensitive)
        if query_lower in display_name.lower():
            matches.append({
                'address': address,
                'short_address': short_address,
                'display_name': display_name,
                'onion': info['onion'],
                'added': info.get('added', 'unknown'),
                'match_type': 'name'
            })
        # Check if query matches address (prefix or full)
        elif query_lower in address.lower():
            matches.append({
                'address': address,
                'short_address': short_address,
                'display_name': display_name,
                'onion': info['onion'],
                'added': info.get('added', 'unknown'),
                'match_type': 'address'
            })
    
    return matches


def display_check_result(matches, query):
    """Display the result of a peer check"""
    print("=" * 70)
    print(f"CHECK: '{query}'")
    print("=" * 70)
    print()
    
    if not matches:
        print(f"❌ Not paired with '{query}'")
        print()
        print("You can pair with them by running:")
        print(f"  python3 oc-tor-net-connect.py '<their-invite-code>'")
        return {
            'found': False,
            'query': query,
            'message': f"Not paired with '{query}'"
        }
    
    if len(matches) == 1:
        peer = matches[0]
        print(f"✅ Paired with: {peer['display_name']}")
        print(f"   Address: {peer['short_address']}")
        print(f"   Onion:   {peer['onion']}")
        print(f"   Added:   {peer['added']}")
        print()
        print("You can send them a message:")
        print(f"  python3 oc-tor-net-send.py '{peer['address']}' 'Hello!'")
        
        return {
            'found': True,
            'query': query,
            'peer': peer
        }
    else:
        print(f"⚠️  Multiple matches for '{query}':")
        for peer in matches:
            print(f"   - {peer['display_name']} ({peer['short_address']})")
        print()
        print("Be more specific with the full name or address.")
        
        return {
            'found': True,
            'query': query,
            'multiple': True,
            'peers': matches
        }


def main():
    peers = load_peers()
    
    # Check for --check argument
    if len(sys.argv) > 1 and sys.argv[1] == '--check':
        if len(sys.argv) < 3:
            print("Usage: oc-tor-net-peers.py --check <name-or-address>")
            print("Example: oc-tor-net-peers.py --check 'Stuart'")
            print("Example: oc-tor-net-peers.py --check '@evNG3V'")
            sys.exit(1)
        
        query = sys.argv[2]
        matches = check_peer(peers, query)
        result = display_check_result(matches, query)
        print("\n" + json.dumps(result, indent=2))
        return result
    
    # Default: list all peers
    peer_list = list_all_peers(peers)
    print("\n" + json.dumps({"peers": peer_list}))
    return peer_list


if __name__ == "__main__":
    main()
