"""
COMPLETE RIPE SYSTEM DEMO
=========================
This script implements the full 20-step strategy for the Decentralized Website Monitoring System.
It handles:
1. ML Training (8 RIPE features)
2. Blockchain Setup
3. Node Registration
4. Initial Reputation & Sharding
5. Website Allocation
6. Continuous Monitoring & Consensus
"""

import os
import sys
import time
import subprocess
import requests
import json
import logging
from concurrent.futures import ThreadPoolExecutor

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Hardhat test accounts (Top 20)
PRIVATE_KEYS = [
    "0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80",
    "0x59c6995e998f97a5a0044966f0945389dc9e86dae88c7a8412f4603b6b78690d",
    "0x5de4111afa1a4b94908f83103eb1f1706367c2e68ca870fc3fb9a804cdab365a",
    "0x7c852118294e51e653712a81e05800f419141751be58f605c371e15141b007a6",
    "0x47e179ec197488593b187f80a00eb0da91f1b9d0b13f8733639f19c30a34926a",
    "0x8b3a350cf5c34c9194ca85829a2df0ec3153be0318b5e2d33a5581813a885023",
    "0x58095166297316719f9f59223e7100808a8a47854619a970e7a2b972e259e51c",
    "0x354ee0d8d73b06385d85d7764724a737f1c11a01726a45778a48722b5e022067",
    "0xd487eb5b29074d28470a7b689a74471f54807469a4e3a890a3651111003f538e",
    "0x37061750238e833446077755b410408544e377651a02195dfb4a45a305943485",
    "0x28f731f82b794f9976378e0638ba4a70659a85072046554b5f4581f185444983",
    "0x31a2936e3c54d1933a2166e409b626e2e04e9c7f66a87702447953255f00e998",
    "0x29841804d06a928f6424e868a8341604a1b021319246195dfb4a45a305943485", # Synthetic/Extra for demo
    "0x41a2936e3c54d1933a2166e409b626e2e04e9c7f66a87702447953255f00e998", # Synthetic/Extra for demo
    "0x51a2936e3c54d1933a2166e409b626e2e04e9c7f66a87702447953255f00e998", # Synthetic/Extra for demo
    "0x61a2936e3c54d1933a2166e409b626e2e04e9c7f66a87702447953255f00e998", # Synthetic/Extra for demo
    "0x71a2936e3c54d1933a2166e409b626e2e04e9c7f66a87702447953255f00e998", # Synthetic/Extra for demo
    "0x81a2936e3c54d1933a2166e409b626e2e04e9c7f66a87702447953255f00e998", # Synthetic/Extra for demo
    "0x91a2936e3c54d1933a2166e409b626e2e04e9c7f66a87702447953255f00e998", # Synthetic/Extra for demo
    "0xa1a2936e3c54d1933a2166e409b626e2e04e9c7f66a87702447953255f00e998"  # Synthetic/Extra for demo
]

NODE_MODES = ["honest"] * 10 + ["suspicious"] * 4 + ["faulty"] * 3 + ["malicious"] * 3
WEBSITES = [
    "https://google.com", 
    "https://github.com", 
    "https://openai.com", 
    "https://amazon.com",
    "https://microsoft.com",
    "https://apple.com",
    "https://facebook.com",
    "https://twitter.com",
    "https://wikipedia.org",
    "https://reddit.com"
]

def run_step(name, command):
    logger.info(f"--- STEP: {name} ---")
    logger.info(f"Running: {' '.join(command)}")
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode != 0:
        logger.error(f"Error in step {name}: {result.stderr}")
        return False
    logger.info(f"Successfully completed {name}")
    return True

def main():
    logger.info("Starting SCALED Implementation Demo (20 Nodes, 10 Websites, 4 Shards)")
    
    # 1. ML Training Phase (Step 1-4)
    logger.info("Phase 1: ML Pipeline Training (8 RIPE Features)")
    if not run_step("Train RIPE Ensemble", [sys.executable, "ml/src/train_ripe_ensemble.py"]):
        return

    # 2. Blockchain Initialization (Step 5)
    logger.info("Phase 2: Blockchain Initialization")
    # Check if blockchain is already running
    try:
        requests.get("http://127.0.0.1:8545")
        logger.info("Found running blockchain (Hardhat)")
    except:
        logger.error("Error: Local blockchain (Hardhat) not found. Please run 'npx hardhat node' in blockchain directory.")
        return

    # 3. Start Nodes (Step 6-10)
    logger.info("Phase 3: Network Setup & Bootstrap (Starting 20 Nodes)")
    nodes = []
    ports = range(8000, 8020)
    
    os.makedirs("logs", exist_ok=True)
    
    for i, port in enumerate(ports):
        node_id = f"node_{i+1}"
        mode = NODE_MODES[i]
        env = os.environ.copy()
        env["NODE_ID"] = node_id
        env["PORT"] = str(port)
        env["PRIVATE_KEY"] = PRIVATE_KEYS[i]
        env["NODE_MODE"] = mode
        env["MONITORED_URLS"] = ",".join(WEBSITES)
        
        log_file = open(f"logs/{node_id}.log", "w")
        p = subprocess.Popen(
            [sys.executable, "node_service/main.py"],
            env=env,
            stdout=log_file, stderr=log_file
        )
        nodes.append(p)
        if (i+1) % 5 == 0:
            logger.info(f"Started {i+1}/20 nodes...")

    logger.info("Waiting 30 seconds for all 20 nodes to boot and register...")
    time.sleep(30)

    # 4. Connect Peers (Optimized for 20 nodes - each node connects to 4 others)
    logger.info("Connecting peers to form a distributed network...")
    for i, port in enumerate(ports):
        # Each node connects to next 4 neighbors in a ring to ensure connectivity
        for j in range(1, 5):
            target_idx = (i + j) % 20
            target_port = ports[target_idx]
            target_id = f"node_{target_idx + 1}"
            try:
                requests.post(f"http://127.0.0.1:{port}/peers", json={
                    "node_id": target_id,
                    "host": "127.0.0.1",
                    "port": target_port
                }, timeout=2)
            except: pass

    logger.info("Network connected. System is now running through Epochs.")
    logger.info("The system will perform: Monitoring -> Feature Extraction -> ML Inference -> Sharding")
    
    try:
        while True:
            # Check status of node_1
            try:
                resp = requests.get("http://127.0.0.1:8000/sharding/status").json()
                logger.info("--- CURRENT SHARDING STATUS ---")
                logger.info(f"Epoch: {resp.get('current_epoch', 'N/A')} | Master Leader: {resp.get('master_leader', 'N/A')}")
                for sid, shard in resp.get('shards', {}).items():
                    members = [f"{m['node_id']}({m['tier']})" for m in shard['members']]
                    sites = shard.get('websites', [])
                    logger.info(f"Shard {sid}: {', '.join(members)} | Websites: {len(sites)}")
                
                # Check reputations
                rep_resp = requests.get("http://127.0.0.1:8000/reputation").json()
                reps = rep_resp.get('reputations', {})
                logger.info(f"Reputations: { {k: round(v, 2) for k, v in reps.items()} }")
                
            except Exception as e:
                logger.warning(f"Status check failed: {e}")
            
            time.sleep(30)
            
    except KeyboardInterrupt:
        logger.info("Stopping demo...")
        for p in nodes:
            p.terminate()
        logger.info("All nodes stopped.")

if __name__ == "__main__":
    main()
