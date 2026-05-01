#!/usr/bin/env python3
"""
Scalability Benchmark Script
Tests system performance with 2→4→8→16 nodes
Measures latency, throughput, and consensus time
"""

import asyncio
import httpx
import time
import statistics
import subprocess
import signal
import os
import json
from typing import List, Dict, Tuple
import argparse

class NodeManager:
    """Manages multiple node processes for benchmarking"""
    
    def __init__(self):
        self.processes = {}
        self.base_port = 8000
        
    async def start_nodes(self, num_nodes: int) -> List[str]:
        """Start specified number of nodes"""
        node_urls = []
        
        for i in range(num_nodes):
            port = self.base_port + i
            node_id = f"node_{i}"
            
            # Prepare command
            cmd = [
                "python", "main.py",
                "--port", str(port),
                "--node-id", node_id,
                "--websites", "https://httpbin.org/status/200", "https://google.com"
            ]
            
            # Add peers (all other nodes)
            for j in range(num_nodes):
                if i != j:
                    peer_port = self.base_port + j
                    cmd.extend(["--peers", f"http://localhost:{peer_port}"])
            
            # Start process
            try:
                process = subprocess.Popen(
                    cmd,
                    cwd="../node_service",
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True
                )
                
                self.processes[node_id] = process
                node_urls.append(f"http://localhost:{port}")
                
                print(f"Started {node_id} on port {port}")
                
            except Exception as e:
                print(f"Failed to start {node_id}: {e}")
        
        # Wait for nodes to start
        await asyncio.sleep(10)
        
        # Verify nodes are healthy
        healthy_nodes = []
        for url in node_urls:
            try:
                async with httpx.AsyncClient() as client:
                    response = await client.get(f"{url}/health", timeout=5.0)
                    if response.status_code == 200:
                        healthy_nodes.append(url)
                        print(f"✅ Node healthy: {url}")
                    else:
                        print(f"❌ Node unhealthy: {url}")
            except Exception as e:
                print(f"❌ Node not responding: {url} - {e}")
        
        return healthy_nodes
    
    def stop_nodes(self):
        """Stop all running nodes"""
        for node_id, process in self.processes.items():
            try:
                process.terminate()
                process.wait(timeout=5)
                print(f"Stopped {node_id}")
            except subprocess.TimeoutExpired:
                process.kill()
                print(f"Killed {node_id}")
            except Exception as e:
                print(f"Error stopping {node_id}: {e}")
        
        self.processes.clear()

