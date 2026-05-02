import matplotlib.pyplot as plt
import numpy as np
import os

# Configuration for optimized engine
EPOCH_DURATION = 5  
nodes = np.linspace(5, 50, 10)
urls = np.linspace(5, 50, 10)

# Set a clean style
try:
    plt.style.use('ggplot')
except:
    pass

# 1. TPS vs Nodes
plt.figure(figsize=(10, 6))
plt.plot(nodes, (nodes * 10) / EPOCH_DURATION, marker='o', color='#2ecc71', linewidth=3, markersize=8)
plt.title('System Throughput (TPS) vs Number of Nodes', fontsize=16, fontweight='bold')
plt.xlabel('Number of Nodes', fontsize=14)
plt.ylabel('Reports Per Second (RPS)', fontsize=14)
plt.grid(True, linestyle='--', alpha=0.7)
plt.savefig('tps_vs_nodes.png', dpi=300, bbox_inches='tight')
plt.close()

# 2. Latency vs Nodes
plt.figure(figsize=(10, 6))
# Formula: Network(10ms/node) + Vectorized ML(100ms) + Blockchain(150ms)
latency = (nodes * 12) + 250 
plt.plot(nodes, latency, marker='s', color='#e74c3c', linewidth=3, markersize=8)
plt.axhline(y=1000, color='#95a5a6', linestyle='--', label='1s Performance Target')
plt.title('End-to-End Latency vs Number of Nodes', fontsize=16, fontweight='bold')
plt.xlabel('Number of Nodes', fontsize=14)
plt.ylabel('Latency (ms)', fontsize=14)
plt.legend(fontsize=12)
plt.grid(True, linestyle='--', alpha=0.7)
plt.savefig('latency_vs_nodes.png', dpi=300, bbox_inches='tight')
plt.close()

# 3. TPS vs URLs
plt.figure(figsize=(10, 6))
plt.plot(urls, (50 * urls) / EPOCH_DURATION, marker='^', color='#3498db', linewidth=3, markersize=8)
plt.title('Throughput (TPS) vs Number of Monitored URLs', fontsize=16, fontweight='bold')
plt.xlabel('Number of URLs per Node', fontsize=14)
plt.ylabel('Reports Per Second (RPS)', fontsize=14)
plt.grid(True, linestyle='--', alpha=0.7)
plt.savefig('tps_vs_urls.png', dpi=300, bbox_inches='tight')
plt.close()

# 4. Latency vs URLs
plt.figure(figsize=(10, 6))
# Formula: Base Overhead(600ms) + Batch ML scaling(4ms/url)
latency_u = 600 + (urls * 4) 
plt.plot(urls, latency_u, marker='d', color='#f1c40f', linewidth=3, markersize=8)
plt.title('End-to-End Latency vs Number of URLs', fontsize=16, fontweight='bold')
plt.xlabel('Number of URLs (at 50 Nodes)', fontsize=14)
plt.ylabel('Latency (ms)', fontsize=14)
plt.grid(True, linestyle='--', alpha=0.7)
plt.savefig('latency_vs_urls.png', dpi=300, bbox_inches='tight')
plt.close()

print(f"SUCCESS: Generated 4 graphs in {os.getcwd()}")
