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
        self.shard_engines = {}  # shard_id -> local ML engine
        self.shard_results = {}  # shard_id -> local results
        
        logger.info(f"EnhancedMLConsensusEngine initialized for node {node_id}")
    
    def load_enhanced_models(self):
        """Load ML_MINOR models with proper scaler handling"""
        try:
            # Try multiple possible paths for models
            possible_paths = [
                os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'ml', 'models'),
                os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))), 'ml', 'models'),
                os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', 'ml', 'models')),
                os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'ml', 'models')),
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
            else:
                # If iso_artifact is the model itself, use RF features as fallback
                self.behavioral_cols = self.rf_feature_cols
                self.iso_scaler = None
            
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
            
            # Normalize ISO score (approximate normalization)
            iso_norm = float(np.clip(iso_score / 10.0, 0.0, 1.0))
            logger.debug(f"ISO normalized: {iso_norm}")
            
            # Fusion approach: Use meta-learner if available, otherwise 70/30 weighted fusion
            if self.meta_model is not None:
                # Use Gradient Boosting meta-learner (spec-compliant)
                meta_features = np.array([[rf_prob, iso_norm, 0.0]])  # 3rd feature placeholder for graph
                meta_proba = self.meta_model.predict_proba(meta_features)[0]
                risk = meta_proba[1] if len(meta_proba) > 1 else meta_proba[0]  # Probability of malicious
                logger.debug(f"Meta-learner risk: {risk}")
            else:
                # Fallback: 70% RF + 30% ISO fusion (original approach)
                risk = (0.7 * rf_prob) + (0.3 * iso_norm)
            
            reputation = 1.0 - float(np.clip(risk, 0.0, 1.0))
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
        logger.info(f"🤖 ML CONSENSUS RUNNING for epoch {epoch_id} with {len(reports)} reports")
        
        results = {
            'epoch_id': epoch_id,
            'engine_type': 'ML_Enhanced',
            'reputations': {},
            'ewma_reputations': {},
            'mitigation_actions': {},
            'shard_distribution': {},
            'alpha': self.alpha,
            'predictions': []  # For epoch_manager compatibility
        }
        
        # CRITICAL FIX: Group reports by sender for proper evaluation
        reports_by_sender = {}
        for r in reports:
            sender = r.get("node_address") or r.get("sender_id") or r.get("node_id") or r.get("received_from")
            if sender:
                reports_by_sender.setdefault(sender, []).append(r)
        
        logger.info(f"Grouped reports by sender: {list(reports_by_sender.keys())}")
        
        # CRITICAL FIX: Update graph for collusion detection
        self._update_collusion_graph(reports)
        
        # Evaluate each sender based on THEIR reports
        for sender_id, sender_reports in reports_by_sender.items():
            logger.info(f"Evaluating sender {sender_id} with {len(sender_reports)} reports")
            
            # Extract features from this sender's reports
            features = self._extract_features_from_reports(
                sender_reports, all_reports_context=reports
            )
            
            # CRITICAL FIX: Add collusion detection features
            collusion_score = self._detect_collusion(sender_id, reports)
            features['collusion_score'] = collusion_score
            
            # Calculate reputation using ML
            reputation = self.calculate_enhanced_reputation(features)
            
            # Apply EWMA smoothing (with corrected formula)
            smoothed_rep = self.apply_ewma_smoothing(sender_id, reputation)
            
            # Store reputations
            results['reputations'][sender_id] = smoothed_rep
            results['ewma_reputations'][sender_id] = self.ewma_reputations.get(sender_id, smoothed_rep)
            
            # Apply mitigation policy
            mitigation = self.apply_mitigation_policy(smoothed_rep)
            results['mitigation_actions'][sender_id] = {
                'status': mitigation.status,
                'action': mitigation.action,
                'shard': mitigation.shard
            }
            
            # Update shard distribution
            shard = mitigation.shard
            results['shard_distribution'][shard] = results['shard_distribution'].get(shard, 0) + 1
            
            # Add prediction for epoch_manager compatibility
            results['predictions'].append({
                'node_id': sender_id,
                'malicious_probability': 1.0 - smoothed_rep,
                'p_malicious': 1.0 - smoothed_rep,  # Alias for compatibility
                'reputation': smoothed_rep,
                'status': mitigation.status,
                'collusion_score': collusion_score
            })
            
            logger.info(f"✅ Sender {sender_id}: reputation={smoothed_rep:.4f}, status={mitigation.status}, collusion={collusion_score:.4f}")
        
        # Store consensus results
        self.consensus_decisions[epoch_id] = results
        
        logger.info(f"✅ Epoch {epoch_id} consensus completed: {len(results['reputations'])} nodes evaluated")
        return results
    
    def get_node_status(self, node_id: str) -> Optional[Dict]:
        """Get current status of a node"""
        if node_id not in self.mitigation_actions:
            return None
        
        decision = self.mitigation_actions[node_id]
        return {
            'node_id': node_id,
            'reputation': self.reputation.get(node_id, 0.0),
            'ewma_reputation': self.ewma_reputations.get(node_id, 0.0),
            'status': decision.status,
            'action': decision.action,
            'shard': decision.shard,
            'history_length': len(self.reputation_history.get(node_id, []))
        }
    
    def get_all_nodes_status(self) -> Dict:
        """Get status of all evaluated nodes"""
        return {
            node_id: self.get_node_status(node_id)
            for node_id in self.mitigation_actions.keys()
        }

    def process_epoch_consensus_legacy(self, epoch_id: int, reports: List[Dict]) -> Dict:
        """Legacy alias retained for compatibility. Uses the main (collusion-aware) implementation."""
        return self.process_epoch_consensus(epoch_id, reports)
    
    def _extract_features_from_reports(self, sender_reports: List[Dict], all_reports_context: List[Dict] = None) -> Dict:
        """Extract features from node reports for ML evaluation (internal method)"""
        if not sender_reports:
            return {}
        
        sender_id = None
        for r in sender_reports:
            sender_id = r.get("node_address") or r.get("sender_id") or r.get("node_id") or r.get("received_from")
            if sender_id:
                break
        
        # peer_agreement_rate: does this sender agree with the majority?
        agreement_scores = []
        for r in sender_reports:
            url = r.get("url")
            our_reachable = r.get("is_reachable")
            
            if all_reports_context and url is not None and our_reachable is not None:
                # Get all other nodes' votes for this URL
                peer_votes = []
                for p in all_reports_context:
                    peer_sender = p.get("node_address") or p.get("sender_id") or p.get("node_id") or p.get("received_from")
                    if (p.get("url") == url and 
                        peer_sender != sender_id and 
                        p.get("is_reachable") is not None):
                        peer_votes.append(p.get("is_reachable"))
                
                if peer_votes:
                    # Majority vote (True if >50% say reachable)
                    majority_reachable = sum(peer_votes) / len(peer_votes) > 0.5
                    agreement_scores.append(1.0 if our_reachable == majority_reachable else 0.0)
        
        peer_agreement_rate = sum(agreement_scores) / len(agreement_scores) if agreement_scores else 0.5
        
        # Calculate other features from sender's reports
        total_reports = len(sender_reports)
        reachable_count = sum(1 for r in sender_reports if r.get("is_reachable", True))
        response_times = [r.get("response_ms", r.get("response_time_ms", 0)) for r in sender_reports if r.get("response_ms") or r.get("response_time_ms")]
        ssl_valid_count = sum(1 for r in sender_reports if r.get("ssl_valid", True))
        
        # Calculate aggregate metrics
        avg_response_time = float(np.mean(response_times)) if response_times else 0.0
        max_response_time = float(max(response_times)) if response_times else 0.0
        success_rate = reachable_count / total_reports if total_reports > 0 else 0.5
        ssl_accuracy = ssl_valid_count / total_reports if total_reports > 0 else 1.0
        
        # Calculate variance in response times (consistency measure)
        if len(response_times) > 1:
            rt_variance = float(np.var(response_times))
            rt_std = float(np.std(response_times))
        else:
            rt_variance = 0.0
            rt_std = 0.0
        
        # Enhanced feature extraction with more dynamic values
        features = {
            "accuracy": success_rate,
            "false_positive_rate": max(0.0, 1.0 - success_rate - 0.1) if success_rate > 0.5 else 0.0,
            "false_negative_rate": max(0.0, 1.0 - success_rate) if success_rate <= 0.5 else 0.0,
            "avg_rt_error": min(avg_response_time / 1000.0, 1.0),  # Normalize to seconds
            "max_rt_error": min(max_response_time / 1000.0, 1.0),
            "peer_agreement_rate": peer_agreement_rate,
            "historical_accuracy": success_rate,
            "accuracy_std_dev": min(rt_std / 1000.0, 1.0) if response_times else 0.1,
            "report_consistency": 1.0 - min(rt_variance / 1000000.0, 1.0) if response_times else 0.5,
            "sudden_change_score": 0.3 if success_rate > 0.8 else 0.7,  # Will be enhanced with historical tracking
            "ssl_accuracy": ssl_accuracy,
            "uptime_deviation": abs(success_rate - 0.99),  # Deviation from ideal uptime
            "rt_consistency": 1.0 - min(rt_std / 1000.0, 1.0) if response_times else 0.5,
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
        
        # For each URL, add edges between nodes that agree
        for url, url_reports in reports_by_url.items():
            node_votes = {}
            for r in url_reports:
                node_id = r.get("node_address") or r.get("sender_id") or r.get("node_id") or r.get("received_from")
                if node_id:
                    node_votes[node_id] = r.get("is_reachable", True)
            
            # Add edges between nodes that agree (potential collusion)
            node_ids = list(node_votes.keys())
            for i, node_i in enumerate(node_ids):
                for node_j in node_ids[i+1:]:
                    if node_votes[node_i] == node_votes[node_j]:
                        # Nodes agree - add or strengthen edge
                        if self.graph.has_edge(node_i, node_j):
                            self.graph[node_i][node_j]['weight'] += 1
                        else:
                            self.graph.add_edge(node_i, node_j, weight=1, agreement=node_votes[node_i])
    
    def _detect_collusion(self, node_id: str, reports: List[Dict]) -> float:
        """Detect collusion for a specific node using graph analysis"""
        if node_id not in self.graph:
            return 0.0
        
        try:
            # Calculate clustering coefficient (high = potential collusion)
            clustering = nx.clustering(self.graph.to_undirected(), node_id)
            
            # Count strong connections (high edge weights)
            strong_connections = sum(1 for _, data in self.graph[node_id].items() if data.get('weight', 0) >= 3)
            
            # Combine metrics for collusion score
            collusion_score = min(1.0, clustering * 0.5 + (strong_connections / max(len(self.graph), 1)) * 0.5)
            
            return collusion_score
        except:
            return 0.0
    
    def get_shard_distribution(self) -> Dict:
        """Get distribution of nodes across shards"""
        shard_counts = defaultdict(int)
        for decision in self.mitigation_actions.values():
            shard_counts[decision.shard] += 1
        
        return dict(shard_counts)
    
    def _assign_nodes_to_shards(self, reports: List[Dict]) -> Dict[str, List[Dict]]:
        """
        Assign nodes to 4 shards based on their reputation scores
        Returns: shard_id -> list of reports for that shard
        """
        shard_assignments = {
            'PRIMARY': [],
            'MONITORING': [],
            'QUARANTINE': [],
            'SLASHED': []
        }
        
        # Group reports by sender
        reports_by_sender = {}
        for r in reports:
            sender = r.get("node_address") or r.get("sender_id") or r.get("node_id") or r.get("received_from")
            if sender:
                reports_by_sender.setdefault(sender, []).append(r)
        
        # Assign each sender to a shard based on their current reputation
        for sender_id, sender_reports in reports_by_sender.items():
            # Get reputation for this sender
            if sender_id in self.reputation:
                rep = self.reputation[sender_id]
            elif sender_id in self.ewma_reputations:
                rep = self.ewma_reputations[sender_id]
            else:
                rep = 0.5  # Default neutral reputation
            
            # Assign to shard based on reputation thresholds
            if rep > self.HEALTHY_T:
                shard = 'PRIMARY'
            elif rep > self.SUSPICIOUS_T:
                shard = 'MONITORING'
            elif rep > self.FAULTY_T:
                shard = 'QUARANTINE'
            else:
                shard = 'SLASHED'
            
            shard_assignments[shard].extend(sender_reports)
            
            # Track in shard lists
            if sender_id not in self.shards[shard]:
                self.shards[shard].append(sender_id)
        
        return shard_assignments
    
    def _process_shard_consensus(self, shard_id: str, reports: List[Dict]) -> Dict:
        """
        Process consensus for a single shard locally
        Each shard runs its own ML evaluation independently
        """
        if not reports:
            return {
                'shard_id': shard_id,
                'evaluated': 0,
                'reputations': {},
                'status': 'empty'
            }
        
        logger.info(f"Processing shard {shard_id} with {len(reports)} reports")
        
        shard_results = {
            'shard_id': shard_id,
            'evaluated': 0,
            'reputations': {},
            'mitigations': {},
            'status': 'active'
        }
        
        # Group reports by sender
        reports_by_sender = {}
        for r in reports:
            sender = r.get("node_address") or r.get("sender_id") or r.get("node_id") or r.get("received_from")
            if sender:
                reports_by_sender.setdefault(sender, []).append(r)
        
        # Evaluate each sender in this shard
        for sender_id, sender_reports in reports_by_sender.items():
            features = self._extract_features_from_reports(sender_reports, all_reports_context=reports)
            
            # Add collusion detection
            collusion_score = self._detect_collusion(sender_id, reports)
            features['collusion_score'] = collusion_score
            
            # Calculate reputation using ML
            reputation = self.calculate_enhanced_reputation(features)
            
            # Apply EWMA smoothing
            smoothed_rep = self.apply_ewma_smoothing(sender_id, reputation)
            
            # Apply mitigation policy
            mitigation = self.apply_mitigation_policy(smoothed_rep)
            
            shard_results['reputations'][sender_id] = smoothed_rep
            shard_results['mitigations'][sender_id] = {
                'status': mitigation.status,
                'action': mitigation.action,
                'shard': mitigation.shard
            }
            shard_results['evaluated'] += 1
        
        logger.info(f"Shard {shard_id} consensus completed: {shard_results['evaluated']} nodes evaluated")
        return shard_results
    
    def _aggregate_shard_results(self, shard_results: Dict[str, Dict]) -> Dict:
        """
        Aggregate results from all shards into global consensus
        This simulates the global aggregation step in sharded consensus
        """
        global_results = {
            'reputations': {},
            'mitigation_actions': {},
            'shard_distribution': {},
            'shard_details': {}
        }
        
        # Combine results from all shards
        for shard_id, results in shard_results.items():
            global_results['shard_details'][shard_id] = results
            
            # Count nodes per shard
            global_results['shard_distribution'][shard_id] = results.get('evaluated', 0)
            
            # Merge reputations
            for node_id, rep in results.get('reputations', {}).items():
                global_results['reputations'][node_id] = rep
            
            # Merge mitigation actions
            for node_id, action in results.get('mitigations', {}).items():
                global_results['mitigation_actions'][node_id] = action
        
        return global_results
    
    def process_sharded_consensus(self, epoch_id: int, reports: List[Dict]) -> Dict:
        """
        Process consensus using REAL parallel sharding
        1. Divide nodes into 4 shards based on reputation
        2. Process each shard independently (local consensus)
        3. Aggregate results into global consensus
        """
        logger.info(f"🚀 STARTING SHARDED CONSENSUS for epoch {epoch_id}")
        
        start_time = time.time()
        
        # Step 1: Assign nodes to shards
        shard_assignments = self._assign_nodes_to_shards(reports)
        logger.info(f"Shard assignments: {[(k, len(v)) for k, v in shard_assignments.items()]}")
        
        # Step 2: Process each shard in parallel.
        # ML evaluation is CPU-bound; asyncio won't provide true parallelism.
        shard_results = {}
        shard_items = [(sid, srep) for sid, srep in shard_assignments.items() if srep]
        if shard_items:
            max_workers = min(4, len(shard_items))
            with ThreadPoolExecutor(max_workers=max_workers) as pool:
                futures = {
                    pool.submit(self._process_shard_consensus, shard_id, shard_reports): shard_id
                    for shard_id, shard_reports in shard_items
                }
                for fut in as_completed(futures):
                    shard_id = futures[fut]
                    try:
                        shard_results[shard_id] = fut.result()
                    except Exception as e:
                        logger.error(f"Shard {shard_id} failed: {e}")
        
        # Step 3: Aggregate all shard results
        global_results = self._aggregate_shard_results(shard_results)
        
        # Step 4: Build final consensus results
        results = {
            'epoch_id': epoch_id,
            'engine_type': 'SHARDED_ML',
            'reputations': global_results['reputations'],
            'ewma_reputations': self.ewma_reputations.copy(),
            'mitigation_actions': global_results['mitigation_actions'],
            'shard_distribution': global_results['shard_distribution'],
            'shard_details': global_results['shard_details'],
            'alpha': self.alpha,
            'predictions': [],
            'processing_time_ms': (time.time() - start_time) * 1000,
            'sharding_enabled': True
        }
        
        # Build predictions list for epoch_manager compatibility
        for node_id, rep in global_results['reputations'].items():
            mitigation = global_results['mitigation_actions'].get(node_id, {})
            results['predictions'].append({
                'node_id': node_id,
                'malicious_probability': 1.0 - rep,
                'p_malicious': 1.0 - rep,
                'reputation': rep,
                'status': mitigation.get('status', 'UNKNOWN'),
                'shard': mitigation.get('shard', 'UNKNOWN')
            })
        
        # Store consensus results
        self.consensus_decisions[epoch_id] = results
        
        logger.info(f"✅ SHARDED CONSENSUS completed in {results['processing_time_ms']:.1f}ms")
        logger.info(f"   Evaluated {len(results['reputations'])} nodes across {len([s for s in results['shard_distribution'].values() if s > 0])} shards")
        
        return results