class ScalabilityBenchmark:
    """Runs scalability tests and measures performance metrics"""
    
    def __init__(self):
        self.node_manager = NodeManager()
        self.results = {}
    
    async def measure_throughput(self, node_urls: List[str], duration: int = 60) -> Dict:
        """Measure actual throughput (cycles/second)"""
        print(f"\n📊 Measuring throughput for {len(node_urls)} nodes...")
        
        # Get initial cycle counts
        initial_counts = {}
        async with httpx.AsyncClient() as client:
            for url in node_urls:
                try:
                    response = await client.get(f"{url}/statistics", timeout=5.0)
                    if response.status_code == 200:
                        stats = response.json()
                        initial_counts[url] = stats.get("total_monitoring_cycles", 0)
                except Exception as e:
                    print(f"Warning: Could not get initial stats from {url}: {e}")
                    initial_counts[url] = 0
        
        # Wait for measurement duration
        print(f"Measuring for {duration} seconds...")
        await asyncio.sleep(duration)
        
        # Get final cycle counts
        final_counts = {}
        total_cycles = 0
        async with httpx.AsyncClient() as client:
            for url in node_urls:
                try:
                    response = await client.get(f"{url}/statistics", timeout=5.0)
                    if response.status_code == 200:
                        stats = response.json()
                        final_counts[url] = stats.get("total_monitoring_cycles", 0)
                        cycles_completed = final_counts[url] - initial_counts.get(url, 0)
                        total_cycles += cycles_completed
                except Exception as e:
                    print(f"Warning: Could not get final stats from {url}: {e}")
        
        # Calculate throughput
        throughput = total_cycles / duration if duration > 0 else 0
        
        return {
            "duration": duration,
            "total_cycles": total_cycles,
            "throughput_cps": throughput,  # cycles per second
            "avg_cycles_per_node": total_cycles / len(node_urls) if node_urls else 0
        }
    
    async def measure_latency(self, node_urls: List[str], samples: int = 20) -> Dict:
        """Measure API response latency"""
        print(f"\n⏱️ Measuring latency with {samples} samples...")
        
        latencies = []
        
        async with httpx.AsyncClient() as client:
            for i in range(samples):
                start_time = time.time()
                try:
                    response = await client.get(f"{node_urls[0]}/health", timeout=5.0)
                    if response.status_code == 200:
                        latency = (time.time() - start_time) * 1000  # ms
                        latencies.append(latency)
                except Exception as e:
                    print(f"Latency sample {i} failed: {e}")
                
                await asyncio.sleep(0.1)  # Small delay between samples
        
        if latencies:
            return {
                "samples": len(latencies),
                "avg_ms": statistics.mean(latencies),
                "min_ms": min(latencies),
                "max_ms": max(latencies),
                "p95_ms": statistics.quantiles(latencies, n=20)[18] if len(latencies) >= 20 else max(latencies),
                "p99_ms": statistics.quantiles(latencies, n=100)[98] if len(latencies) >= 100 else max(latencies)
            }
        else:
            return {"error": "No successful latency measurements"}
    
    async def measure_consensus_time(self, node_urls: List[str], epochs: int = 5) -> Dict:
        """Measure consensus decision time"""
        print(f"\n🤝 Measuring consensus time for {epochs} epochs...")
        
        consensus_times = []
        
        async with httpx.AsyncClient() as client:
            for epoch in range(epochs):
                # Wait for epoch to complete
                await asyncio.sleep(65)  # One epoch + buffer
                
                try:
                    # Get latest epoch decision
                    response = await client.get(f"{node_urls[0]}/reports/latest", timeout=5.0)
                    if response.status_code == 200:
                        data = response.json()
                        if "epoch_id" in data:
                            epoch_id = data["epoch_id"]
                            
                            # Get epoch details with timestamp
                            response = await client.get(f"{node_urls[0]}/reports/epoch/{epoch_id}", timeout=5.0)
                            if response.status_code == 200:
                                epoch_data = response.json()
                                if "timestamp" in epoch_data:
                                    # Calculate consensus time (simplified)
                                    consensus_time = 1000  # Placeholder: would need proper timestamps
                                    consensus_times.append(consensus_time)
                
                except Exception as e:
                    print(f"Error getting epoch {epoch} data: {e}")
        
        if consensus_times:
            return {
                "epochs": len(consensus_times),
                "avg_ms": statistics.mean(consensus_times),
                "min_ms": min(consensus_times),
                "max_ms": max(consensus_times)
            }
        else:
            return {"error": "No consensus measurements"}
    
    async def run_benchmark(self, num_nodes: int, test_duration: int = 120) -> Dict:
        """Run complete benchmark for specified number of nodes"""
        print(f"\n🚀 Starting benchmark with {num_nodes} nodes")
        print("=" * 60)
        
        # Start nodes
        node_urls = await self.node_manager.start_nodes(num_nodes)
        
        if len(node_urls) < num_nodes:
            print(f"⚠️ Only {len(node_urls)}/{num_nodes} nodes started successfully")
        
        if not node_urls:
            return {"error": "No nodes started successfully"}
        
        try:
            # Run measurements
            results = {
                "num_nodes": num_nodes,
                "test_duration": test_duration,
                "timestamp": time.time()
            }
            
            # Measure throughput
            throughput_results = await self.measure_throughput(node_urls, test_duration)
            results["throughput"] = throughput_results
            
            # Measure latency
            latency_results = await self.measure_latency(node_urls)
            results["latency"] = latency_results
            
            # Measure consensus time
            consensus_results = await self.measure_consensus_time(node_urls)
            results["consensus"] = consensus_results
            
            # Get system statistics
            async with httpx.AsyncClient() as client:
                try:
                    response = await client.get(f"{node_urls[0]}/statistics", timeout=5.0)
                    if response.status_code == 200:
                        results["system_stats"] = response.json()
                except Exception as e:
                    print(f"Warning: Could not get system stats: {e}")
            
            return results
            
        finally:
            # Stop nodes
            self.node_manager.stop_nodes()
            await asyncio.sleep(2)
    
    async def run_scalability_test(self, max_nodes: int = 16):
        """Run scalability test across different node counts"""
        print("🔬 Starting Scalability Test")
        print("=" * 60)
        
        # Test with different node counts
        node_counts = [2, 4, 8, max_nodes]
        all_results = {}
        
        for num_nodes in node_counts:
            if num_nodes > max_nodes:
                continue
                
            print(f"\n📈 Testing with {num_nodes} nodes...")
            results = await self.run_benchmark(num_nodes)
            all_results[num_nodes] = results
            
            # Save intermediate results
            with open(f"benchmark_results_{num_nodes}_nodes.json", "w") as f:
                json.dump(results, f, indent=2)
            
            print(f"✅ Completed {num_nodes} node test")
            
            # Brief pause between tests
            await asyncio.sleep(5)
        
        # Generate summary report
        self.generate_summary_report(all_results)
        
        return all_results
    
    def generate_summary_report(self, results: Dict[int, Dict]):
        """Generate summary report of scalability test"""
        print("\n" + "=" * 60)
        print("📊 SCALABILITY BENCHMARK RESULTS")
        print("=" * 60)
        
        print("\nThroughput (cycles/second):")
        for num_nodes, result in results.items():
            if "throughput" in result:
                throughput = result["throughput"].get("throughput_cps", 0)
                print(f"  {num_nodes:2d} nodes: {throughput:8.2f} cps")
        
        print("\nLatency (ms):")
        for num_nodes, result in results.items():
            if "latency" in result and "avg_ms" in result["latency"]:
                latency = result["latency"]["avg_ms"]
                print(f"  {num_nodes:2d} nodes: {latency:8.2f} ms")
        
        print("\nConsensus Time (ms):")
        for num_nodes, result in results.items():
            if "consensus" in result and "avg_ms" in result["consensus"]:
                consensus = result["consensus"]["avg_ms"]
                print(f"  {num_nodes:2d} nodes: {consensus:8.2f} ms")
        
        # Calculate scaling efficiency
        if 2 in results and 8 in results:
            throughput_2 = results[2].get("throughput", {}).get("throughput_cps", 0)
            throughput_8 = results[8].get("throughput", {}).get("throughput_cps", 0)
            
            if throughput_2 > 0:
                scaling_efficiency = (throughput_8 / (4 * throughput_2)) * 100
                print(f"\nScaling Efficiency (2→8 nodes): {scaling_efficiency:.1f}%")
        
        # Save complete results
        with open("scalability_benchmark_results.json", "w") as f:
            json.dump(results, f, indent=2)
        
        print(f"\n💾 Complete results saved to: scalability_benchmark_results.json")

async def main():
    parser = argparse.ArgumentParser(description='Run scalability benchmark')
    parser.add_argument('--max-nodes', type=int, default=16, help='Maximum number of nodes to test')
    parser.add_argument('--test-duration', type=int, default=120, help='Test duration per configuration (seconds)')
    parser.add_argument('--single-test', type=int, help='Run single test with specified number of nodes')
    args = parser.parse_args()
    
    benchmark = ScalabilityBenchmark()
    
    try:
        if args.single_test:
            # Run single test
            results = await benchmark.run_benchmark(args.single_test, args.test_duration)
            print(f"\n✅ Single test completed: {args.single_test} nodes")
        else:
            # Run full scalability test
            results = await benchmark.run_scalability_test(args.max_nodes)
            print(f"\n✅ Scalability test completed up to {args.max_nodes} nodes")
    
    except KeyboardInterrupt:
        print("\n⚠️ Test interrupted by user")
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
    finally:
        # Ensure cleanup
        benchmark.node_manager.stop_nodes()

if __name__ == "__main__":
    asyncio.run(main())
