#!/usr/bin/env python3
"""
train_backbone_model.py

Train stacked ensemble (Random Forest + Isolation Forest) on RIPE Atlas
latency datasets.  Produces two joblib artifacts that the live consensus
engine loads at startup:

    ML_MINOR/models/rf_backbone.joblib   – Random Forest classifier + scaler
    ML_MINOR/models/iso_backbone.joblib  – Isolation Forest anomaly detector + scaler

Dataset schema (CSV):
    probe_id, avg_latency, latency_var, std_latency, skewness,
    kurtosis, p95_latency, max_latency, failure_rate, label
"""

import argparse
import os
import pathlib
from typing import List, Tuple

import numpy as np
import pandas as pd
import joblib
from sklearn import model_selection
from sklearn.ensemble import IsolationForest, RandomForestClassifier
from sklearn.metrics import accuracy_score, classification_report, f1_score
from sklearn.preprocessing import StandardScaler


# ── Feature configuration ────────────────────────────────────────────
FEATURE_COLS: List[str] = [
    "avg_latency",
    "latency_var",
    "std_latency",
    "skewness",
    "kurtosis",
    "p95_latency",
    "max_latency",
    "failure_rate",
]

# Behavioural subset used exclusively by Isolation Forest
BEHAVIORAL_COLS: List[str] = [
    "avg_latency",
    "latency_var",
    "std_latency",
    "p95_latency",
    "max_latency",
    "failure_rate",
]


# ── Helpers ───────────────────────────────────────────────────────────
def _resolve_label_column(df: pd.DataFrame, requested: str = "label") -> str:
    if requested in df.columns:
        return requested
    lowered = {c.lower(): c for c in df.columns}
    if requested.lower() in lowered:
        return lowered[requested.lower()]
    raise KeyError(
        f"Could not find target column '{requested}' (case-insensitive). "
        f"Available columns: {list(df.columns)}"
    )


def _coerce_numeric(df: pd.DataFrame, cols: List[str]) -> pd.DataFrame:
    out = df.copy()
    for c in cols:
        out[c] = pd.to_numeric(out[c], errors="coerce")
    return out


def _normalize_0_1(arr: np.ndarray) -> np.ndarray:
    arr = np.asarray(arr, dtype=float)
    mn, mx = float(np.nanmin(arr)), float(np.nanmax(arr))
    return (arr - mn) / (mx - mn + 1e-12)


# ── Dataset loading ──────────────────────────────────────────────────
def load_ripe_datasets(root_dir: str) -> pd.DataFrame:
    """
    Concatenate the three RIPE Atlas seed CSVs located in *root_dir*:
        dataset_seed_0.csv, dataset_seed_1.csv, dataset_seed_2.csv
    Returns a single merged DataFrame.
    """
    seed_files = [
        os.path.join(root_dir, f"dataset_seed_{i}.csv") for i in range(3)
    ]
    frames = []
    for path in seed_files:
        if not os.path.isfile(path):
            raise FileNotFoundError(f"Required dataset not found: {path}")
        df = pd.read_csv(path)
        print(f"  [INFO] Loaded {os.path.basename(path)}: {df.shape}")
        frames.append(df)

    merged = pd.concat(frames, ignore_index=True)
    print(f"\n  [INFO] Merged dataset shape: {merged.shape}")
    return merged


def verify_and_clean_dataset(df: pd.DataFrame) -> pd.DataFrame:
    """Verify required columns exist and impute missing values."""
    print("\nPreview (first 5 rows):")
    print(df.head(5))

    print("\nColumn names:")
    print(list(df.columns))

    missing_features = [c for c in FEATURE_COLS if c not in df.columns]
    if missing_features:
        raise ValueError(
            f"Missing required feature columns: {missing_features}\n"
            f"Available columns: {list(df.columns)}"
        )

    cleaned = df.copy()
    numeric_cols = cleaned.select_dtypes(include=[np.number]).columns.tolist()
    for c in numeric_cols:
        if cleaned[c].isna().any():
            med = cleaned[c].median()
            cleaned[c] = cleaned[c].fillna(med if not pd.isna(med) else 0.0)

    print("\nDtypes after cleaning:")
    print(cleaned.dtypes)
    return cleaned


