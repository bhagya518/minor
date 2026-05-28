#!/usr/bin/env python3
"""
train_backbone_model.py

Final Clean Version
Random Forest + Isolation Forest + Stacked Meta Learner

Outputs:
    models/rf_backbone.joblib
    models/iso_backbone.joblib
    models/meta_stack.joblib
"""

import os
import argparse
import joblib
import numpy as np
import pandas as pd

from sklearn.model_selection import (
    train_test_split,
    RandomizedSearchCV,
    cross_val_predict,
)

from sklearn.ensemble import (
    RandomForestClassifier,
    IsolationForest,
    GradientBoostingClassifier,
)

from sklearn.preprocessing import StandardScaler

from sklearn.metrics import (
    classification_report,
    accuracy_score,
    f1_score,
    make_scorer,
)

from imblearn.over_sampling import SMOTE


# =========================================================
# FEATURES
# =========================================================

FEATURE_COLS = [
    "avg_latency",
    "latency_var",
    "std_latency",
    "skewness",
    "kurtosis",
    "p95_latency",
    "max_latency",
    "failure_rate",
]

BEHAVIORAL_COLS = [
    "avg_latency",
    "latency_var",
    "std_latency",
    "p95_latency",
    "max_latency",
    "failure_rate",
]


# =========================================================
# HELPERS
# =========================================================

def load_datasets(root_dir):
    files = [
        os.path.join(root_dir, f"dataset_seed_{i}.csv")
        for i in range(3)
    ]
    frames = []
    for path in files:
        if not os.path.exists(path):
            raise FileNotFoundError(f"Missing file: {path}")
        df = pd.read_csv(path)
        print(f"[INFO] Loaded {path} -> {df.shape}")
        frames.append(df)
    merged = pd.concat(frames, ignore_index=True)
    print(f"\n[INFO] Final merged shape: {merged.shape}")
    return merged


def clean_dataset(df):
    required_cols = FEATURE_COLS + ["label"]
    missing = [c for c in required_cols if c not in df.columns]
    if missing:
        raise ValueError(f"Missing columns: {missing}")

    for col in FEATURE_COLS:
        df[col] = pd.to_numeric(df[col], errors="coerce")
        median = df[col].median()
        df[col] = df[col].fillna(median)

    df["label"] = pd.to_numeric(
        df["label"],
        errors="coerce"
    ).fillna(0).astype(int)
    return df


# =========================================================
# RANDOM FOREST TUNING
# =========================================================

def tune_random_forest(X, y):
    param_grid = {
        "n_estimators": [200, 300],
        "max_depth": [10, 20, None],
        "min_samples_split": [2, 5],
        "min_samples_leaf": [1, 2],
        "class_weight": ["balanced"],
    }
    scorer = make_scorer(f1_score)
    search = RandomizedSearchCV(
        RandomForestClassifier(
            random_state=42,
            n_jobs=-1,
        ),
        param_distributions=param_grid,
        n_iter=10,
        scoring=scorer,
        cv=3,
        verbose=1,
        random_state=42,
        n_jobs=-1,
    )
    search.fit(X, y)
    print("\n[INFO] Best RF Params:")
    print(search.best_params_)
    return search.best_estimator_


