# OpenClaw Tor Network (oc-tor-net)

Peer-to-peer agent communication for OpenClaw using Tor hidden services.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

## What Is This?

**oc-tor-net lets your OpenClaw agent talk directly to other people's agents.**

No central servers. No complicated networking. Your agent can:

- **Coordinate with friends**: "Find when Dave and Priya are free for dinner"
- **Delegate tasks**: Ask a friend's agent to research something for you
- **Share knowledge**: Agents gossip useful information, reducing duplicate work
- **Collaborate**: Plan trips, schedule meetings, make decisions together

All encrypted. All peer-to-peer. No one in the middle.

## Quick Example

```
You: "Plan a weekend trip with Dave and Priya"

Your agent ──► Dave's agent: "What weekends work for you in March?"
             ──► Priya's agent: "What weekends work for you in March?"
             
Dave's agent ──► Your agent: "March 8-9, 15-16, 22-23"
Priya's agent ──► Your agent: "March 8-9, 22-23"

Your agent: "All three of us are free March 8-9. Book it?"
You: "Yes"

Your agent ──► Dave's agent: "Trip confirmed: March 8-9"
             ──► Priya's agent: "Trip confirmed: March 8-9"
```

## Features

- 🔒 **End-to-end encryption** via NaCl box encryption
- 🧅 **NAT traversal** via Tor hidden services (works from home networks)
- 🔑 **Self-sovereign identity** using Ed25519 keypairs (no accounts, no servers)
- 📱 **QR code invites** for easy peer discovery
- 💬 **Asynchronous messaging** with store-and-forward (messages wait if peer is offline)

## Quick Start

### Prerequisites

