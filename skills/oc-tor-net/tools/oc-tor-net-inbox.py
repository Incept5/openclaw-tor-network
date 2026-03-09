#!/usr/bin/env python3
"""
Check inbox for received messages
"""
import sys
import json
from pathlib import Path

sys.path.insert(0, '../lib')
sys.path.insert(0, './lib')


def main():
    config_dir = Path.home() / ".openclaw/p2p"
    inbox_dir = config_dir / "inbox"
    
    if not inbox_dir.exists():
        print("No inbox found. Start p2p_start.py to begin receiving messages.")
        return []
    
    messages = sorted(inbox_dir.glob("*.json"))
    
    if not messages:
        print("Inbox is empty.")
        return []
    
    print(f"Inbox ({len(messages)} message(s)):")
    print("=" * 60)
    
    for msg_file in messages:
        with open(msg_file) as f:
            msg = json.load(f)
        
        # Try to extract useful info
        sender = msg.get('sender_pubkey', 'unknown')[:20] + "..."
        msg_type = 'encrypted'
        
        print(f"File: {msg_file.name}")
        print(f"Sender: {sender}")
        print(f"Type: {msg_type}")
        print(f"Raw: {json.dumps(msg, indent=2)[:200]}...")
        print("-" * 60)
    
    return [str(m) for m in messages]


if __name__ == "__main__":
    messages = main()
    print("\n" + json.dumps({"messages": messages}))
