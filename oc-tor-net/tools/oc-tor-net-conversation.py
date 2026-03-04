#!/usr/bin/env python3
"""
Get conversation history with a specific peer

Usage:
  oc-tor-net-conversation.py "Stuart"     # Show conversation with Stuart
  oc-tor-net-conversation.py "@evNG3V"    # By address prefix
"""
import sys
import json
from pathlib import Path
from datetime import datetime


def load_peers():
    """Load peers from disk"""
    config_dir = Path.home() / ".openclaw/p2p"
    peers_file = config_dir / "peers.json"
    
    if peers_file.exists():
        with open(peers_file) as f:
            return json.load(f)
    return {}


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


def load_conversation(peer_address):
    """Load all messages to/from a specific peer"""
    config_dir = Path.home() / ".openclaw/p2p"
    inbox_dir = config_dir / "inbox"
    
    messages = []
    
    # Check inbox and processed
    for folder in [inbox_dir, inbox_dir / "processed"]:
        if not folder.exists():
            continue
        
        for filepath in folder.glob("*.json"):
            try:
                with open(filepath) as f:
                    data = json.load(f)
                
                # Check if this message is to/from the peer
                sender = data.get('sender', '')
                
                if sender == peer_address:
                    messages.append({
                        'direction': 'received',
                        'timestamp': data.get('ts', 'unknown'),
                        'type': data.get('type', 'unknown'),
                        'content': data.get('content', {})
                    })
                    
            except Exception:
                continue
    
    # Sort by timestamp
    messages.sort(key=lambda x: x['timestamp'])
    return messages


def display_conversation(messages, peer_name):
    """Display conversation in a chat-like format"""
    if not messages:
        print(f"No conversation history with {peer_name}.")
        return
    
    print("=" * 70)
    print(f"CONVERSATION WITH {peer_name}")
    print("=" * 70)
    print()
    
    for msg in messages:
        ts = msg['timestamp']
        if ts != 'unknown' and 'T' in ts:
            try:
                dt = datetime.fromisoformat(ts.replace('Z', '+00:00'))
                ts = dt.strftime('%H:%M')
            except:
                pass
        
        direction = "←" if msg['direction'] == 'received' else "→"
        content = msg['content']
        
        if msg['type'] == 'text':
            text = content.get('text', '')
        elif msg['type'] == 'handshake':
            text = "[Handshake - connection established]"
        elif msg['type'] == 'query':
            text = f"[Query: {content.get('query_type', 'unknown')}]"
        elif msg['type'] == 'response':
            text = f"[Response: {json.dumps(content.get('result', {}))[:50]}]"
        else:
            text = str(content)[:50]
        
        print(f"{ts} {direction} {text}")
    
    print()
    print(f"Total: {len(messages)} message(s)")


def main():
    if len(sys.argv) < 2:
        print("Usage: oc-tor-net-conversation.py <peer-name>")
        print("Example: oc-tor-net-conversation.py 'Stuart'")
        sys.exit(1)
    
    query = sys.argv[1]
    peers = load_peers()
    
    # Find peer
    matches = find_peer(peers, query)
    
    if not matches:
        print(f"❌ No peer found matching '{query}'")
        return
    
    if len(matches) > 1:
        print(f"⚠️  Multiple matches for '{query}':")
        for addr, info in matches:
            print(f"   - {info.get('display_name', 'Unknown')}")
        return
    
    address, info = matches[0]
    display_name = info.get('display_name', 'Unknown')
    
    # Load and display conversation
    messages = load_conversation(address)
    display_conversation(messages, display_name)
    
    return {
        'peer': display_name,
        'address': address,
        'message_count': len(messages)
    }


if __name__ == "__main__":
    result = main()
    if result:
        print("\n" + json.dumps(result, indent=2))
