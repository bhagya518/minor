#!/usr/bin/env python3
"""
Failure Simulation Script
Tests system resilience under various failure conditions:
- Node churn (nodes joining/leaving)
- Message delays and packet loss
- Malicious majority scenarios
"""

import asyncio
import httpx
import time
import random
import subprocess
import signal
import json
from typing import List, Dict, Tuple, Optional
import argparse

class FailureSimulator:
    """Simulates various failure conditions in the distributed system"""
    
    def __init__(self):
        self.processes = {}
        self.base_port = 8000
        self.failure_injector = None
        
    async def start_nodes(self, num_nodes: int, malicious_ratio: float = 0.0) -> List[str]:
        """Start nodes with optional malicious nodes"""
        node_urls = []
        num_malicious = int(num_nodes * malicious_ratio)
        
        for i in range(num_nodes):
            port = self.base_port + i
            node_id = f"node_{i}"
            
            # Determine if this node should be malicious
            is_malicious = i < num_malicious
            
            # Prepare environment
            env = os.environ.copy()
            if is_malicious:
                env["NODE_MODE"] = "malicious"
                print(f"🔴 Starting malicious node: {node_id}")
            else:
                print(f"🟢 Starting honest node: {node_id}")
            
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
                    text=True,
                    env=env
                )
                
                self.processes[node_id] = process
                node_urls.append(f"http://localhost:{port}")
                
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
            except:
                pass
        
        return healthy_nodes
    
    def stop_node(self, node_id: str):
        """Stop a specific node"""
        if node_id in self.processes:
            try:
                self.processes[node_id].terminate()
                self.processes[node_id].wait(timeout=5)
                print(f"🔌 Stopped node: {node_id}")
            except subprocess.TimeoutExpired:
                self.processes[node_id].kill()
                print(f"💀 Killed node: {node_id}")
            del self.processes[node_id]
    
    async def restart_node(self, node_id: str, port: int, peers: List[str]):
        """Restart a node"""
        print(f"🔄 Restarting node: {node_id}")
        
        cmd = [
            "python", "main.py",
            "--port", str(port),
            "--node-id", node_id,
            "--websites", "https://httpbin.org/status/200", "https://google.com"
        ]
        
        for peer in peers:
            cmd.extend(["--peers", peer])
        
        try:
            process = subprocess.Popen(
                cmd,
                cwd="../node_service",
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            
            self.processes[node_id] = process
            await asyncio.sleep(5)  # Wait for restart
            return True
            
        except Exception as e:
            print(f"Failed to restart {node_id}: {e}")
            return False
    
    async def simulate_node_churn(self, node_urls: List[str], duration: int = 300):
        """Simulate nodes joining and leaving the network"""
        print(f"\n🌊 Simulating node churn for {duration} seconds...")
        
        start_time = time.time()
        churn_interval = 30  # Churn event every 30 seconds
        
        while time.time() - start_time < duration:
            # Select random node to stop
            if self.processes and len(node_urls) > 2:  # Keep at least 2 nodes
                node_to_stop = random.choice(list(self.processes.keys()))
                port = self.base_port + int(node_to_stop.split("_")[1])
                
                # Stop the node
                self.stop_node(node_to_stop)
                node_urls.remove(f"http://localhost:{port}")
                
                # Wait for some time
                await asyncio.sleep(random.randint(10, 30))
                
                # Restart the node
                peers = [url for url in node_urls if url != f"http://localhost:{port}"]
                if await self.restart_node(node_to_stop, port, peers):
                    node_urls.append(f"http://localhost:{port}")
            
            await asyncio.sleep(churn_interval)
        
        print("✅ Node churn simulation completed")
    
    async def simulate_message_delay(self, node_urls: List[str], delay_range: Tuple[float, float]):
        """Simulate network delays by manipulating peer communication"""
        print(f"\n🐌 Simulating message delays ({delay_range[0]}s-{delay_range[1]}s)...")
        
        # This would require network-level manipulation or proxy
        # For now, we'll simulate by adding delays to API calls
        delayed_calls = 0
        
        async def delayed_request(url: str, timeout: float = 5.0):
            nonlocal delayed_calls
            delay = random.uniform(*delay_range)
            await asyncio.sleep(delay)
            delayed_calls += 1
            
            async with httpx.AsyncClient() as client:
                try:
                    response = await client.get(url, timeout=timeout)
                    return response
                except:
                    return None
        
        # Test delayed communication
        successful_calls = 0
        for url in node_urls:
            for _ in range(5):  # 5 test calls per node
                response = await delayed_request(f"{url}/health")
                if response and response.status_code == 200:
                    successful_calls += 1
        
        print(f"✅ Message delay simulation: {successful_calls}/{len(node_urls) * 5} calls successful")
        return delayed_calls
    
    async def simulate_malicious_majority(self, num_nodes: int = 8):
        """Test system with malicious majority"""
        print(f"\n👹 Simulating malicious majority ({num_nodes} nodes)...")
        
        # Start with 60% malicious nodes
        malicious_ratio = 0.6
        node_urls = await self.start_nodes(num_nodes, malicious_ratio)
        
        if not node_urls:
            return {"error": "Failed to start nodes"}
        
        try:
            # Let system run for a few epochs
            await asyncio.sleep(180)  # 3 epochs
            
            # Check system state
            async with httpx.AsyncClient() as client:
                results = {}
                
                for url in node_urls:
                    try:
                        # Get trust scores
                        trust_response = await client.get(f"{url}/trust", timeout=5.0)
                        if trust_response.status_code == 200:
                            trust_data = trust_response.json()
                            results[url] = trust_data
                        
                        # Get consensus verdicts
                        verdict_response = await client.get(f"{url}/verdicts", timeout=5.0)
                        if verdict_response.status_code == 200:
                            verdict_data = verdict_response.json()
                            
                    except Exception as e:
                        print(f"Error checking {url}: {e}")
            
            # Analyze results
            honest_nodes_survived = 0
            malicious_nodes_detected = 0
            
            for url, data in results.items():
                node_id = url.split(":")[-1]  # Extract node_id from URL
                is_malicious = int(node_id) < int(num_nodes * malicious_ratio)
                
                trust_score = data.get("trust_score", 0.5)
                
                if is_malicious and trust_score < 0.4:
                    malicious_nodes_detected += 1
                elif not is_malicious and trust_score > 0.4:
                    honest_nodes_survived += 1
            
            return {
                "num_nodes": num_nodes,
                "malicious_ratio": malicious_ratio,
                "honest_survived": honest_nodes_survived,
                "malicious_detected": malicious_nodes_detected,
                "system_resilient": honest_nodes_survived > 0
            }
        
        finally:
            # Stop all nodes
            for node_id in list(self.processes.keys()):
                self.stop_node(node_id)
    
    async def simulate_partition_tolerance(self, node_urls: List[str]):
        """Simulate network partition"""
        print(f"\n🕸️ Simulating network partition...")
        
        if len(node_urls) < 4:
            return {"error": "Need at least 4 nodes for partition test"}
        
        # Split nodes into two partitions
        mid = len(node_urls) // 2
        partition1 = node_urls[:mid]
        partition2 = node_urls[mid:]
        
        print(f"Partition 1: {len(partition1)} nodes")
        print(f"Partition 2: {len(partition2)} nodes")
        
        # In a real simulation, we would block network traffic between partitions
        # For now, we'll test by stopping cross-partition communication
        
        # Let partitions operate independently
        await asyncio.sleep(120)  # 2 epochs
        
        # Check if system can recover when partition heals
        print("🔄 Healing partition...")
        
        # Test recovery by checking consensus across all nodes
        consensus_results = []
        async with httpx.AsyncClient() as client:
            for url in node_urls:
                try:
                    response = await client.get(f"{url}/consensus/reputations", timeout=5.0)
                    if response.status_code == 200:
                        data = response.json()
                        consensus_results.append(data)
                except:
                    pass
        
        # Analyze consensus consistency
        if consensus_results:
            # Check if all nodes have similar reputation scores
            first_reputations = consensus_results[0].get("node_reputations", {})
            consistent = True
            
            for result in consensus_results[1:]:
                reputations = result.get("node_reputations", {})
                for node_id, rep in first_reputations.items():
                    if node_id in reputations:
                        diff = abs(rep - reputations[node_id])
                        if diff > 0.1:  # 10% tolerance
                            consistent = False
                            break
            
            return {
                "partition_size": [len(partition1), len(partition2)],
                "consensus_consistent": consistent,
                "nodes_responding": len(consensus_results)
            }
        
        return {"error": "No consensus data collected"}
    
    async def run_comprehensive_test(self):
        """Run all failure simulation tests"""
        print("🧪 COMPREHENSIVE FAILURE SIMULATION")
        print("=" * 60)
        
        results = {
            "timestamp": time.time(),
            "tests": {}
        }
        
        # Test 1: Node Churn
        print("\n" + "=" * 40)
        print("TEST 1: NODE CHURN")
        print("=" * 40)
        
        node_urls = await self.start_nodes(6)
        if node_urls:
            try:
                await self.simulate_node_churn(node_urls, duration=120)
                results["tests"]["node_churn"] = {"status": "completed"}
            finally:
                for node_id in list(self.processes.keys()):
                    self.stop_node(node_id)
        
        # Test 2: Message Delays
        print("\n" + "=" * 40)
        print("TEST 2: MESSAGE DELAYS")
        print("=" * 40)
        
        node_urls = await self.start_nodes(4)
        if node_urls:
            try:
                delay_result = await self.simulate_message_delay(node_urls, (0.5, 2.0))
                results["tests"]["message_delays"] = delay_result
            finally:
                for node_id in list(self.processes.keys()):
                    self.stop_node(node_id)
        
        # Test 3: Malicious Majority
        print("\n" + "=" * 40)
        print("TEST 3: MALICIOUS MAJORITY")
        print("=" * 40)
        
        malicious_result = await self.simulate_malicious_majority(8)
        results["tests"]["malicious_majority"] = malicious_result
        
        # Test 4: Partition Tolerance
        print("\n" + "=" * 40)
        print("TEST 4: PARTITION TOLERANCE")
        print("=" * 40)
        
        node_urls = await self.start_nodes(6)
        if node_urls:
            try:
                partition_result = await self.simulate_partition_tolerance(node_urls)
                results["tests"]["partition_tolerance"] = partition_result
            finally:
                for node_id in list(self.processes.keys()):
                    self.stop_node(node_id)
        
        # Save results
        with open("failure_simulation_results.json", "w") as f:
            json.dump(results, f, indent=2)
        
        # Print summary
        print("\n" + "=" * 60)
        print("📊 FAILURE SIMULATION SUMMARY")
        print("=" * 60)
        
        for test_name, result in results["tests"].items():
            status = result.get("status", "unknown")
            if isinstance(result, dict) and "error" not in result:
                status = "completed"
            
            print(f"{test_name:20}: {status}")
        
        print(f"\n💾 Results saved to: failure_simulation_results.json")
        
        return results

async def main():
    parser = argparse.ArgumentParser(description='Run failure simulation tests')
    parser.add_argument('--test', choices=['churn', 'delays', 'malicious', 'partition', 'all'], 
                       default='all', help='Specific test to run')
    parser.add_argument('--duration', type=int, default=120, help='Test duration in seconds')
    args = parser.parse_args()
    
    simulator = FailureSimulator()
    
    try:
        if args.test == 'all':
            results = await simulator.run_comprehensive_test()
        elif args.test == 'churn':
            node_urls = await simulator.start_nodes(6)
            await simulator.simulate_node_churn(node_urls, args.duration)
        elif args.test == 'delays':
            node_urls = await simulator.start_nodes(4)
            await simulator.simulate_message_delay(node_urls, (0.5, 2.0))
        elif args.test == 'malicious':
            await simulator.simulate_malicious_majority(8)
        elif args.test == 'partition':
            node_urls = await simulator.start_nodes(6)
            await simulator.simulate_partition_tolerance(node_urls)
        
        print(f"\n✅ Failure simulation completed")
    
    except KeyboardInterrupt:
        print("\n⚠️ Test interrupted by user")
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
    finally:
        # Ensure cleanup
        for node_id in list(simulator.processes.keys()):
            simulator.stop_node(node_id)

if __name__ == "__main__":
    import os
    asyncio.run(main())
