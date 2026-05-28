#!/usr/bin/env python3
"""
Enhanced ML Consensus Engine integrating ML_MINOR capabilities
Combines RF + IF fusion with EWMA smoothing and 4-tier mitigation
"""

import os
import json
import math
import socket
from dataclasses import dataclass, asdict
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
import warnings
from collections import defaultdict
from typing import Dict, List, Tuple, Optional
import numpy as np
import pandas as pd
import networkx as nx
from sklearn.ensemble import RandomForestClassifier, IsolationForest
from sklearn.preprocessing import StandardScaler, MinMaxScaler
import joblib
import logging
import hashlib
import time
from datetime import datetime, timedelta
import asyncio

warnings.filterwarnings("ignore", category=DeprecationWarning)
warnings.filterwarnings("ignore", category=UserWarning)

# Set debug level
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

class MitigationDecision:
    def __init__(self, status: str, action: str, shard: str):
        self.status = status  # HEALTHY/SUSPICIOUS/FAULTY/MALICIOUS
        self.action = action  # ALLOW/WARN/QUARANTINE/SLASHED
        self.shard = shard    # PRIMARY/MONITORING/QUARANTINE/SLASHED

class EnhancedMLConsensusEngine:
    """
    Enhanced ML consensus engine with ML_MINOR integration
    """
    
    # Shard constants
    PRIMARY = "PRIMARY"
    MONITORING = "MONITORING"
    QUARANTINE = "QUARANTINE"
    SLASHED = "SLASHED"
    
    def __init__(self, node_id: str, alpha: float = 0.3, iso_contamination: float = 0.15):
        self.node_id = node_id
        self.alpha = alpha  # EWMA smoothing factor
        self.iso_contamination = iso_contamination
        
        # History buffers
        self.node_latency_history = defaultdict(list)
        self.node_failure_history = defaultdict(list)
        self.history_window_size = 50
        
        # ML Models (ML_MINOR approach)
        self.rf_model = None
        self.iso_model = None
        self.meta_model = None  # Gradient Boosting meta-learner
        self.rf_scaler = None
        self.iso_scaler = None
        self.models_loaded = False
        
        # Feature columns
        self.rf_feature_cols = []
        self.behavioral_cols = []
        
        # Load ML_MINOR models
        self.load_enhanced_models()
        
        # Enhanced reputation tracking with EWMA
        self.reputation = {}  # node_id -> current_reputation
        self.reputation_history = defaultdict(list)  # node_id -> [reputation_history]
        self.ewma_reputations = {}  # node_id -> ewma_reputation
        
        # Graph for network analysis
        self.graph = nx.DiGraph()
        
        # Enhanced mitigation thresholds (4-tier)
        self.HEALTHY_T = 0.8
        self.SUSPICIOUS_T = 0.5
        self.FAULTY_T = 0.2
        
        # Consensus tracking
        self.consensus_votes = defaultdict(list)  # epoch_id -> [votes]
        self.consensus_decisions = {}  # epoch_id -> consensus_decision
        
        # Mitigation tracking
        self.mitigation_actions = {}  # node_id -> MitigationDecision
        
        # REAL SHARDING: 4 parallel shards with local processing
        self.shards = {
            'PRIMARY': [],      # High reputation nodes
            'MONITORING': [],  # Medium reputation nodes  
            'QUARANTINE': [],  # Low reputation nodes
            'SLASHED': []      # Malicious nodes
        }
        
        # Persistence
        self.state_file = os.path.join(os.path.dirname(__file__), '..', f'reputation_state_{self.node_id}.json')
        self.load_state()
        
        self.shard_engines = {}  # shard_id -> local ML engine
        self.shard_results = {}  # shard_id -> local results
        
        logger.info(f"EnhancedMLConsensusEngine initialized for node {node_id}")

    def get_all_nodes_status(self) -> Dict[str, Dict]:
        """Get the current status and reputation for all known nodes"""
        status_map = {}
        # Get all unique nodes from our tracking dicts
        all_nodes = set(self.reputation.keys()) | set(self.ewma_reputations.keys()) | set(self.mitigation_actions.keys())
        
        for nid in all_nodes:
            rep = self.reputation.get(nid, 0.95)
            ewma = self.ewma_reputations.get(nid, 0.95)
            decision = self.mitigation_actions.get(nid)
            
            if decision:
                status_map[nid] = {
                    "reputation": rep,
                    "ewma_reputation": ewma,
                    "status": decision.status,
                    "action": decision.action,
                    "shard": decision.shard
                }
            else:
                # Default for nodes with no mitigation decision yet
                mitigation = self.apply_mitigation_policy(ewma)
                status_map[nid] = {
                    "reputation": rep,
                    "ewma_reputation": ewma,
                    "status": mitigation.status,
                    "action": mitigation.action,
                    "shard": mitigation.shard
                }
        return status_map

    def get_shard_distribution(self) -> Dict[str, int]:
        """Get the number of nodes in each shard"""
        dist = {"PRIMARY": 0, "MONITORING": 0, "QUARANTINE": 0, "SLASHED": 0}
        for nid, ewma in self.ewma_reputations.items():
            decision = self.apply_mitigation_policy(ewma)
            dist[decision.shard] += 1
        return dist
    
    def save_state(self):
        """Save current reputation state to disk"""
        try:
            state = {
                'reputation': self.reputation,
                'ewma_reputations': self.ewma_reputations,
                'last_updated': datetime.now().isoformat()
            }
            with open(self.state_file, 'w') as f:
                json.dump(state, f, indent=4)
            logger.info(f"💾 Saved reputation state for {len(self.reputation)} nodes")
        except Exception as e:
            logger.error(f"Failed to save reputation state: {e}")

    def load_state(self):
        """Load reputation state from disk"""
        if os.path.exists(self.state_file):
            try:
                with open(self.state_file, 'r') as f:
                    state = json.load(f)
                self.reputation = state.get('reputation', {})
                self.ewma_reputations = state.get('ewma_reputations', {})
                logger.info(f"📂 Loaded reputation state for {len(self.reputation)} nodes")
            except Exception as e:
                logger.error(f"Failed to load reputation state: {e}")
        else:
            logger.info("No existing reputation state found, starting fresh")

    def load_enhanced_models(self):
        """Load ML_MINOR models with proper scaler handling"""
        try:
            # Try multiple possible paths for models
            possible_paths = [
                os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'ML_MINOR', 'models'),
                os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))), 'ML_MINOR', 'models'),
                os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', 'ML_MINOR', 'models')),
                os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'ML_MINOR', 'models')),
            ]
            
            model_path = None
            for path in possible_paths:
                if os.path.exists(path) and os.path.isfile(os.path.join(path, 'rf_backbone.joblib')):
                    model_path = path
                    logger.info(f"Found models at: {model_path}")
                    break
            
            if not model_path:
                raise FileNotFoundError(f"Could not find models in any of these paths: {possible_paths}")
            
            # Load Random Forest model
            rf_artifact = joblib.load(os.path.join(model_path, 'rf_backbone.joblib'))
            self.rf_model = rf_artifact['model']
            self.rf_feature_cols = list(rf_artifact['feature_cols'])
            
            # CRITICAL FIX: Load the saved scaler from artifact
            if 'scaler' in rf_artifact and rf_artifact['scaler'] is not None:
                self.rf_scaler = rf_artifact['scaler']
                logger.info(f"✅ Loaded trained RF scaler from artifact")
            else:
                # Fallback: create a new scaler (will need fitting)
                rf_scaler_type = rf_artifact.get('scaler_type', 'standard')
                if rf_scaler_type == 'minmax':
                    self.rf_scaler = MinMaxScaler()
                else:
                    self.rf_scaler = StandardScaler()
                logger.warning("⚠️ No trained scaler found in RF artifact, created new scaler")
            
            # Load Isolation Forest model
            iso_artifact = joblib.load(os.path.join(model_path, 'iso_backbone.joblib'))
            self.iso_model = iso_artifact['model']
            # Handle different model artifact structures
            if isinstance(iso_artifact, dict):
                self.behavioral_cols = list(iso_artifact.get('behavioral_cols', iso_artifact.get('feature_cols', [])))
                self.iso_scaler = iso_artifact.get('scaler')
                self.iso_min = iso_artifact.get('iso_min', -0.5)
                self.iso_max = iso_artifact.get('iso_max', 0.5)
            else:
                # If iso_artifact is the model itself, use RF features as fallback
                self.behavioral_cols = self.rf_feature_cols
                self.iso_scaler = None
                self.iso_min = -0.5
                self.iso_max = 0.5
            
            # Load Gradient Boosting meta-learner if available
            meta_path = os.path.join(model_path, 'meta_learner.joblib')
            if os.path.exists(meta_path):
                try:
                    meta_artifact = joblib.load(meta_path)
                    if isinstance(meta_artifact, dict):
                        self.meta_model = meta_artifact['model']
                    else:
                        self.meta_model = meta_artifact
                    logger.info("✅ Loaded Gradient Boosting meta-learner")
                except Exception as e:
                    logger.warning(f"⚠️ Could not load meta-learner: {e}")
                    self.meta_model = None
            else:
                logger.info("ℹ️ No meta-learner found, using RF+ISO fusion only")
            
            # CRITICAL FIX: Add compatibility aliases for epoch_manager integration
            self.feature_cols = self.rf_feature_cols  # Alias for epoch_manager
            self.scaler = self.rf_scaler  # Alias for epoch_manager
            self.scaler_fitted = hasattr(self.rf_scaler, 'mean_') if self.rf_scaler else False
            
            self.models_loaded = True
            
            logger.info(f"✅ Loaded ML_MINOR enhanced models")
            logger.info(f"RF features: {len(self.rf_feature_cols)}")
            logger.info(f"Behavioral features: {len(self.behavioral_cols)}")
            logger.info(f"Scaler fitted: {self.scaler_fitted}")
            
        except Exception as e:
            logger.error(f"❌ Failed to load enhanced models: {e}")
            logger.info("Will fall back to basic consensus")
    
    def update_node_reputation(self, node_id: str, trust_score: float):
        """Simple method to update node reputation from trust score"""
        try:
            # Store reputation
            self.reputation[node_id] = trust_score
            self.reputation_history[node_id].append(trust_score)
            
            # Get previous for logging continuity
            prev_val = self.ewma_reputations.get(node_id, trust_score)
            
            # Apply EWMA smoothing
            smoothed_reputation = self.apply_ewma_smoothing(node_id, trust_score)
            
            # Apply mitigation policy
            decision = self.apply_mitigation_policy(smoothed_reputation)
            self.mitigation_actions[node_id] = decision
            
            # Final Step: Persist this local update
            self.save_state()
            
            logger.debug(f"Reputation Continuity for {node_id}: {(prev_val or 0.0):.4f} (prev) -> {(smoothed_reputation or 0.0):.4f} (new)")
            
        except Exception as e:
            logger.error(f"Error updating reputation for {node_id}: {e}")
    
    def apply_mitigation_policy(self, reputation_score: float) -> MitigationDecision:
        """Apply 4-tier mitigation policy from ML_MINOR"""
        if reputation_score > self.HEALTHY_T:
            return MitigationDecision(status="HEALTHY", action="ALLOW", shard="PRIMARY")
        elif reputation_score > self.SUSPICIOUS_T:
            return MitigationDecision(status="SUSPICIOUS", action="WARN", shard="MONITORING")
        elif reputation_score > self.FAULTY_T:
            return MitigationDecision(status="FAULTY", action="QUARANTINE", shard="QUARANTINE")
        else:
            return MitigationDecision(status="MALICIOUS", action="SLASHED", shard="SLASHED")
    
    def normalize_0_1(self, arr: np.ndarray, mn: float, mx: float) -> np.ndarray:
        """Normalize array to 0-1 range"""
        return (arr - mn) / (mx - mn + 1e-12)

    def calculate_batch_reputation(self, features_list: List[Dict]) -> List[float]:
        """Vectorized batch reputation calculation for high performance"""
        if not features_list:
            return []
        
        try:
            # 1. Prepare RF Feature Matrix
            rf_data = []
            for feat in features_list:
                row = [float(feat.get(col, 0.0)) for col in self.rf_feature_cols]
                rf_data.append(row)
            
            rf_matrix = np.array(rf_data)
            if hasattr(self.rf_scaler, 'mean_'):
                rf_scaled = self.rf_scaler.transform(rf_matrix)
            else:
                rf_scaled = rf_matrix
            
            # Batch RF Prediction
            rf_probs = self.rf_model.predict_proba(rf_scaled)[:, 1]
            
            # 2. Prepare ISO Feature Matrix
            iso_data = []
            for feat in features_list:
                row = [float(feat.get(col, 0.0)) for col in self.behavioral_cols]
                iso_data.append(row)
            
            iso_matrix = np.array(iso_data)
            if self.iso_scaler and hasattr(self.iso_scaler, 'mean_'):
                iso_scaled = self.iso_scaler.transform(iso_matrix)
            else:
                iso_scaled = iso_matrix
                
            # Batch ISO Prediction
            iso_scores = -self.iso_model.decision_function(iso_scaled)
            iso_norms = np.clip((iso_scores - self.iso_min) / (self.iso_max - self.iso_min + 1e-12), 0.0, 1.0)
            
            # 3. Fusion (Vectorized)
            if self.meta_model is not None:
                meta_input = np.column_stack((rf_probs, iso_norms, np.zeros_like(rf_probs)))
                meta_probs = self.meta_model.predict_proba(meta_input)
                reputations = meta_probs[:, 1] if meta_probs.shape[1] > 1 else meta_probs[:, 0]
            else:
                iso_reps = 1.0 - iso_norms
                reputations = (0.7 * rf_probs) + (0.3 * iso_reps)
            
            return np.clip(reputations, 0.0, 1.0).tolist()
            
        except Exception as e:
            logger.error(f"Error in batch reputation calculation: {e}")
            return [0.5] * len(features_list)
    
    def calculate_enhanced_reputation(self, features: Dict) -> float:
        """Calculate enhanced reputation using ML models"""
        try:
            # Debug: Log the features being passed
            logger.debug(f"Features passed to ML model: {features}")

            # Validate required features to avoid silent garbage input
            missing_rf = [c for c in self.rf_feature_cols if c not in features]
            missing_beh = [c for c in self.behavioral_cols if c not in features]
            if missing_rf or missing_beh:
                logger.error(f"Missing required features (rf={missing_rf}, behavioral={missing_beh})")
                return 0.5
            
            # Prepare RF features
            rf_features = []
            for col in self.rf_feature_cols:
                val = features.get(col, 0.0)
                rf_features.append(float(val))
            
            logger.debug(f"RF features prepared: {rf_features}")
            logger.debug(f"Expected RF features: {self.rf_feature_cols}")
            
            # Scale RF features
            rf_input = np.array(rf_features).reshape(1, -1)
            
            # CRITICAL FIX: Check if scaler is properly fitted from trained artifact
            if not hasattr(self.rf_scaler, 'mean_'):
                logger.error("❌ RF scaler not fitted - predictions will be invalid!")
                logger.error("   The scaler should be loaded from the trained model artifact.")
                logger.error("   Falling back to unscaled features (accuracy will suffer).")
                rf_scaled = rf_input  # Use unscaled as fallback
            else:
                # CRITICAL FIX: Use transform() NOT fit_transform() - scaler is already trained
                rf_scaled = self.rf_scaler.transform(rf_input)
            
            logger.debug(f"RF features scaled: {rf_scaled}")
            
            # Get RF probability
            rf_prob = float(self.rf_model.predict_proba(rf_scaled)[:, 1][0])
            logger.debug(f"RF probability: {rf_prob}")
            
            # Prepare behavioral features for Isolation Forest
            beh_features = []
            for col in self.behavioral_cols:
                val = features.get(col, 0.0)
                beh_features.append(float(val))
            
            logger.debug(f"Behavioral features prepared: {beh_features}")
            
            # Scale behavioral features
            beh_input = np.array(beh_features).reshape(1, -1)
            
            # ISO scaler must come from trained artifact; do not fit on dummy data.
            if self.iso_scaler is not None:
                if not hasattr(self.iso_scaler, 'mean_'):
                    logger.error("❌ ISO scaler not fitted - skipping behavioral scaling")
                    beh_scaled = beh_input
                else:
                    beh_scaled = self.iso_scaler.transform(beh_input)
            else:
                beh_scaled = beh_input  # Skip scaling if no scaler
            
            # Get Isolation Forest score (normalized)
            iso_score = float(-self.iso_model.decision_function(beh_scaled)[0])
            logger.debug(f"ISO score: {iso_score}")
            
            # Normalize ISO score using trained bounds
            iso_norm = float(np.clip((iso_score - self.iso_min) / (self.iso_max - self.iso_min + 1e-12), 0.0, 1.0))
            logger.debug(f"ISO normalized: {iso_norm}")
            
            # Fusion approach: Use meta-learner if available, otherwise 70/30 weighted fusion
            if self.meta_model is not None:
                # Use Gradient Boosting meta-learner (spec-compliant)
                meta_features = np.array([[rf_prob, iso_norm, 0.0]])  # 3rd feature placeholder for graph
                meta_proba = self.meta_model.predict_proba(meta_features)[0]
                # CRITICAL FIX: RF model predicts Class 1 = HONEST, so use probability directly as reputation
                reputation = meta_proba[1] if len(meta_proba) > 1 else meta_proba[0]  # Probability of honest
                logger.debug(f"Meta-learner reputation: {reputation}")
            else:
                # CRITICAL FIX: RF model predicts Class 1 = HONEST, so rf_prob IS the reputation
                # ISO detects anomalies (higher = more anomalous), so invert it
                iso_reputation = 1.0 - iso_norm
                # Fallback: 70% RF (honest probability) + 30% ISO (honest probability)
                reputation = (0.7 * rf_prob) + (0.3 * iso_reputation)
            
            reputation = float(np.clip(reputation, 0.0, 1.0))
            logger.debug(f"Final reputation: {reputation}")
            
            return reputation
            
        except Exception as e:
            logger.error(f"Error calculating enhanced reputation: {e}")
            return 0.5
    
    def apply_ewma_smoothing(self, node_id: str, current_reputation: float) -> float:
        """Apply EWMA smoothing to reputation with CORRECT formula"""
        if node_id not in self.ewma_reputations:
            # Initialize with current reputation
            self.ewma_reputations[node_id] = current_reputation
            return current_reputation
        
        # CRITICAL FIX: Correct EWMA formula - weight NEW data more (alpha=0.3)
        # Wrong: ewma = alpha * old + (1-alpha) * new  # This weights history 70%
        # Correct: ewma = alpha * new + (1-alpha) * old  # This weights new data 30%
        ewma_rep = self.alpha * current_reputation + (1.0 - self.alpha) * self.ewma_reputations[node_id]
        self.ewma_reputations[node_id] = ewma_rep
        
        return ewma_rep
    
    async def calculate_enhanced_reputation_async(self, features: Dict) -> float:
        """Async wrapper for calculate_enhanced_reputation to avoid blocking event loop"""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.calculate_enhanced_reputation, features)
    
    async def evaluate_node_async(self, node_id: str, features: Dict) -> Tuple[float, MitigationDecision]:
        """Async wrapper for evaluate_node to avoid blocking event loop"""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.evaluate_node, node_id, features)
    
    def evaluate_node(self, node_id: str, features: Dict) -> Tuple[float, MitigationDecision]:
        """Evaluate node and return reputation with mitigation decision"""
        # Calculate raw reputation
        raw_reputation = self.calculate_enhanced_reputation(features)
        
        # Apply EWMA smoothing
        smoothed_reputation = self.apply_ewma_smoothing(node_id, raw_reputation)
        
        # Store reputation
        self.reputation[node_id] = smoothed_reputation
        self.reputation_history[node_id].append(smoothed_reputation)
        
        # Apply mitigation policy
        decision = self.apply_mitigation_policy(smoothed_reputation)
        self.mitigation_actions[node_id] = decision
        
        return smoothed_reputation, decision
    
    def extract_features_from_report(self, report: Dict) -> Dict:
        """Extract features from a single monitoring report (singular)"""
        features = {}
        
        # Basic monitoring features
        features['accuracy'] = report.get('accuracy', 0.0)
        features['false_positive_rate'] = report.get('false_positive_rate', 0.0)
        features['false_negative_rate'] = report.get('false_negative_rate', 0.0)
        features['avg_rt_error'] = report.get('avg_rt_error', 0.0)
        features['max_rt_error'] = report.get('max_rt_error', 0.0)
        features['peer_agreement_rate'] = report.get('peer_agreement_rate', 0.0)
        features['historical_accuracy'] = report.get('historical_accuracy', 0.0)
        features['accuracy_std_dev'] = report.get('accuracy_std_dev', 0.0)
        features['report_consistency'] = report.get('report_consistency', 0.0)
        features['sudden_change_score'] = report.get('sudden_change_score', 0.0)
        features['ssl_accuracy'] = report.get('ssl_accuracy', 0.0)
        features['uptime_deviation'] = report.get('uptime_deviation', 0.0)
        features['rt_consistency'] = report.get('rt_consistency', 0.0)
        
        # Behavioral features for anomaly detection
        features['itt_jitter'] = report.get('itt_jitter', 0.0)
        features['response_time_variance'] = report.get('response_time_variance', 0.0)
        features['report_frequency'] = report.get('report_frequency', 0.0)
        features['timeout_rate'] = report.get('timeout_rate', 0.0)
        features['error_burst_score'] = report.get('error_burst_score', 0.0)
        
        return features
    
    def extract_features_from_reports(self, reports: List[Dict]) -> pd.DataFrame:
        """Extract features from multiple reports and return DataFrame (plural - for epoch_manager)"""
        if not reports:
            return pd.DataFrame()
        
        features_list = []
        for report in reports:
            features = self.extract_features_from_report(report)
            features_list.append(features)
        
        df = pd.DataFrame(features_list)
        return df
    
    def process_consensus_round(self, epoch_id: str, reports: List[Dict]) -> Dict:
        """Process consensus round with enhanced ML evaluation (legacy compatibility method)"""
        # CRITICAL FIX: Add compatibility alias - this is called by some legacy code
        # Delegate to the main process_epoch_consensus method
        return self.process_epoch_consensus(int(epoch_id) if isinstance(epoch_id, str) and epoch_id.isdigit() else epoch_id, reports)
    
    def process_epoch_consensus(self, epoch_id: int, reports: List[Dict]) -> Dict:
        """
        Process epoch consensus using ML models - MAIN CONSENSUS METHOD
        This is called by epoch_manager to evaluate all reports for an epoch
        """
        logger.info(f"🚀 STARTING SHARDED CONSENSUS for epoch {epoch_id}")
        
        results = {
            'epoch_id': epoch_id,
            'engine_type': 'ML_Enhanced_Sharding',
            'reputations': {},
            'ewma_reputations': {},
            'mitigation_actions': {},
            'shard_distribution': {
                'PRIMARY': 0,
                'MONITORING': 0,
                'QUARANTINE': 0,
                'SLASHED': 0
            },
            'alpha': self.alpha,
            'processing_time_ms': 0
        }
        
        start_time = time.time()
        
        # Group reports by sender for proper evaluation
        reports_by_sender = {}
        for r in reports:
            sender = r.get("node_address") or r.get("sender_id") or r.get("node_id") or r.get("received_from")
            if sender:
                reports_by_sender.setdefault(sender, []).append(r)
        
        # Assign nodes to shards based on CURRENT reputation
        current_shards = {
            'PRIMARY': [],
            'MONITORING': [],
            'QUARANTINE': [],
            'SLASHED': []
        }
        
        for sender_id in reports_by_sender.keys():
            rep = self.ewma_reputations.get(sender_id, 0.90)
            if rep > self.HEALTHY_T:
                current_shards['PRIMARY'].append(sender_id)
            elif rep > self.SUSPICIOUS_T:
                current_shards['MONITORING'].append(sender_id)
            elif rep > self.FAULTY_T:
                current_shards['QUARANTINE'].append(sender_id)
            else:
                current_shards['SLASHED'].append(sender_id)
        
        logger.info(f"Shard assignments: {[(k, len(v)) for k, v in current_shards.items()]}")
        
        # High Performance Pass 1: Extract features for ALL nodes
        all_node_ids = list(reports_by_sender.keys())
        features_to_predict = []
        for sender_id in all_node_ids:
            sender_reports = reports_by_sender[sender_id]
            # Extract per‑node features (no extra context argument)
            features = self.extract_features_from_reports(sender_reports)
            features['collusion_score'] = 0.0
            features_to_predict.append(features)
        
        # High Performance Pass 2: Batch Predict reputations (Vectorized)
        batch_reputations = self.calculate_batch_reputation(features_to_predict)
        
        # High Performance Pass 3: Apply smoothing and policies
        for i, sender_id in enumerate(all_node_ids):
            reputation = batch_reputations[i]
            
            # Apply EWMA smoothing
            smoothed_rep = self.apply_ewma_smoothing(sender_id, reputation)
            
            # Update internal state
            self.reputation[sender_id] = smoothed_rep
            self.reputation_history[sender_id].append(smoothed_rep)
            
            # Apply mitigation
            mitigation = self.apply_mitigation_policy(smoothed_rep)
            self.mitigation_actions[sender_id] = mitigation
            
            # Store in results
            results['reputations'][sender_id] = smoothed_rep
            results['ewma_reputations'][sender_id] = smoothed_rep
            results['mitigation_actions'][sender_id] = {
                'status': mitigation.status,
                'action': mitigation.action,
                'shard': mitigation.shard
            }
            results['shard_distribution'][mitigation.shard] += 1
            
        results['processing_time_ms'] = (time.time() - start_time) * 1000
        
        # --- HUMAN READABLE SUMMARY ---
        healthy = results['shard_distribution'].get('PRIMARY', 0)
        warning = results['shard_distribution'].get('MONITORING', 0)
        faulty = results['shard_distribution'].get('QUARANTINE', 0)
        slashed = results['shard_distribution'].get('SLASHED', 0)
        
        logger.info("=" * 60)
        logger.info(f"📊 EPOCH {results.get('epoch_id', '???')} NETWORK HEALTH")
        logger.info(f"   [✅ Healthy: {healthy}]  [⚠️ Warning: {warning}]  [🚫 Faulty: {faulty}]  [💀 Slashed: {slashed}]")
        logger.info(f"   ⏱️  Processed {len(all_node_ids)} nodes in {results['processing_time_ms']:.1f}ms")
        logger.info("=" * 60)
        
        # Final Step: Persist state after each epoch
        self.save_state()
        
        return results


        """Extract 8 statistical latency and failure features for ML consensus.
        Uses rolling history buffers (window size self.history_window_size) to compute statistics.
        Returns a dict with keys: avg_latency, latency_variance, std_latency, skewness, kurtosis, p95_latency, max_latency, failure_rate.
        """
        if not sender_reports:
            return {}

        # Extract latency values from current reports
        current_latencies = [r.get("response_ms") or r.get("response_time_ms") for r in sender_reports if r.get("response_ms") or r.get("response_time_ms")]
        # Failure indicator (1 if not reachable, else 0)
        current_failures = [0 if r.get("is_reachable", True) else 1 for r in sender_reports]

        # Update rolling latency history
        latency_hist = self.node_latency_history[sender_id]
        latency_hist.extend(current_latencies)
        if len(latency_hist) > self.history_window_size:
            del latency_hist[:len(latency_hist) - self.history_window_size]

        # Update rolling failure history
        failure_hist = self.node_failure_history[sender_id]
        failure_hist.extend(current_failures)
        if len(failure_hist) > self.history_window_size:
            del failure_hist[:len(failure_hist) - self.history_window_size]

        # Compute statistics from history (fallback to current if history empty)
        if latency_hist:
            series = pd.Series(latency_hist)
            avg_latency = series.mean()
            latency_variance = series.var()
            std_latency = series.std()
            skewness = series.skew()
            kurtosis = series.kurt()
            p95_latency = np.percentile(series, 95)
            max_latency = series.max()
        else:
            avg_latency = latency_variance = std_latency = skewness = kurtosis = p95_latency = max_latency = 0.0

        failure_rate = float(sum(failure_hist) / len(failure_hist)) if failure_hist else 0.0

        features = {
            "avg_latency": float(avg_latency),
            "latency_variance": float(latency_variance),
            "std_latency": float(std_latency),
            "skewness": float(skewness),
            "kurtosis": float(kurtosis),
            "p95_latency": float(p95_latency),
            "max_latency": float(max_latency),
            "failure_rate": float(failure_rate),
        }

        logger.debug(f"Features for sender {sender_id}: {features}")
        return features

    def _update_collusion_graph(self, reports: List[Dict]):
        """Update the collusion detection graph based on reports"""
        # Group reports by URL to find agreement patterns
        reports_by_url = {}
        for r in reports:
            url = r.get("url")
            if url:
                reports_by_url.setdefault(url, []).append(r)
        
        for url, url_reports in reports_by_url.items():
            for i in range(len(url_reports)):
                for j in range(i + 1, len(url_reports)):
                    node_i = url_reports[i].get("node_address")
                    node_j = url_reports[j].get("node_address")
                    
                    if node_i and node_j and node_i != node_j:
                        vote_i = url_reports[i].get("is_reachable")
                        vote_j = url_reports[j].get("is_reachable")
                        
                        if vote_i == vote_j:
                            # Agreement edge
                            if self.graph.has_edge(node_i, node_j):
                                self.graph[node_i][node_j]['weight'] += 1
                            else:
                                self.graph.add_edge(node_i, node_j, weight=1)
    
    def _detect_collusion(self, node_id: str, reports: List[Dict]) -> float:
        """Detect collusion for a specific node"""
        if node_id not in self.graph:
            return 0.0
        
        # Use PageRank or centralities for collusion detection
        try:
            centrality = nx.degree_centrality(self.graph).get(node_id, 0.0)
            return min(centrality * 2.0, 1.0)
        except:
            return 0.0

class MLConsensusEngine(EnhancedMLConsensusEngine):
    """Compatibility wrapper for legacy imports."""

    def load_ensemble_models(self) -> None:
        """Legacy alias to load enhanced models."""
        self.load_enhanced_models()

    def predict_malicious_probability(self, features_df: pd.DataFrame) -> pd.DataFrame:
        """
        Legacy wrapper for prediction.

        Takes a DataFrame where each row is a feature set, computes the enhanced
        reputation (probability of *honest*) via `calculate_enhanced_reputation`,
        then returns a DataFrame with a single column `p_malicious` representing
        the probability of being malicious (i.e. 1 - reputation).
        """
        if features_df.empty:
            return pd.DataFrame(columns=["p_malicious"])
        # Compute reputation for each row
        reputations = [
            self.calculate_enhanced_reputation(row.to_dict())
            for _, row in features_df.iterrows()
        ]
        # Convert to malicious probability
        malicious = [1.0 - r for r in reputations]
        return pd.DataFrame({"p_malicious": malicious})

    pass
