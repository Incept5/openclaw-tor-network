#!/usr/bin/env python3
"""
OpenClaw skill tool for checking P2P messages
This tool is called by the OpenClaw agent to poll for new P2P messages
"""
import sys
import json
from pathlib import Path
from datetime import datetime

def check_p2p_messages():
    """Check for new P2P messages and return them"""
    
    # Check urgent inbox first (for real-time notifications)
    urgent_dir = Path.home() / ".openclaw" / "p2p" / "inbox" / "urgent"
    normal_dir = Path.home() / ".openclaw" / "p2p" / "inbox"
    notify_dir = Path.home() / ".openclaw" / "p2p" / "notifications"
    
    messages = []
    
    # Process urgent messages first
    if urgent_dir.exists():
        for filepath in sorted(urgent_dir.glob("*.json")):
            try:
                with open(filepath) as f:
                    data = json.load(f)
                
                # Move to processed
                processed_dir = urgent_dir / "processed"
                processed_dir.mkdir(exist_ok=True)
                filepath.rename(processed_dir / filepath.name)
                
                messages.append({
                    'priority': 'urgent',
                    'data': data
                })
            except Exception as e:
                print(f"Error processing urgent message {filepath}: {e}", file=sys.stderr)
    
    # Check notifications
    if notify_dir.exists():
        for filepath in sorted(notify_dir.glob("*.json")):
            try:
                with open(filepath) as f:
                    data = json.load(f)
                
                # Move to processed
                processed_dir = notify_dir / "processed"
                processed_dir.mkdir(exist_ok=True)
                filepath.rename(processed_dir / filepath.name)
                
                messages.append({
                    'priority': 'normal',
                    'data': data
                })
            except Exception as e:
                print(f"Error processing notification {filepath}: {e}", file=sys.stderr)
    
    # Check regular inbox (for manual polling)
    if normal_dir.exists():
        for filepath in sorted(normal_dir.glob("*.json")):
            try:
                with open(filepath) as f:
                    data = json.load(f)
                
                # Don't move these - let the user clear them manually
                messages.append({
                    'priority': 'low',
                    'data': data,
                    'file': str(filepath)
                })
            except Exception as e:
                print(f"Error reading message {filepath}: {e}", file=sys.stderr)
    
    return messages

def format_for_agent(messages):
    """Format messages for the OpenClaw agent to understand"""
    
    if not messages:
        return {
            'has_messages': False,
            'count': 0,
            'summary': 'No new P2P messages'
        }
    
    # Build summary
    urgent_count = sum(1 for m in messages if m.get('priority') == 'urgent')
    normal_count = sum(1 for m in messages if m.get('priority') == 'normal')
    
    summary_parts = []
    if urgent_count:
        summary_parts.append(f"{urgent_count} urgent")
    if normal_count:
        summary_parts.append(f"{normal_count} new")
    if len(messages) - urgent_count - normal_count:
        summary_parts.append(f"{len(messages) - urgent_count - normal_count} in inbox")
    
    return {
        'has_messages': True,
        'count': len(messages),
        'summary': ', '.join(summary_parts) if summary_parts else f"{len(messages)} messages",
        'messages': messages
    }

if __name__ == "__main__":
    messages = check_p2p_messages()
    result = format_for_agent(messages)
    
    # Output JSON for OpenClaw to parse
    print(json.dumps(result, indent=2))