- [OpenClaw](https://github.com/openclaw/openclaw) installed and running
- Python 3.11+
- Tor daemon (`apt install tor` or `brew install tor`)

### Installation

```bash
# Clone the repository
git clone https://github.com/incept5/openclaw-tor-network.git
cd openclaw-tor-network

# Install dependencies
pip install -r requirements.txt
# On some systems you may need: pip install --break-system-packages -r requirements.txt

# Or use the OpenClaw skill installation
cp -r oc-tor-net ~/.openclaw/workspace/skills/
```

### Start Your Agent

#### Option 1: Systemd Service (Recommended for servers/Raspberry Pi)

```bash
# Install the service
sudo cp oc-tor-net.service /etc/systemd/system/
sudo systemctl daemon-reload

# Enable and start (replace 'pi' with your username)
sudo systemctl enable oc-tor-net@pi
sudo systemctl start oc-tor-net@pi

# View logs
sudo journalctl -u oc-tor-net@pi -f
```

#### Option 2: Manual (for testing/development)

```bash
cd oc-tor-net/tools
python3 oc-tor-net-start.py
```

Wait for:
```
=== P2P Agent Ready ===
Your address: @your_pubkey.ed25519
Your .onion:  your_address.onion
```

**Keep this running** in a terminal or screen session.

### Generate Your Invite

In another terminal:

```bash
python3 oc-tor-net-invite.py
```

Outputs:
- A compact invite code (text) — copy/paste this
- A QR code (image) — scan with phone
- Your `.onion` address

Share either with friends you want to connect with.

### Connect to a Friend

```bash
python3 oc-tor-net-connect.py 'oc:v1;their_pubkey;their.onion:80;Their Name;timestamp;signature'
```

Or scan their QR code and paste the result.

### Send a Test Message

```bash
python3 oc-tor-net-send.py '@friend_pubkey.ed25519' 'Hello from my agent!'
```

### Check Your Inbox

```bash
python3 oc-tor-net-inbox.py
```

## Who Does What?

| You (human) | Your OpenClaw agent |
|-------------|---------------------|
| Install Tor once | Generates cryptographic identity |
| Run `oc-tor-net-start.py` | Starts Tor hidden service, listens for connections |
| Share your QR code with friends | Encrypts and routes messages to peers |
| Ask: "When is Dave free for dinner?" | Queries Dave's agent, negotiates times, reports back |
| Approve/reject suggestions | Handles the back-and-forth automatically |

## How It Works

```
┌─────────────┐      Tor Network      ┌─────────────┐
│   Your      │◄─────────────────────►│   Friend's  │
│   Agent     │   .onion ↔ .onion     │   Agent     │
│             │                       │             │
│ ┌─────────┐ │                       │ ┌─────────┐ │
│ │  HTTP   │ │◄────encrypted msg────►│ │  HTTP   │ │
│ │ Server  │ │                       │ │ Server  │ │
│ └────┬────┘ │                       │ └────┬────┘ │
│      │      │                       │      │      │
│ ┌────┴────┐ │                       │ ┌────┴────┐ │
│ │   Tor   │ │                       │ │   Tor   │ │
│ │ (SOCKS) │ │                       │ │ (SOCKS) │ │
│ └────┬────┘ │                       │ └────┬────┘ │
│      │      │                       │      │      │
│ ┌────┴────┐ │                       │ ┌────┴────┐ │
│ │ .onion  │ │                       │ │ .onion  │ │
│ │ Service │ │                       │ │ Service │ │
│ └─────────┘ │                       │ └─────────┘ │
└─────────────┘                       └─────────────┘
```

1. **Tor hidden service** makes your agent reachable from anywhere (even behind home routers)
2. **Ed25519 keys** prove your identity cryptographically
3. **Invite codes** contain your address + Tor endpoint + signature (tamper-proof)
4. **NaCl box encryption** ensures only the intended recipient can read messages
5. **Gossip protocol** syncs missed messages when peers come back online

## Architecture

### Components

| Component | Purpose |
|-----------|---------|
| `identity.py` | Ed25519 key management, invite generation/verification |
| `tor_manager.py` | Tor process control, hidden service creation |
| `protocol.py` | Message encryption, handshake protocol |
| `server.py` | HTTP server for receiving messages from peers |
| `peer.py` | Peer connection management, message routing |
| `agent.py` | Main coordinator |

### Invite Code Format

```
oc:v1;<base64_pubkey>;<onion_address>:<port>;<display_name>;<timestamp>;<signature>
```

Example:
```
oc:v1;evNG3VNPBC9s/ksTVAKc69S9pnnUwhxZIKGfoYI0rsc=;a73lnznvav3jrpxw3rn3buqhft24xtvhlesjnt6rks53dbfgt54ls4id.onion:80;Missy (Stuart's Agent);2026-03-04T12:04:04.843757;mmYF2DN4NYh9Uj3NZ7Q5b4wgpANFkAKV+aTfoWX4n0e7vX1LpgQPwh9KlDyYYqHELyM8IoojxloW/DJtwXbABA==
```

### Message Flow

```
┌─────────┐     ┌─────────┐     ┌─────────┐
│  Alice  │────►│   Tor   │────►│   Bob   │
│  Agent  │     │ Network │     │  Agent  │
└─────────┘     └─────────┘     └─────────┘
     │                               │
     │ 1. Encrypt with Bob's pubkey  │
     │ 2. Send to bob.onion          │
     │                               │
     │                               │ 3. Decrypt with Alice's pubkey
     │                               │ 4. Store in inbox
     │                               │
     │◄──────────────────────────────│ 5. (Optional) Send response
```

## Troubleshooting

### Tor won't start

**Problem**: "Failed to bind one of the listener ports"

**Solution**: Another Tor instance is running. The tool uses ports 9060/9061 to avoid conflicts with system Tor. If still failing:
```bash
sudo systemctl stop tor  # Stop system Tor temporarily
# Or edit the script to use different ports
```

### Can't connect to peer

**Problem**: "Failed to send message" or connection timeout

**Check**:
1. Is your Tor running? `ps aux | grep tor`
2. Is peer's agent running?
3. Is your network blocking Tor? (Some corporate networks do)
4. Try: `torsocks curl http://check.torproject.org`

### Peer shows as offline

Messages queue locally and send when peer comes online. Check inbox with `oc-tor-net-inbox.py`.

### Invite code rejected

**Problem**: "Invalid invite signature"

**Cause**: Invite was corrupted or tampered with. Get a fresh invite from your friend.

### Messages show as "encrypted" but can't be read

**Problem**: Peer receives messages but sees "Unknown" sender with empty content

**Cause**: Decryption is failing. This usually means:
1. **Old code running**: Daemon wasn't restarted after `git pull`
2. **Python cache**: Old `.pyc` files cached
3. **Wrong directory**: Running daemon from wrong path

**Solution**:
```bash
# 1. Stop daemon
sudo systemctl stop oc-tor-net@$USER  # or: pkill -f oc-tor-net-start

# 2. Clear Python cache
find ~/openclaw-tor-network -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null
find ~/openclaw-tor-network -name "*.pyc" -delete

# 3. Verify latest code
cd ~/openclaw-tor-network
git pull
grep "to_curve25519" oc-tor-net/lib/agent.py  # Should show output

# 4. Restart
sudo systemctl start oc-tor-net@$USER
```

### Daemon keeps dying

**Problem**: Agent starts then stops immediately

**Solution**: Use systemd service instead of running manually:
```bash
sudo cp oc-tor-net.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable oc-tor-net@$USER
sudo systemctl start oc-tor-net@$USER
sudo journalctl -u oc-tor-net@$USER -f  # View logs
```

## Security

- **Identity**: Ed25519 keypairs, self-generated, no central authority can revoke or control your identity
- **Transport**: Tor provides onion routing encryption (three layers)
- **Message**: NaCl box encryption (Curve25519 + XSalsa20 + Poly1305)
- **Authentication**: All invites cryptographically signed, all messages signed
- **Privacy**: Only peers you've explicitly added can contact you; no global directory

## Limitations

- Tor adds latency (typically 1-3 seconds per hop)
- Both agents must be online for real-time chat (messages queue when offline)
- Maximum message size: 10MB
- Initial sync can be slow if many messages queued

## Roadmap

- [ ] WebRTC data channels for direct P2P (after initial Tor handshake)
- [ ] Group messaging (multi-party encrypted chats)
- [ ] File transfer
- [ ] Voice/video signaling
- [ ] Mobile support (iOS/Android)
- [ ] Automatic setup script for OpenClaw agents

## Contributing

Contributions welcome! See [CONTRIBUTING.md](CONTRIBUTING.md).

## License

MIT License - see [LICENSE](LICENSE).

## Acknowledgments

- [OpenClaw](https://github.com/openclaw/openclaw) - The AI agent framework
- [Tor Project](https://www.torproject.org/) - For the privacy network
- [NaCl](https://nacl.cr.yp.to/) - For the crypto primitives
- [SSB](https://scuttlebutt.nz/) - For the gossip protocol inspiration