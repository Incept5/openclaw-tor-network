#!/usr/bin/env python3
"""
Generate an invite code to share with others
"""
import sys
import json

sys.path.insert(0, '../lib')
sys.path.insert(0, './lib')

try:
    from agent import P2PAgent
    from identity import Identity
except ImportError as e:
    print(f"Error: {e}")
    sys.exit(1)


def main():
    # Check if agent is running by looking for identity
    import os
    from pathlib import Path
    
    config_dir = Path.home() / ".openclaw/p2p"
    identity_file = config_dir / "identity.json"
    tor_hostname = config_dir / "tor" / "hidden_service" / "hostname"
    
    if not identity_file.exists():
        print("Error: No identity found. Run p2p_start.py first.")
        sys.exit(1)
    
    if not tor_hostname.exists():
        print("Error: Tor not running. Run p2p_start.py first.")
        sys.exit(1)
    
    # Load identity
    identity = Identity(str(config_dir))
    
    # Read onion address
    with open(tor_hostname) as f:
        onion = f.read().strip()
    
    # Generate invite
    invite = identity.generate_invite(onion, port=80)
    invite_code = identity.encode_invite(invite)
    
    print("=" * 60)
    print("YOUR P2P INVITE CODE")
    print("=" * 60)
    print()
    print(invite_code)
    print()
    print("=" * 60)
    print()
    print("Share this code with friends to let them connect to your agent.")
    print()
    print("They can accept it with:")
    print(f"  python3 p2p_accept_invite.py '{invite_code}'")
    print()
    
    # Generate QR code if possible
    try:
        import qrcode
        qr = qrcode.QRCode(version=1, box_size=2, border=1)
        qr.add_data(invite_code)
        qr.make(fit=True)
        
        print("QR Code:")
        qr.print_ascii(invert=True)
        print()
        
        # Also save to file
        qr_img = qr.make_image(fill_color="black", back_color="white")
        qr_path = "/tmp/p2p-invite.png"
        qr_img.save(qr_path)
        print(f"QR code also saved to: {qr_path}")
        
    except ImportError:
        print("(Install 'qrcode' package to see QR code)")
    
    # Output JSON for programmatic use
    output = {
        "invite_code": invite_code,
        "address": identity.get_address(),
        "onion": onion
    }
    
    # Save to file
    invite_file = config_dir / "invite.json"
    with open(invite_file, 'w') as f:
        json.dump(output, f, indent=2)
    
    print(f"\nInvite saved to: {invite_file}")
    
    return output


if __name__ == "__main__":
    result = main()
    # Also print JSON for piping
    print("\n" + json.dumps(result))
