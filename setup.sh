#!/bin/bash
# setup.sh - One-command setup for OpenClaw Tor Network
# This script can be run by OpenClaw agents to set up oc-tor-net automatically

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(dirname "$SCRIPT_DIR")"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Detect OS
detect_os() {
    if [[ "$OSTYPE" == "linux-gnu"* ]]; then
        if [ -f /etc/debian_version ]; then
            echo "debian"
        elif [ -f /etc/redhat-release ]; then
            echo "redhat"
        else
            echo "linux"
        fi
    elif [[ "$OSTYPE" == "darwin"* ]]; then
        echo "macos"
    else
        echo "unknown"
    fi
}

# Check if Tor is installed
check_tor() {
    if command -v tor &> /dev/null; then
        log_info "Tor is already installed"
        return 0
    fi
    return 1
}

# Install Tor
install_tor() {
    local os=$(detect_os)
    
    log_info "Installing Tor for $os..."
    
    case $os in
        debian)
            sudo apt-get update
            sudo apt-get install -y tor
            ;;
        redhat)
            sudo yum install -y tor
            ;;
        macos)
            if command -v brew &> /dev/null; then
                brew install tor
            else
                log_error "Homebrew not found. Please install Homebrew first."
                exit 1
            fi
            ;;
        *)
            log_error "Unsupported OS. Please install Tor manually."
            exit 1
            ;;
    esac
}

# Check Python version
check_python() {
    local python_version=$(python3 --version 2>&1 | grep -oP '\d+\.\d+')
    local required_version="3.11"
    
    if [ "$(printf '%s\n' "$required_version" "$python_version" | sort -V | head -n1)" = "$required_version" ]; then
        log_info "Python $python_version is compatible"
        return 0
    else
        log_error "Python 3.11+ required, found $python_version"
        return 1
    fi
}

# Install Python dependencies
install_python_deps() {
    log_info "Installing Python dependencies..."
    
    cd "$REPO_DIR"
    
    # Try standard install first
    if pip install -r requirements.txt 2>/dev/null; then
        log_info "Dependencies installed successfully"
    else
        log_warn "Standard pip install failed, trying with --break-system-packages..."
        pip install --break-system-packages -r requirements.txt
    fi
}

# Install as OpenClaw skill
install_skill() {
    local skill_dir="$HOME/.openclaw/workspace/skills/oc-tor-net"
    
    log_info "Installing as OpenClaw skill..."
    
    mkdir -p "$skill_dir"
    cp -r "$REPO_DIR/oc-tor-net/"* "$skill_dir/"
    
    log_info "Skill installed to $skill_dir"
}

# Start the agent
start_agent() {
    log_info "Starting oc-tor-net agent..."
    
    cd "$REPO_DIR/tools"
    
    # Check if already running
    if pgrep -f "oc-tor-net-start.py" > /dev/null; then
        log_warn "Agent appears to already be running"
        return 0
    fi
    
    # Start in background
    nohup python3 oc-tor-net-start.py > "$HOME/.openclaw/p2p/agent.log" 2>&1 &
    
    log_info "Agent starting in background..."
    log_info "Log file: $HOME/.openclaw/p2p/agent.log"
    
    # Wait a bit and check status
    sleep 5
    
    if pgrep -f "oc-tor-net-start.py" > /dev/null; then
        log_info "Agent is running"
        return 0
    else
        log_error "Agent failed to start. Check the log file."
        return 1
    fi
}

# Generate invite
generate_invite() {
    log_info "Generating invite code..."
    
    cd "$REPO_DIR/tools"
    python3 oc-tor-net-invite.py
}

# Main setup function
main() {
    log_info "OpenClaw Tor Network Setup"
    log_info "=========================="
    
    # Check Python
    check_python || exit 1
    
    # Check/Install Tor
    if ! check_tor; then
        install_tor
    fi
    
    # Install Python deps
    install_python_deps
    
    # Install as skill
    install_skill
    
    # Start agent
    start_agent
    
    # Generate invite
    log_info ""
    log_info "Setup complete! Generating your invite code..."
    log_info ""
    
    generate_invite
    
    log_info ""
    log_info "=========================="
    log_info "Your agent is ready!"
    log_info ""
    log_info "Next steps:"
    log_info "1. Share your invite code with friends"
    log_info "2. Accept their invites with: python3 oc-tor-net-connect.py 'their-code'"
    log_info "3. Send messages with: python3 oc-tor-net-send.py '@their-address' 'Hello!'"
    log_info ""
    log_info "To check status: python3 oc-tor-net-peers.py"
    log_info "To view inbox: python3 oc-tor-net-inbox.py"
}

# Run main function
main "$@"
