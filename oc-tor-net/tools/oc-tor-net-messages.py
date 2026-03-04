#!/usr/bin/env python3
"""
Query and manage P2P messages

Usage:
  oc-tor-net-messages.py                    # Check for new messages
  oc-tor-net-messages.py --from "Stuart"    # Show messages from specific peer
  oc-tor-net-messages.py --latest           # Show only latest message
  oc-tor-net-messages.py --mark-read        # Mark all as read (move to processed)
"""
import sys
import json
from pathlib import Path
from datetime import datetime


def load_messages(inbox_dir, processed=False):
    """Load messages from inbox or processed folder"""
    messages = []
    
    if not inbox_dir.exists():
        return messages
    
    # Get all JSON files
    pattern = "*.json"
    if processed:
        inbox_dir = inbox_dir / "processed"
        if not inbox_dir.exists():
            return messages
    
    for filepath in sorted(inbox_dir.glob(pattern)):
        try:
            with open(filepath) as f:
                data = json.load(f)
            
            # Extract timestamp from filename if possible
            ts = filepath.stem.split('_')[0] if '_' in filepath.stem else None
            
            messages.append({
                'file': str(filepath),
                'timestamp': ts or data.get('ts', 'unknown'),
                'data': data
            })
        except Exception as e:
            print(f"Error reading {filepath}: {e}", file=sys.stderr)
    
    return messages


def get_peer_name(peers, address):
    """Get display name for a peer address"""
    if address in peers:
        return peers[address].get('display_name', 'Unknown')
    return address[:20] + "..."


def display_messages(messages, peers, show_latest=False):
    """Display messages in a formatted way"""
    if not messages:
        print("No messages.")
        return {'has_messages': False, 'count': 0}
    
    if show_latest:
        messages = messages[-1:]
        print("=" * 70)
        print("LATEST MESSAGE")
        print("=" * 70)
    else:
        print("=" * 70)
        print(f"MESSAGES ({len(messages)} total)")
        print("=" * 70)
    
    print()
    
    for i, msg in enumerate(messages, 1):
        data = msg['data']
        sender = data.get('sender', 'Unknown')
        sender_name = get_peer_name(peers, sender)
        msg_type = data.get('type', 'unknown')
        content = data.get('content', {})
        
        # Format timestamp
        ts = msg.get('timestamp', 'unknown')
        if ts != 'unknown' and 'T' in ts:
            try:
                dt = datetime.fromisoformat(ts.replace('Z', '+00:00'))
                ts = dt.strftime('%Y-%m-%d %H:%M')
            except:
                pass
        
        print(f"{i}. From: {sender_name}")
        print(f"   Time: {ts}")
        print(f"   Type: {msg_type}")
        
        # Format content based on type
        if msg_type == 'text':
            text = content.get('text', '')
            print(f"   Text: {text[:100]}{'...' if len(text) > 100 else ''}")
        elif msg_type == 'query':
            query_type = content.get('query_type', 'unknown')
            print(f"   Query: {query_type}")
            params = content.get('params', {})
            if params:
                print(f"   Params: {json.dumps(params, indent=2)}")
        elif msg_type == 'response':
            result = content.get('result', {})
            print(f"   Response: {json.dumps(result, indent=2)[:200]}")
        elif msg_type == 'handshake':
            print(f"   Handshake from {content.get('display_name', 'Unknown')}")
        else:
            print(f"   Content: {json.dumps(content, indent=2)[:200]}")
        
        print()
    
    return {
        'has_messages': True,
        'count': len(messages),
        'messages': messages
    }


def filter_by_peer(messages, peer_query, peers):
    """Filter messages by peer name or address"""
    query_lower = peer_query.lower()
    filtered = []
    
    for msg in messages:
        sender = msg['data'].get('sender', '')
        sender_name = get_peer_name(peers, sender).lower()
        
        if query_lower in sender.lower() or query_lower in sender_name:
            filtered.append(msg)
    
    return filtered


def mark_all_read(inbox_dir):
    """Move all messages to processed folder"""
    processed_dir = inbox_dir / "processed"
    processed_dir.mkdir(exist_ok=True)
    
    count = 0
    for filepath in inbox_dir.glob("*.json"):
        try:
            dest = processed_dir / filepath.name
            filepath.rename(dest)
            count += 1
        except Exception as e:
            print(f"Error moving {filepath}: {e}", file=sys.stderr)
    
    return count


def main():
    config_dir = Path.home() / ".openclaw" / "p2p"
    inbox_dir = config_dir / "inbox"
    peers_file = config_dir / "peers.json"
    
    # Load peers for name resolution
    peers = {}
    if peers_file.exists():
        with open(peers_file) as f:
            peers = json.load(f)
    
    # Parse arguments
    if '--mark-read' in sys.argv:
        count = mark_all_read(inbox_dir)
        print(f"Marked {count} message(s) as read.")
        return {'marked_read': count}
    
    # Load messages
    messages = load_messages(inbox_dir)
    
    # Filter by peer if specified
    if '--from' in sys.argv:
        idx = sys.argv.index('--from')
        if idx + 1 < len(sys.argv):
            peer_query = sys.argv[idx + 1]
            messages = filter_by_peer(messages, peer_query, peers)
            if not messages:
                print(f"No messages from '{peer_query}'.")
                return {'has_messages': False, 'filtered_by': peer_query}
    
    # Show latest only
    show_latest = '--latest' in sys.argv
    
    # Display
    result = display_messages(messages, peers, show_latest)
    
    # Output JSON
    print("\n" + json.dumps(result, indent=2, default=str))
    return result


if __name__ == "__main__":
    main()
