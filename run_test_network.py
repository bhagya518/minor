import subprocess
import time
import os
import signal
import sys
import requests

def main():
    print("Starting 4 nodes...")
    nodes = []
    
    # Environment variables
    env_honest = os.environ.copy()
    env_honest["NODE_MODE"] = "honest"
    
    env_malicious = os.environ.copy()
    env_malicious["NODE_MODE"] = "malicious"
    
    # Start nodes
    try:
        # Node 1
        with open("logs/node_1.log", "w") as f1:
            p1 = subprocess.Popen(["python", "node_service/main.py", "--port", "8101", "--node-id", "node_1"], 
                                 env=env_honest, stdout=f1, stderr=f1)
            nodes.append(p1)
            
        # Node 2
        with open("logs/node_2.log", "w") as f2:
            p2 = subprocess.Popen(["python", "node_service/main.py", "--port", "8102", "--node-id", "node_2"], 
                                 env=env_honest, stdout=f2, stderr=f2)
            nodes.append(p2)
            
        # Node 3
        with open("logs/node_3.log", "w") as f3:
            p3 = subprocess.Popen(["python", "node_service/main.py", "--port", "8103", "--node-id", "node_3"], 
                                 env=env_honest, stdout=f3, stderr=f3)
            nodes.append(p3)
            
        # Node 4 (Malicious)
        with open("logs/node_4.log", "w") as f4:
            p4 = subprocess.Popen(["python", "node_service/main.py", "--port", "8104", "--node-id", "node_4"], 
                                 env=env_malicious, stdout=f4, stderr=f4)
            nodes.append(p4)
            
        print("Waiting for nodes to start (10s)...")
        time.sleep(10)
        
        # Connect nodes via peers endpoint
        print("Connecting peers...")
        peers = [
            {"node_id": "node_1", "host": "127.0.0.1", "port": 8101},
            {"node_id": "node_2", "host": "127.0.0.1", "port": 8102},
            {"node_id": "node_3", "host": "127.0.0.1", "port": 8103},
            {"node_id": "node_4", "host": "127.0.0.1", "port": 8104}
        ]
        
        for port in [8101, 8102, 8103, 8104]:
            for peer in peers:
                if peer["port"] != port:
                    try:
                        requests.post(f"http://127.0.0.1:{port}/peers", json=peer, timeout=2)
                    except Exception as e:
                        print(f"Failed to connect peer to port {port}: {e}")
                        
        print("Peers connected. Waiting 90 seconds for an epoch to pass and consensus to run...")
        for i in range(9):
            time.sleep(10)
            print(f"... {90 - (i+1)*10} seconds left")
            
    finally:
        print("Terminating nodes...")
        for p in nodes:
            try:
                p.terminate()
            except:
                pass

if __name__ == "__main__":
    main()
