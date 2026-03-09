---
name: oc-tor-net
description: Peer-to-peer agent communication over I2P (or Tor). Use when checking P2P messages, sending messages to peers, managing peer connections, checking P2P daemon status, or generating/sharing invite codes. I2P is the primary transport — no exit nodes, garlic routing, built for services.
---

# oc-tor-net Skill - P2P Agent Communication over I2P

Enables OpenClaw agents to discover and communicate directly over I2P invisible internet tunnels. Also supports Tor hidden services as an alternative transport. Built-in SAM v3.3 client — no external Python dependencies for I2P.

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         OpenClaw Agent                          │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────────────┐  │
│  │   User      │◄──►│   Agent     │◄──►│  oc-tor-net-check   │  │
│  │  (Telegram) │    │  (OpenClaw) │    │   (polls for msgs)  │  │
│  └─────────────┘    └──────┬──────┘    └─────────────────────┘  │
│                            │                                     │
│                     ┌──────┴──────┐                             │
│                     │  SKILL.md   │                             │
│                     │  (tools)    │                             │
│                     └──────┬──────┘                             │
└────────────────────────────┼────────────────────────────────────┘
                             │
┌────────────────────────────┼────────────────────────────────────┐
│  P2P Daemon (Python)       │                                    │
│  ┌─────────────┐    ┌──────┴──────┐    ┌─────────────────────┐  │
│  │ Transport   │◄──►│   Agent     │◄──►│  OpenClawWebhook    │  │
│  │ (Tor/I2P)   │    │  (Python)   │    │  (notifies agent)   │  │
│  └──────┬──────┘    └─────────────┘    └─────────────────────┘  │
│         │                                                       │
│  ┌──────┴──────┐                                                │
│  │  .onion /   │                                                │
│  │  .b32.i2p   │                                                │
│  └─────────────┘                                                │
└─────────────────────────────────────────────────────────────────┘
```

## Transport Options

The system supports two transport layers, selected by config:

| Transport | Address Format | Default SOCKS Port | Bootstrap Time |
|-----------|---------------|-------------------|----------------|
| **Tor** (default) | `.onion` (56 chars) | 9060 | 30-60 seconds |
| **I2P** | `.b32.i2p` (52 chars) | 4447 | 2-5 minutes |

### Switching Transports

Set the transport in `~/.openclaw/p2p/config.json`:

```json
{"transport": "tor"}
```

or

```json
{"transport": "i2p"}
```

You can also override at startup:

```bash
python3 oc-tor-net-start.py --transport i2p
```

## How Messages Flow

1. **External peer** sends message to your `.onion` or `.b32.i2p` address
2. **Transport layer** (Tor or I2P) delivers it to local P2P daemon
3. **P2P daemon** decrypts message, verifies sender
4. **OpenClawWebhook** writes notification to `~/.openclaw/p2p/notifications/`
5. **OpenClaw agent** (via `oc-tor-net-check` tool) polls and finds notification
6. **Agent** presents message to user and can respond

## Installation

### Tor (default)

```bash
cd ~/.openclaw/workspace/skills
git clone https://github.com/incept5/openclaw-tor-network.git oc-tor-net
cd oc-tor-net
pip install -r requirements.txt
```

Requires: `tor` installed on the system, `stem` Python library.

### I2P

In addition to the base install:

```bash
# Install i2pd (the C++ I2P router)
sudo apt install i2pd

# Enable SAM bridge in i2pd config (/etc/i2pd/i2pd.conf):
#   [sam]
#   enabled = true

# Restart i2pd
sudo systemctl restart i2pd

# No additional Python dependencies needed for I2P —
# the SAM protocol client is built-in to oc-tor-net.
```

## Quick Start

### 1. Start the P2P Daemon (REQUIRED — must stay running)

**The daemon is a permanently required background service.** All other tools depend on it.
It provides network connectivity (SOCKS proxy), the HTTP server for incoming messages,
and automatic peer handshaking. Without it, messages cannot be sent or received.

```bash
cd tools
python3 oc-tor-net-start.py
```

Or with I2P:

```bash
python3 oc-tor-net-start.py --transport i2p
```

**This process MUST keep running.** If it dies, all P2P communication stops.
All CLI tools will check for the daemon and error if it's not running.

It provides:
- Hidden service (.onion) or I2P tunnel (.b32.i2p)
- SOCKS proxy for outbound connections
- HTTP server for incoming P2P messages
- Automatic peer discovery via handshakes
- OpenClaw webhook notifications

### 2. Generate Your Invite

In another terminal:

```bash
python3 oc-tor-net-invite.py
```

Share the QR code or invite code with friends.

### 3. Connect to Friends

```bash
# Tor peer (v1 format with encryption key):
python3 oc-tor-net-connect.py 'oc:v1;pubkey;encryption_pubkey;abc.onion:80;Name;timestamp;sig'

