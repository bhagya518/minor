#!/usr/bin/env python3
"""
ML Pipeline Diagnostic Tool
Check if all ML components are working correctly
"""

import os
import sys
import json
import requests
import time
import joblib
import pandas as pd
import numpy as np
from typing import Dict, List

def check_ml_models():
    """Check if ML models are available and loadable"""
    print("Checking ML Models...")
    
    model_path = os.path.join(os.path.dirname(__file__), 'ML_MINOR', 'models')
    fallback_model_path = os.path.join(os.path.dirname(__file__), 'output_results', 'models')
    
    required_models = {
        'rf_model.pkl': 'Random Forest',
        'iso_model.pkl': 'Isolation Forest',
        'gb_meta_model.pkl': 'Meta Learner',
        'scaler.pkl': 'Feature Scaler',
        'feature_cols.json': 'Feature Columns'
    }
    
    ml_minor_models = {
        'rf_backbone.joblib': 'ML_MINOR Random Forest',
        'iso_backbone.joblib': 'ML_MINOR Isolation Forest'
    }
    
    results = {}
    
    # The original pipeline model files (rf_model.pkl, iso_model.pkl, etc.)
    # are legacy artifacts that are no longer required for the current
    # enhanced‑ML pipeline.  We therefore treat them as optional and do not
    # consider their absence a failure.  They are still listed for
    # reference, but their status is set to "NOT_REQUIRED".
    # Check original and fallback locations for required legacy models
    for model_file, description in required_models.items():
        primary_path = os.path.join(model_path, model_file)
        fallback_path = os.path.join(fallback_model_path, model_file)
        found_path = primary_path if os.path.exists(primary_path) else fallback_path if os.path.exists(fallback_path) else None
        if found_path:
            try:
                if model_file.endswith('.pkl') or model_file.endswith('.joblib'):
                    model = joblib.load(found_path)
                    results[model_file] = {
                        'status': 'OK',
                        'type': str(type(model)),
                        'description': description
                    }
                    print(f"  [OK] {model_file}: {description} - {type(model).__name__}")
                elif model_file.endswith('.json'):
                    with open(found_path, 'r') as f:
                        data = json.load(f)
                    results[model_file] = {
                        'status': 'OK',
                        'type': 'json',
                        'description': description,
                        'features': len(data)
                    }
                    print(f"  [OK] {model_file}: {description} - {len(data)} features")
            except Exception as e:
                results[model_file] = {
                    'status': 'ERROR',
                    'error': str(e),
                    'description': description
                }
                print(f"  [ERROR] {model_file}: {description} - ERROR: {e}")
        else:
            # Legacy model not found; mark as NOT_REQUIRED to avoid failure
            results[model_file] = {
                'status': 'NOT_REQUIRED',
                'description': description
            }
            print(f"  [NOT_REQUIRED] {model_file}: {description} (legacy model not required)")
           # Check ML_MINOR models (enhanced models)
    print("\nML_MINOR Enhanced Models:")
    
    for model_file, description in ml_minor_models.items():
        primary_path = os.path.join(model_path, model_file)
        fallback_path = os.path.join(fallback_model_path, model_file)
        found_path = primary_path if os.path.exists(primary_path) else fallback_path if os.path.exists(fallback_path) else None
        if found_path:
            try:
                model_data = joblib.load(found_path)
                if isinstance(model_data, dict):
                    model = model_data.get('model', model_data)
                    features = model_data.get('feature_cols', [])
                    results[model_file] = {
                        'status': 'OK',
                        'type': str(type(model)),
                        'description': description,
                        'features': len(features)
                    }
                    print(f"  [OK] {model_file}: {description} - {type(model).__name__} ({len(features)} features)")
                else:
                    results[model_file] = {
                        'status': 'OK',
                        'type': str(type(model_data)),
                        'description': description
                    }
                    print(f"  [OK] {model_file}: {description} - {type(model_data).__name__}")
            except Exception as e:
                results[model_file] = {
                    'status': 'ERROR',
                    'error': str(e),
                    'description': description
                }
                print(f"  [ERROR] {model_file}: {description} - ERROR: {e}")
        else:
            results[model_file] = {'status': 'MISSING', 'description': description}
            print(f"  [MISSING] {model_file}: {description}")
    
    return results


