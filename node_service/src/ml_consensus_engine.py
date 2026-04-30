#!/usr/bin/env python3
"""
Enhanced ML Consensus Engine integrating ML_MINOR capabilities
Combines RF + IF fusion with EWMA smoothing and 4-tier mitigation
"""

import os
import json
import math
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
    
    def __init__(self, node_id: str, alpha: float = 0.9, iso_contamination: float = 0.15):
        self.node_id = node_id
        self.alpha = alpha  # EWMA smoothing factor
        self.iso_contamination = iso_contamination
        
        # ML Models (ML_MINOR approach)
        self.rf_model = None
        self.iso_model = None
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
        
        # Compatibility aliases for epoch_manager integration
        self.feature_cols = self.rf_feature_cols if hasattr(self, 'rf_feature_cols') else []
        self.scaler = self.rf_scaler if hasattr(self, 'rf_scaler') else None
        self.scaler_fitted = self.models_loaded
        
        # Enhanced mitigation thresholds (4-tier)
        self.HEALTHY_T = 0.8
        self.SUSPICIOUS_T = 0.5
        self.FAULTY_T = 0.2
        
        # Consensus tracking
        self.consensus_votes = defaultdict(list)  # epoch_id -> [votes]
        self.consensus_decisions = {}  # epoch_id -> consensus_decision
        
        # Mitigation tracking
        self.mitigation_actions = {}  # node_id -> MitigationDecision
        
        logger.info(f"EnhancedMLConsensusEngine initialized for node {node_id}")
    
    def load_enhanced_models(self):
        """Load ML_MINOR models"""
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
            
            # Use the saved scaler if available
            self.rf_scaler = rf_artifact.get('scaler')
            if self.rf_scaler is None:
                # Fallback: create a new scaler
                rf_scaler_type = rf_artifact.get('scaler_type', 'standard')
                if rf_scaler_type == 'minmax':
                    self.rf_scaler = MinMaxScaler()
                else:
                    self.rf_scaler = StandardScaler()
                logger.warning("No scaler found in RF model artifact, creating new scaler")
            
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
            
            self.models_loaded = True
            
            # Update compatibility aliases after successful loading
            self.feature_cols = self.rf_feature_cols
            self.scaler = self.rf_scaler
            self.scaler_fitted = True
            
            logger.info(f"✅ Loaded ML_MINOR enhanced models")
            logger.info(f"RF features: {len(self.rf_feature_cols)}")
            logger.info(f"Behavioral features: {len(self.behavioral_cols)}")
            
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
        """Calculate reputation using ML_MINOR RF + IF fusion"""
        if not self.models_loaded:
            return 0.5  # Default neutral reputation
        
        try:
            # Debug: Log the features being passed
            logger.debug(f"Features passed to ML model: {features}")
            
            # Prepare RF features
            rf_features = []
            for col in self.rf_feature_cols:
                val = features.get(col, 0.0)
                rf_features.append(float(val))
            
            logger.debug(f"RF features prepared: {rf_features}")
            logger.debug(f"Expected RF features: {self.rf_feature_cols}")
            
            # Scale RF features
            rf_input = np.array(rf_features).reshape(1, -1)
            
            # Check if scaler is fitted, if not, fit it with dummy data
            if not hasattr(self.rf_scaler, 'mean_'):
                # Fit scaler with dummy data (all zeros) as fallback
                dummy_data = np.zeros((1, len(self.rf_feature_cols)))
                self.rf_scaler.fit(dummy_data)
                logger.warning("RF scaler was not fitted, fitted with dummy data")
            
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
            
            # Check if ISO scaler is fitted, if not, fit it with dummy data
            if self.iso_scaler and not hasattr(self.iso_scaler, 'mean_'):
                # Fit scaler with dummy data (all zeros) as fallback
                dummy_data = np.zeros((1, len(self.behavioral_cols)))
                self.iso_scaler.fit(dummy_data)
                logger.warning("ISO scaler was not fitted, fitted with dummy data")
            
            if self.iso_scaler:
                beh_scaled = self.iso_scaler.transform(beh_input)
            else:
                beh_scaled = beh_input  # Skip scaling if no scaler
            
            # Get Isolation Forest score (normalized)
            iso_score = float(-self.iso_model.decision_function(beh_scaled)[0])
            logger.debug(f"ISO score: {iso_score}")
            
            # Normalize ISO score (approximate normalization)
            iso_norm = float(np.clip(iso_score / 10.0, 0.0, 1.0))
            logger.debug(f"ISO normalized: {iso_norm}")
            
            # Fusion: 70% RF + 30% ISO (ML_MINOR approach)
            risk = (0.7 * rf_prob) + (0.3 * iso_norm)
            reputation = 1.0 - float(np.clip(risk, 0.0, 1.0))
            logger.debug(f"Final reputation: {reputation}")
            
            return reputation
            
        except Exception as e:
            logger.error(f"Error calculating enhanced reputation: {e}")
            return 0.5
    
    def apply_ewma_smoothing(self, node_id: str, current_reputation: float) -> float:
        """Apply EWMA smoothing to reputation"""
        if node_id not in self.ewma_reputations:
            # Initialize with current reputation
            self.ewma_reputations[node_id] = current_reputation
            return current_reputation
        
        # Apply EWMA formula (corrected: weight NEW data with alpha)
        # With alpha=0.9: 90% weight on new data, 10% on history for fast attack detection
        ewma_rep = self.alpha * current_reputation + (1.0 - self.alpha) * self.ewma_reputations[node_id]
        self.ewma_reputations[node_id] = ewma_rep
        
        return ewma_rep
    
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
    
    def extract_features_from_reports(self, reports: List[Dict]) -> pd.DataFrame:
        """Extract features from multiple reports (plural version for epoch_manager compatibility)"""
        features_list = []
        for report in reports:
            features = self.extract_features_from_report(report)
            features_list.append(features)
        return pd.DataFrame(features_list)
    
    def extract_features_from_report(self, report: Dict) -> Dict:
        """Extract features from monitoring report"""
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
    
    def process_consensus_round(self, epoch_id: str, reports: List[Dict]) -> Dict:
        """Process consensus round with enhanced ML evaluation"""
        results = {
            'epoch_id': epoch_id,
            'evaluations': {},
            'mitigation_actions': {},
            'consensus_decision': None,
            'summary': {}
        }
        
        node_evaluations = {}
        
        # Evaluate each node
        for report in reports:
            node_id = report.get('node_id')
            if not node_id:
                continue
                
            features = self.extract_features_from_report(report)
            reputation, decision = self.evaluate_node(node_id, features)
            
            node_evaluations[node_id] = {
                'reputation': reputation,
                'status': decision.status,
                'action': decision.action,
                'shard': decision.shard,
                'features': features
            }
            
            results['evaluations'][node_id] = node_evaluations[node_id]
            results['mitigation_actions'][node_id] = {
                'status': decision.status,
                'action': decision.action,
                'shard': decision.shard
            }
        
        # Consensus decision based on majority of HEALTHY nodes
        healthy_nodes = [nid for nid, eval in node_evaluations.items() if eval['status'] == 'HEALTHY']
        total_nodes = len(node_evaluations)
        
        if total_nodes > 0:
            healthy_ratio = len(healthy_nodes) / total_nodes
            consensus_decision = {
                'majority_healthy': healthy_ratio > 0.5,
                'healthy_nodes': healthy_nodes,
                'total_nodes': total_nodes,
                'healthy_ratio': healthy_ratio
            }
            results['consensus_decision'] = consensus_decision
        
        # Summary statistics
        status_counts = {}
        for evaluation in node_evaluations.values():
            status = evaluation['status']
            status_counts[status] = status_counts.get(status, 0) + 1
        
        results['summary'] = {
            'total_evaluated': total_nodes,
            'status_distribution': status_counts,
            'average_reputation': np.mean([eval['reputation'] for eval in node_evaluations.values()]) if node_evaluations else 0.0
        }
        
        # Store consensus results
        self.consensus_decisions[epoch_id] = results
        
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
    
    def process_epoch_consensus(self, epoch_id: int, reports: List[Dict]) -> Dict:
        """
        Process epoch consensus using ML models
        This is called by epoch_manager to evaluate all reports for an epoch
        """
        logger.info(f"Processing epoch {epoch_id} with {len(reports)} reports")
        
        results = {
            'epoch_id': epoch_id,
            'engine_type': 'ML_Enhanced',
            'reputations': {},
            'ewma_reputations': {},
            'mitigation_actions': {},
            'shard_distribution': {},
            'alpha': self.alpha
        }
        
        # CORRECT — evaluate each sender independently
        reports_by_sender = {}
        for r in reports:
            sender = r.get("node_address") or r.get("sender_id") or r.get("received_from")
            if sender:
                reports_by_sender.setdefault(sender, []).append(r)
        
        logger.info(f"Grouped reports by sender: {list(reports_by_sender.keys())}")
        
        # Evaluate each sender based on THEIR reports only
        for sender_id, sender_reports in reports_by_sender.items():
            logger.info(f"Evaluating sender {sender_id} with {len(sender_reports)} reports")
            
            # peer_agreement needs the full pool for majority computation
            features = self._extract_features_from_reports(
                sender_reports, all_reports_context=reports
            )
            
            # Calculate reputation using ML
            reputation = self.calculate_enhanced_reputation(features)
            
            # Apply EWMA smoothing
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
            
            logger.info(f"Sender {sender_id}: reputation={smoothed_rep:.4f}, status={mitigation.status}")
        
        logger.info(f"Epoch {epoch_id} consensus completed: {len(results['reputations'])} nodes evaluated")
        return results
    
    def _extract_features_from_reports(self, sender_reports: List[Dict], all_reports_context: List[Dict] = None) -> Dict:
        """Extract features from node reports for ML evaluation"""
        if not sender_reports:
            return {}
        
        # peer_agreement_rate: does this sender agree with the majority?
        agreement_scores = []
        for r in sender_reports:
            url = r.get("url")
            our_reachable = r.get("is_reachable")
            sender_id = r.get("node_address") or r.get("sender_id") or r.get("received_from")
            
            if all_reports_context and url is not None and our_reachable is not None:
                # Get all other nodes' votes for this URL
                peer_votes = []
                for p in all_reports_context:
                    peer_sender = p.get("node_address") or p.get("sender_id") or p.get("received_from")
                    if (p.get("url") == url and 
                        peer_sender != sender_id and 
                        p.get("is_reachable") is not None):
                        peer_votes.append(p.get("is_reachable"))
                
                if peer_votes:
                    # Majority vote (True if >50% say reachable)
                    majority_reachable = sum(peer_votes) / len(peer_votes) > 0.5
                    agreement_scores.append(1.0 if our_reachable == majority_reachable else 0.0)
                    logger.debug(f"URL {url}: sender {sender_id} says {our_reachable}, majority {majority_reachable}, peers: {peer_votes}")
        
        peer_agreement_rate = sum(agreement_scores) / len(agreement_scores) if agreement_scores else 0.5
        
        # Calculate other features from sender's reports
        total_reports = len(sender_reports)
        reachable_count = sum(1 for r in sender_reports if r.get("is_reachable", True))
        response_times = [r.get("response_ms", r.get("response_time_ms", 0)) for r in sender_reports if r.get("response_ms") or r.get("response_time_ms")]
        
        # Calculate aggregate metrics
        avg_response_time = float(np.mean(response_times)) if response_times else 0.0
        success_rate = reachable_count / total_reports if total_reports > 0 else 0.5
        
        # Calculate advanced features that the model expects
        # Remove hardcoded defaults - use actual calculated values
        features = {
            "accuracy": success_rate,  # Actual success rate, not hardcoded
            "false_positive_rate": 1.0 - success_rate if success_rate > 0.5 else 0.0,  # Based on actual performance
            "false_negative_rate": 1.0 - success_rate if success_rate <= 0.5 else 0.0,  # Based on actual performance
            "avg_rt_error": min(avg_response_time / 1000.0, 0.5),  # Cap at 0.5 seconds, lower is better
            "max_rt_error": min(float(max(response_times)) / 1000.0 if response_times else 0.0, 0.5),
            "peer_agreement_rate": peer_agreement_rate,  # Actually computed from majority comparison
            "historical_accuracy": success_rate,  # Use actual success rate
            "accuracy_std_dev": 0.1 if success_rate > 0.8 else 0.4,  # Based on consistency
            "report_consistency": success_rate,  # Use actual consistency
            "sudden_change_score": 0.1 if success_rate > 0.8 else 0.7,  # Based on stability
            "ssl_accuracy": 0.95,  # Assume good SSL unless specified otherwise
            "uptime_deviation": 0.1 if success_rate > 0.8 else 0.5,  # Based on uptime
            "rt_consistency": 0.9 if success_rate > 0.8 else 0.3,  # Based on response time consistency
        }
        
        logger.debug(f"Features for sender: {features}")
        return features
    
    def get_shard_distribution(self) -> Dict:
        """Get distribution of nodes across shards"""
        shard_counts = defaultdict(int)
        for decision in self.mitigation_actions.values():
            shard_counts[decision.shard] += 1
        
        return dict(shard_counts)