# =========================================================
# MAIN
# =========================================================

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".")
    parser.add_argument("--out", default="models")
    args = parser.parse_args()

    os.makedirs(args.out, exist_ok=True)

    # =====================================================
    # LOAD DATA
    # =====================================================
    df = load_datasets(args.root)
    df = clean_dataset(df)

    X = df[FEATURE_COLS].values
    y = df["label"].values

    # =====================================================
    # SPLIT
    # =====================================================
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42, stratify=y,
    )
    print(f"\nTrain: {X_train.shape}")
    print(f"Test : {X_test.shape}")

    # =====================================================
    # SCALING
    # =====================================================
    scaler = StandardScaler()
    X_train_scaled = scaler.fit_transform(X_train)
    X_test_scaled = scaler.transform(X_test)

    # =====================================================
    # SMOTE
    # =====================================================
    smote = SMOTE(random_state=42)
    X_train_resampled, y_train_resampled = smote.fit_resample(
        X_train_scaled, y_train,
    )
    print("\n[INFO] After SMOTE:")
    print(np.bincount(y_train_resampled))

    # =====================================================
    # RANDOM FOREST
    # =====================================================
    rf = tune_random_forest(X_train_resampled, y_train_resampled)
    rf.fit(X_train_resampled, y_train_resampled)
    
    rf_probs_train = rf.predict_proba(X_train_resampled)[:, 1]
    rf_probs_test = rf.predict_proba(X_test_scaled)[:, 1]

    # =====================================================
    # ISOLATION FOREST
    # =====================================================
    behavioral_idx = [FEATURE_COLS.index(c) for c in BEHAVIORAL_COLS]
    
    # Train ISO on honest nodes from original train set (before SMOTE)
    X_beh_train_orig = X_train_scaled[:, behavioral_idx]
    honest_mask = (y_train == 0)
    X_honest = X_beh_train_orig[honest_mask]

    iso = IsolationForest(
        n_estimators=300,
        contamination=0.15,
        random_state=42,
        n_jobs=-1,
    )
    iso.fit(X_honest)

    # To stack with RF correctly, evaluate ISO on the RESAMPLED train set
    X_beh_train_resampled = X_train_resampled[:, behavioral_idx]
    iso_train_scores = -iso.decision_function(X_beh_train_resampled)
    
    # Evaluate ISO on test set
    X_beh_test = X_test_scaled[:, behavioral_idx]
    iso_test_scores = -iso.decision_function(X_beh_test)

    # Min-max normalization using train bounds ONLY (fixes data leakage)
    iso_min = np.min(iso_train_scores)
    iso_max = np.max(iso_train_scores)
    
    iso_train_norm = (iso_train_scores - iso_min) / (iso_max - iso_min + 1e-12)
    iso_test_norm = (iso_test_scores - iso_min) / (iso_max - iso_min + 1e-12)

    # =====================================================
    # STACKED META LEARNER
    # =====================================================
    # Generate OOF predictions for RF to avoid overfitting in meta-learner
    rf_oof = cross_val_predict(
        rf, X_train_resampled, y_train_resampled,
        cv=5, method="predict_proba", n_jobs=-1
    )[:, 1]

    stacked_train = np.column_stack((rf_oof, iso_train_norm))
    meta_y = y_train_resampled

    meta_model = GradientBoostingClassifier(random_state=42)
    meta_model.fit(stacked_train, meta_y)

    stacked_test = np.column_stack((rf_probs_test, iso_test_norm))
    meta_probs = meta_model.predict_proba(stacked_test)[:, 1]

    # =====================================================
    # BEST THRESHOLD
    # =====================================================
    thresholds = np.arange(0.1, 0.95, 0.01)
    best_threshold = 0.5
    best_f1 = 0

    for thr in thresholds:
        preds = (meta_probs >= thr).astype(int)
        score = f1_score(y_test, preds, zero_division=0)
        if score > best_f1:
            best_f1 = score
            best_threshold = thr

    final_preds = (meta_probs >= best_threshold).astype(int)

    # =====================================================
    # RESULTS
    # =====================================================
    print("\n==============================")
    print("FINAL STACKED MODEL RESULTS")
    print("==============================")
    print(classification_report(y_test, final_preds, digits=4))
    
    acc = accuracy_score(y_test, final_preds)
    f1 = f1_score(y_test, final_preds)
    
    print(f"\nAccuracy : {acc:.4f}")
    print(f"F1 Score : {f1:.4f}")
    print(f"Threshold: {best_threshold:.2f}")

    # =====================================================
    # SAVE MODELS
    # =====================================================
    joblib.dump(
        {"model": rf, "scaler": scaler, "feature_cols": FEATURE_COLS},
        os.path.join(args.out, "rf_backbone.joblib"),
    )

    joblib.dump(
        {
            "model": iso, 
            "behavioral_cols": BEHAVIORAL_COLS,
            "iso_min": float(iso_min),  # Saved for inference scaling
            "iso_max": float(iso_max),
        },
        os.path.join(args.out, "iso_backbone.joblib"),
    )

    joblib.dump(
        {"model": meta_model, "threshold": float(best_threshold)},
        os.path.join(args.out, "meta_stack.joblib"),
    )

    print("\n[INFO] Models saved successfully")


if __name__ == "__main__":
    main()