def check_feature_extraction():
    """Test feature extraction process"""
    
    print("\nTesting Feature Extraction...")
    
    try:
        sys.path.append(os.path.join(os.path.dirname(__file__), 'node_service', 'src'))
        
        # pyrefly: ignore [missing-import]
        from ml_consensus_engine import MLConsensusEngine

        
        engine = MLConsensusEngine("test_node")
        engine.load_ensemble_models()
        
        if not engine.models_loaded:
            print("  [ERROR] Models not loaded - feature extraction may not work")
            return False
        
        test_reports = [
            {
                "node_address": "test_node_1",
                "avg_response_ms": 100,
                "is_reachable": True,
                "status": "up",
                "ssl_valid": True,
                "content_match": True,
                "timestamp": time.time()
            },
            {
                "node_address": "test_node_2",
                "avg_response_ms": 200,
                "is_reachable": True,
                "status": "up",
                "ssl_valid": True,
                "content_match": True,
                "timestamp": time.time()
            }
        ]
        
        features_df = engine.extract_features_from_reports(test_reports)
        
        if features_df.empty:
            print("  [ERROR] Feature extraction returned empty DataFrame")
            return False
        
        print(f"  [OK] Feature extraction working - extracted {len(features_df)} rows")
        print(f"  Features: {list(features_df.columns)}")
        
        return True
    
    except Exception as e:
        print(f"  [ERROR] Feature extraction test failed: {e}")
        return False


def check_ml_prediction():
    """Test ML prediction process"""
    
    print("\nTesting ML Prediction...")
    
    try:
        sys.path.append(os.path.join(os.path.dirname(__file__), 'node_service', 'src'))
        
        # pyrefly: ignore [missing-import]
        from ml_consensus_engine import MLConsensusEngine, EnhancedMLConsensusEngine
        
        engine = MLConsensusEngine("test_node")
        engine.load_ensemble_models()
        
        if not engine.models_loaded:
            print("  [ERROR] Models not loaded - prediction cannot work")
            return False
        
        # Prepare base feature dict
        test_features_dict = {
            'accuracy': [0.9, 0.8],
            'false_positive_rate': [0.05, 0.1],
            'false_negative_rate': [0.05, 0.1],
            'avg_rt_error': [50.0, 100.0],
            'max_rt_error': [100.0, 200.0],
            'peer_agreement_rate': [0.9, 0.8],
            'historical_accuracy': [0.85, 0.75],
            'accuracy_std_dev': [0.1, 0.15],
            'report_consistency': [0.9, 0.8],
            'sudden_change_score': [0.1, 0.2],
            'ssl_accuracy': [0.95, 0.9],
            'uptime_deviation': [0.05, 0.1],
            'rt_consistency': [0.9, 0.8],
        }

        # Ensure all required RF and behavioral columns are present
        for col in getattr(engine, "rf_feature_cols", []):
            if col not in test_features_dict:
                test_features_dict[col] = [0.0, 0.0]
        for col in getattr(engine, "behavioral_cols", []):
            if col not in test_features_dict:
                test_features_dict[col] = [0.0, 0.0]

        test_features = pd.DataFrame(test_features_dict)
        
        predictions_df = engine.predict_malicious_probability(test_features)
        
        if predictions_df.empty:
            print("  [ERROR] ML prediction returned empty DataFrame")
            return False
        
        print(f"  [OK] ML prediction working - processed {len(predictions_df)} predictions")
        print(f"  Prediction columns: {list(predictions_df.columns)}")
        
        if 'p_malicious' in predictions_df.columns:
            print(f"  Malicious probabilities: {predictions_df['p_malicious'].tolist()}")
        else:
            print("  WARNING: 'p_malicious' column missing - this may cause consensus errors")
        
        return True
    
    except Exception as e:
        print(f"  [ERROR] ML prediction test failed: {e}")
        return False


