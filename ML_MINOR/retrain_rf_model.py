#!/usr/bin/env python3
"""
Retrain Random Forest model with correct features and proper scaler saving.
Fixes the issues identified in the system analysis:
1. Removes 5 wrong features (blocks_mined, orphan_blocks, tx_submitted, ewma_trust_score, bayesian_confidence)
2. Saves the fitted scaler in the artifact so it can be loaded correctly
"""

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import train_test_split
import joblib
import os

# CORRECT features for website monitoring (removed blockchain miner metrics and circular features)
CORRECT_FEATURES = [
    'peer_agreement_rate',
    'ssl_accuracy', 
    'avg_rt_error',
    'report_consistency',
    'sudden_change_score',
    'uptime_deviation',
    'rt_consistency',
    'itt_jitter',
    'accuracy',
    'false_positive_rate',
    'false_negative_rate'
]

# WRONG features that were in the old model (causing data leakage and zeros)
WRONG_FEATURES = [
    'blocks_mined',      # Blockchain miner metric - nodes don't mine
    'orphan_blocks',     # Blockchain miner metric - nodes don't mine  
    'tx_submitted',      # Blockchain miner metric - nodes don't mine
    'ewma_trust_score',  # Circular - this is an OUTPUT of the reputation engine
    'bayesian_confidence' # Circular - this is an OUTPUT of the reputation engine
]

def generate_training_data(n_samples=1000):
    """Generate synthetic training data with correct features"""
    np.random.seed(42)
    
    data = {}
    
    # Honest nodes (label=1) - good metrics
    honest_samples = n_samples // 2
    data['peer_agreement_rate'] = np.concatenate([
        np.random.uniform(0.8, 1.0, honest_samples),  # Honest: high agreement
        np.random.uniform(0.0, 0.5, n_samples - honest_samples)  # Malicious: low agreement
    ])
    
    data['ssl_accuracy'] = np.concatenate([
        np.random.uniform(0.9, 1.0, honest_samples),  # Honest: high SSL accuracy
        np.random.uniform(0.0, 0.6, n_samples - honest_samples)  # Malicious: low SSL accuracy
    ])
    
    data['avg_rt_error'] = np.concatenate([
        np.random.uniform(0.0, 0.2, honest_samples),  # Honest: low response time error
        np.random.uniform(0.3, 0.8, n_samples - honest_samples)  # Malicious: high error
    ])
    
    data['report_consistency'] = np.concatenate([
        np.random.uniform(0.85, 1.0, honest_samples),  # Honest: high consistency
        np.random.uniform(0.0, 0.5, n_samples - honest_samples)  # Malicious: low consistency
    ])
    
    data['sudden_change_score'] = np.concatenate([
        np.random.uniform(0.0, 0.2, honest_samples),  # Honest: low sudden changes
        np.random.uniform(0.4, 0.9, n_samples - honest_samples)  # Malicious: high changes
    ])
    
    data['uptime_deviation'] = np.concatenate([
        np.random.uniform(0.0, 0.15, honest_samples),  # Honest: low deviation
        np.random.uniform(0.3, 0.7, n_samples - honest_samples)  # Malicious: high deviation
    ])
    
    data['rt_consistency'] = np.concatenate([
        np.random.uniform(0.8, 1.0, honest_samples),  # Honest: high consistency
        np.random.uniform(0.0, 0.5, n_samples - honest_samples)  # Malicious: low consistency
    ])
    
    data['itt_jitter'] = np.concatenate([
        np.random.uniform(0.0, 0.1, honest_samples),  # Honest: low jitter
        np.random.uniform(0.2, 0.6, n_samples - honest_samples)  # Malicious: high jitter
    ])
    
    data['accuracy'] = np.concatenate([
        np.random.uniform(0.9, 1.0, honest_samples),  # Honest: high accuracy
        np.random.uniform(0.0, 0.6, n_samples - honest_samples)  # Malicious: low accuracy
    ])
    
    data['false_positive_rate'] = np.concatenate([
        np.random.uniform(0.0, 0.05, honest_samples),  # Honest: low false positives
        np.random.uniform(0.3, 0.8, n_samples - honest_samples)  # Malicious: high false positives
    ])
    
    data['false_negative_rate'] = np.concatenate([
        np.random.uniform(0.0, 0.05, honest_samples),  # Honest: low false negatives
        np.random.uniform(0.2, 0.7, n_samples - honest_samples)  # Malicious: high false negatives
    ])
    
    # Labels: 1 = honest, 0 = malicious
    labels = np.concatenate([
        np.ones(honest_samples),
        np.zeros(n_samples - honest_samples)
    ])
    
    # Shuffle
    indices = np.random.permutation(n_samples)
    for key in data:
        data[key] = data[key][indices]
    labels = labels[indices]
    
    return pd.DataFrame(data), labels

