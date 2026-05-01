#!/usr/bin/env python3
"""
Comprehensive test to verify ML is working correctly in the system
"""

import sys
import os
import time
import json
sys.path.append(os.path.join(os.path.dirname(__file__), 'node_service', 'src'))

from ml_consensus_engine import EnhancedMLConsensusEngine
import numpy as np

def test_ml_models_loading():
    """Test 1: Check if ML models load correctly"""
    print("=" * 60)
    print("TEST 1: ML Models Loading")
    print("=" * 60)
    
    engine = EnhancedMLConsensusEngine("test_node")
    
    try:
        engine.load_enhanced_models()
        
        if engine.models_loaded:
            print("✅ ML models loaded successfully")
            print(f"   RF feature columns: {len(engine.rf_feature_cols) if hasattr(engine, 'rf_feature_cols') else 'Unknown'}")
            print(f"   Behavioral columns: {len(engine.behavioral_cols) if hasattr(engine, 'behavioral_cols') else 'Unknown'}")
            print(f"   Scaler fitted: {engine.scaler_fitted if hasattr(engine, 'scaler_fitted') else 'Unknown'}")
            return True
        else:
            print("❌ ML models failed to load")
            return False
    except Exception as e:
        print(f"❌ Exception loading models: {e}")
        return False

def test_ml_feature_extraction():
    """Test 2: Check if ML feature extraction works"""
    print("\n" + "=" * 60)
    print("TEST 2: ML Feature Extraction")
    print("=" * 60)
    
    engine = EnhancedMLConsensusEngine("test_node")
    
    # Create test reports
    test_reports = [
        {
            "node_address": "node_honest",
            "url": "https://google.com",
            "response_ms": 100,
            "is_reachable": True,
            "ssl_valid": True,
            "timestamp": time.time()
        },
        {
            "node_address": "node_honest", 
            "url": "https://github.com",
            "response_ms": 150,
            "is_reachable": True,
            "ssl_valid": True,
            "timestamp": time.time() + 1
        }
    ]
    
    try:
        features = engine._extract_features_from_reports(test_reports)
        
        print("✅ Feature extraction successful")
        print(f"   Extracted features: {list(features.keys())}")
        
        # Check for required 11 features
        required_features = [
            'accuracy', 'false_positive_rate', 'false_negative_rate', 'avg_rt_error',
            'peer_agreement_rate', 'report_consistency', 'sudden_change_score',
            'ssl_accuracy', 'uptime_deviation', 'rt_consistency', 'itt_jitter'
        ]
        
        missing_features = [f for f in required_features if f not in features]
        if missing_features:
            print(f"⚠️ Missing features: {missing_features}")
            return False
        else:
            print("✅ All 11 required features present")
            return True
            
    except Exception as e:
        print(f"❌ Exception in feature extraction: {e}")
        return False

def test_ml_reputation_calculation():
    """Test 3: Check if ML reputation calculation works"""
    print("\n" + "=" * 60)
    print("TEST 3: ML Reputation Calculation")
    print("=" * 60)
    
    engine = EnhancedMLConsensusEngine("test_node")
    
    # Try to load models first
    try:
        engine.load_enhanced_models()
    except:
        print("⚠️ Models not loaded, testing fallback calculation")
    
    # Create test features for honest and malicious nodes
    honest_features = {
        'accuracy': 0.95,
        'false_positive_rate': 0.05,
        'false_negative_rate': 0.05,
        'avg_rt_error': 0.1,
        'peer_agreement_rate': 0.9,
        'report_consistency': 0.9,
        'sudden_change_score': 0.1,
        'ssl_accuracy': 0.95,
        'uptime_deviation': 0.1,
        'rt_consistency': 0.9,
        'itt_jitter': 0.1
    }
    
    malicious_features = {
        'accuracy': 0.1,
        'false_positive_rate': 0.8,
        'false_negative_rate': 0.8,
        'avg_rt_error': 0.9,
        'peer_agreement_rate': 0.3,
        'report_consistency': 0.3,
        'sudden_change_score': 0.7,
        'ssl_accuracy': 0.2,
        'uptime_deviation': 0.5,
        'rt_consistency': 0.3,
        'itt_jitter': 0.4
    }
    
    try:
        # Test honest node
        honest_rep = engine.calculate_enhanced_reputation(honest_features)
        print(f"✅ Honest node reputation: {honest_rep:.4f}")
        
        # Test malicious node  
        malicious_rep = engine.calculate_enhanced_reputation(malicious_features)
        print(f"✅ Malicious node reputation: {malicious_rep:.4f}")
        
        # Check if reputations are different and reasonable
        if honest_rep > malicious_rep:
            print("✅ ML correctly distinguishes honest vs malicious")
        else:
            print("❌ ML failed to distinguish honest vs malicious")
            return False
            
        # Check if reputations are in reasonable range
        if 0.0 <= honest_rep <= 1.0 and 0.0 <= malicious_rep <= 1.0:
            print("✅ Reputations in valid range [0,1]")
        else:
            print("❌ Reputations out of valid range")
            return False
            
        return True
        
    except Exception as e:
        print(f"❌ Exception in reputation calculation: {e}")
        return False

