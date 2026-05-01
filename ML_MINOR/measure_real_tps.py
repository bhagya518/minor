#!/usr/bin/env python3
"""
Real TPS (Transactions Per Second) Measurement
Measures actual monitoring cycles completed per second instead of using a formula.
"""

import asyncio
import time
import httpx
import statistics
from typing import List, Dict
import argparse

async def measure_node_tps(node_url: str, duration_seconds: int = 60) -> Dict:
    """
    Measure actual TPS from a running node by counting monitoring cycles.
    
    Args:
        node_url: URL of the node (e.g., http://localhost:8005)
        duration_seconds: How long to measure (default 60 seconds)
    
    Returns:
        Dict with TPS metrics
    """
    print(f"Measuring TPS for node: {node_url}")
    print(f"Duration: {duration_seconds} seconds")
    print("-" * 60)
    
    async with httpx.AsyncClient() as client:
        # Get initial epoch
        start_time = time.time()
        initial_epoch = int(start_time // 60)
        
        # Track monitoring cycles
        cycle_count = 0
        start_cycle_count = 0
        
        # Get initial cycle count from /statistics endpoint
        try:
            stats = await client.get(f"{node_url}/statistics", timeout=5.0)
            if stats.status_code == 200:
                stats_data = stats.json()
                start_cycle_count = stats_data.get("total_monitoring_cycles", 0)
                print(f"Initial cycle count: {start_cycle_count}")
        except Exception as e:
            print(f"Warning: Could not get initial stats: {e}")
        
        # Wait for measurement duration
        print(f"Measuring for {duration_seconds} seconds...")
        await asyncio.sleep(duration_seconds)
        
        # Get final cycle count
        end_time = time.time()
        final_cycle_count = 0
        
        try:
            stats = await client.get(f"{node_url}/statistics", timeout=5.0)
            if stats.status_code == 200:
                stats_data = stats.json()
                final_cycle_count = stats_data.get("total_monitoring_cycles", 0)
                print(f"Final cycle count: {final_cycle_count}")
        except Exception as e:
            print(f"Warning: Could not get final stats: {e}")
        
        # Calculate TPS
        elapsed_time = end_time - start_time
        cycles_completed = final_cycle_count - start_cycle_count
        tps = cycles_completed / elapsed_time if elapsed_time > 0 else 0
        
        # Get node info
        node_info = {}
        try:
            health = await client.get(f"{node_url}/health", timeout=5.0)
            if health.status_code == 200:
                node_info = health.json()
        except Exception as e:
            print(f"Warning: Could not get node info: {e}")
        
        result = {
            "node_url": node_url,
            "duration_seconds": elapsed_time,
            "cycles_completed": cycles_completed,
            "tps": tps,
            "node_id": node_info.get("node_id", "unknown"),
            "timestamp": time.time()
        }
        
        print("-" * 60)
        print(f"✅ MEASUREMENT COMPLETE")
        print(f"   Duration: {elapsed_time:.2f} seconds")
        print(f"   Cycles completed: {cycles_completed}")
        print(f"   TPS: {tps:.4f} cycles/second")
        print(f"   Node ID: {result['node_id']}")
        
        return result

async def measure_multi_node_tps(node_urls: List[str], duration_seconds: int = 60) -> Dict:
    """
    Measure TPS across multiple nodes and aggregate.
    
    Args:
        node_urls: List of node URLs
        duration_seconds: Measurement duration
    
    Returns:
        Dict with aggregated TPS metrics
    """
    print(f"Measuring TPS across {len(node_urls)} nodes")
    print(f"Duration: {duration_seconds} seconds")
    print("=" * 60)
    
    # Measure each node in parallel
    tasks = [measure_node_tps(url, duration_seconds) for url in node_urls]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    # Filter successful results
    successful_results = [r for r in results if isinstance(r, dict)]
    failed_results = [r for r in results if isinstance(r, Exception)]
    
    if failed_results:
        print(f"\n⚠️ Failed to measure {len(failed_results)} nodes:")
        for e in failed_results:
            print(f"   Error: {e}")
    
    if not successful_results:
        print("❌ No successful measurements")
        return {}
    
    # Calculate aggregate metrics
    tps_values = [r["tps"] for r in successful_results]
    total_tps = sum(tps_values)
    avg_tps = statistics.mean(tps_values) if tps_values else 0
    median_tps = statistics.median(tps_values) if tps_values else 0
    min_tps = min(tps_values) if tps_values else 0
    max_tps = max(tps_values) if tps_values else 0
    
    aggregate_result = {
        "num_nodes": len(successful_results),
        "duration_seconds": duration_seconds,
        "total_tps": total_tps,
        "avg_tps": avg_tps,
        "median_tps": median_tps,
        "min_tps": min_tps,
        "max_tps": max_tps,
        "node_results": successful_results,
        "timestamp": time.time()
    }
    
    print("\n" + "=" * 60)
    print("📊 AGGREGATE TPS METRICS")
    print("=" * 60)
    print(f"   Nodes measured: {aggregate_result['num_nodes']}")
    print(f"   Total TPS: {total_tps:.4f} cycles/second")
    print(f"   Average TPS: {avg_tps:.4f} cycles/second")
    print(f"   Median TPS: {median_tps:.4f} cycles/second")
    print(f"   Min TPS: {min_tps:.4f} cycles/second")
    print(f"   Max TPS: {max_tps:.4f} cycles/second")
    print("\nPer-node breakdown:")
    for r in successful_results:
        print(f"   {r['node_id']}: {r['tps']:.4f} TPS")
    
    return aggregate_result

async def main():
    parser = argparse.ArgumentParser(description='Measure real TPS from monitoring nodes')
    parser.add_argument('--nodes', nargs='+', default=['http://localhost:8005'],
                       help='Node URLs to measure (default: http://localhost:8005)')
    parser.add_argument('--duration', type=int, default=60,
                       help='Measurement duration in seconds (default: 60)')
    args = parser.parse_args()
    
    if len(args.nodes) == 1:
        # Single node measurement
        result = await measure_node_tps(args.nodes[0], args.duration)
    else:
        # Multi-node measurement
        result = await measure_multi_node_tps(args.nodes, args.duration)
    
    # Save results to file
    import json
    output_file = "tps_measurement_results.json"
    with open(output_file, 'w') as f:
        json.dump(result, f, indent=2)
    print(f"\n💾 Results saved to: {output_file}")

if __name__ == "__main__":
    asyncio.run(main())
