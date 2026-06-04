import json
import os
from datetime import datetime

# Node configuration
NODE_IDS = [f"node_{i}" for i in range(1, 9)]
# Map node IDs to desired reputations to represent all 4 tiers
REPUTATIONS = {
    "node_1": 0.95, # PRIMARY
    "node_2": 0.92, # PRIMARY
    "node_3": 0.65, # MONITORING
    "node_4": 0.60, # MONITORING
    "node_5": 0.35, # QUARANTINE
    "node_6": 0.30, # QUARANTINE
    "node_7": 0.15, # SLASHED
    "node_8": 0.10  # SLASHED
}

def setup_demo():
    print("Setting up 8-node 4-tier sharding demonstration...")
    
    node_service_dir = "node_service"
    if not os.path.exists(node_service_dir):
        print(f"Error: {node_service_dir} directory not found.")
        return

    # Create reputation state for each node
    # All nodes must agree on the reputations of everyone else
    master_state = {
        "reputation": REPUTATIONS,
        "ewma_reputations": REPUTATIONS,
        "last_updated": datetime.now().isoformat()
    }

    for node_id in NODE_IDS:
        state_file = os.path.join(node_service_dir, f"reputation_state_{node_id}.json")
        with open(state_file, 'w') as f:
            json.dump(master_state, f, indent=4)
        print(f"  Created state file for {node_id}")

    print("\nDemonstration setup complete!")
    print("Nodes are now seeded with the following tiers:")
    print("  Tier 1 (PRIMARY): node_1, node_2")
    print("  Tier 2 (MONITORING): node_3, node_4")
    print("  Tier 3 (QUARANTINE): node_5, node_6")
    print("  Tier 4 (SLASHED): node_7, node_8")

if __name__ == "__main__":
    setup_demo()