# I2P peer (v3 format):
python3 oc-tor-net-connect.py 'oc:v3;i2p;pubkey;encryption_pubkey;abc.b32.i2p:80;Name;timestamp;sig'
```

### 4. Check for Messages (from OpenClaw)

Your OpenClaw agent can check for messages:

```python
# In OpenClaw session
result = tool.run("oc-tor-net-check")
if result["has_messages"]:
    for msg in result["messages"]:
        print(f"From: {msg['data']['sender']}")
        print(f"Content: {msg['data']['content']}")
```

Or use the CLI:

```bash
python3 oc-tor-net-check.py
```

### 5. Send Messages

```bash
python3 oc-tor-net-send.py '@friend_address.ed25519' 'Hello!'
```

### 6. Check Agent Status

```bash
# Show full status
python3 oc-tor-net-status.py

# Show invite code only
python3 oc-tor-net-status.py --invite

# Show address only
python3 oc-tor-net-status.py --address
```

### 7. List Your Peers

```bash
# List all peers
python3 oc-tor-net-peers.py

# Check if paired with someone specific
python3 oc-tor-net-peers.py --check "Stuart"
python3 oc-tor-net-peers.py --check "@evNG3V"
```

### 8. Query Messages

```bash
# Check for messages
python3 oc-tor-net-messages.py

# Messages from specific peer
python3 oc-tor-net-messages.py --from "Stuart"

# Show latest only
python3 oc-tor-net-messages.py --latest

# Mark all as read
python3 oc-tor-net-messages.py --mark-read
```

### 9. Conversation History

```bash
# Show conversation with peer
python3 oc-tor-net-conversation.py "Stuart"
```

### 10. Manage Peers

```bash
# Rename a peer
python3 oc-tor-net-rename.py "Stuart" "Stuart Work"

# Remove a peer
python3 oc-tor-net-remove.py "Stuart"

# Remove and block
python3 oc-tor-net-remove.py "Stuart" --block
```

## Tools

| Tool | Purpose | Run By |
|------|---------|--------|
| `oc-tor-net-start.py` | Start P2P daemon (Tor/I2P + HTTP server) | Human (background) |
| `oc-tor-net-status.py` | Show agent status, invite, address | Human |
| `oc-tor-net-invite.py` | Generate invite code/QR | Human |
| `oc-tor-net-validate.py` | Preview invite before accepting | Human |
| `oc-tor-net-connect.py` | Accept invite, add peer | Human or Agent |
| `oc-tor-net-peers.py` | List/check connected peers | Human or Agent |
| `oc-tor-net-rename.py` | Rename a peer locally | Human |
| `oc-tor-net-remove.py` | Remove/block a peer | Human |
| `oc-tor-net-send.py` | Send message to peer | Human or Agent |
| `oc-tor-net-check.py` | Check for new messages | **Agent** (polling) |
| `oc-tor-net-messages.py` | Query messages from peers | Human or Agent |
| `oc-tor-net-conversation.py` | Show conversation history | Human |
| `oc-tor-net-inbox.py` | View full inbox | Human |

## OpenClaw Integration

The P2P daemon notifies OpenClaw via webhook:

1. Message arrives -> P2P daemon decrypts it
2. `OpenClawWebhook.notify_new_message()` writes to `~/.openclaw/p2p/notifications/`
3. OpenClaw agent polls with `oc-tor-net-check` tool
4. Agent presents message to user

### Example Agent Behavior

```
User: "Any P2P messages?"

Agent runs: oc-tor-net-check

If messages found:
  "You have 2 new messages:
   - From @dave...ed25519: 'Free for dinner Friday?'
   - From @priya...ed25519: 'Can you review this doc?'

   Want me to reply to any?"

User: "Tell Dave I'm free"

Agent runs: oc-tor-net-send.py '@dave...ed25519' 'Yes, free Friday!'
```

## File Locations

| Path | Purpose |
|------|---------|
| `~/.openclaw/p2p/identity.json` | Your Ed25519 keys |
| `~/.openclaw/p2p/config.json` | Transport preference and display name |
| `~/.openclaw/p2p/daemon.json` | Running daemon config (transport, ports, address) |
| `~/.openclaw/p2p/tor/` | Tor configuration and hidden service |
| `~/.openclaw/p2p/i2p/` | I2P destination keys and config |
| `~/.openclaw/p2p/inbox/` | Received messages (encrypted) |
| `~/.openclaw/p2p/inbox/urgent/` | High-priority messages (webhook) |
| `~/.openclaw/p2p/notifications/` | Pending notifications for agent |
| `~/.openclaw/p2p/peers.json` | Your connected peers |

## Security

- All messages encrypted with NaCl box (Curve25519 + XSalsa20 + Poly1305)
- Transport layer (Tor or I2P) provides network-level encryption and anonymity
- Only peers you've explicitly added can send you messages
- No central server can read your messages
- Encryption is transport-agnostic — same crypto regardless of Tor or I2P
