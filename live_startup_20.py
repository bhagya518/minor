"""
live_startup_20.py
Starts 20 nodes using subprocess and waits for them to be ready.
"""

import subprocess
import time
import os
import requests

NODES = "abcdefghijklmnopqrst"
BASE_PORT = 8005
processes = []

print(f"--- STARTING 20 REAL NODES (Ports {BASE_PORT} to {BASE_PORT+19}) ---")

for i, char in enumerate(NODES):
    port = BASE_PORT + i
    node_id = f"node_{char}"
    
    # Set environment variables for node mode
    env = os.environ.copy()
    if char in ['d', 'm']:
        env['NODE_MODE'] = 'malicious'
        mode_str = "MALICIOUS"
    else:
        env['NODE_MODE'] = 'honest'
        mode_str = "HONEST"
    
    # Start the process in a way that works on Windows
    cmd = [
        "python", "main.py", 
        "--port", str(port), 
        "--node-id", node_id
    ]
    
    print(f"  > Launching {node_id} ({mode_str}) on port {port}...")
    
    # Use subprocess.Popen to run in background
    p = subprocess.Popen(
        cmd, 
        cwd="node_service", 
        env=env,
        creationflags=subprocess.CREATE_NEW_CONSOLE if os.name == 'nt' else 0
    )
    processes.append(p)
    time.sleep(0.5) # Fast startup

print("\n--- WAITING 15s FOR INITIALIZATION ---")
time.sleep(15)

print("\n--- RUNNING SETUP_NETWORK.PY ---")
subprocess.run(["python", "setup_network.py"])

print("\n--- ALL NODES LIVE ---")
print("You can now run live_benchmark_20.py to collect results.")