def test_ml_mitigation_policy():
    """Test 4: Check if ML mitigation policy works"""
    print("\n" + "=" * 60)
    print("TEST 4: ML Mitigation Policy")
    print("=" * 60)
    
    engine = EnhancedMLConsensusEngine("test_node")
    
    test_reputations = [
        (0.9, "HEALTHY", "PRIMARY"),
        (0.7, "SUSPICIOUS", "MONITORING"), 
        (0.4, "FAULTY", "QUARANTINE"),
        (0.1, "MALICIOUS", "SLASHED")
    ]
    
    try:
        for rep, expected_status, expected_shard in test_reputations:
            decision = engine.apply_mitigation_policy(rep)
            
            if decision.status == expected_status and decision.shard == expected_shard:
                print(f"✅ Reputation {rep:.1f} → {decision.status}/{decision.shard}")
            else:
                print(f"❌ Reputation {rep:.1f}: Expected {expected_status}/{expected_shard}, got {decision.status}/{decision.shard}")
                return False
                
        return True
        
    except Exception as e:
        print(f"❌ Exception in mitigation policy: {e}")
        return False

def test_ml_sharded_consensus():
    """Test 5: Check if ML sharded consensus works"""
    print("\n" + "=" * 60)
    print("TEST 5: ML Sharded Consensus")
    print("=" * 60)
    
    engine = EnhancedMLConsensusEngine("test_node")
    
    # Try to load models
    try:
        engine.load_enhanced_models()
        models_status = "✅ Loaded" if engine.models_loaded else "⚠️ Fallback"
    except:
        models_status = "❌ Failed"
    
    print(f"Model status: {models_status}")
    
    # Create test reports for different node types
    test_reports = [
        {
            "node_address": "node_honest",
            "url": "https://google.com",
            "response_ms": 100,
            "is_reachable": True,
            "ssl_valid": True,
            "timestamp": time.time()
        },
        {
            "node_address": "node_malicious",
            "url": "https://github.com", 
            "response_ms": 5000,
            "is_reachable": False,
            "ssl_valid": False,
            "timestamp": time.time()
        }
    ]
    
    try:
        epoch_id = int(time.time() // 60)
        
        if hasattr(engine, 'process_sharded_consensus'):
            results = engine.process_sharded_consensus(epoch_id, test_reports)
            
            print("✅ Sharded consensus executed")
            print(f"   Engine type: {results.get('engine_type')}")
            print(f"   Processing time: {results.get('processing_time_ms', 0):.2f}ms")
            print(f"   Sharding enabled: {results.get('sharding_enabled')}")
            
            # Check shard distribution
            shard_dist = results.get('shard_distribution', {})
            if shard_dist:
                print(f"   Shard distribution: {shard_dist}")
            
            # Check reputations
            reputations = results.get('reputations', {})
            if reputations:
                print(f"   Calculated reputations: {[(k, f'{v:.3f}') for k, v in reputations.items()]}")
            
            return True
        else:
            print("❌ process_sharded_consensus method not found")
            return False
            
    except Exception as e:
        print(f"❌ Exception in sharded consensus: {e}")
        return False

def main():
    """Run all ML tests"""
    print("🤖 COMPREHENSIVE ML WORKING TEST")
    print("Testing if ML is working correctly in the system...")
    
    tests = [
        ("Models Loading", test_ml_models_loading),
        ("Feature Extraction", test_ml_feature_extraction), 
        ("Reputation Calculation", test_ml_reputation_calculation),
        ("Mitigation Policy", test_ml_mitigation_policy),
        ("Sharded Consensus", test_ml_sharded_consensus)
    ]
    
    results = []
    for test_name, test_func in tests:
        try:
            result = test_func()
            results.append((test_name, result))
        except Exception as e:
            print(f"❌ {test_name} crashed: {e}")
            results.append((test_name, False))
    
    # Summary
    print("\n" + "=" * 60)
    print("ML TEST SUMMARY")
    print("=" * 60)
    
    passed = 0
    total = len(results)
    
    for test_name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status}: {test_name}")
        if result:
            passed += 1
    
    print(f"\nOverall: {passed}/{total} tests passed")
    
    if passed == total:
        print("🎉 ML is working correctly!")
        return True
    else:
        print("⚠️ ML has some issues that need attention")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
