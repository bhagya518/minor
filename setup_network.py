"""
setup_network.py (8-Node Sharded Version)
1. Detects online nodes dynamically
2. Creates shards of up to 10 nodes each
3. Assigns each shard 5 unique URLs to monitor
4. Implements Gossip-style registration (Fanout=4 per node)
"""

import requests
import time
import random
import json

# ── Configuration ────────────────────────────────────────────
MAX_NODES = 8
BASE_PORT = 8005
GOSSIP_FANOUT = 4
NODES_PER_SHARD = 10
URLS_PER_SHARD = 5

print("\n=== INITIALIZING SHARDED NETWORK ===")

# ── Step 1: Discover online nodes ────────────────────────────
print("\n[STEP 1] Discovering online nodes...")
online_nodes = {}
pubkeys = {}

print("  Waiting for nodes to initialize...")
# Give nodes time to start their FastAPI servers
time.sleep(15)

for i in range(MAX_NODES):
    port = BASE_PORT + i
    base_url = f"http://127.0.0.1:{port}"
    # Retry health check up to 3 times per node
    for attempt in range(3):
        try:
            r = requests.get(f"{base_url}/health", timeout=3)
            if r.status_code == 200:
                data = r.json()
                real_node_id = data.get("node_id", f"node_{i}")
                online_nodes[real_node_id] = base_url
                pk = data.get("public_key")
                if pk:
                    pubkeys[real_node_id] = pk
                print(f"  ✅ Found {real_node_id} at port {port}")
                break
        except Exception:
            if attempt < 2:
                time.sleep(1)

TOTAL = len(online_nodes)
print(f"  Found {TOTAL} online nodes")

if TOTAL < 2:
    print("ERROR: Need at least 2 nodes online.")
    exit(1)

# ── Step 2: Create dynamic shards ────────────────────────────
print(f"\n[STEP 2] Creating shards ({NODES_PER_SHARD} nodes per shard)...")
node_list = list(online_nodes.keys())
random.shuffle(node_list)

shards = {}
shard_id = 0
for i in range(0, len(node_list), NODES_PER_SHARD):
    shard_members = node_list[i:i + NODES_PER_SHARD]
    shard_name = f"SHARD_{shard_id}"
    shards[shard_name] = shard_members
    shard_id += 1

NUM_SHARDS = len(shards)
print(f"  Created {NUM_SHARDS} shards")
for name, members in shards.items():
    print(f"    {name}: {len(members)} nodes")

# ── Step 3: Gossip Registration (Fanout=4) ───────────────────
print(f"\n[STEP 3] Gossip Registration (Fanout={GOSSIP_FANOUT})...")
total_connections = 0
failed_connections = 0

for node_id in online_nodes:
    potential_peers = [n for n in online_nodes if n != node_id]
    peers_to_add = random.sample(potential_peers, min(GOSSIP_FANOUT, len(potential_peers)))
    for peer_id in peers_to_add:
        if node_id not in pubkeys:
            print(f"  ⚠️ Skipping {node_id} → {peer_id}: no public key for {node_id}")
            continue
        payload = {
            "node_id": node_id,
            "url": online_nodes[node_id],
            "public_key_hex": pubkeys[node_id],
        }
        registered = False
        for attempt in range(3):
            try:
                print(f"  Attempting registration: {node_id} -> {peer_id}")
                resp = requests.post(f"{online_nodes[peer_id]}/peers/register", json=payload, timeout=3)
                if resp.status_code == 200:
                    print(f"  ✅ Registration success: {resp.text}")
                    total_connections += 1
                    registered = True
                    break
                else:
                    print(f"  ⚠️ {node_id} -> {peer_id}: HTTP {resp.status_code}, Response: {resp.text}")
            except Exception as exc:
                print(f"  ❌ Error registering {node_id} -> {peer_id}: {exc}")
                if attempt < 2:
                    time.sleep(0.5)
        if not registered:
            failed_connections += 1

full_mesh = TOTAL * (TOTAL - 1)
print(f"  Total connections: {total_connections}")
print(f"  Failed connections: {failed_connections}")
print(f"  Full mesh would be: {full_mesh}")
print(f"  Reduction: {100 - (total_connections / max(full_mesh, 1) * 100):.1f}%")

# ── Step 4: Sharded URL Assignment ───────────────────────────
print(f"\n[STEP 4] Sharded URL Assignment ({URLS_PER_SHARD} URLs per shard)...")

# Generate URL pool (unique monitoring targets)
URL_POOL = [f"https://httpbin.org/status/{200 + i}" for i in range(100)]

for shard_idx, (shard_name, members) in enumerate(shards.items()):
    start_idx = (shard_idx * URLS_PER_SHARD) % len(URL_POOL)
    shard_urls = URL_POOL[start_idx:start_idx + URLS_PER_SHARD]
    for node_id in members:
        if node_id not in online_nodes:
            continue
        payload = {"urls": shard_urls}
        try:
            requests.post(f"{online_nodes[node_id]}/config/urls", json=payload, timeout=1)
        except Exception:
            pass
    print(f"  {shard_name}: assigned {len(shard_urls)} URLs to {len(members)} nodes")

# ── Step 5: Save network topology ────────────────────────────
topology = {
    "total_nodes": TOTAL,
    "num_shards": NUM_SHARDS,
    "gossip_fanout": GOSSIP_FANOUT,
    "total_connections": total_connections,
    "full_mesh_connections": full_mesh,
    "shards": {name: members for name, members in shards.items()},
    "urls_per_shard": URLS_PER_SHARD,
    "timestamp": time.time()
}

with open("network_topology.json", "w") as f:
    json.dump(topology, f, indent=2)

print(f"\n{'='*50}")
print(f"  NETWORK SETUP COMPLETE")
print(f"{'='*50}")
print(f"  Nodes Online:     {TOTAL}")
print(f"  Shards:           {NUM_SHARDS}")
print(f"  URLs per Shard:   {URLS_PER_SHARD}")
print(f"  Gossip Fanout:    {GOSSIP_FANOUT}")
print(f"  Connections:      {total_connections} (vs {full_mesh} full mesh)")
print(f"  Topology saved:   network_topology.json")
print(f"{'='*50}")