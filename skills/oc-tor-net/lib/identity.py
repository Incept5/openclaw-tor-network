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
            # Load encryption key, or derive deterministically from Ed25519 seed
            if 'encryption_seed' in data:
                from nacl.public import PrivateKey
                enc_seed = base64.b64decode(data['encryption_seed'])
                self.encryption_key = PrivateKey(enc_seed)
            else:
                # Derive Curve25519 key from Ed25519 signing key (deterministic).
                # This ensures legacy identities always get the same encryption key
                # rather than generating a random one that breaks existing peers.
                from nacl.public import PrivateKey
                from nacl.bindings import crypto_sign_ed25519_sk_to_curve25519
                # Ed25519 "sk" in libsodium is the 64-byte seed+pubkey concatenation
                ed25519_sk = bytes(self.signing_key) + bytes(self.verify_key)
                curve25519_sk = crypto_sign_ed25519_sk_to_curve25519(ed25519_sk)
                self.encryption_key = PrivateKey(curve25519_sk)
                self._save()
                print("[IDENTITY] Derived encryption key from signing key (legacy identity migrated)")
        else:
            self.signing_key = SigningKey.generate()
            self.verify_key = self.signing_key.verify_key
            from nacl.public import PrivateKey
            self.encryption_key = PrivateKey.generate()
            self._save()
    
    def _save(self):
        """Save identity to disk"""
        data = {
            'seed': base64.b64encode(bytes(self.signing_key)).decode(),
            'public_key': self.get_public_key_b64(),
            'encryption_seed': base64.b64encode(bytes(self.encryption_key)).decode(),
            'encryption_public_key': base64.b64encode(bytes(self.encryption_key.public_key)).decode(),
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

    def get_encryption_pubkey_b64(self) -> str:
        """Get base64-encoded Curve25519 encryption public key"""
        return base64.b64encode(bytes(self.encryption_key.public_key)).decode()

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
    
    def generate_invite(self, network_address: str, port: int = 80,
                        display_name: str = None, encryption_pubkey: str = None,
                        transport: str = 'tor', full_destination: str = None) -> dict:
        """Generate an invite structure.
        For I2P, full_destination should be the base64 public destination
        (needed for SAM STREAM CONNECT which can't resolve .b32.i2p)."""
        if display_name is None:
            display_name = self.get_display_name()

        if encryption_pubkey is None:
            encryption_pubkey = self.get_encryption_pubkey_b64()

        timestamp = datetime.utcnow().isoformat()
        # Sanitise display name — semicolons break the semicolon-delimited invite format
        safe_name = display_name.replace(';', ',')
        # Use version 3 for non-tor transports, version 1 for tor (backwards compat)
        version = 3 if transport != 'tor' else 1
        payload = {
            'v': version,
            'pubkey': self.get_public_key_b64(),
            'encryption_pubkey': encryption_pubkey,
            'onion': network_address,
            'port': port,
            'name': safe_name,
            'transport': transport,
            'ts': timestamp
        }
        # Include full I2P destination for SAM routing
        if full_destination:
            payload['dest'] = full_destination
        # Sign the canonical JSON (sort_keys ensures deterministic ordering)
        message = json.dumps(payload, sort_keys=True).encode()
        payload['sig'] = self.sign_b64(message)
        return payload
    
    def encode_invite(self, invite: dict) -> str:
        """Encode invite to compact string format.
        Semicolons in display names are replaced with commas to avoid
        breaking the semicolon-delimited format.
        """
        transport = invite.get('transport', 'tor')
        network_addr = invite.get('onion', '')
        # Name is already sanitised in generate_invite(), but belt-and-braces
        safe_name = invite.get('name', 'Anonymous Agent').replace(';', ',')

        if transport == 'tor':
            # oc:v1;pubkey;encryption_pubkey;onion:port;name;timestamp;sig
            # (unchanged format for backwards compat with tor-only peers)
            parts = [
                f"oc:v{invite['v']}",
                invite['pubkey'],
                invite.get('encryption_pubkey', invite['pubkey']),
                f"{network_addr}:{invite['port']}",
                safe_name,
                invite['ts'],
                invite['sig']
            ]
        else:
            # oc:v3;transport;pubkey;encryption_pubkey;address:port;name;timestamp;sig[;dest]
            parts = [
                'oc:v3',
                transport,
                invite['pubkey'],
                invite.get('encryption_pubkey', invite['pubkey']),
                f"{network_addr}:{invite['port']}",
                safe_name,
                invite['ts'],
                invite['sig']
            ]
            # Append full destination for I2P SAM routing (optional 9th field)
            if invite.get('dest'):
                parts.append(invite['dest'])
        return ';'.join(parts)
    
    @staticmethod
    def decode_invite(invite_str: str) -> dict:
        """Decode compact invite string.
        
        IMPORTANT: The returned dict (minus 'sig') must exactly match the payload
        that was signed during generate_invite(), since verify_invite() re-serialises
        with sort_keys=True. Extra keys like 'address' are added AFTER the core
        payload to avoid breaking signature verification.
        """
        parts = invite_str.split(';')

        # Handle both "oc:v1" and "oc:1" formats
        version_part = parts[0].split(':')[1]
        version = int(version_part.replace('v', ''))

        if version == 3 and len(parts) in (8, 9):
            # v3 format: oc:v3;transport;pubkey;encryption_pubkey;address:port;name;ts;sig[;dest]
            transport = parts[1]
            network_addr = parts[4].rsplit(':', 1)[0]
            # Core payload matches what was signed (same keys as generate_invite)
            result = {
                'v': version,
                'pubkey': parts[2],
                'encryption_pubkey': parts[3],
                'onion': network_addr,
                'port': int(parts[4].rsplit(':', 1)[1]),
                'name': parts[5],
                'transport': transport,
                'ts': parts[6],
                'sig': parts[7]
            }
            # Optional full destination (for I2P SAM routing)
            if len(parts) == 9 and parts[8]:
                result['dest'] = parts[8]
            return result
        elif len(parts) == 7:
            # v2 format (tor with encryption key): oc:v1;pubkey;encryption_pubkey;onion:port;name;ts;sig
            network_addr = parts[3].rsplit(':', 1)[0]
            transport = 'tor'
            # Core payload matches what was signed
            result = {
                'v': version,
                'pubkey': parts[1],
                'encryption_pubkey': parts[2],
                'onion': network_addr,
                'port': int(parts[3].rsplit(':', 1)[1]),
                'name': parts[4],
                'transport': transport,
                'ts': parts[5],
                'sig': parts[6]
            }
            return result
        elif len(parts) == 6:
            # v1 format (legacy, no encryption key): oc:v1;pubkey;onion:port;name;ts;sig
            network_addr = parts[2].rsplit(':', 1)[0]
            return {
                'v': version,
                'pubkey': parts[1],
                'onion': network_addr,
                'port': int(parts[2].rsplit(':', 1)[1]),
                'name': parts[3],
                'ts': parts[4],
                'sig': parts[5]
            }
        else:
            raise ValueError(f"Invalid invite format: expected 6, 7, or 8 parts, got {len(parts)}")
    
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
