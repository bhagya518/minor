#!/usr/bin/env python3
"""
Test script to verify sharding is working in the ML consensus engine
"""

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), 'node_service', 'src'))

from ml_consensus_engine import EnhancedMLConsensusEngine
import time

def test_sharding():
    print("Testing ML Consensus Engine Sharding...")
    
    # Initialize engine
    engine = EnhancedMLConsensusEngine("test_node")
    
    # Try to load models
    try:
        engine.load_enhanced_models()
        if engine.models_loaded:
            print("✅ ML models loaded successfully")
        else:
            print("⚠️ ML models not loaded, using fallback")
    except Exception as e:
        print(f"❌ Model loading failed: {e}")
    
    # Create test reports for different nodes with different reputations
    test_reports = [
        # High reputation node (should go to PRIMARY)
        {
            "node_address": "node_honest",
            "url": "https://google.com",
            "response_ms": 100,
            "is_reachable": True,
            "ssl_valid": True,
            "timestamp": time.time()
        },
        # Medium reputation node (should go to MONITORING)
        {
            "node_address": "node_suspicious",
            "url": "https://github.com", 
            "response_ms": 500,
            "is_reachable": True,
            "ssl_valid": False,
            "timestamp": time.time()
        },
        # Low reputation node (should go to QUARANTINE)
        {
            "node_address": "node_faulty",
            "url": "https://httpbin.org",
            "response_ms": 2000,
            "is_reachable": False,
            "ssl_valid": False,
            "timestamp": time.time()
        },
        # Malicious node (should go to SLASHED)
        {
            "node_address": "node_malicious",
            "url": "https://example.com",
            "response_ms": 5000,
            "is_reachable": False,
            "ssl_valid": False,
            "timestamp": time.time()
        }
    ]
    
    # Set some initial reputations to test shard assignment
    engine.reputation["node_honest"] = 0.9    # PRIMARY
    engine.reputation["node_suspicious"] = 0.6  # MONITORING  
    engine.reputation["node_faulty"] = 0.3     # QUARANTINE
    engine.reputation["node_malicious"] = 0.1   # SLASHED
    
    print(f"\nInitial reputations: {engine.reputation}")
    
    # Test sharded consensus
    epoch_id = int(time.time() // 60)
    
    print(f"\n🚀 Running sharded consensus for epoch {epoch_id}...")
    
    if hasattr(engine, 'process_sharded_consensus'):
        results = engine.process_sharded_consensus(epoch_id, test_reports)
        
        print(f"\n✅ Sharded consensus completed!")
        print(f"Engine type: {results.get('engine_type')}")
        print(f"Sharding enabled: {results.get('sharding_enabled')}")
        print(f"Processing time: {results.get('processing_time_ms', 0):.2f}ms")
        
        print(f"\n📊 Shard distribution:")
        shard_dist = results.get('shard_distribution', {})
        for shard, count in shard_dist.items():
            print(f"  {shard}: {count} nodes")
        
        print(f"\n🎯 Final reputations:")
        reputations = results.get('reputations', {})
        for node_id, rep in reputations.items():
            mitigation = results.get('mitigation_actions', {}).get(node_id, {})
            shard = mitigation.get('shard', 'UNKNOWN')
            print(f"  {node_id}: {rep:.3f} → {shard}")
        
        print(f"\n🔍 Shard details:")
        shard_details = results.get('shard_details', {})
        for shard_id, details in shard_details.items():
            evaluated = details.get('evaluated', 0)
            status = details.get('status', 'unknown')
            print(f"  {shard_id}: {evaluated} nodes evaluated ({status})")
        
        return True
    else:
        print("❌ process_sharded_consensus method not found!")
        return False

if __name__ == "__main__":
    success = test_sharding()
    if success:
        print("\n✅ Sharding test completed successfully!")
    else:
        print("\n❌ Sharding test failed!")
        sys.exit(1)
