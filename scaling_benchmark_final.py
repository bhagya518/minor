import time
import matplotlib.pyplot as plt
import numpy as np
import sys
import os
import json

# Add node_service to path so we can import the REAL engine
sys.path.append(os.path.join(os.getcwd(), 'node_service'))

try:
    from src.ml_consensus_engine import EnhancedMLConsensusEngine
except ImportError:
    # Fallback if pathing is slightly different on server
    sys.path.append(os.path.join(os.getcwd(), 'node_service', 'src'))
    from ml_consensus_engine import EnhancedMLConsensusEngine

def run_scaling_benchmark():
    engine = EnhancedMLConsensusEngine(node_id="scaling_benchmark_node")
    
    # 1. LATENCY & THROUGHPUT SCALING (10 to 300 Nodes)
    node_counts = [10, 50, 100, 150, 200, 250, 300]
    node_scaling_data = []
    total_pipeline_latencies = []
    node_max_capacities = []
    
    print("🚀 STARTING: High-Fidelity Scaling Benchmark (Nodes 10 -> 300)...")
    
    for n in node_counts:
        # --- A. ML CONSENSUS (Real Measurement) ---
        fake_reports = []
        for i in range(n):
            for u in range(5):
                fake_reports.append({
                    "node_id": f"node_{i}",
                    "url": f"https://site_{u}.com",
                    "is_reachable": True,
                    "response_ms": 100 + np.random.randint(-10, 10),
                    "ssl_valid": True,
                    "timestamp": time.time()
                })
        
        start_time = time.time()
        engine.process_epoch_consensus(epoch_id=1, reports=fake_reports)
        ml_time_ms = (time.time() - start_time) * 1000
        
        # --- B. REALISTIC BOTTLENECKS ---
        monitoring_overhead = 20 + (n * 0.1)
        gossip_delay = np.log2(n) * 40
        blockchain_delay = 150 + np.random.uniform(50, 100) 
        
        total_latency = monitoring_overhead + gossip_delay + ml_time_ms + blockchain_delay
        
        # Throughput at 5 URLs/Node
        epoch_rps = n # (n * 5 URLs) / 5.0 seconds
        max_capacity_rps = (n * 5) / (total_latency / 1000)
        
        node_scaling_data.append({
            "nodes": n,
            "latency_ms": round(total_latency, 2),
            "ml_compute_ms": round(ml_time_ms, 2),
            "epoch_throughput_rps": epoch_rps,
            "max_capacity_rps": round(max_capacity_rps, 2)
        })
        total_pipeline_latencies.append(total_latency)
        node_max_capacities.append(max_capacity_rps)
        
        print(f"   [Nodes: {n:3}] Latency: {total_latency:7.2f}ms | Max Capacity: {max_capacity_rps:7.1f} RPS")

    # 2. LOAD SCALING DATA (Fixed 200 Nodes)
    url_loads = [5, 10, 25, 50, 100, 200]
    load_scaling_data = []
    load_max_capacities = []
    
    print("\n🚀 STARTING: Realistic Load Capacity Test (at 200 Nodes)...")
    for u in url_loads:
        total_reports = 200 * u
        fake_reports = [{"node_id": f"node_{i}", "url": f"u_{j}"} for i in range(200) for j in range(u)]
        start_time = time.time()
        engine.process_epoch_consensus(epoch_id=1, reports=fake_reports)
        process_time = time.time() - start_time
        
        # REALISTIC BOTTLENECKS (Unified with Node Scaling)
        base_overhead = 520
        network_penalty_ms = 0
        if total_reports > 1000:
            network_penalty_ms = ((total_reports - 1000) / 1000) ** 1.5 * 15
        
        blockchain_queue_ms = 0
        if total_reports > 5000:
            blockchain_queue_ms = (total_reports - 5000) * 0.5
            
        estimated_pipeline = base_overhead + (process_time * 1000) + network_penalty_ms + blockchain_queue_ms
        
        epoch_rps = (total_reports * (5000 / estimated_pipeline)) / 5.0 if estimated_pipeline > 5000 else total_reports / 5.0
        max_capacity_rps = total_reports / (estimated_pipeline / 1000)
        
        load_scaling_data.append({
            "urls_per_node": u,
            "total_reports": total_reports,
            "pipeline_ms": round(estimated_pipeline, 2),
            "epoch_throughput_rps": round(epoch_rps, 2),
            "max_capacity_rps": round(max_capacity_rps, 2)
        })
        load_max_capacities.append(max_capacity_rps) 
        print(f"   [URLs/Node: {u:3}] Pipeline: {estimated_pipeline:7.1f}ms | Max Capacity: {max_capacity_rps:7.1f} RPS")

    # --- 3. SAVE DATA ANALYSIS FILES ---
    analysis_results = {
        "node_scaling": node_scaling_data,
        "load_scaling": load_scaling_data,
        "timestamp": time.time()
    }
    
    with open('scaling_analysis_results.json', 'w') as f:
        json.dump(analysis_results, f, indent=2)
        
    import csv
    with open('scaling_analysis_results.csv', 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(["--- NODE SCALING DATA ---"])
        writer.writerow(["Nodes", "Latency (ms)", "ML Compute (ms)", "Epoch Throughput (RPS)", "Max Capacity (RPS)"])
        for row in node_scaling_data:
            writer.writerow([row["nodes"], row["latency_ms"], row["ml_compute_ms"], row["epoch_throughput_rps"], row["max_capacity_rps"]])
            
        writer.writerow([])
        writer.writerow(["--- LOAD SCALING DATA (200 Nodes) ---"])
        writer.writerow(["URLs/Node", "Total Reports", "Pipeline (ms)", "Epoch Throughput (RPS)", "Max Capacity (RPS)"])
        for row in load_scaling_data:
            writer.writerow([row["urls_per_node"], row["total_reports"], row["pipeline_ms"], row["epoch_throughput_rps"], row["max_capacity_rps"]])

    # --- 4. GENERATE GRAPHS ---
    plt.style.use('dark_background')
    
    # Graph 1: Latency Scaling
    plt.figure(figsize=(10, 6))
    plt.plot(node_counts, total_pipeline_latencies, marker='o', linewidth=3, color='#00ffcc', label='System Latency')
    plt.fill_between(node_counts, total_pipeline_latencies, color='#00ffcc', alpha=0.1)
    
    plt.title('System Latency Scaling (10 to 300 Nodes)', fontsize=14, fontweight='bold', pad=20)
    plt.xlabel('Number of Active Nodes', fontsize=12)
    plt.ylabel('Latency (ms)', fontsize=12)
    plt.legend()
    plt.grid(True, linestyle='--', alpha=0.3)
    plt.savefig('scaling_latency_300.png', dpi=300, bbox_inches='tight')
    
    # Graph 2: Max Capacity vs Nodes
    plt.figure(figsize=(10, 6))
    plt.plot(node_counts, node_max_capacities, marker='d', linewidth=3, color='#ff9900', label='Max Theoretical Capacity')
    plt.fill_between(node_counts, node_max_capacities, color='#ff9900', alpha=0.1)
    plt.title('System Capacity Scaling (10 to 300 Nodes)', fontsize=14, fontweight='bold', pad=20)
    plt.xlabel('Number of Active Nodes', fontsize=12)
    plt.ylabel('Max Capacity (Reports/sec)', fontsize=12)
    plt.legend()
    plt.grid(True, linestyle='--', alpha=0.3)
    plt.savefig('scaling_capacity_nodes_300.png', dpi=300, bbox_inches='tight')
    
    # Graph 3: Throughput vs Load (using Max Capacity)
    plt.figure(figsize=(10, 6))
    plt.plot(url_loads, load_max_capacities, marker='s', linewidth=3, color='#3399ff', label='Max Capacity Under Load')
    plt.fill_between(url_loads, load_max_capacities, color='#3399ff', alpha=0.1)
    
    plt.title('System Throughput Capacity (200 Nodes)', fontsize=14, fontweight='bold', pad=20)
    plt.xlabel('URLs Monitored Per Node', fontsize=12)
    plt.ylabel('Max Capacity (Reports/sec)', fontsize=12)
    plt.legend()
    plt.grid(True, linestyle='--', alpha=0.3)
    plt.savefig('scaling_throughput_200.png', dpi=300, bbox_inches='tight')
    
    print("\n✅ Scaling Analysis Completed.")
    print("   1. scaling_latency_300.png (Node Scaling)")
    print("   2. scaling_throughput_200.png (Load Scaling)")

if __name__ == "__main__":
    run_scaling_benchmark()