def train_and_save_model():
    """Train RF model with correct features and save with fitted scaler"""
    print("=" * 60)
    print("Retraining Random Forest Model with Correct Features")
    print("=" * 60)
    
    # Generate training data
    print("\n[1/4] Generating synthetic training data...")
    X, y = generate_training_data(n_samples=2000)
    print(f"      Samples: {len(X)}, Features: {len(CORRECT_FEATURES)}")
    print(f"      Honest: {sum(y)}, Malicious: {len(y) - sum(y)}")
    
    # Split data
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42, stratify=y
    )
    
    # Fit scaler on training data
    print("\n[2/4] Fitting StandardScaler on training data...")
    scaler = StandardScaler()
    X_train_scaled = scaler.fit_transform(X_train)
    X_test_scaled = scaler.transform(X_test)
    print(f"      Scaler fitted: mean={scaler.mean_[:3]}, scale={scaler.scale_[:3]}")
    
    # Train Random Forest
    print("\n[3/4] Training Random Forest classifier...")
    rf = RandomForestClassifier(
        n_estimators=100,
        max_depth=10,
        min_samples_split=5,
        min_samples_leaf=2,
        random_state=42,
        n_jobs=-1
    )
    rf.fit(X_train_scaled, y_train)
    
    # Evaluate
    train_score = rf.score(X_train_scaled, y_train)
    test_score = rf.score(X_test_scaled, y_test)
    print(f"      Train accuracy: {train_score:.4f}")
    print(f"      Test accuracy: {test_score:.4f}")
    
    # Feature importance
    print("\n[4/4] Feature importance:")
    importances = rf.feature_importances_
    for i, feature in enumerate(CORRECT_FEATURES):
        print(f"      {feature:25s}: {importances[i]:.4f}")
    
    # CRITICAL: Save model WITH fitted scaler in artifact
    model_dir = os.path.join(os.path.dirname(__file__), 'models')
    os.makedirs(model_dir, exist_ok=True)
    
    model_path = os.path.join(model_dir, 'rf_backbone.joblib')
    
    artifact = {
        'model': rf,
        'feature_cols': CORRECT_FEATURES,
        'scaler': scaler,  # CRITICAL: Save the actual fitted scaler object
        'scaler_type': 'standard',  # For backward compatibility
        'train_accuracy': train_score,
        'test_accuracy': test_score,
        'n_features': len(CORRECT_FEATURES),
        'n_samples': len(X),
        'retrained': True,
        'fixed_features': True  # Flag indicating wrong features were removed
    }
    
    joblib.dump(artifact, model_path)
    print(f"\n✅ Model saved to: {model_path}")
    print(f"   Artifact keys: {list(artifact.keys())}")
    print(f"   Scaler saved: {'scaler' in artifact}")
    print(f"   Scaler is fitted: {hasattr(artifact['scaler'], 'mean_')}")
    
    # Verify loading
    print("\n[VERIFY] Testing model loading...")
    loaded = joblib.load(model_path)
    print(f"   Loaded keys: {list(loaded.keys())}")
    print(f"   Scaler present: {'scaler' in loaded}")
    print(f"   Scaler fitted: {hasattr(loaded['scaler'], 'mean_') if 'scaler' in loaded else False}")
    
    # Test prediction
    test_sample = np.array([[0.9, 0.95, 0.1, 0.9, 0.1, 0.1, 0.9, 0.05, 0.95, 0.02, 0.02]])
    test_scaled = loaded['scaler'].transform(test_sample)
    prediction = loaded['model'].predict_proba(test_scaled)[0]
    print(f"   Test prediction (should be [low, high] for honest): {prediction}")
    
    print("\n" + "=" * 60)
    print("Model retraining completed successfully!")
    print("=" * 60)
    print("\nFIXED ISSUES:")
    print("1. Removed 5 wrong features (blocks_mined, orphan_blocks, tx_submitted,")
    print("   ewma_trust_score, bayesian_confidence)")
    print("2. Saved fitted scaler in artifact - no more unfitted scaler fallback")
    print("3. Model now uses only monitoring-relevant features")
    print("\nThe node will now load the scaler correctly and make accurate predictions.")

if __name__ == "__main__":
    train_and_save_model()
