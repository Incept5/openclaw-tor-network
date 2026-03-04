"""
HTTP server for receiving messages from peers
"""
import json
import os
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from typing import Callable, Dict
from datetime import datetime


def debug_log(msg):
    """Write debug message to log file directly"""
    try:
        log_file = Path.home() / ".openclaw" / "p2p" / "daemon.log"
        with open(log_file, 'a') as f:
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            f.write(f"[{timestamp}] [SERVER] {msg}\n")
    except:
        pass


class MessageHandler(BaseHTTPRequestHandler):
    """HTTP request handler for incoming P2P messages"""
    
    # Class-level storage for callbacks
    message_callback: Callable = None
    inbox_dir: Path = None
    
    def log_message(self, format, *args):
        """Suppress default logging"""
        pass
    
    def do_GET(self):
        """Handle GET requests (health check)"""
        if self.path == '/health':
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({'status': 'ok'}).encode())
        else:
            self.send_response(404)
            self.end_headers()
    
    def do_POST(self):
        """Handle incoming messages"""
        if self.path == '/message':
            content_length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(content_length)
            
            try:
                message = json.loads(body)
                debug_log(f"Received message: {list(message.keys())}")
                
                # Store in inbox
                if MessageHandler.inbox_dir:
                    self._store_message(message)
                    debug_log("Message stored to inbox")
                
                # Notify callback
                debug_log(f"Checking callback: {MessageHandler.message_callback is not None}")
                if MessageHandler.message_callback:
                    debug_log("Calling message callback...")
                    try:
                        MessageHandler.message_callback(message)
                        debug_log("Callback completed successfully")
                    except Exception as e:
                        debug_log(f"Callback FAILED: {e}")
                else:
                    debug_log("No callback registered!")
                
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'status': 'received'}).encode())
                
            except json.JSONDecodeError:
                self.send_response(400)
                self.end_headers()
        else:
            self.send_response(404)
            self.end_headers()
    
    def _store_message(self, message: dict):
        """Store message to inbox"""
        import uuid
        from datetime import datetime
        
        msg_id = str(uuid.uuid4())
        timestamp = datetime.utcnow().isoformat()
        
        filename = f"{timestamp}_{msg_id}.json"
        filepath = MessageHandler.inbox_dir / filename
        
        with open(filepath, 'w') as f:
            json.dump(message, f, indent=2)


class MessageServer:
    """HTTP server for receiving P2P messages"""
    
    def __init__(self, port: int = 8765, inbox_dir: str = None):
        self.port = port
        self.server = None
        self.thread = None
        
        if inbox_dir is None:
            inbox_dir = os.path.expanduser("~/.openclaw/p2p/inbox")
        self.inbox_dir = Path(inbox_dir)
        self.inbox_dir.mkdir(parents=True, exist_ok=True)
        
        MessageHandler.inbox_dir = self.inbox_dir
    
    def start(self, message_callback: Callable = None):
        """Start the message server in a background thread"""
        MessageHandler.message_callback = message_callback
        
        self.server = HTTPServer(('127.0.0.1', self.port), MessageHandler)
        
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        
        print(f"Message server listening on 127.0.0.1:{self.port}")
    
    def stop(self):
        """Stop the message server"""
        if self.server:
            self.server.shutdown()
            self.server.server_close()
        if self.thread:
            self.thread.join(timeout=5)
    
    def get_inbox_messages(self) -> list:
        """Get all messages from inbox"""
        messages = []
        for filepath in sorted(self.inbox_dir.glob("*.json")):
            with open(filepath) as f:
                messages.append(json.load(f))
        return messages
    
    def clear_inbox(self):
        """Clear all messages from inbox"""
        for filepath in self.inbox_dir.glob("*.json"):
            filepath.unlink()
