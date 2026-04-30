#!/usr/bin/env python3
"""
attack_simulation.py

Simulate various attacks on the decentralized monitoring system to test robustness
"""

import asyncio
import time
import json
import random
from typing import Dict, List, Optional
import logging

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class AttackSimulator:
    """Simulate various attack scenarios on the monitoring system"""
    
    def __init__(self, honest_nodes: List[str], malicious_nodes: List[str]):
        """
        Initialize attack simulator
        
        Args:
            honest_nodes: List of honest node IDs
            malicious_nodes: List of malicious node IDs
        """
        self.honest_nodes = honest_nodes
        self.malicious_nodes = malicious_nodes
        self.all_nodes = honest_nodes + malicious_nodes
        
    async def simulate_malicious_reports(self, epoch_id: int, peer_client) -> Dict:
        """
        Simulate malicious nodes sending fake monitoring reports
        
        Args:
            epoch_id: Current epoch
            peer_client: Peer client instance
            
        Returns:
            Attack results
        """
        logger.info(f"Simulating malicious reports for epoch {epoch_id}")
        
        results = {
            'malicious_reports_sent': 0,
            'honest_reports_sent': 0,
            'attack_detected': False
        }
        
        # Malicious nodes send false reports (claiming honest sites are down)
        for node_id in self.malicious_nodes:
            # Create fake report claiming a popular site is down
            fake_report = {
                'node_address': node_id,
                'url': 'https://google.com',
                'is_reachable': False,  # Lie - say it's not reachable
                'ssl_valid': False,     # Lie - say SSL is invalid
                'response_ms': 9999,     # Lie - say very slow
                'status_code': 500,      # Lie - say server error
                'epoch_id': epoch_id,
                'timestamp': time.time(),
                'signature': f'fake_signature_{node_id}_{epoch_id}'  # Fake signature
            }
            
            # Send fake report to peers
            try:
                await peer_client.broadcast_message(
                    'monitoring_result',
                    fake_report,
                    ttl=2
                )
                results['malicious_reports_sent'] += 1
                logger.info(f"Malicious node {node_id} sent fake report")
            except Exception as e:
                logger.error(f"Failed to send fake report from {node_id}: {e}")
        
        # Honest nodes send real reports
        for node_id in self.honest_nodes[:3]:  # Simulate 3 honest nodes
            real_report = {
                'node_address': node_id,
                'url': 'https://google.com',
                'is_reachable': True,   # Truthful - site is reachable
                'ssl_valid': True,      # Truthful - SSL is valid
                'response_ms': 150,      # Reasonable response time
                'status_code': 200,     # Success
                'epoch_id': epoch_id,
                'timestamp': time.time(),
                'signature': f'real_signature_{node_id}_{epoch_id}'
            }
            
            try:
                await peer_client.broadcast_message(
                    'monitoring_result',
                    real_report,
                    ttl=2
                )
                results['honest_reports_sent'] += 1
                logger.info(f"Honest node {node_id} sent real report")
            except Exception as e:
                logger.error(f"Failed to send real report from {node_id}: {e}")
        
        # Check if attack was detected (would need access to epoch_manager)
        # This is a placeholder - in real implementation, check consensus results
        results['attack_detected'] = results['malicious_reports_sent'] > results['honest_reports_sent']
        
        return results
    
    async def simulate_sybil_attack(self, epoch_id: int, peer_client) -> Dict:
        """
        Simulate Sybil attack - many fake nodes trying to influence consensus
        
        Args:
            epoch_id: Current epoch
            peer_client: Peer client instance
            
        Returns:
            Attack results
        """
        logger.info(f"Simulating Sybil attack for epoch {epoch_id}")
        
        results = {
            'sybil_nodes_created': 0,
            'reports_sent': 0,
            'attack_successful': False
        }
        
        # Create 10 fake Sybil nodes
        sybil_nodes = []
        for i in range(10):
            sybil_id = f"sybil_node_{i}_{epoch_id}"
            sybil_nodes.append(sybil_id)
            
            # Add Sybil node to peer list (in real attack, they'd connect directly)
            await peer_client.add_peer(sybil_id, "localhost", 9000 + i)
            results['sybil_nodes_created'] += 1
        
        # All Sybil nodes send coordinated malicious reports
        for sybil_id in sybil_nodes:
            malicious_report = {
                'node_address': sybil_id,
                'url': 'https://github.com',
                'is_reachable': False,  # Coordinated lie
                'ssl_valid': False,
                'response_ms': 9999,
                'status_code': 500,
                'epoch_id': epoch_id,
                'timestamp': time.time(),
                'signature': f'sybil_signature_{sybil_id}_{epoch_id}'
            }
            
            try:
                await peer_client.broadcast_message(
                    'monitoring_result',
                    malicious_report,
                    ttl=2
                )
                results['reports_sent'] += 1
            except Exception as e:
                logger.error(f"Sybil node {sybil_id} failed to send report: {e}")
        
        # Attack is successful if Sybil nodes outnumber honest nodes
        results['attack_successful'] = len(sybil_nodes) > len(self.honest_nodes)
        
        logger.info(f"Sybil attack: {results['sybil_nodes_created']} nodes, {results['reports_sent']} reports")
        
        return results
    
    async def simulate_delayed_reports(self, epoch_id: int, peer_client) -> Dict:
        """
        Simulate delayed reports to test timeout handling
        
        Args:
            epoch_id: Current epoch
            peer_client: Peer client instance
            
        Returns:
            Attack results
        """
        logger.info(f"Simulating delayed reports for epoch {epoch_id}")
        
        results = {
            'delayed_reports': 0,
            'timed_out_reports': 0,
            'consensus_affected': False
        }
        
        # Send some reports immediately
        for node_id in self.honest_nodes[:2]:
            report = {
                'node_address': node_id,
                'url': 'https://stackoverflow.com',
                'is_reachable': True,
                'ssl_valid': True,
                'response_ms': 200,
                'status_code': 200,
                'epoch_id': epoch_id,
                'timestamp': time.time(),
                'signature': f'immediate_{node_id}_{epoch_id}'
            }
            
            try:
                await peer_client.broadcast_message('monitoring_result', report)
            except Exception as e:
                logger.error(f"Failed to send immediate report from {node_id}: {e}")
        
        # Delay some reports beyond consensus timeout
        await asyncio.sleep(6)  # Wait longer than consensus_timeout (5s)
        
        for node_id in self.malicious_nodes[:2]:
            delayed_report = {
                'node_address': node_id,
                'url': 'https://stackoverflow.com',
                'is_reachable': False,  # Contradicting report
                'ssl_valid': False,
                'response_ms': 5000,
                'status_code': 404,
                'epoch_id': epoch_id,
                'timestamp': time.time(),
                'signature': f'delayed_{node_id}_{epoch_id}'
            }
            
            try:
                await peer_client.broadcast_message('monitoring_result', delayed_report)
                results['delayed_reports'] += 1
                logger.info(f"Delayed report sent from {node_id}")
            except Exception as e:
                results['timed_out_reports'] += 1
                logger.error(f"Delayed report from {node_id} failed: {e}")
        
        # Check if consensus was affected (would need epoch_manager access)
        results['consensus_affected'] = results['delayed_reports'] > 0
        
        return results
    
    async def simulate_signature_forgery(self, epoch_id: int, peer_client) -> Dict:
        """
        Simulate attempts to forge signatures on reports
        
        Args:
            epoch_id: Current epoch
            peer_client: Peer client instance
            
        Returns:
            Attack results
        """
        logger.info(f"Simulating signature forgery for epoch {epoch_id}")
        
        results = {
            'forged_reports': 0,
            'rejected_reports': 0,
            'attack_successful': False
        }
        
        # Try to forge signatures for honest nodes
        for node_id in self.honest_nodes[:3]:
            # Create report with forged signature
            forged_report = {
                'node_address': node_id,  # Impersonate honest node
                'url': 'https://reddit.com',
                'is_reachable': False,    # Lie about site status
                'ssl_valid': False,
                'response_ms': 9999,
                'status_code': 500,
                'epoch_id': epoch_id,
                'timestamp': time.time(),
                'signature': f'FORGED_SIGNATURE_{node_id}_{epoch_id}',  # Obvious forgery
                'report_hash': f'fake_hash_{node_id}_{epoch_id}'
            }
            
            try:
                await peer_client.broadcast_message('monitoring_result', forged_report)
                results['forged_reports'] += 1
                logger.warning(f"Forged report sent impersonating {node_id}")
            except Exception as e:
                results['rejected_reports'] += 1
                logger.info(f"Forged report from {node_id} was rejected: {e}")
        
        # Attack is successful if any forged reports were accepted
        results['attack_successful'] = results['forged_reports'] > 0
        
        return results
    
    async def run_full_attack_suite(self, peer_client, num_epochs: int = 5) -> Dict:
        """
        Run all attack simulations for multiple epochs
        
        Args:
            peer_client: Peer client instance
            num_epochs: Number of epochs to simulate
            
        Returns:
            Complete attack results
        """
        logger.info(f"Starting full attack suite for {num_epochs} epochs")
        
        all_results = {
            'malicious_reports': [],
            'sybil_attacks': [],
            'delayed_reports': [],
            'signature_forgery': [],
            'summary': {}
        }
        
        for epoch in range(num_epochs):
            epoch_id = int(time.time()) + epoch
            
            logger.info(f"=== Epoch {epoch_id} Attack Simulation ===")
            
            # Run each attack type
            malicious_result = await self.simulate_malicious_reports(epoch_id, peer_client)
            all_results['malicious_reports'].append(malicious_result)
            
            sybil_result = await self.simulate_sybil_attack(epoch_id, peer_client)
            all_results['sybil_attacks'].append(sybil_result)
            
            delayed_result = await self.simulate_delayed_reports(epoch_id, peer_client)
            all_results['delayed_reports'].append(delayed_result)
            
            forged_result = await self.simulate_signature_forgery(epoch_id, peer_client)
            all_results['signature_forgery'].append(forged_result)
            
            # Wait between epochs
            await asyncio.sleep(2)
        
        # Calculate summary statistics
        all_results['summary'] = {
            'total_malicious_reports': sum(r['malicious_reports_sent'] for r in all_results['malicious_reports']),
            'total_sybil_nodes': sum(r['sybil_nodes_created'] for r in all_results['sybil_attacks']),
            'total_delayed_reports': sum(r['delayed_reports'] for r in all_results['delayed_reports']),
            'total_forged_reports': sum(r['forged_reports'] for r in all_results['signature_forgery']),
            'attacks_detected': sum(1 for r in all_results['malicious_reports'] if r['attack_detected']),
            'sybil_attacks_successful': sum(1 for r in all_results['sybil_attacks'] if r['attack_successful'])
        }
        
        logger.info("=== Attack Simulation Complete ===")
        logger.info(f"Summary: {json.dumps(all_results['summary'], indent=2)}")
        
        return all_results


async def main():
    """Main function to run attack simulations"""
    # Define test nodes
    honest_nodes = ['node_A', 'node_B', 'node_C', 'node_D']
    malicious_nodes = ['attacker_X', 'attacker_Y']
    
    # Create simulator
    simulator = AttackSimulator(honest_nodes, malicious_nodes)
    
    # Create a mock peer client (in real usage, this would be the actual peer client)
    class MockPeerClient:
        async def broadcast_message(self, message_type, data, ttl=2):
            logger.info(f"Mock broadcast: {message_type} - {data.get('node_address', 'unknown')}")
            await asyncio.sleep(0.1)  # Simulate network delay
        
        async def add_peer(self, node_id, host, port):
            logger.info(f"Mock add peer: {node_id} at {host}:{port}")
    
    mock_client = MockPeerClient()
    
    # Run attack simulations
    results = await simulator.run_full_attack_suite(mock_client, num_epochs=3)
    
    # Print results
    print("\n=== ATTACK SIMULATION RESULTS ===")
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
