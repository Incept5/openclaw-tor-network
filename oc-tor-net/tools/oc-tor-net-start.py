#!/usr/bin/env python3
"""
Start the P2P agent (runs Tor, starts message server)
"""
import sys
import os
import time
import signal
from pathlib import Path

# Setup logging to file
try:
    log_dir = Path.home() / '.openclaw' / 'p2p'
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / 'daemon.log'
except Exception as e:
    print(f"Error creating log directory: {e}")
    log_file = Path('/tmp/oc-tor-net-daemon.log')

class Logger:
    def __init__(self, filepath):
        self.filepath = filepath
        try:
            self.file = open(filepath, 'a')
        except Exception as e:
            print(f"Error opening log file {filepath}: {e}")
            self.file = None

    def log(self, message):
        timestamp = time.strftime('%Y-%m-%d %H:%M:%S')
        line = f"[{timestamp}] {message}"
        print(line)
        if self.file:
            self.file.write(line + '\n')
            self.file.flush()

    def close(self):
        if self.file:
            self.file.close()

logger = Logger(log_file)
logger.log("=== Daemon starting ===")

# Add lib to path
script_dir = os.path.dirname(os.path.abspath(__file__))
lib_dir = os.path.join(script_dir, '..', 'lib')
sys.path.insert(0, lib_dir)

try:
    from agent import P2PAgent
except ImportError as e:
    logger.log(f"Error: Cannot import P2PAgent: {e}")
    sys.exit(1)


def main():
    agent = P2PAgent()
    
    def signal_handler(sig, frame):
        logger.log("Shutting down...")
        agent.stop()
        logger.close()
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    try:
        agent.start()
        logger.log("Agent is running. Press Ctrl+C to stop.")
        logger.log(f"Log file: {log_file}")
        
        # Keep running with periodic status
        counter = 0
        while True:
            time.sleep(1)
            counter += 1
            if counter % 60 == 0:  # Every 60 seconds
                logger.log(f"[DEBUG] Daemon alive - {counter} seconds uptime")
                
    except Exception as e:
        logger.log(f"Error: {e}")
        import traceback
        logger.log(traceback.format_exc())
        agent.stop()
        logger.close()
        sys.exit(1)


if __name__ == "__main__":
    main()