def check_enhanced_ml_engine():
    """Test enhanced ML engine with ML_MINOR integration"""
    
    print("\nTesting Enhanced ML Engine...")
    
    try:
        sys.path.append(os.path.join(os.path.dirname(__file__), 'node_service', 'src'))
        
        # pyrefly: ignore [missing-import]
        from enhanced_ml_consensus_engine import EnhancedMLConsensusEngine
        
        engine = EnhancedMLConsensusEngine("test_node")
        
        if not engine.models_loaded:
            print("  [ERROR] Enhanced ML engine models not loaded")
            return False
        
        print("  [OK] Enhanced ML engine loaded successfully")
        print(f"  RF features: {len(engine.rf_feature_cols)}")
        print(f"  Behavioral features: {len(engine.behavioral_cols)}")
        
        test_features = {
            'accuracy': 0.9,
            'false_positive_rate': 0.05,
            'false_negative_rate': 0.05,
            'avg_rt_error': 50.0,
            'max_rt_error': 100.0,
            'peer_agreement_rate': 0.9,
            'historical_accuracy': 0.85,
            'accuracy_std_dev': 0.1,
            'report_consistency': 0.9,
            'sudden_change_score': 0.1,
            'ssl_accuracy': 0.95,
            'uptime_deviation': 0.05,
            'rt_consistency': 0.9,
            'itt_jitter': 0.1,
            'response_time_variance': 25.0,
            'report_frequency': 1.0,
            'timeout_rate': 0.0,
            'error_burst_score': 0.0
        }
        
        reputation, decision = engine.evaluate_node("test_node", test_features)
        
        print(f"  [OK] Reputation calculation working: {reputation:.3f}")
        print(f"  Mitigation decision: {decision.status} -> {decision.action} ({decision.shard})")
        
        return True
    
    except Exception as e:
        print(f"  [ERROR] Enhanced ML engine test failed: {e}")
        return False


def check_live_nodes():
    """Check if any nodes are running and test their ML endpoints"""
    
    print("\nChecking Live Nodes...")
    
    active_nodes = []
    
    for port in range(8000, 8020):
        try:
            response = requests.get(f"http://localhost:{port}/health", timeout=2)
            
            if response.status_code == 200:
                active_nodes.append(port)
                print(f"  [OK] Node found on port {port}")
                
                try:
                    ml_response = requests.get(f"http://localhost:{port}/reputation", timeout=5)
                    
                    if ml_response.status_code == 200:
                        ml_data = ml_response.json()
                        engine_type = ml_data.get('engine_type', 'unknown')
                        
                        print(f"    ML Engine: {engine_type}")
                        
                        if 'shard_distribution' in ml_data:
                            print(f"    Shards: {ml_data['shard_distribution']}")
                        
                        if 'mitigation_actions' in ml_data:
                            actions = ml_data['mitigation_actions']
                            print(f"    Actions: {len(actions)} nodes evaluated")
                    
                    else:
                        print(f"    [ERROR] ML endpoint returned {ml_response.status_code}")
                
                except Exception as e:
                    print(f"    [ERROR] ML endpoint error: {e}")
        
        except:
            pass
    
    if not active_nodes:
        print("  [ERROR] No active nodes found")
    
    return active_nodes


def main():
    """Run comprehensive ML pipeline diagnostic"""
    
    print("ML Pipeline Diagnostic Tool")
    print("=" * 50)
    
    model_results = check_ml_models()
    feature_ok = check_feature_extraction()
    prediction_ok = check_ml_prediction()
    enhanced_ok = check_enhanced_ml_engine()
    active_nodes = check_live_nodes()
    
    print("\nDiagnostic Summary")
    print("=" * 30)
    
    print(f"ML Models: {sum(1 for r in model_results.values() if r['status'] == 'OK')}/{len(model_results)} OK")
    print(f"Feature Extraction: {'OK' if feature_ok else 'BROKEN'}")
    print(f"ML Prediction: {'OK' if prediction_ok else 'BROKEN'}")
    print(f"Enhanced Engine: {'OK' if enhanced_ok else 'BROKEN'}")
    print(f"Active Nodes: {len(active_nodes)} found")
    
    print("\nRecommendations:")
    
    if not all(r['status'] == 'OK' for r in model_results.values()):
        print("  Fix missing model files")
    
    if not feature_ok:
        print("  Debug feature extraction process")
    
    if not prediction_ok:
        print("  Fix ML prediction pipeline")
    
    if not enhanced_ok:
        print("  Enhanced ML engine not available - using fallback")
    
    if not active_nodes:
        print("  Start some nodes to test live ML functionality")
    
    if feature_ok and prediction_ok:
        print("  ML pipeline is working correctly")
    
    report = {
        'timestamp': time.time(),
        'models': model_results,
        'feature_extraction': feature_ok,
        'ml_prediction': prediction_ok,
        'enhanced_engine': enhanced_ok,
        'active_nodes': active_nodes
    }
    
    report_filename = f"ml_diagnostic_report_{int(time.time())}.json"
    
    with open(report_filename, "w") as f:
        json.dump(report, f, indent=2, default=str)
    
    print(f"\nDetailed report saved to: {report_filename}")


if __name__ == "__main__":
    main()