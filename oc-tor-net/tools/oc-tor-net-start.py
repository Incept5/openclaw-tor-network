#!/usr/bin/env python3
"""
Start the P2P agent (runs Tor, starts message server)
"""
import sys
import os
import time
import signal

# Add lib to path
script_dir = os.path.dirname(os.path.abspath(__file__))
lib_dir = os.path.join(script_dir, '..', 'lib')
sys.path.insert(0, lib_dir)

try:
    from agent import P2PAgent
except ImportError as e:
    print(f"Error: Cannot import P2PAgent: {e}")
    sys.exit(1)


def main():
    agent = P2PAgent()
    
    def signal_handler(sig, frame):
        print("\nShutting down...")
        agent.stop()
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    try:
        agent.start()
        print("\nAgent is running. Press Ctrl+C to stop.\n")
        
        # Keep running
        while True:
            time.sleep(1)
            
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        agent.stop()
        sys.exit(1)


if __name__ == "__main__":
    main()
