"""
Identity management - Ed25519 keypairs for agent authentication
"""
import os
import json
import base64
from pathlib import Path
from datetime import datetime
from nacl.signing import SigningKey, VerifyKey
from nacl.encoding import Base64Encoder, RawEncoder
from nacl.exceptions import BadSignatureError


class Identity:
    """Manages the agent's cryptographic identity"""
    
    def __init__(self, config_dir: str = None):
        if config_dir is None:
            config_dir = os.path.expanduser("~/.openclaw/p2p")
        self.config_dir = Path(config_dir)
        self.config_dir.mkdir(parents=True, exist_ok=True)
        
        self.keys_file = self.config_dir / "identity.json"
        self.signing_key = None
        self.verify_key = None
        self._load_or_create()
    
    def _load_or_create(self):
        """Load existing identity or generate new one"""
        if self.keys_file.exists():
            with open(self.keys_file, 'r') as f:
                data = json.load(f)
            seed = base64.b64decode(data['seed'])
            self.signing_key = SigningKey(seed)
            self.verify_key = self.signing_key.verify_key
        else:
            self.signing_key = SigningKey.generate()
            self.verify_key = self.signing_key.verify_key
            self._save()
    
    def _save(self):
        """Save identity to disk"""
        data = {
            'seed': base64.b64encode(bytes(self.signing_key)).decode(),
            'public_key': self.get_public_key_b64(),
            'created': datetime.utcnow().isoformat()
        }
        with open(self.keys_file, 'w') as f:
            json.dump(data, f, indent=2)
        # Restrict permissions
        os.chmod(self.keys_file, 0o600)
    
    def get_display_name(self) -> str:
        """Get the display name for this agent"""
        config_file = self.config_dir / "config.json"
        if config_file.exists():
            with open(config_file) as f:
                config = json.load(f)
            return config.get('display_name', 'Anonymous Agent')
        return 'Anonymous Agent'
    
    def set_display_name(self, name: str):
        """Set the display name for this agent"""
        config_file = self.config_dir / "config.json"
        config = {}
        if config_file.exists():
            with open(config_file) as f:
                config = json.load(f)
        config['display_name'] = name
        with open(config_file, 'w') as f:
            json.dump(config, f, indent=2)
    
    def get_public_key(self) -> VerifyKey:
        """Get the verify key object"""
        return self.verify_key
    
    def get_public_key_b64(self) -> str:
        """Get base64-encoded public key"""
        return base64.b64encode(bytes(self.verify_key)).decode()
    
    def get_address(self) -> str:
        """Get SSB-style address: @pubkey.ed25519"""
        return f"@{self.get_public_key_b64()}.ed25519"
    
    def sign(self, message: bytes) -> bytes:
        """Sign a message"""
        return self.signing_key.sign(message).signature
    
    def sign_b64(self, message: bytes) -> str:
        """Sign and return base64 signature"""
        return base64.b64encode(self.sign(message)).decode()
    
    def verify(self, message: bytes, signature: bytes, public_key: VerifyKey) -> bool:
        """Verify a signature"""
        try:
            public_key.verify(message, signature)
            return True
        except BadSignatureError:
            return False
    
    @staticmethod
    def parse_address(address: str) -> VerifyKey:
        """Parse @pubkey.ed25519 into VerifyKey"""
        if not address.startswith('@') or not address.endswith('.ed25519'):
            raise ValueError(f"Invalid address format: {address}")
        key_b64 = address[1:-8]  # Remove @ and .ed25519
        key_bytes = base64.b64decode(key_b64)
        return VerifyKey(key_bytes)
    
    def generate_invite(self, onion_address: str, port: int = 80, display_name: str = None) -> dict:
        """Generate an invite structure"""
        if display_name is None:
            display_name = self.get_display_name()
        
        timestamp = datetime.utcnow().isoformat()
        payload = {
            'v': 1,
            'pubkey': self.get_public_key_b64(),
            'onion': onion_address,
            'port': port,
            'name': display_name,
            'ts': timestamp
        }
        # Sign the canonical JSON
        message = json.dumps(payload, sort_keys=True).encode()
        payload['sig'] = self.sign_b64(message)
        return payload
    
    def encode_invite(self, invite: dict) -> str:
        """Encode invite to compact string format"""
        # oc:v1;pubkey;onion:port;name;timestamp;sig
        parts = [
            f"oc:v{invite['v']}",
            invite['pubkey'],
            f"{invite['onion']}:{invite['port']}",
            invite.get('name', 'Anonymous Agent'),
            invite['ts'],
            invite['sig']
        ]
        return ';'.join(parts)
    
    @staticmethod
    def decode_invite(invite_str: str) -> dict:
        """Decode compact invite string"""
        parts = invite_str.split(';')
        if len(parts) != 6:
            raise ValueError(f"Invalid invite format: expected 6 parts, got {len(parts)}")
        
        # Handle both "oc:v1" and "oc:1" formats
        version_part = parts[0].split(':')[1]
        version = int(version_part.replace('v', ''))
        
        return {
            'v': version,
            'pubkey': parts[1],
            'onion': parts[2].rsplit(':', 1)[0],
            'port': int(parts[2].rsplit(':', 1)[1]),
            'name': parts[3],
            'ts': parts[4],
            'sig': parts[5]
        }
    
    @staticmethod
    def verify_invite(invite: dict) -> bool:
        """Verify an invite's signature"""
        # Reconstruct the signed message
        payload = {k: v for k, v in invite.items() if k != 'sig'}
        message = json.dumps(payload, sort_keys=True).encode()
        signature = base64.b64decode(invite['sig'])
        
        # Get public key from invite
        pubkey_bytes = base64.b64decode(invite['pubkey'])
        verify_key = VerifyKey(pubkey_bytes)
        
        try:
            verify_key.verify(message, signature)
            return True
        except BadSignatureError:
            return False