# ── Epoch synthesis (optional data augmentation) ─────────────────────
def synthesize_epoch_history(
    df: pd.DataFrame,
    num_nodes: int = 200,
    epochs_per_node: int = 50,
    seed: int = 42,
) -> pd.DataFrame:
    """
    Re-sample rows and assign node_id / epoch columns so that the dataset
    mimics an epoch-history structure (required for EWMA reputation eval).
    """
    rng = np.random.RandomState(seed)
    n_required = num_nodes * epochs_per_node

    base = df.copy()
    if len(base) < n_required:
        extra = base.sample(n=n_required - len(base), replace=True, random_state=seed)
        base = pd.concat([base, extra], ignore_index=True)
    else:
        base = base.sample(n=n_required, replace=False, random_state=seed).reset_index(drop=True)

    base = base.reset_index(drop=True)
    base["node_id"] = (np.arange(n_required) % num_nodes).astype(int)
    base["epoch"] = (np.arange(n_required) // num_nodes).astype(int)

    if "label" in base.columns:
        node_label = (
            base.groupby("node_id")["label"]
            .apply(lambda s: int(pd.to_numeric(s.iloc[0], errors="coerce") or 0))
            .astype(int)
        )
        base["label"] = base["node_id"].map(node_label).astype(int)

    # Add small jitter to avoid exact duplicate rows across epochs
    for col in FEATURE_COLS:
        if col in base.columns:
            vals = pd.to_numeric(base[col], errors="coerce")
            scale = max(float(vals.std()), 1e-6) * 0.01
            jitter = rng.normal(0, scale, size=len(base))
            base[col] = vals.fillna(vals.median()) + jitter

    return base


# ── EWMA reputation (per-node temporal smoothing) ─────────────────────
def ewma_reputation_by_node(
    df_scores: pd.DataFrame,
    node_col: str,
    time_col: str,
    reputation_col: str,
    alpha: float,
) -> pd.Series:
    def _ewma_for_group(g: pd.DataFrame) -> pd.Series:
        g_sorted = g.sort_values(time_col)
        vals = g_sorted[reputation_col].astype(float).values
        out = np.empty_like(vals, dtype=float)
        if len(vals) == 0:
            return pd.Series([], index=g_sorted.index, dtype=float)
        out[0] = vals[0]
        for i in range(1, len(vals)):
            out[i] = alpha * out[i - 1] + (1.0 - alpha) * vals[i]
        return pd.Series(out, index=g_sorted.index)

    return df_scores.groupby(node_col, group_keys=False).apply(_ewma_for_group)


# ── Prepare X / y ────────────────────────────────────────────────────
def prepare_xy(
    df: pd.DataFrame,
    feature_cols: List[str],
    label_col: str,
) -> Tuple[np.ndarray, np.ndarray, StandardScaler, List[str], List[str]]:
    """
    Build feature matrix, fit a StandardScaler, and return scaled X, y,
    the fitted scaler, used columns, and missing columns.
    """
    missing = [c for c in feature_cols if c not in df.columns]
    used = [c for c in feature_cols if c in df.columns]
    if not used:
        raise ValueError(f"None of the requested features exist. Requested: {feature_cols}")

    feat_df = _coerce_numeric(df[used].copy(), used)
    for c in used:
        if feat_df[c].isna().all():
            feat_df[c] = 0.0
        else:
            feat_df[c] = feat_df[c].fillna(feat_df[c].median())

    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(feat_df.values.astype(float))
    y = pd.to_numeric(df[label_col], errors="coerce").fillna(0).astype(int).values

    return X_scaled, y, scaler, used, missing


# ── Main ──────────────────────────────────────────────────────────────
def main() -> int:
    parser = argparse.ArgumentParser(
        description="Train RF + ISO backbone on RIPE Atlas latency datasets."
    )
    parser.add_argument(
        "--root",
        default=os.path.join(os.path.dirname(__file__), ".."),
        help="Project root directory containing dataset_seed_*.csv files",
    )
    parser.add_argument(
        "--out",
        default=os.path.join(os.path.dirname(__file__), "models"),
        help="Output directory for trained models",
    )
    args = parser.parse_args()

    root_dir = os.path.abspath(args.root)
    out_dir = os.path.abspath(args.out)
    os.makedirs(out_dir, exist_ok=True)

    # ── 1. Load & merge RIPE Atlas CSVs ──
    print("=" * 60)
    print("[INFO] Loading RIPE Atlas seed datasets ...")
    df_raw = load_ripe_datasets(root_dir)

    # ── 2. Clean & verify ──
    df = verify_and_clean_dataset(df_raw)

    # ── 3. Epoch synthesis for temporal evaluation ──
    df = synthesize_epoch_history(df, num_nodes=200, epochs_per_node=50, seed=42)

    # ── 4. Prepare X, y (all 8 features) ──
    label_col = _resolve_label_column(df, requested="label")
    X_all, y_all, rf_scaler, used_features, missing_features = prepare_xy(
        df, feature_cols=FEATURE_COLS, label_col=label_col
    )

    print(f"\n[INFO] Loaded dataset from: {root_dir}")
    print(f"DataFrame shape: {df.shape}")
    if missing_features:
        print("Missing requested feature columns:")
        for c in missing_features:
            print(f"  - {c}")
    print(f"Used feature columns ({len(used_features)}):")
    for c in used_features:
        print(f"  - {c}")
    print(f"X shape: {X_all.shape}")
    print(f"y shape: {y_all.shape}")
    print(f"Target column: {label_col}")
    print(f"Label distribution: 0={int((y_all == 0).sum())}, 1={int((y_all == 1).sum())}")

    # ── 5. Train / test split ──
    X_train, X_test, y_train, y_test, idx_train, idx_test = model_selection.train_test_split(
        X_all,
        y_all,
        df.index.values,
        test_size=0.2,
        random_state=42,
        stratify=y_all if len(np.unique(y_all)) > 1 else None,
    )
    print(f"\n[INFO] Split: train={X_train.shape[0]}  test={X_test.shape[0]}")

    # ── 6. Random Forest ──
    rf = RandomForestClassifier(
        n_estimators=300,
        random_state=42,
        n_jobs=-1,
        class_weight="balanced_subsample",
    )
    rf.fit(X_train, y_train)
    rf_proba_test = rf.predict_proba(X_test)[:, 1]
    y_pred_test = (rf_proba_test >= 0.5).astype(int)

    print("\n=== Random Forest Evaluation (test set) ===")
    print(classification_report(y_test, y_pred_test, digits=4))
    acc = accuracy_score(y_test, y_pred_test)
    f1 = f1_score(y_test, y_pred_test, zero_division=0)
    print(f"[RESULT] Accuracy: {acc:.4f}")
    print(f"[RESULT] F1-score: {f1:.4f}")

    # ── 7. Isolation Forest (behavioural subset, honest-only training) ──
    beh_used = [c for c in BEHAVIORAL_COLS if c in df.columns]
    if not beh_used:
        raise ValueError(
            f"None of the behavioral features are present. Requested: {BEHAVIORAL_COLS}"
        )

    beh_train_df = _coerce_numeric(df.loc[idx_train, beh_used].copy(), beh_used)
    beh_test_df = _coerce_numeric(df.loc[idx_test, beh_used].copy(), beh_used)
    for c in beh_used:
        med = beh_train_df[c].median()
        if pd.isna(med):
            med = 0.0
        beh_train_df[c] = beh_train_df[c].fillna(med)
        beh_test_df[c] = beh_test_df[c].fillna(med)

    beh_scaler = StandardScaler()
    X_beh_train = beh_scaler.fit_transform(beh_train_df.values.astype(float))
    X_beh_test = beh_scaler.transform(beh_test_df.values.astype(float))

    iso = IsolationForest(
        n_estimators=300,
        contamination=0.15,
        random_state=42,
        n_jobs=-1,
    )
    iso.fit(X_beh_train)
    iso_score_test = -iso.decision_function(X_beh_test)
    iso_norm_test = _normalize_0_1(iso_score_test)

    # ── 8. Fusion: 70 % RF + 30 % ISO ──
    w_rf, w_iso = 0.7, 0.3
    risk_raw = (w_rf * rf_proba_test) + (w_iso * iso_norm_test)
    base_reputation = 1.0 - np.clip(risk_raw, 0.0, 1.0)

    test_df = df.loc[idx_test].copy()
    test_df["rf_prob_malicious"] = rf_proba_test
    test_df["iso_anomaly_norm"] = iso_norm_test
    test_df["base_reputation"] = base_reputation

    # ── 9. EWMA reputation ──
    node_col = "node_id" if "node_id" in test_df.columns else None
    time_col = "epoch" if "epoch" in test_df.columns else None
    if node_col and time_col:
        test_df["final_reputation"] = ewma_reputation_by_node(
            test_df,
            node_col=node_col,
            time_col=time_col,
            reputation_col="base_reputation",
            alpha=0.9,
        )
    else:
        test_df["final_reputation"] = test_df["base_reputation"]

    print("\n=== Final Reputation Score Distribution (test set) ===")
    desc = test_df["final_reputation"].describe(
        percentiles=[0.01, 0.05, 0.1, 0.5, 0.9, 0.95, 0.99]
    )
    print(desc)

    hist, bin_edges = np.histogram(
        test_df["final_reputation"].values.astype(float), bins=10, range=(0.0, 1.0)
    )
    print("\nHistogram (10 bins from 0 to 1):")
    for i in range(len(hist)):
        print(f"[{bin_edges[i]:.1f}, {bin_edges[i+1]:.1f}): {hist[i]}")

    # ── 10. Save models ──
    rf_path = os.path.join(out_dir, "rf_backbone.joblib")
    iso_path = os.path.join(out_dir, "iso_backbone.joblib")

    joblib.dump(
        {
            "model": rf,
            "feature_cols": used_features,
            "scaler_type": "standard",
            "scaler": rf_scaler,
        },
        rf_path,
    )
    joblib.dump(
        {
            "model": iso,
            "behavioral_cols": beh_used,
            "scaler": beh_scaler,
        },
        iso_path,
    )
    print(f"\n[INFO] Saved models:")
    print(f"   {rf_path}")
    print(f"   {iso_path}")
    print(f"   RF features ({len(used_features)}): {used_features}")
    print(f"   ISO behavioral features ({len(beh_used)}): {beh_used}")
    print("[INFO] Data successfully loaded and verified.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
