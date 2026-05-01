#!/usr/bin/env python3
"""
Debug ML prediction to understand the inversion issue
"""

import sys
import os
import time
sys.path.append(os.path.join(os.path.dirname(__file__), 'node_service', 'src'))

from ml_consensus_engine import EnhancedMLConsensusEngine
import numpy as np

def debug_ml_prediction():
    """Debug what the ML model is actually predicting"""
    print("🔍 DEBUGGING ML PREDICTION")
    print("=" * 50)
    
    engine = EnhancedMLConsensusEngine("test_node")
    
    # Load models
    try:
        engine.load_enhanced_models()
        if not engine.models_loaded:
            print("❌ Models failed to load")
            return
    except Exception as e:
        print(f"❌ Exception loading models: {e}")
        return
    
    print("✅ Models loaded successfully")
    
    # Test features for honest node
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
    
    # Test features for malicious node
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
    
    print("\n🔬 Testing Honest Node Features:")
    print(f"Features: {honest_features}")
    
    # Debug step by step
    try:
        # Prepare RF features
        rf_features = []
        for col in engine.rf_feature_cols:
            val = honest_features.get(col, 0.0)
            rf_features.append(float(val))
        
        print(f"RF features array: {rf_features}")
        
        # Scale RF features
        rf_input = np.array(rf_features).reshape(1, -1)
        rf_scaled = engine.rf_scaler.transform(rf_input)
        
        print(f"RF scaled features: {rf_scaled}")
        
        # Get RF probability
        rf_prob = float(engine.rf_model.predict_proba(rf_scaled)[:, 1][0])
        print(f"RF probability (class 1): {rf_prob}")
        
        # Check what the classes are
        classes = engine.rf_model.classes_
        print(f"RF classes: {classes}")
        print(f"Class 0 = {classes[0]}, Class 1 = {classes[1]}")
        
        # Get ISO score
        beh_features = []
        for col in engine.behavioral_cols:
            val = honest_features.get(col, 0.0)
            beh_features.append(float(val))
        
        beh_input = np.array(beh_features).reshape(1, -1)
        beh_scaled = engine.iso_scaler.transform(beh_input)
        iso_score = float(-engine.iso_model.decision_function(beh_scaled)[0])
        iso_norm = float(np.clip(iso_score / 10.0, 0.0, 1.0))
        
        print(f"ISO score: {iso_score}, normalized: {iso_norm}")
        
        # Calculate final risk and reputation
        risk = (0.7 * rf_prob) + (0.3 * iso_norm)
        reputation = 1.0 - float(np.clip(risk, 0.0, 1.0))
        
        print(f"Combined risk: {risk}")
        print(f"Final reputation: {reputation}")
        
        print("\n🔬 Testing Malicious Node Features:")
        print(f"Features: {malicious_features}")
        
        # Same for malicious
        rf_features_mal = []
        for col in engine.rf_feature_cols:
            val = malicious_features.get(col, 0.0)
            rf_features_mal.append(float(val))
        
        rf_input_mal = np.array(rf_features_mal).reshape(1, -1)
        rf_scaled_mal = engine.rf_scaler.transform(rf_input_mal)
        rf_prob_mal = float(engine.rf_model.predict_proba(rf_scaled_mal)[:, 1][0])
        
        beh_features_mal = []
        for col in engine.behavioral_cols:
            val = malicious_features.get(col, 0.0)
            beh_features_mal.append(float(val))
        
        beh_input_mal = np.array(beh_features_mal).reshape(1, -1)
        beh_scaled_mal = engine.iso_scaler.transform(beh_input_mal)
        iso_score_mal = float(-engine.iso_model.decision_function(beh_scaled_mal)[0])
        iso_norm_mal = float(np.clip(iso_score_mal / 10.0, 0.0, 1.0))
        
        risk_mal = (0.7 * rf_prob_mal) + (0.3 * iso_norm_mal)
        reputation_mal = 1.0 - float(np.clip(risk_mal, 0.0, 1.0))
        
        print(f"RF probability (class 1): {rf_prob_mal}")
        print(f"ISO score: {iso_score_mal}, normalized: {iso_norm_mal}")
        print(f"Combined risk: {risk_mal}")
        print(f"Final reputation: {reputation_mal}")
        
        print("\n🎯 ANALYSIS:")
        print(f"Honest node: RF prob={rf_prob:.3f}, risk={risk:.3f}, reputation={reputation:.3f}")
        print(f"Malicious node: RF prob={rf_prob_mal:.3f}, risk={risk_mal:.3f}, reputation={reputation_mal:.3f}")
        
        # Determine if class 1 means "honest" or "malicious"
        if rf_prob < 0.5 and rf_prob_mal > 0.5:
            print("✅ Class 1 = MALICIOUS (higher prob = more malicious)")
            print("   Current formula reputation = 1.0 - risk is CORRECT")
        elif rf_prob > 0.5 and rf_prob_mal < 0.5:
            print("❌ Class 1 = HONEST (higher prob = more honest)")
            print("   Current formula reputation = 1.0 - risk is WRONG")
            print("   Should use reputation = risk (no inversion)")
        else:
            print("⚠️ Cannot determine class meaning from this test")
        
    except Exception as e:
        print(f"❌ Exception during debug: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    debug_ml_prediction()
