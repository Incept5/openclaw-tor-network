#!/usr/bin/env python3
"""
Generate an invite code to share with others
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
    from transport import TransportFactory
except ImportError as e:
    print(f"Error: {e}")
    sys.exit(1)


def main():
    from pathlib import Path

    config_dir = Path.home() / ".openclaw/p2p"
    identity_file = config_dir / "identity.json"
    daemon_json = config_dir / "daemon.json"

    if not identity_file.exists():
        print("Error: No identity found. Run oc-tor-net-start.py first.")
        sys.exit(1)

    # Read transport and network address from daemon.json
    transport = 'tor'
    network_address = None
    if daemon_json.exists():
        try:
            with open(daemon_json) as f:
                daemon_config = json.load(f)
            transport = daemon_config.get('transport', 'tor')
            network_address = daemon_config.get('address', daemon_config.get('onion_address'))
        except (json.JSONDecodeError, OSError):
            pass

    # Fallback for Tor: read hostname file
    if not network_address and transport == 'tor':
        tor_hostname = config_dir / "tor" / "hidden_service" / "hostname"
        if tor_hostname.exists():
            with open(tor_hostname) as f:
                network_address = f.read().strip()

    if not network_address:
        print("Error: Transport not running. Run oc-tor-net-start.py first.")
        sys.exit(1)

    # Load identity
    identity = Identity(str(config_dir))
    
    # Get or set display name
    current_name = identity.get_display_name()
    
    print("=" * 60)
    print("P2P INVITE SETUP")
    print("=" * 60)
    print()
    print("This name will be shown to people you invite:")
    print()
    
    if current_name != "Anonymous Agent":
        print(f"Current name: {current_name}")
        response = input("Keep this name? [Y/n] or enter new name: ").strip()
        if response and response.lower() != 'y':
            display_name = response
            identity.set_display_name(display_name)
        else:
            display_name = current_name
    else:
        print("You haven't set a display name yet.")
        print()
        print("When someone receives your invite, they will see this name")
        print("in their peer list and in messages from you.")
        print()
        print("Examples:")
        print("  - 'Stuart's Agent'")
        print("  - 'Missy (Stuart's OpenClaw)'")
        print("  - 'Stuart - Work Agent'")
        print()
        display_name = input("Enter your display name: ").strip()
        if not display_name:
            display_name = "Anonymous Agent"
        identity.set_display_name(display_name)
    
    print()
    print(f"Your display name: {display_name}")
    print()
    print("When someone accepts your invite, they will see:")
    print(f"  '{display_name} (@evNG3V...ed25519)' in their peer list")
    print(f"  'Message from {display_name}' when you send messages")
    print()
    
    # Generate invite with display name
    invite = identity.generate_invite(network_address, port=80, display_name=display_name,
                                      transport=transport)
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
    print(f"  python3 oc-tor-net-connect.py '{invite_code}'")
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
        print(f"QR code saved to: {qr_path}")
        
    except ImportError:
        print("(Install 'qrcode' package to see QR code)")
    
    # Output JSON for programmatic use
    output = {
        "invite_code": invite_code,
        "display_name": display_name,
        "address": identity.get_address(),
        "network_address": network_address,
        "transport": transport
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
