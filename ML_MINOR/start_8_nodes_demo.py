import subprocess
import time
import os
import requests
import signal
import sys

# Hardhat test accounts (first 8)
PRIVATE_KEYS = [
    "0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80",
    "0x59c6995e998f97a5a0044966f0945389dc9e86dae88c7a8412f4603b6b78690d",
    "0x5de4111afa1a4b94908f83103eb1f1706367c2e68ca870fc3fb9a804cdab365a",
    "0x7c852118294e51e653712a81e05800f419141751be58f605c371e15141b007a6",
    "0x47e179ec197488593b187f80a00eb0da91f1b9d0b13f8733639f19c30a34926a",
    "0x8b3a350cf5c34c9194ca85829a2df0ec3153be0318b5e2d3348e872092edffba",
    "0x92db14e403b83dfe3df233f83dfa3a0d7096f21ca9b0d6d6b8d88b2b4ec1564e",
    "0x4bbbf85ce3377467afe5d46f804f221813b2bb87f24d81f60f1fcdbf7cbf4356"
]

def main():
    print("Starting 8 nodes for 4-tier sharding demonstration...")
    nodes = []
    ports = range(8000, 8008)
    
    # Ensure logs directory exists
    if not os.path.exists("logs"):
        os.makedirs("logs")

    # Start nodes
    for i, port in enumerate(ports):
        node_id = f"node_{i+1}"
        log_file = f"logs/{node_id}.log"
        print(f"  Starting {node_id} on port {port} using unique account...")
        
        # Set environment variables for each node
        env = os.environ.copy()
        env["NODE_ID"] = node_id
        env["PORT"] = str(port)
        env["PRIVATE_KEY"] = PRIVATE_KEYS[i]
        env["MONITORING_INTERVAL"] = "15"
        
        with open(log_file, "w") as f:
            p = subprocess.Popen(
                ["python", "node_service/main.py"],
                env=env,
                stdout=f, stderr=f
            )
            nodes.append(p)
    
    print("\nWaiting 30 seconds for nodes to initialize and load ML models...")
    for i in range(30):
        time.sleep(1)
        if (i+1) % 10 == 0:
            print(f"  {30 - (i+1)} seconds left...")
    
    # Connect peers to form a full mesh network
    print("\nConnecting peers to form the network...")
    for port in ports:
        for target_port in ports:
            if port == target_port: continue
            
            target_id = f"node_{target_port - 8000 + 1}"
            peer_data = {
                "node_id": target_id,
                "host": "127.0.0.1",
                "port": target_port
            }
            try:
                # Use a small timeout to avoid hanging if a node is slow
                requests.post(f"http://127.0.0.1:{port}/peers", json=peer_data, timeout=5)
            except Exception as e:
                pass # Silently fail if node not fully ready
    
    print("\nNetwork initialized! The nodes are seeded with different reputations.")
    print("Summary of expected tiers:")
    print("  node_1, node_2: PRIMARY (Healthy)")
    print("  node_3, node_4: MONITORING (Suspicious)")
    print("  node_5, node_6: QUARANTINE (Faulty)")
    print("  node_7, node_8: SLASHED (Malicious)")
    
    print("\nVerification Commands:")
    print("  1. Check Node 1's view of all nodes:")
    print("     curl http://127.0.0.1:8000/statistics")
    print("  2. Check sharding distribution:")
    print("     curl http://127.0.0.1:8000/sharding/status (if available) or check logs")
    
    print("\nKeep this script running to keep nodes active.")
    print("Press Ctrl+C to stop all nodes.")
    
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nStopping all nodes...")
        for p in nodes:
            try:
                p.terminate()
            except:
                pass
        print("All nodes stopped.")

if __name__ == "__main__":
    main()
