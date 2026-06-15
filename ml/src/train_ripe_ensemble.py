"""
Train the Ensemble ML model using the 8 RIPE statistical features.
This matches the provided technical strategy.
"""

import pandas as pd
import numpy as np
from sklearn.ensemble import RandomForestClassifier, IsolationForest, GradientBoostingClassifier
from sklearn.neighbors import LocalOutlierFactor
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler, PowerTransformer
from sklearn.experimental import enable_iterative_imputer
from sklearn.impute import IterativeImputer
import joblib
import os
import logging
import json
from datetime import datetime

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class RIPEEnsembleTrainer:
    def __init__(self, output_path):
        self.output_path = output_path
        self.scaler = StandardScaler()
        self.imputer = IterativeImputer(max_iter=10, random_state=42)
        self.transformer = PowerTransformer()
        
        # 8 RIPE features from proposed architecture
        self.feature_columns = [
            'avg_latency',      # F01 - Mean response time
            'latency_var',      # F02 - Variance of latencies
            'std_latency',      # F03 - Standard deviation
            'skewness',         # F04 - Skewness of distribution
            'kurtosis',         # F05 - Kurtosis (tailedness)
            'p95_latency',      # F06 - 95th percentile
            'max_latency',      # F07 - Maximum latency
            'failure_rate'      # F08 - Failure rate
        ]
        
    def generate_synthetic_data(self, n_samples=1000):
        """Generate synthetic RIPE-8 data for training with realistic overlap"""
        logger.info(f"Generating {n_samples} synthetic RIPE-8 samples...")
        
        # Honest nodes (low latency, low variance) - with some outliers
        n_honest = int(n_samples * 0.8)
        honest_data = {
            'avg_latency': np.random.normal(0.120, 0.040, n_honest),
            'latency_var': np.random.normal(0.001, 0.0005, n_honest),
            'std_latency': np.random.normal(0.030, 0.015, n_honest),
            'skewness': np.random.normal(0.5, 0.5, n_honest),
            'kurtosis': np.random.normal(3.0, 1.0, n_honest),
            'p95_latency': np.random.normal(0.180, 0.060, n_honest),
            'max_latency': np.random.normal(0.250, 0.100, n_honest),
            'failure_rate': np.random.beta(1, 50, n_honest), # Mostly near 0
            'label': 0
        }
        
        # Malicious nodes (higher latency, high variance, higher failure) - with subtle cases
        n_malicious = n_samples - n_honest
        malicious_data = {
            'avg_latency': np.random.normal(0.250, 0.120, n_malicious),
            'latency_var': np.random.normal(0.010, 0.008, n_malicious),
            'std_latency': np.random.normal(0.100, 0.050, n_malicious),
            'skewness': np.random.normal(1.5, 1.0, n_malicious),
            'kurtosis': np.random.normal(7.0, 4.0, n_malicious),
            'p95_latency': np.random.normal(0.400, 0.200, n_malicious),
            'max_latency': np.random.normal(0.800, 0.400, n_malicious),
            'failure_rate': np.random.beta(2, 8, n_malicious), # Higher, but overlaps with honest
            'label': 1
        }
        
        df_honest = pd.DataFrame(honest_data)
        df_malicious = pd.DataFrame(malicious_data)
        df = pd.concat([df_honest, df_malicious]).sample(frac=1).reset_index(drop=True)
        
        # Clip values to realistic ranges
        for col in self.feature_columns:
            df[col] = df[col].clip(lower=0)
            
        return df

    def load_ripe_dataset(self, file_path):
        """Load the real RIPE Atlas dataset and augment with SUBTLE malicious samples"""
        logger.info(f"Loading real RIPE dataset from {file_path}")
        df_real = pd.read_csv(file_path)
        
        # Pre-process: Handle -1.0 values (typically represent timeouts/errors in RIPE)
        # Convert -1.0 in latency columns to a high value (e.g., 2x max) and increment failure rate
        for col in ['avg_latency', 'p95_latency', 'max_latency']:
            mask = df_real[col] < 0
            if mask.any():
                max_val = df_real[df_real[col] >= 0][col].max()
                df_real.loc[mask, col] = max_val * 1.5
                # If avg_latency was -1, it's a failure
                if col == 'avg_latency':
                    df_real.loc[mask, 'failure_rate'] = df_real.loc[mask, 'failure_rate'] + 0.1
        
        # Ensure only required columns are used
        df_real = df_real[self.feature_columns]
        df_real['label'] = 0 # Mark as honest
        
        # Add EXTREME jitter and noise to honest nodes to simulate a very noisy real-world network
        for col in self.feature_columns:
            if col == 'failure_rate':
                # Inject significant failures for honest nodes (0-10%) to confuse with malicious
                noise = np.random.beta(2, 10, len(df_real)) * 0.2
            else:
                std_val = df_real[col].std()
                if std_val == 0 or np.isnan(std_val):
                    std_val = df_real[col].mean() * 0.3 + 0.01
                # Increase noise to 50% of std - very aggressive noise
                noise = np.random.normal(0, std_val * 0.50, len(df_real))
            
            df_real[col] = (df_real[col] + noise).clip(lower=0)
        
        # Calculate stats for malicious augmentation
        means = df_real.mean()
        stds = df_real.std()
        
        # Generate NEAR-IDENTICAL malicious samples (Advanced Persistent Threats)
        n_malicious = len(df_real) // 4 
        malicious_data = {}
        for col in self.feature_columns:
            if 'latency' in col or 'var' in col:
                # Malicious nodes are almost identical (1.05x shift)
                malicious_data[col] = np.random.normal(means[col] * 1.08, stds[col] * 1.2, n_malicious)
            elif 'failure_rate' in col:
                # Malicious failure rate HEAVILY overlaps with honest (e.g. 5% vs 8%)
                malicious_data[col] = np.random.beta(4, 15, n_malicious) * 0.3
            else:
                malicious_data[col] = np.random.normal(means[col] * 1.05, stds[col] * 1.1, n_malicious)
        
        df_malicious = pd.DataFrame(malicious_data)
        df_malicious['label'] = 1 # Mark as malicious
        
        # Diagnostic prints to verify overlap
        print("\n=== CLASS OVERLAP ANALYSIS ===")
        for col in ['avg_latency', 'failure_rate', 'std_latency']:
            h_mean = df_real[col].mean()
            m_mean = df_malicious[col].mean()
            print(f" {col:15} | Honest: {h_mean:8.4f} | Malicious: {m_mean:8.4f} | Diff: {((m_mean/h_mean)-1)*100:5.1f}%")
        
        # Combine and shuffle
        df_combined = pd.concat([df_real, df_malicious]).sample(frac=1).reset_index(drop=True)
        
        # Correlation check
        corr = df_combined.corr()['label'].sort_values(ascending=False)
        print("\nTop Feature Correlations with Label:")
        print(corr.head(5))
        print("=" * 30 + "\n")
        
        # Final clip
        for col in self.feature_columns:
            df_combined[col] = df_combined[col].clip(lower=0)
            
        logger.info(f"Final dataset prepared: {len(df_combined)} samples ({len(df_real)} honest, {n_malicious} malicious)")
        return df_combined

    def train(self, data_path=None):
        """Train and evaluate the ensemble models"""
        if data_path and os.path.exists(data_path):
            df = self.load_ripe_dataset(data_path)
        else:
            logger.warning("Real dataset not found, falling back to synthetic generation")
            df = self.generate_synthetic_data(n_samples=2000)
            
        X = df[self.feature_columns]
        y = df['label']
        
        # Handle Missing Values (NaNs) early
        logger.info("Imputing missing values...")
        X_imputed = self.imputer.fit_transform(X)
        X_df = pd.DataFrame(X_imputed, columns=self.feature_columns)
        
        X_train, X_test, y_train, y_test = train_test_split(X_df, y, test_size=0.2, random_state=42)
        
        # Transform skewed distributions and scale
        logger.info("Applying PowerTransform and Scaling...")
        X_train_trans = self.transformer.fit_transform(X_train)
        X_train_scaled = self.scaler.fit_transform(X_train_trans)
        
        X_test_trans = self.transformer.transform(X_test)
        X_test_scaled = self.scaler.transform(X_test_trans)
        
        # 1. Random Forest (Supervised)
        logger.info("Training Random Forest backbone...")
        rf = RandomForestClassifier(n_estimators=100, random_state=42)
        rf.fit(X_train_scaled, y_train)
        
        # 2. Isolation Forest (Unsupervised Behavioral)
        logger.info("Training Isolation Forest backbone...")
        iso = IsolationForest(contamination=0.2, random_state=42)
        iso.fit(X_train_scaled)
        
        # 3. Graph Anomaly (Network-based / Local Density)
        logger.info("Training Graph Anomaly (Local Outlier Factor)...")
        # novelty=True allows using predict and score_samples on new data
        lof = LocalOutlierFactor(n_neighbors=20, contamination=0.2, novelty=True)
        lof.fit(X_train_scaled)
        
        # --- PREPARE STACKING FOR META-LEARNER ---
        logger.info("Preparing stacking features for Meta-Learner...")
        
        # RF Probabilities
        rf_probs_train = rf.predict_proba(X_train_scaled)[:, 1]
        
        # ISO Scores (Normalized)
        iso_scores_train = -iso.decision_function(X_train_scaled)
        iso_min, iso_max = iso_scores_train.min(), iso_scores_train.max()
        iso_norm_train = (iso_scores_train - iso_min) / (iso_max - iso_min + 1e-9)
        
        # LOF Scores (Normalized)
        lof_scores_train = -lof.score_samples(X_train_scaled)
        lof_min, lof_max = lof_scores_train.min(), lof_scores_train.max()
        lof_norm_train = (lof_scores_train - lof_min) / (lof_max - lof_min + 1e-9)
        
        stack_X_train = np.column_stack([rf_probs_train, iso_norm_train, lof_norm_train])
        
        # 4. Meta-Learner (Gradient Boosting)
        logger.info("Training Meta-Learner...")
        meta = GradientBoostingClassifier(random_state=42)
        meta.fit(stack_X_train, y_train)
        
        # --- EVALUATION ---
        logger.info("Evaluating Individual and Ensemble Models...")
        
        # 1. RF Performance
        y_pred_rf = rf.predict(X_test_scaled)
        
        # 2. ISO Performance
        iso_scores_test = -iso.decision_function(X_test_scaled)
        iso_norm_test = np.clip((iso_scores_test - iso_min) / (iso_max - iso_min + 1e-9), 0, 1)
        y_pred_iso = (iso_norm_test > 0.5).astype(int)
        
        # 3. LOF Performance
        lof_scores_test = -lof.score_samples(X_test_scaled)
        lof_norm_test = np.clip((lof_scores_test - lof_min) / (lof_max - lof_min + 1e-9), 0, 1)
        y_pred_lof = (lof_norm_test > 0.5).astype(int)
        
        # 4. Ensemble Performance
        rf_probs_test = rf.predict_proba(X_test_scaled)[:, 1]
        stack_X_test = np.column_stack([rf_probs_test, iso_norm_test, lof_norm_test])
        y_pred_meta = meta.predict(stack_X_test)
        y_prob_meta = meta.predict_proba(stack_X_test)[:, 1]
        
        from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score, confusion_matrix, roc_curve, auc
        import matplotlib.pyplot as plt
        import seaborn as sns
        
        def get_metrics(y_true, y_pred):
            return {
                'acc': float(accuracy_score(y_true, y_pred)),
                'prec': float(precision_score(y_true, y_pred, zero_division=0)),
                'rec': float(recall_score(y_true, y_pred, zero_division=0)),
                'f1': float(f1_score(y_true, y_pred, zero_division=0))
            }

        m_rf = get_metrics(y_test, y_pred_rf)
        m_iso = get_metrics(y_test, y_pred_iso)
        m_lof = get_metrics(y_test, y_pred_lof)
        m_meta = get_metrics(y_test, y_pred_meta)
        
        # Store results in JSON
        performance_data = {
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'dataset_info': {
                'total_samples': len(df),
                'honest_samples': int(len(df[df['label'] == 0])),
                'malicious_samples': int(len(df[df['label'] == 1]))
            },
            'models': {
                'random_forest': m_rf,
                'isolation_forest': m_iso,
                'graph_anomaly_lof': m_lof,
                'ensemble_meta': m_meta
            }
        }
        
        metrics_json_path = os.path.join(self.output_path, 'performance_metrics.json')
        with open(metrics_json_path, 'w') as f:
            json.dump(performance_data, f, indent=4)
        logger.info(f"Performance metrics saved to {metrics_json_path}")

        print("\n" + "="*60)
        print(f"{'MODEL':<20} | {'ACC':<6} | {'PREC':<6} | {'REC':<6} | {'F1':<6}")
        print("-" * 60)
        print(f"{'Random Forest':<20} | {m_rf['acc']:>5.2%} | {m_rf['prec']:>5.2%} | {m_rf['rec']:>5.2%} | {m_rf['f1']:>5.2%}")
        print(f"{'Isolation Forest':<20} | {m_iso['acc']:>5.2%} | {m_iso['prec']:>5.2%} | {m_iso['rec']:>5.2%} | {m_iso['f1']:>5.2%}")
        print(f"{'Graph Anomaly (LOF)':<20} | {m_lof['acc']:>5.2%} | {m_lof['prec']:>5.2%} | {m_lof['rec']:>5.2%} | {m_lof['f1']:>5.2%}")
        print(f"{'Ensemble (Meta)':<20} | {m_meta['acc']:>5.2%} | {m_meta['prec']:>5.2%} | {m_meta['rec']:>5.2%} | {m_meta['f1']:>5.2%}")
        print("="*60 + "\n")
        
        # Generate Visualization - Accuracy Only
        plt.figure(figsize=(10, 6))
        
        models_labels = ['Random Forest', 'Isolation Forest', 'Graph (LOF)', 'Ensemble']
        accuracies = [m_rf['acc'], m_iso['acc'], m_lof['acc'], m_meta['acc']]
        colors = ['skyblue', 'salmon', 'khaki', 'lightgreen']
        
        bars = plt.bar(models_labels, accuracies, color=colors)
        plt.ylabel('Accuracy Score')
        plt.title('Model Accuracy Comparison')
        plt.ylim(0, 1.1)
        
        # Add labels on top of bars
        for bar in bars:
            height = bar.get_height()
            plt.text(bar.get_x() + bar.get_width()/2., height + 0.02,
                    f'{height:.2%}', ha='center', va='bottom')
        
        plt.tight_layout()
        graph_path = os.path.join(self.output_path, 'accuracy_comparison.png')
        plt.savefig(graph_path)
        logger.info(f"Accuracy comparison graph saved to {graph_path}")
        
        # Save artifacts
        os.makedirs(self.output_path, exist_ok=True)
        joblib.dump({
            'rf': rf, 
            'iso': iso, 
            'lof': lof, 
            'meta': meta, 
            'scaler': self.scaler, 
            'imputer': self.imputer,
            'transformer': self.transformer,
            'iso_bounds': {'min': iso_min, 'max': iso_max},
            'lof_bounds': {'min': lof_min, 'max': lof_max},
            'feature_cols': self.feature_columns
        }, os.path.join(self.output_path, 'ripe_ensemble_full.joblib'))
        
        logger.info(f"✅ Full ensemble saved to {self.output_path}")

if __name__ == "__main__":
    trainer = RIPEEnsembleTrainer("models")
    # Path to the real RIPE dataset
    dataset_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "ripe_monitoring_dataset.csv")
    trainer.train(dataset_path)
