"""
Webhook client for notifying OpenClaw gateway of new messages
"""
import json
import requests
from typing import Optional


class OpenClawWebhook:
    """Sends notifications to OpenClaw gateway when P2P messages arrive"""
    
    def __init__(self, gateway_url: str = None, session_key: str = None):
        """
        Initialize webhook client.
        
        Args:
            gateway_url: OpenClaw gateway WebSocket/HTTP endpoint
                         Default: ws://127.0.0.1:18789 (local gateway)
            session_key: Optional session key for routing to specific agent
        """
        if gateway_url is None:
            # Default to local OpenClaw gateway
            gateway_url = "http://127.0.0.1:18789"
        
        self.gateway_url = gateway_url.rstrip('/')
        self.session_key = session_key
    
    def notify_new_message(self, message: dict, sender_address: str = None) -> bool:
        """
        Notify OpenClaw that a new P2P message has arrived.
        
        Args:
            message: The decrypted message content
            sender_address: The sender's P2P address (@pubkey.ed25519)
        
        Returns:
            True if notification sent successfully
        """
        payload = {
            'type': 'p2p_message',
            'sender': sender_address,
            'content': message,
            'channel': 'p2p'
        }
        
        # Try multiple notification methods
        
        # Method 1: Direct HTTP POST to gateway API (if available)
        if self._post_to_gateway(payload):
            return True
        
        # Method 2: Write to notification file that OpenClaw polls
        if self._write_notification_file(payload):
            return True
        
        # Method 3: Store in special inbox that OpenClaw monitors
        if self._write_to_priority_inbox(payload):
            return True
        
        return False
    
    def _post_to_gateway(self, payload: dict) -> bool:
        """Try to POST directly to OpenClaw gateway"""
        try:
            # OpenClaw gateway may have an HTTP endpoint for external events
            url = f"{self.gateway_url}/event"
            response = requests.post(
                url,
                json=payload,
                timeout=5,
                headers={'Content-Type': 'application/json'}
            )
            return response.status_code == 200
        except Exception:
            # Gateway may not have this endpoint
            return False
    
    def _write_notification_file(self, payload: dict) -> bool:
        """Write notification to a file that OpenClaw polls"""
        import os
        from pathlib import Path
        from datetime import datetime
        
        try:
            notify_dir = Path.home() / ".openclaw" / "p2p" / "notifications"
            notify_dir.mkdir(parents=True, exist_ok=True)
            
            timestamp = datetime.utcnow().isoformat()
            filename = f"{timestamp}_p2p.json"
            filepath = notify_dir / filename
            
            with open(filepath, 'w') as f:
                json.dump(payload, f, indent=2)
            
            return True
        except Exception as e:
            print(f"Failed to write notification: {e}")
            return False
    
    def _write_to_priority_inbox(self, payload: dict) -> bool:
        """Write to a priority inbox that OpenClaw monitors closely"""
        import os
        from pathlib import Path
        from datetime import datetime
        
        try:
            # Use a special 'urgent' subdirectory
            inbox_dir = Path.home() / ".openclaw" / "p2p" / "inbox" / "urgent"
            inbox_dir.mkdir(parents=True, exist_ok=True)
            
            timestamp = datetime.utcnow().isoformat()
            filename = f"URGENT_{timestamp}_p2p.json"
            filepath = inbox_dir / filename
            
            with open(filepath, 'w') as f:
                json.dump(payload, f, indent=2)
            
            return True
        except Exception as e:
            print(f"Failed to write to priority inbox: {e}")
            return False
    
    def notify_agent_via_telegram(self, bot_token: str, chat_id: str, message: dict, sender: str) -> bool:
        """
        Fallback: Send notification via Telegram if gateway is unavailable.
        This requires the agent to have Telegram channel configured.
        """
        try:
            url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
            text = f"📨 New P2P message from {sender}\n\n{json.dumps(message.get('content', {}), indent=2)}"
            
            response = requests.post(
                url,
                json={'chat_id': chat_id, 'text': text},
                timeout=10
            )
            return response.status_code == 200
        except Exception:
            return False
