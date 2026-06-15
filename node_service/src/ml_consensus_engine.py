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
        self.node_ssl_history = defaultdict(list)
        self.node_agreement_history = defaultdict(list)
        self.node_report_times = defaultdict(list)
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
        self.graph_trust_scores = {}
        
        # Graph trust weights (Slide 11 Fusion)
        self.w1 = 0.30  # ReputationScore weight
        self.w2 = 0.20  # GraphTrustScore weight
        self.w3 = 0.35  # RandomForestTrust weight
        self.w4 = 0.15  # IsolationForestTrust weight
        
        # Enhanced mitigation thresholds (4-tier - Slide 19 alignment)
        self.HEALTHY_T = 0.60      # PRIMARY  : trust >= 0.60
        self.SUSPICIOUS_T = 0.38   # MONITORING: 0.38 <= trust < 0.60
        self.FAULTY_T = 0.20       # QUARANTINE: 0.20 <= trust < 0.38
        # trust < 0.20 is SLASHED tier
        
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

    def _assign_nodes_to_shards(self):
        """Assign nodes to shards based on current reputations"""
        self.shards = {
            'PRIMARY': [],
            'MONITORING': [],
            'QUARANTINE': [],
            'SLASHED': []
        }
        # Use reputations if ewma_reputations is empty
        source = self.ewma_reputations if self.ewma_reputations else self.reputation
        for node_id, rep in source.items():
            decision = self.apply_mitigation_policy(rep)
            self.shards[decision.shard].append(node_id)
        logger.info(f"Assigned nodes to shards: {[(k, len(v)) for k, v in self.shards.items()]}")

    def sync_state(self, reputations: Dict[str, float], mitigation_actions: Dict[str, Dict]):
        """Sync local state with external source of truth (e.g. leader decision)"""
        for node_id, rep in reputations.items():
            self.reputation[node_id] = rep
            self.ewma_reputations[node_id] = rep
            
        for node_id, action_dict in mitigation_actions.items():
            if isinstance(action_dict, dict):
                self.mitigation_actions[node_id] = MitigationDecision(
                    status=action_dict.get("status", "HEALTHY"),
                    action=action_dict.get("action", "ALLOW"),
                    shard=action_dict.get("shard", "PRIMARY")
                )
        
        # Re-assign shards based on new reputations
        self._assign_nodes_to_shards()
        self.save_state()

    def process_sharded_consensus(self, epoch_id: int, reports: List[Dict]) -> Dict:
        """
        Process consensus using sharded approach (delegates to process_epoch_consensus)
        """
        return self.process_epoch_consensus(epoch_id, reports)

    def process_website_consensus(self, url: str, reports: List[Dict]) -> Dict:
        """
        Calculate consensus for a specific website based on reports.
        Selection: UP/DOWN status and average latency.
        """
        if not reports:
            return {"url": url, "final_status": "DOWN", "avg_latency": 0}

        # Filter reports for this URL
        url_reports = [r for r in reports if r.get("url") == url]
        if not url_reports:
            return {"url": url, "final_status": "DOWN", "avg_latency": 0}

        # Step 1: Status Consensus (Majority Vote)
        up_votes = [1 if r.get("is_reachable", True) else 0 for r in url_reports]
        final_status = "UP" if np.mean(up_votes) >= 0.5 else "DOWN"

        # Step 2: Latency Consensus (Average of nodes that agree with the majority status)
        majority_reachable = (final_status == "UP")
        agreeing_latencies = [
            float(r.get("response_ms", r.get("response_time_ms", 0)))
            for r in url_reports
            if r.get("is_reachable", True) == majority_reachable
        ]

        avg_latency = np.mean(agreeing_latencies) if agreeing_latencies else 0

        logger.info(f"Consensus for {url}: {final_status} ({avg_latency:.1f}ms) based on {len(url_reports)} reports")
        
        return {
            "url": url,
            "final_status": final_status,
            "avg_latency": float(avg_latency)
        }

    def _update_reputations_from_consensus(self, global_verdict: Dict, reports: List[Dict]) -> Dict:
        """
        Update node reputations based on agreement with global consensus
        """
        reputation_updates = {}
        
        for report in reports:
            node_id = report.get('node_id') or report.get('node_address', 'unknown')
            status = report.get('status', 'error')
            node_verdict = 'UP' if status == 'success' or report.get('is_reachable') else 'DOWN'
            
            # Check if node agreed with global consensus
            agreed = (node_verdict == global_verdict['verdict'])
            
            # Update reputation
            current_rep = self.reputation.get(node_id, 0.95)
            if agreed:
                # Small reward for agreement
                new_rep = min(1.0, current_rep + 0.01)
            else:
                # Penalty for disagreement
                new_rep = max(0.0, current_rep - 0.15)
                
            self.reputation[node_id] = new_rep
            reputation_updates[node_id] = new_rep
            
            # ALSO update EWMA
            self.apply_ewma_smoothing(node_id, new_rep)
        
        return reputation_updates

    def get_shard_assignment(self, num_shards: int = 4) -> Dict[str, int]:
        """
        Get shard assignment based on reputation sorting
        
        Args:
            num_shards: Number of shards to create
            
        Returns:
            Dict mapping node_id -> shard_id
        """
        if not self.reputation:
            return {}
        
        # Sort nodes by reputation (high to low) 
        sorted_nodes = sorted(self.reputation.items(), key=lambda x: x[1], reverse=True)
        
        # Round-robin assignment to distribute high/low rep nodes evenly
        assignment = {}
        for i, (node_id, reputation) in enumerate(sorted_nodes):
            shard_id = i % num_shards
            assignment[node_id] = shard_id
        
        return assignment

    def get_shard_distribution(self) -> Dict[str, int]:
        """Get the number of nodes in each shard"""
        dist = {"PRIMARY": 0, "MONITORING": 0, "QUARANTINE": 0, "SLASHED": 0}
        for nid, ewma in self.ewma_reputations.items():
            decision = self.apply_mitigation_policy(ewma)
            dist[decision.shard] += 1
        return dist

    def _assign_nodes_to_shards(self):
        """Assign nodes to shards based on current reputations"""
        self.shards = {
            'PRIMARY': [],
            'MONITORING': [],
            'QUARANTINE': [],
            'SLASHED': []
        }
        for node_id, rep in self.ewma_reputations.items():
            decision = self.apply_mitigation_policy(rep)
            self.shards[decision.shard].append(node_id)
        logger.info(f"Assigned nodes to shards: {[(k, len(v)) for k, v in self.shards.items()]}")
    
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
                
                # Apply mitigation policy to loaded reputations to initialize tiers
                for nid, rep in self.reputation.items():
                    self.mitigation_actions[nid] = self.apply_mitigation_policy(rep)
                
                logger.info(f"📂 Loaded reputation state for {len(self.reputation)} nodes and initialized tiers")
            except Exception as e:
                logger.error(f"Failed to load reputation state: {e}")
        else:
            logger.info("No existing reputation state found, starting fresh")

    def load_enhanced_models(self):
        """Load ML_MINOR models with proper scaler handling"""
        try:
            # Try multiple possible paths for models
            possible_paths = [
                os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'models')),
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
                iso_min_saved = iso_artifact.get('iso_min')
                iso_max_saved = iso_artifact.get('iso_max')
            else:
                # If iso_artifact is the model itself, use RF features as fallback
                self.behavioral_cols = self.rf_feature_cols
                self.iso_scaler = None
                iso_min_saved = None
                iso_max_saved = None

            # FIX: Calibrate ISO bounds if not stored in artifact.
            # The artifact was saved without iso_min/iso_max, so we compute
            # realistic bounds by scoring a synthetic representative dataset.
            if iso_min_saved is None or iso_max_saved is None:
                try:
                    n_features = len(self.behavioral_cols)
                    # Generate synthetic samples covering the expected operating range
                    rng = np.random.default_rng(42)
                    cal_samples = rng.uniform(
                        [0] * n_features,
                        [5000, 1e7, 3000, 7000, 10000, 1.0][:n_features],
                        (1000, n_features)
                    )
                    if self.iso_scaler is not None and hasattr(self.iso_scaler, 'mean_'):
                        cal_samples = self.iso_scaler.transform(cal_samples)
                    cal_scores = -self.iso_model.decision_function(cal_samples)
                    self.iso_min = float(cal_scores.min())
                    self.iso_max = float(cal_scores.max())
                    logger.info(f"✅ Calibrated ISO bounds from synthetic data: min={self.iso_min:.4f} max={self.iso_max:.4f}")
                except Exception as cal_e:
                    logger.warning(f"⚠️ ISO calibration failed ({cal_e}), using fallback bounds")
                    self.iso_min = 0.30
                    self.iso_max = 0.35
            else:
                self.iso_min = iso_min_saved
                self.iso_max = iso_max_saved
            
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
    
    def apply_mitigation_policy(self, reputation_score: float, node_id: Optional[str] = None) -> MitigationDecision:
        """Apply 4-tier mitigation policy from ML_MINOR"""
        effective_score = reputation_score
        if node_id is not None:
            g_score = self.graph_trust_scores.get(node_id, 0.95)
            if g_score < 0.3:
                effective_score = min(effective_score, self.SUSPICIOUS_T)
                logger.info(f"Node {node_id} demoted due to low Graph Trust Score ({g_score:.4f} < 0.3)")
                
        if effective_score > self.HEALTHY_T:
            return MitigationDecision(status="HEALTHY", action="ALLOW", shard="PRIMARY")
        elif effective_score > self.SUSPICIOUS_T:
            return MitigationDecision(status="SUSPICIOUS", action="WARN", shard="MONITORING")
        elif effective_score > self.FAULTY_T:
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
            # FIX: class 0 = HONEST (high-trust), class 1 = MALICIOUS.
            # We want P(honest) as the reputation signal, so use column 0.
            rf_all_probs = self.rf_model.predict_proba(rf_scaled)
            honest_class_idx = list(self.rf_model.classes_).index(0) if 0 in self.rf_model.classes_ else 0
            rf_probs = rf_all_probs[:, honest_class_idx]
            
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
            
            # Extract previous reputations and graph trust scores
            prev_reps = []
            graph_trusts = []
            for feat in features_list:
                node_id = feat.get('node_id') or feat.get('node_address')
                prev_reps.append(self.ewma_reputations.get(node_id, 0.95))
                graph_trusts.append(self.graph_trust_scores.get(node_id, 0.95))
                
            prev_reps = np.array(prev_reps)
            graph_trusts = np.array(graph_trusts)
            
            # 3. Fusion (Vectorized)
            if self.meta_model is not None:
                meta_input = np.column_stack((rf_probs, iso_norms, 1.0 - graph_trusts))
                meta_probs = self.meta_model.predict_proba(meta_input)
                reputations = meta_probs[:, 1] if meta_probs.shape[1] > 1 else meta_probs[:, 0]
            else:
                iso_reps = 1.0 - iso_norms
                # FinalTrust = w1 * ReputationScore + w2 * GraphTrustScore + w3 * RandomForestTrust + w4 * IsolationForestTrust
                reputations = (self.w1 * prev_reps) + (self.w2 * graph_trusts) + (self.w3 * rf_probs) + (self.w4 * iso_reps)
            
            return np.clip(reputations, 0.0, 1.0).tolist()
            
        except Exception as e:
            logger.error(f"Error in batch reputation calculation: {e}")
            return [0.5] * len(features_list)
    
    def calculate_enhanced_reputation(self, features: Dict, node_id: Optional[str] = None) -> float:
        """Calculate enhanced reputation using ML models"""
        try:
            # Debug: Log the features being passed
            logger.debug(f"Features passed to ML model: {features}")

            if node_id is None:
                node_id = features.get('node_id') or features.get('node_address')

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
            # FIX: class 0 = HONEST, class 1 = MALICIOUS. Use P(honest) = class 0 probability.
            rf_all = self.rf_model.predict_proba(rf_scaled)
            honest_idx = list(self.rf_model.classes_).index(0) if 0 in self.rf_model.classes_ else 0
            rf_prob = float(rf_all[:, honest_idx][0])
            logger.debug(f"RF probability (honest): {rf_prob}")
            
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
            
            # Get previous reputation and graph trust score
            prev_rep = self.ewma_reputations.get(node_id, 0.95)
            graph_trust = self.graph_trust_scores.get(node_id, 0.95)
            
            # Fusion approach: Use meta-learner if available, otherwise weighted fusion
            if self.meta_model is not None:
                # Use Gradient Boosting meta-learner (spec-compliant)
                meta_features = np.array([[rf_prob, iso_norm, float(1.0 - graph_trust)]])  # 3rd feature for graph anomaly
                meta_proba = self.meta_model.predict_proba(meta_features)[0]
                # Meta-learner predicts Class 1 = MALICIOUS, Class 0 = HONEST
                # We need Malicious Probability for Slide 17 formula
                malicious_probability = meta_proba[1] if len(meta_proba) > 1 else meta_proba[0]
                logger.debug(f"Meta-learner malicious probability: {malicious_probability}")
            else:
                # Weighted Fusion fallback (Higher score = More Malicious for this formula)
                # MaliciousProb = w1 * (1-PrevRep) + w2 * (1-GraphTrust) + w3 * (1-RFTrust) + w4 * ISONorm
                malicious_probability = (self.w1 * (1.0 - prev_rep)) + (self.w2 * (1.0 - graph_trust)) + \
                                        (self.w3 * (1.0 - rf_prob)) + (self.w4 * iso_norm)
                logger.debug(f"Weighted Fusion malicious probability: {malicious_probability}")
            
            # 4. Reputation Calculation (Slide 17)
            # Formula: Reputation = 1 - MaliciousProbability
            reputation = 1.0 - malicious_probability
            reputation = float(np.clip(reputation, 0.0, 1.0))
            logger.debug(f"Reputation calculation (Slide 17): 1 - {malicious_probability:.4f} = {reputation:.4f}")

            return reputation
            
        except Exception as e:
            logger.error(f"Error calculating enhanced reputation: {e}")
            return 0.5
    
    def apply_ewma_smoothing(self, node_id: str, current_reputation: float) -> float:
        """Apply EWMA smoothing to reputation (Slide 18 Formula)"""
        if node_id not in self.ewma_reputations:
            # Initialize with current reputation
            self.ewma_reputations[node_id] = current_reputation
            return current_reputation

        # Slide 18 Formula: Rep_new = alpha * Rep_old + (1 - alpha) * Rep_current
        # alpha is the smoothing factor (e.g., 0.3)
        old_rep = self.ewma_reputations[node_id]
        ewma_rep = (self.alpha * old_rep) + ((1.0 - self.alpha) * current_reputation)
        self.ewma_reputations[node_id] = ewma_rep

        logger.debug(f"EWMA Update (Slide 18) for {node_id}: {self.alpha}*{old_rep:.4f} + {(1.0-self.alpha)}*{current_reputation:.4f} = {ewma_rep:.4f}")
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
        raw_reputation = self.calculate_enhanced_reputation(features, node_id)
        
        # Apply EWMA smoothing
        smoothed_reputation = self.apply_ewma_smoothing(node_id, raw_reputation)
        
        # Store reputation
        self.reputation[node_id] = smoothed_reputation
        self.reputation_history[node_id].append(smoothed_reputation)
        
        # Apply mitigation policy
        decision = self.apply_mitigation_policy(smoothed_reputation, node_id)
        self.mitigation_actions[node_id] = decision
        
        return smoothed_reputation, decision

    def extract_features_from_report(self, report: Dict, majority_verdicts: Optional[Dict[str, bool]] = None) -> Dict:
        """
        Extract features from a single monitoring report.
        Computes the 8 RIPE Atlas features for ML model.
        """
        # Default features if report is incomplete (in seconds)
        features = {
            # 8 RIPE Atlas features (in seconds)
            'avg_latency': 0.150,
            'latency_var': 0.0001,
            'std_latency': 0.010,
            'skewness': 0.0,
            'kurtosis': 0.0,
            'p95_latency': 0.180,
            'max_latency': 0.200,
            'failure_rate': 0.0,
        }
        
        # Extract node_id to track history
        node_id = report.get('node_id') or report.get('node_address', 'unknown')
        
        # Get current latency and failure status
        raw_latency = report.get('response_ms', report.get('response_time_ms', -1))
        current_latency = float(raw_latency) if raw_latency is not None else -1.0
        is_failure = (report.get('status') == 'error' or 
                      report.get('http_status', 0) == 0 or
                      current_latency < 0)
        
        # Update history buffers
        if current_latency >= 0:
            self.node_latency_history[node_id].append(current_latency)
            if len(self.node_latency_history[node_id]) > self.history_window_size:
                self.node_latency_history[node_id].pop(0)
        
        self.node_failure_history[node_id].append(1 if is_failure else 0)
        if len(self.node_failure_history[node_id]) > self.history_window_size:
            self.node_failure_history[node_id].pop(0)
            
        # Get history lists
        latencies = self.node_latency_history[node_id]
        failures = self.node_failure_history[node_id]
        
        if len(latencies) > 0:
            latency_array = np.array(latencies)
            avg_lat = float(np.mean(latency_array))
            
            # CONVERT TO SECONDS for RIPE Atlas ML model inputs
            features['avg_latency'] = avg_lat / 1000.0
            features['latency_var'] = float(np.var(latency_array)) / 1000000.0
            features['std_latency'] = float(np.std(latency_array)) / 1000.0
            
            if len(latencies) >= 3:
                mean = np.mean(latency_array)
                std = np.std(latency_array)
                if std > 0:
                    features['skewness'] = float(np.mean(((latency_array - mean) / std) ** 3))
            
            if len(latencies) >= 4:
                mean = np.mean(latency_array)
                std = np.std(latency_array)
                if std > 0:
                    features['kurtosis'] = float(np.mean(((latency_array - mean) / std) ** 4) - 3)
            
            features['p95_latency'] = float(np.percentile(latency_array, 95)) / 1000.0
            features['max_latency'] = float(np.max(latency_array)) / 1000.0
 
        if len(failures) > 0:
            features['failure_rate'] = float(np.mean(failures))
            
        return features      
        return features
    
    def _extract_features_from_reports(self, reports: List[Dict]) -> Dict[str, Dict]:
        """
        Internal method: Extract features from multiple reports per node
        """
        node_features = {}
        
        # Group reports by node
        reports_by_node = defaultdict(list)
        for report in reports:
            node_id = report.get('node_id') or report.get('node_address', 'unknown')
            reports_by_node[node_id].append(report)
            
        # Compute majority verdicts for URLs in this epoch
        majority_verdict_by_url = {}
        reports_by_url = defaultdict(list)
        for r in reports:
            url = r.get('url')
            if url:
                reports_by_url[url].append(r)
        for url, url_reports in reports_by_url.items():
            votes = [1 if r.get('is_reachable', True) else 0 for r in url_reports]
            majority_verdict_by_url[url] = (np.mean(votes) >= 0.5) if votes else True

        # Extract features for each node
        for node_id, node_reports in reports_by_node.items():
            # Process each report to update history
            latest_features = {}
            for report in node_reports:
                latest_features = self.extract_features_from_report(report, majority_verdict_by_url)
            
            node_features[node_id] = latest_features
        
        return node_features
    
    def extract_features_from_reports(self, reports: List[Dict]) -> pd.DataFrame:
        """
        Extract features from multiple reports and return DataFrame (plural - for epoch_manager)
        Uses the internal _extract_features_from_reports method for consistency
        
        Args:
            reports: List of monitoring reports
            
        Returns:
            DataFrame with 8 RIPE Atlas features per node
        """
        if not reports:
            return pd.DataFrame()
        
        # Use internal method to extract features
        node_features = self._extract_features_from_reports(reports)
        
        # Convert to DataFrame
        features_list = []
        for node_id, features in node_features.items():
            feature_row = features.copy()
            feature_row['node_id'] = node_id
            features_list.append(feature_row)
        
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
        
        # Trigger interaction graph update and calculate graph trust scores
        self._update_interaction_graph(reports)
        self.graph_trust_scores = self._calculate_graph_trust_scores()
        logger.info(f"Updated interaction graph and calculated Graph Trust Scores: {self.graph_trust_scores}")

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
        node_features_dict = self._extract_features_from_reports(reports)
        
        features_to_predict = []
        for sender_id in all_node_ids:
            features = node_features_dict.get(sender_id, {}).copy()
            features['collusion_score'] = 0.0
            features['node_id'] = sender_id  # Set node_id for calculate_batch_reputation
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
            
            # Apply mitigation with node_id parameter to enable graph-trust based demotion
            mitigation = self.apply_mitigation_policy(smoothed_rep, sender_id)
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

    def _update_interaction_graph(self, reports: List[Dict]):
        """
        Update the P2P interaction graph.
        Nodes represent blockchain participants.
        Edges represent communication or validation interactions.
        Edge weights represent frequency and node reputations.
        """
        if not hasattr(self, 'graph') or self.graph is None:
            self.graph = nx.DiGraph()
            
        # Group reports by monitored URL
        reports_by_url = {}
        for r in reports:
            sender = r.get("node_address") or r.get("node_id") or r.get("sender_id") or r.get("received_from")
            if not sender:
                continue
            if sender not in self.graph:
                self.graph.add_node(sender)
                
            # Communication interaction: increment edge with self.node_id
            if sender != self.node_id:
                if self.graph.has_edge(sender, self.node_id):
                    self.graph[sender][self.node_id]['weight'] = self.graph[sender][self.node_id].get('weight', 1.0) + 1.0
                else:
                    self.graph.add_edge(sender, self.node_id, weight=1.0)
                    
            url = r.get("url")
            if url:
                reports_by_url.setdefault(url, []).append(r)
                
        # Consensus validation interactions (agreement matches)
        for url, url_reports in reports_by_url.items():
            for i in range(len(url_reports)):
                for j in range(i + 1, len(url_reports)):
                    node_i = url_reports[i].get("node_address") or url_reports[i].get("node_id")
                    node_j = url_reports[j].get("node_address") or url_reports[j].get("node_id")
                    
                    if node_i and node_j and node_i != node_j:
                        vote_i = url_reports[i].get("is_reachable")
                        vote_j = url_reports[j].get("is_reachable")
                        
                        # Weight represents validation agreement
                        weight_modifier = 1.5 if vote_i == vote_j else 0.1
                        
                        # Scale based on current reputations
                        rep_i = self.ewma_reputations.get(node_i, 0.90)
                        rep_j = self.ewma_reputations.get(node_j, 0.90)
                        combined_trust = (rep_i + rep_j) / 2.0
                        scaled_weight = weight_modifier * combined_trust
                        
                        # Update edge node_i -> node_j
                        if self.graph.has_edge(node_i, node_j):
                            self.graph[node_i][node_j]['weight'] = self.graph[node_i][node_j].get('weight', 1.0) + scaled_weight
                        else:
                            self.graph.add_edge(node_i, node_j, weight=scaled_weight)
                            
                        # Update edge node_j -> node_i
                        if self.graph.has_edge(node_j, node_i):
                            self.graph[node_j][node_i]['weight'] = self.graph[node_j][node_i].get('weight', 1.0) + scaled_weight
                        else:
                            self.graph.add_edge(node_j, node_i, weight=scaled_weight)

    def _calculate_graph_trust_scores(self) -> Dict[str, float]:
        """
        Calculate normalized graph trust scores for all nodes in the interaction graph.
        Uses the exact pagerank and degree anomaly logic from 2ndUDScalability_Malicious.ipynb:
          pagerank_z = |(pagerank - mean) / (std + 1e-9)|
          deg = in_degree + out_degree
          deg_z = |(deg - mean) / (std + 1e-9)|
          graph_score_raw = (pagerank_z + deg_z) / 2.0
          graph_score = (graph_score_raw - min) / (max - min + 1e-9)
        Since the notebook's graph_score represents maliciousness/anomaly, we invert it
        as (1.0 - graph_score) to get the GraphTrustScore (higher is more trusted).
        """
        scores = {}
        if not self.graph or len(self.graph.nodes) == 0:
            return {}
            
        nodes_list = list(self.graph.nodes)
        if len(nodes_list) <= 1:
            return {n: 0.95 for n in nodes_list}
            
        # 1. Pagerank Centrality
        try:
            pagerank = nx.pagerank(self.graph, weight='weight')
        except Exception as e:
            logger.warning(f"Error calculating pagerank: {e}")
            pagerank = {n: 1.0 / len(nodes_list) for n in nodes_list}
            
        # 2. Degree
        in_deg = dict(self.graph.in_degree(weight="weight"))
        out_deg = dict(self.graph.out_degree(weight="weight"))
        
        pr_vals = np.array([pagerank.get(node, 0.0) for node in nodes_list])
        deg_vals = np.array([in_deg.get(node, 0.0) + out_deg.get(node, 0.0) for node in nodes_list])
        
        # Calculate means and std devs
        pr_mean = np.mean(pr_vals)
        pr_std = np.std(pr_vals)
        deg_mean = np.mean(deg_vals)
        deg_std = np.std(deg_vals)
        
        # Calculate one-sided Z-scores (only penalizing below mean)
        pr_z = np.clip((pr_mean - pr_vals) / (pr_std + 1e-9), 0.0, None)
        deg_z = np.clip((deg_mean - deg_vals) / (deg_std + 1e-9), 0.0, None)
        
        graph_score_raw = (pr_z + deg_z) / 2.0
        
        raw_min = graph_score_raw.min()
        raw_max = graph_score_raw.max()
        
        # Scale to 0-1 range
        if raw_max - raw_min > 1e-9:
            graph_score = (graph_score_raw - raw_min) / (raw_max - raw_min + 1e-9)
        else:
            graph_score = np.zeros_like(graph_score_raw)
            
        # Invert to trust score
        graph_trust_scores = 1.0 - graph_score
        
        logger.info(f"Graph Trust calculation details:")
        for idx, node in enumerate(nodes_list):
            logger.info(f"  Node {node}: PR={pr_vals[idx]:.4f} (z_anom={pr_z[idx]:.4f}), Deg={deg_vals[idx]:.4f} (z_anom={deg_z[idx]:.4f}) -> RawAnom={graph_score_raw[idx]:.4f} -> NormAnom={graph_score[idx]:.4f} -> Trust={graph_trust_scores[idx]:.4f}")
        
        
        for idx, node in enumerate(nodes_list):
            scores[node] = float(np.clip(graph_trust_scores[idx], 0.0, 1.0))
            
        return scores

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
