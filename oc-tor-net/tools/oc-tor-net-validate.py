#!/usr/bin/env python3
"""
Validate an invite code without accepting it

Usage:
  oc-tor-net-validate.py '<invite-code>'
"""
import sys
import json
import os

# Add lib to path
script_dir = os.path.dirname(os.path.abspath(__file__))
lib_dir = os.path.join(script_dir, '..', 'lib')
sys.path.insert(0, lib_dir)

try:
    from identity import Identity
except ImportError as e:
    print(f"Error: {e}")
    sys.exit(1)


def main():
    if len(sys.argv) < 2:
        print("Usage: oc-tor-net-validate.py '<invite-code>'")
        print()
        print("Validates an invite code without accepting it.")
        print("Use this to preview who you're about to connect with.")
        sys.exit(1)
    
    invite_code = sys.argv[1]
    
    print("=" * 70)
    print("VALIDATE INVITE")
    print("=" * 70)
    print()
    
    try:
        # Decode invite
        invite = Identity.decode_invite(invite_code)
        
        print("Invite format: ✅ Valid")
        print()
        print("Details:")
        print(f"  Display name: {invite.get('name', 'Anonymous Agent')}")
        print(f"  Public key:   {invite['pubkey'][:20]}...")
        print(f"  Onion:        {invite['onion']}")
        print(f"  Port:         {invite['port']}")
        print(f"  Timestamp:    {invite['ts']}")
        print()
        
        # Verify signature
        if Identity.verify_invite(invite):
            print("Signature: ✅ Valid")
            print()
            print("This invite is genuine. You can safely accept it with:")
            print(f"  python3 oc-tor-net-connect.py '{invite_code}'")
            
            return {
                'valid': True,
                'verified': True,
                'display_name': invite.get('name', 'Anonymous Agent'),
                'onion': invite['onion']
            }
        else:
            print("Signature: ❌ INVALID")
            print()
            print("⚠️  WARNING: This invite may be tampered with or forged.")
            print("Do not accept it unless you trust the source.")
            
            return {
                'valid': True,
                'verified': False,
                'warning': 'Invalid signature'
            }
            
    except Exception as e:
        print(f"Invite format: ❌ Invalid")
        print(f"Error: {e}")
        
        return {
            'valid': False,
            'error': str(e)
        }


if __name__ == "__main__":
    result = main()
    print("\n" + json.dumps(result, indent=2))
