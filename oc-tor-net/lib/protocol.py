"""
Encrypted message protocol using NaCl box encryption
"""
import json
import base64
from datetime import datetime
from typing import Dict, Optional
from nacl.public import PrivateKey, PublicKey, Box
from nacl.encoding import Base64Encoder
from nacl.utils import random


class MessageProtocol:
    """Handles encryption/decryption of messages between agents"""
    
    @staticmethod
    def encrypt_message(
        message: dict,
        sender_signing_key,  # For signing
        recipient_public_key: PublicKey
    ) -> dict:
        """
        Encrypt a message for a specific recipient.
        Returns encrypted payload ready for transmission.
        """
        # Generate ephemeral keypair for this message
        ephemeral_private = PrivateKey.generate()
        ephemeral_public = ephemeral_private.public_key
        
        # Create box for encryption
        box = Box(ephemeral_private, recipient_public_key)
        
        # Serialize and encrypt message
        plaintext = json.dumps(message).encode()
        nonce = random(Box.NONCE_SIZE)
        ciphertext = box.encrypt(plaintext, nonce).ciphertext
        
        # Sign the ciphertext + ephemeral pubkey
        sign_data = bytes(ephemeral_public) + ciphertext
        signature = sender_signing_key.sign(sign_data).signature
        
        return {
            'v': 1,
            'ephemeral_pubkey': base64.b64encode(bytes(ephemeral_public)).decode(),
            'ciphertext': base64.b64encode(ciphertext).decode(),
            'nonce': base64.b64encode(nonce).decode(),
            'sender_pubkey': base64.b64encode(bytes(sender_signing_key.verify_key)).decode(),
            'signature': base64.b64encode(signature).decode()
        }
    
    @staticmethod
    def decrypt_message(
        encrypted: dict,
        recipient_private_key: PrivateKey,
        sender_verify_key  # For signature verification
    ) -> Optional[dict]:
        """
        Decrypt a message from a sender.
        Returns decrypted message dict or None if invalid.
        """
        try:
            # Decode components
            ephemeral_public = PublicKey(base64.b64decode(encrypted['ephemeral_pubkey']))
            ciphertext = base64.b64decode(encrypted['ciphertext'])
            nonce = base64.b64decode(encrypted['nonce'])
            signature = base64.b64decode(encrypted['signature'])
            
            # Verify signature
            sign_data = bytes(ephemeral_public) + ciphertext
            try:
                sender_verify_key.verify(sign_data, signature)
            except Exception:
                return None  # Invalid signature
            
            # Decrypt
            box = Box(recipient_private_key, ephemeral_public)
            plaintext = box.decrypt(ciphertext, nonce)
            
            return json.loads(plaintext)
        except Exception as e:
            print(f"[DEBUG] Decryption failed: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    @staticmethod
    def create_message(
        msg_type: str,
        content: dict,
        thread_id: str = None,
        sender_info: dict = None
    ) -> dict:
        """Create a standard message envelope"""
        msg = {
            'type': msg_type,
            'content': content,
            'ts': datetime.utcnow().isoformat(),
            'thread': thread_id or generate_thread_id()
        }
        
        # Include sender info for auto-add capability
        if sender_info:
            msg['sender_info'] = sender_info
        
        return msg
    
    @staticmethod
    def create_handshake(identity, onion_address: str, port: int = 80, encryption_pubkey_b64: str = None) -> dict:
        """Create initial handshake message with full identity info for auto-add"""
        content = {
            'address': identity.get_address(),
            'display_name': identity.get_display_name(),
            'onion': onion_address,
            'port': port,
            'agent': 'openclaw',
            'version': '1.0.0'
        }
        if encryption_pubkey_b64:
            content['encryption_pubkey'] = encryption_pubkey_b64
        return MessageProtocol.create_message('handshake', content)
    
    @staticmethod
    def create_query(query_type: str, params: dict) -> dict:
        """Create a query message"""
        return MessageProtocol.create_message('query', {
            'query_type': query_type,
            'params': params
        })
    
    @staticmethod
    def create_response(query_id: str, result: dict) -> dict:
        """Create a response to a query"""
        return MessageProtocol.create_message('response', {
            'query_id': query_id,
            'result': result
        })


def generate_thread_id() -> str:
    """Generate a unique thread ID"""
    import uuid
    return str(uuid.uuid4())
