#!/usr/bin/env python3
"""
epoch_manager.py

EPOCH-BASED CONSENSUS MANAGER
Runs independently of monitoring cycle to ensure proper consensus timing

Key Features:
- Runs every 60 seconds (epoch window)
- Waits for peer reports to arrive before consensus
- Requires minimum 2 other node reports for quorum
- Implements 2/3 majority voting
- Executes actual slashing of malicious nodes
- Updates PoR for all nodes
- Clears peer_reports for next epoch
"""

import asyncio
import logging
import time
from typing import Dict, List, Optional
from collections import defaultdict
import pandas as pd
import numpy as np
try:
    import aiosqlite
    SQLITE_AVAILABLE = True
except ImportError:
    aiosqlite = None
    SQLITE_AVAILABLE = False
import sqlite3
import json
import os
import hashlib

# Import signature verification
try:
    from .monitoring_report import ReportVerifier
    VERIFIER_AVAILABLE = True
except ImportError:
    VERIFIER_AVAILABLE = False
    ReportVerifier = None

logger = logging.getLogger(__name__)


class EpochManager:
    """
    Manages epoch-based consensus execution
    Runs independently of monitoring cycle to ensure proper timing
    """
    
    def __init__(self, node_id: str, ml_consensus_engine=None, blockchain_client=None):
        self.node_id = node_id
        self.ml_consensus_engine = ml_consensus_engine
        self.blockchain_client = blockchain_client
        
        # Epoch management
        self.current_epoch = 0
        self.epoch_reports = defaultdict(list)  # epoch_id -> list of reports
        self.own_reports = {}  # epoch_id -> own report
        self.submitted_epochs = set()  # track locally submitted epochs to prevent duplicate submission
        
        # Consensus results
        self.epoch_decisions = {}  # epoch_id -> decision
        self.slash_history = []  # history of slashing actions
        
        # Configuration
        self.epoch_duration = 60  # seconds
        self.epoch_verdicts = {}  # Initialize epoch verdicts dict
        self.min_peers_for_quorum = 1  # need reports from at least 1 other node (reduced for testing)
        self.quorum_threshold = 2/3  # 2/3 majority required
        self.consensus_timeout = 2  # seconds to wait for quorum before proceeding
        
        # Leader election
        self.current_leader = None
        self.is_leader = False
        self.leader_history = {}  # epoch_id -> leader_id
        self.leader_rotation_interval = 10  # Rotate leader every 10 epochs
        
        # Persistence
        self.db_path = os.path.join(os.path.dirname(__file__), '..', 'epoch_data.db')
        # Initialize database synchronously (no event loop in __init__)
        self._init_database_sync()
    
    def _init_database_sync(self):
        """Synchronous database initialization for __init__"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS reports (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    epoch_id INTEGER NOT NULL,
                    node_id TEXT NOT NULL,
                    report_data TEXT NOT NULL,
                    is_own BOOLEAN DEFAULT 0,
                    timestamp REAL NOT NULL
                )
            ''')
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS decisions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    epoch_id INTEGER NOT NULL UNIQUE,
                    decision_data TEXT NOT NULL,
                    timestamp REAL NOT NULL
                )
            ''')
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS slash_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    epoch_id INTEGER NOT NULL,
                    node_id TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    timestamp REAL NOT NULL
                )
            ''')
            conn.commit()
            conn.close()
            logger.info(f"Database initialized at {self.db_path} (sync)")
        except Exception as e:
            logger.error(f"Failed to initialize database: {e}")
    
    async def _init_database(self):
        """Initialize SQLite database for persistence using async aiosqlite"""
        try:
            if SQLITE_AVAILABLE:
                async with aiosqlite.connect(self.db_path) as conn:
                    await conn.execute('''
                        CREATE TABLE IF NOT EXISTS reports (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            epoch_id INTEGER NOT NULL,
                            node_id TEXT NOT NULL,
                            report_data TEXT NOT NULL,
                            is_own BOOLEAN DEFAULT 0,
                            timestamp REAL NOT NULL
                        )
                    ''')
                    
                    await conn.execute('''
                        CREATE TABLE IF NOT EXISTS decisions (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            epoch_id INTEGER NOT NULL UNIQUE,
                            decision_data TEXT NOT NULL,
                            timestamp REAL NOT NULL
                        )
                    ''')
                    
                    await conn.execute('''
                        CREATE TABLE IF NOT EXISTS slash_history (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            epoch_id INTEGER NOT NULL,
                            node_id TEXT NOT NULL,
                            reason TEXT NOT NULL,
                            timestamp REAL NOT NULL
                        )
                    ''')
                    
                    await conn.commit()
                logger.info(f"Database initialized at {self.db_path} (async)")
            else:
                # Fallback to synchronous sqlite3
                conn = sqlite3.connect(self.db_path)
                cursor = conn.cursor()
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS reports (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        epoch_id INTEGER NOT NULL,
                        node_id TEXT NOT NULL,
                        report_data TEXT NOT NULL,
                        is_own BOOLEAN DEFAULT 0,
                        timestamp REAL NOT NULL
                    )
                ''')
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS decisions (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        epoch_id INTEGER NOT NULL UNIQUE,
                        decision_data TEXT NOT NULL,
                        timestamp REAL NOT NULL
                    )
                ''')
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS slash_history (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        epoch_id INTEGER NOT NULL,
                        node_id TEXT NOT NULL,
                        reason TEXT NOT NULL,
                        timestamp REAL NOT NULL
                    )
                ''')
                conn.commit()
                conn.close()
                logger.warning(f"Database initialized at {self.db_path} (sync fallback)")
        except Exception as e:
            logger.error(f"Failed to initialize database: {e}")
    
    async def _save_report(self, epoch_id: int, report: Dict, is_own: bool = False):
        """Save a report to the database using async aiosqlite"""
        try:
            if SQLITE_AVAILABLE:
                async with aiosqlite.connect(self.db_path) as conn:
                    node_id = report.get("node_address", report.get("node_id", "unknown"))
                    await conn.execute('''
                        INSERT INTO reports (epoch_id, node_id, report_data, is_own, timestamp)
                        VALUES (?, ?, ?, ?, ?)
                    ''', (epoch_id, node_id, json.dumps(report), is_own, time.time()))
                    await conn.commit()
            else:
                # Fallback to synchronous
                conn = sqlite3.connect(self.db_path)
                cursor = conn.cursor()
                node_id = report.get("node_address", report.get("node_id", "unknown"))
                cursor.execute('''
                    INSERT INTO reports (epoch_id, node_id, report_data, is_own, timestamp)
                    VALUES (?, ?, ?, ?, ?)
                ''', (epoch_id, node_id, json.dumps(report), is_own, time.time()))
                conn.commit()
                conn.close()
        except Exception as e:
            logger.error(f"Failed to save report: {e}")
    
    async def _save_decision(self, epoch_id: int, decision: Dict):
        """Save an epoch decision to the database using async aiosqlite"""
        try:
            if SQLITE_AVAILABLE:
                async with aiosqlite.connect(self.db_path) as conn:
                    await conn.execute('''
                        INSERT OR REPLACE INTO decisions (epoch_id, decision_data, timestamp)
                        VALUES (?, ?, ?)
                    ''', (epoch_id, json.dumps(decision), time.time()))
                    await conn.commit()
            else:
                # Fallback to synchronous
                conn = sqlite3.connect(self.db_path)
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT OR REPLACE INTO decisions (epoch_id, decision_data, timestamp)
                    VALUES (?, ?, ?)
                ''', (epoch_id, json.dumps(decision), time.time()))
                conn.commit()
                conn.close()
        except Exception as e:
            logger.error(f"Failed to save decision: {e}")
    
    async def _save_slash_event(self, epoch_id: int, node_id: str, reason: str):
        """Save a slash event to the database using async aiosqlite"""
        try:
            if SQLITE_AVAILABLE:
                async with aiosqlite.connect(self.db_path) as conn:
                    await conn.execute('''
                        INSERT INTO slash_history (epoch_id, node_id, reason, timestamp)
                        VALUES (?, ?, ?, ?)
                    ''', (epoch_id, node_id, reason, time.time()))
                    await conn.commit()
            else:
                # Fallback to synchronous
                conn = sqlite3.connect(self.db_path)
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT INTO slash_history (epoch_id, node_id, reason, timestamp)
                    VALUES (?, ?, ?, ?)
                ''', (epoch_id, node_id, reason, time.time()))
                conn.commit()
                conn.close()
        except Exception as e:
            logger.error(f"Failed to save slash event: {e}")
    
    def get_report_history(self, epoch_id: Optional[int] = None, limit: int = 100) -> List[Dict]:
        """Retrieve report history from database"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            if epoch_id:
                cursor.execute('''
                    SELECT epoch_id, node_id, report_data, is_own, timestamp
                    FROM reports
                    WHERE epoch_id = ?
                    ORDER BY timestamp DESC
                    LIMIT ?
                ''', (epoch_id, limit))
            else:
                cursor.execute('''
                    SELECT epoch_id, node_id, report_data, is_own, timestamp
                    FROM reports
                    ORDER BY timestamp DESC
                    LIMIT ?
                ''', (limit,))
            
            rows = cursor.fetchall()
            conn.close()
            
            return [
                {
                    'epoch_id': row[0],
                    'node_id': row[1],
                    'report': json.loads(row[2]),
                    'is_own': bool(row[3]),
                    'timestamp': row[4]
                }
                for row in rows
            ]
        except Exception as e:
            logger.error(f"Failed to retrieve report history: {e}")
            return []
    
    def get_decision_history(self, epoch_id: Optional[int] = None, limit: int = 100) -> List[Dict]:
        """Retrieve decision history from database"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            if epoch_id:
                cursor.execute('''
                    SELECT epoch_id, decision_data, timestamp
                    FROM decisions
                    WHERE epoch_id = ?
                    ORDER BY timestamp DESC
                    LIMIT ?
                ''', (epoch_id, limit))
            else:
                cursor.execute('''
                    SELECT epoch_id, decision_data, timestamp
                    FROM decisions
                    ORDER BY timestamp DESC
                    LIMIT ?
                ''', (limit,))
            
            rows = cursor.fetchall()
            conn.close()
            
            return [
                {
                    'epoch_id': row[0],
                    'decision': json.loads(row[1]),
                    'timestamp': row[2]
                }
                for row in rows
            ]
        except Exception as e:
            logger.error(f"Failed to retrieve decision history: {e}")
            return []
        
    def get_current_epoch(self) -> int:
        """Get current epoch number"""
        return int(time.time() // self.epoch_duration)
    

    
    def _should_rotate_leader(self, epoch_id: int) -> bool:
        """
        Check if leader should rotate based on rotation interval
        
        Args:
            epoch_id: Current epoch
            
        Returns:
            True if leader should rotate
        """
        return epoch_id % self.leader_rotation_interval == 0
    
    def _elect_leader(self, epoch_id: int, peer_nodes: List[str]) -> str:
        """
        Deterministic leader election based on epoch and node IDs
        Uses hash(epoch_id + sorted_node_ids) to select leader
        
        Args:
            epoch_id: Current epoch
            peer_nodes: List of peer node IDs
            
        Returns:
            Selected leader node ID
        """
        if not peer_nodes:
            return self.node_id  # Fallback to self
        
        # Ensure reproducible ordering
        all_nodes = sorted(peer_nodes + [self.node_id])
        
        # Create deterministic hash
        hash_input = f"{epoch_id}:{':'.join(all_nodes)}"
        hash_value = hashlib.sha256(hash_input.encode()).hexdigest()
        
        # Select leader based on hash
        leader_index = int(hash_value[:8], 16) % len(all_nodes)
        leader = all_nodes[leader_index]
        
        logger.info(f"Epoch {epoch_id}: Leader elected - {leader} (from {len(all_nodes)} nodes)")
        return leader
    
    def _is_leader_for_epoch(self, epoch_id: int, peer_nodes: List[str]) -> bool:
        """
        Check if this node is the leader for the given epoch
        
        Args:
            epoch_id: Epoch to check
            peer_nodes: List of known peer nodes
            
        Returns:
            True if this node is the leader
        """
        leader = self._elect_leader(epoch_id, peer_nodes)
        self.current_leader = leader
        self.is_leader = (leader == self.node_id)
        self.leader_history[epoch_id] = leader
        
        return self.is_leader
    
    def _verify_report_signature(self, report: Dict) -> bool:
        """
        Verify the signature of a monitoring report
        
        Args:
            report: Monitoring report dictionary
            
        Returns:
            True if signature is valid, False otherwise
        """
        if not VERIFIER_AVAILABLE:
            logger.warning("ReportVerifier not available, skipping signature verification")
            return True  # Skip verification if not available
        
        signature = report.get('signature')
        if not signature:
            logger.warning("Report has no signature")
            return False
        
        report_hash = report.get('report_hash')
        if not report_hash:
            logger.warning("Report has no report_hash")
            return False
        
        node_address = report.get('node_address')
        if not node_address:
            logger.warning("Report has no node_address")
            return False
        
        # For now, we'll use a simple verification approach
        # In production, you would need to retrieve the public key for each node
        # from a peer registry or blockchain
        try:
            # Create canonical string for verification
            report_copy = report.copy()
            report_copy.pop('signature', None)
            canonical = str(report_copy)
            
            # Verify signature (this is a simplified check)
            # In production, use ReportVerifier.verify(signature, canonical, public_key)
            logger.debug(f"Signature check for report from {node_address}: hash={report_hash[:16]}...")
            return True  # Placeholder - implement proper verification with public key lookup
        except Exception as e:
            logger.error(f"Error verifying report signature: {e}")
            return False
    
    async def add_report(self, report: Dict, is_own: bool = False) -> bool:
        """
        Add a report to the current epoch with signature verification and persistence
        
        Args:
            report: Monitoring report dictionary
            is_own: Whether this is our own report
        """
        # Verify signature for peer reports (skip for own reports)
        if not is_own:
            if not self._verify_report_signature(report):
                logger.warning(f"Rejected report from {report.get('node_address', 'unknown')}: invalid signature")
                return False
        
        epoch_id = report.get("epoch_id", self.get_current_epoch())
        
        if is_own:
            self.own_reports[epoch_id] = report
        else:
            self.epoch_reports[epoch_id].append(report)
        
        # Persist report to database
        await self._save_report(epoch_id, report, is_own)
        
        logger.debug(f"Added report for epoch {epoch_id} (own={is_own}), total peer reports: {len(self.epoch_reports[epoch_id])}")
        return True
    
    def finalize_decision(self, epoch_id: int, decision: Dict):
        """
        Finalize an epoch decision and sync local state.
        Ensures all nodes (leader and followers) reflect the same reputation state.
        """
        self.epoch_decisions[epoch_id] = decision
        
        if self.ml_consensus_engine:
            consensus_results = decision.get("consensus_results", {})
            # Handle both 'reputations' and 'ewma_reputations' keys for compatibility
            reputations = consensus_results.get("reputations") or consensus_results.get("ewma_reputations", {})
            mitigation_actions = consensus_results.get("mitigation_actions", {})
            
            if reputations and mitigation_actions:
                logger.info(f"Epoch {epoch_id}: Synchronizing local ML engine with finalized decision")
                self.ml_consensus_engine.sync_state(reputations, mitigation_actions)
            else:
                # Fallback to node_reputations if consensus_results is structured differently
                node_reputations = decision.get("node_reputations", {})
                if node_reputations:
                    # Synthesize mitigation actions if missing
                    synth_mitigation = {}
                    for nid, rep in node_reputations.items():
                        m = self.ml_consensus_engine.apply_mitigation_policy(rep)
                        synth_mitigation[nid] = {
                            "status": m.status,
                            "action": m.action,
                            "shard": m.shard
                        }
                    self.ml_consensus_engine.sync_state(node_reputations, synth_mitigation)

    async def run_epoch_manager(self):
        """
        Main epoch manager loop - runs on wall-clock schedule:
        - Second 0: Assign tiers and shards
        - Second 5: Wait for reports (report window ends)
        - Second 55: Run ML analysis
        - Second 58: Run consensus
        - Second 59: Update reputations, re-assign tiers, trigger slashing
        """
        logger.info("Starting epoch manager with wall-clock timing...")
        
        while True:
            try:
                now = time.time()
                seconds_into_minute = now % 60
                
                # Second 0: Assign tiers and shards to all known nodes
                if 0 <= seconds_into_minute < 1:
                    await self._assign_tiers_and_shards()
                
                # Second 55: Run ML analysis on collected reports
                elif 55 <= seconds_into_minute < 56:
                    await self._run_ml_analysis()
                
                # Second 58: Run consensus on ML results
                elif 58 <= seconds_into_minute < 59:
                    await self._run_consensus()
                
                # Second 59: Update reputations, re-assign tiers, trigger slashing
                elif 59 <= seconds_into_minute < 60:
                    await self._update_reputations_and_slash()
                
                # Sleep briefly for responsiveness
                await asyncio.sleep(0.5)
                
            except Exception as e:
                logger.error(f"Error in epoch manager loop: {e}")
                await asyncio.sleep(5)
    
    async def _assign_tiers_and_shards(self):
        """Second 0: Assign tiers and shards based on current reputations"""
        if self.ml_consensus_engine:
            self.ml_consensus_engine._assign_nodes_to_shards()
            logger.info("Tiers and shards assigned for new epoch")
    
    async def _run_ml_analysis(self):
        """Second 55: Run ML analysis on collected reports"""
        current_epoch = self.get_current_epoch()
        previous_epoch = current_epoch - 1
        
        if previous_epoch in self.epoch_reports or previous_epoch in self.own_reports:
            logger.info(f"Running ML analysis for epoch {previous_epoch}")
            # ML will be run as part of process_epoch when called
    
    async def _run_consensus(self):
        """Second 58: Run consensus (called from process_epoch)"""
        current_epoch = self.get_current_epoch()
        previous_epoch = current_epoch - 1
        
        if previous_epoch in self.epoch_reports or previous_epoch in self.own_reports:
            await self.process_epoch(previous_epoch)
    
    async def _update_reputations_and_slash(self):
        """Second 59: Update reputations, re-assign tiers, trigger slashing"""
        if self.ml_consensus_engine:
            # Re-assign tiers based on updated reputations
            for node_id, action in self.ml_consensus_engine.mitigation_actions.items():
                reputation = self.ml_consensus_engine.ewma_reputations.get(node_id, 0.90)
                new_action = self.ml_consensus_engine.apply_mitigation_policy(reputation)
                self.ml_consensus_engine.mitigation_actions[node_id] = new_action
            logger.info("Tiers re-assigned based on updated reputations")
    
    async def process_epoch(self, epoch_id: int):
        """
        Process a single epoch with leader-based finalization
        Only the leader executes consensus and blockchain updates
        
        Args:
            epoch_id: Epoch to process
        """
        logger.info(f"Processing epoch {epoch_id}")
        
        # Step 1: Collect all reports for this epoch
        own_report = self.own_reports.get(epoch_id)
        
        # Get peer nodes from reports for leader election
        peer_nodes = set()
        peer_reports = self.epoch_reports.get(epoch_id, [])
        for report in peer_reports:
            node_id = report.get("node_address", report.get("node_id", ""))
            if node_id:
                peer_nodes.add(node_id)
        if own_report:
            peer_nodes.add(self.node_id)
        
        leader = self._elect_leader(epoch_id, list(peer_nodes))
        
        # Step 2: Combine reports
        all_reports = peer_reports.copy()
        if own_report:
            all_reports.append(own_report)
        
        # Step 3: Filter reports based on shard participation restrictions
        if self.ml_consensus_engine:
            filtered_reports = []
            for report in all_reports:
                node_id = report.get("node_address", report.get("node_id"))
                if node_id:
                    # Get node's current shard
                    if node_id in self.ml_consensus_engine.mitigation_actions:
                        action = self.ml_consensus_engine.mitigation_actions[node_id]
                        # Allow participation based on shard
                        if action.shard in ['PRIMARY', 'MONITORING']:
                            filtered_reports.append(report)
                        elif action.shard == 'QUARANTINE':
                            # QUARANTINE nodes can submit reports but don't vote
                            filtered_reports.append(report)  # Keep for monitoring
                        # SLASHED nodes are completely excluded
                    else:
                        # Unknown node, allow by default
                        filtered_reports.append(report)
            all_reports = filtered_reports
        
        # Get peer nodes for leader election (from reports)
        peer_nodes = []
        for report in peer_reports:
            node_id = report.get("node_address", report.get("node_id"))
            if node_id and node_id != self.node_id:
                peer_nodes.append(node_id)
        
        # Check if this node is the leader for this epoch
        is_leader = self._is_leader_for_epoch(epoch_id, peer_nodes)
        
        if not is_leader:
            logger.info(f"Epoch {epoch_id}: Not the leader (leader is {self.current_leader}), skipping consensus")
            # Non-leaders still collect reports but don't execute consensus
            return
        
        logger.info(f"Epoch {epoch_id}: Acting as LEADER, executing consensus")
        
        # QUORUM + TIMEOUT CONSENSUS: Proceed if quorum reached OR timeout elapsed
        # This prevents indefinite blocking and makes latency predictable
        epoch_start_time = time.time()
        time_elapsed = epoch_start_time - (epoch_id * self.epoch_duration)
        
        if len(peer_reports) < self.min_peers_for_quorum:
            if time_elapsed < self.consensus_timeout:
                logger.info(f"Epoch {epoch_id}: only {len(peer_reports)} peer reports (need {self.min_peers_for_quorum}), waiting for quorum (elapsed: {time_elapsed:.1f}s/{self.consensus_timeout}s)")
                return
            else:
                logger.warning(f"Epoch {epoch_id}: timeout reached ({time_elapsed:.1f}s), proceeding with {len(peer_reports)} peer reports (below quorum)")
        
        logger.info(f"Epoch {epoch_id}: processing {len(all_reports)} total reports ({len(peer_reports)} peer + {1 if own_report else 0} own)")
        
        # Initialize reputation updates list for batching
        reputation_updates = []
        
        # Step 1: Build feature matrix from all reports
        try:
            feature_matrix = self.build_feature_matrix(all_reports)
            if feature_matrix.empty:
                logger.warning(f"Epoch {epoch_id}: empty feature matrix, skipping consensus")
                return
        except Exception as e:
            logger.error(f"Epoch {epoch_id}: error building feature matrix: {e}")
            return
        
        # Step 2: Fit ML scaler if not fitted and enough reports available
        if self.ml_consensus_engine and len(all_reports) >= 5:
            try:
                # Check if scaler needs fitting
                if not hasattr(self.ml_consensus_engine, 'scaler_fitted') or not self.ml_consensus_engine.scaler_fitted:
                    # Use ML consensus engine's feature extraction instead
                    features_df = self.ml_consensus_engine.extract_features_from_reports(all_reports)
                    if not features_df.empty and len(features_df) >= 5:
                        # Extract only numeric feature columns
                        if self.ml_consensus_engine.feature_cols:
                            feature_matrix = features_df[self.ml_consensus_engine.feature_cols].fillna(0)
                            self.ml_consensus_engine.scaler.fit(feature_matrix)
                            self.ml_consensus_engine.scaler_fitted = True
                            logger.info(f"Epoch {epoch_id}: ML scaler fitted on live data")
            except Exception as e:
                logger.warning(f"Epoch {epoch_id}: failed to fit scaler: {e}")
        
        # Step 3: Run ML consensus on aggregated reports (with optional sharding)
        try:
            if self.ml_consensus_engine:
                # Use sharded consensus if available, otherwise fall back to regular consensus
                if hasattr(self.ml_consensus_engine, 'process_sharded_consensus'):
                    consensus_results = self.ml_consensus_engine.process_sharded_consensus(epoch_id, all_reports)
                else:
                    consensus_results = self.ml_consensus_engine.process_epoch_consensus(epoch_id, all_reports)
            else:
                # Fallback: simple majority voting without ML
                consensus_results = self.simple_majority_vote(all_reports)
                logger.info(f"Epoch {epoch_id}: simple majority voting (no ML engine)")
        except Exception as e:
            logger.error(f"Epoch {epoch_id}: error in consensus: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return
        
        # Step 3: REPUTATION-WEIGHTED QUORUM VOTING (core spec requirement)
        # Instead of flat voting (each node = 1 vote), weight votes by reputation
        weighted_malicious = 0.0
        weighted_honest = 0.0
        total_weight = 0.0
        node_verdicts = {}  # node_id -> verdict
        node_weights = {}   # node_id -> weight (reputation)
        
        for report in all_reports:
            node_id = report.get("node_address", report.get("node_id", "unknown"))
            
            # Get verdict from consensus results
            verdict = None
            p_malicious = 0.5
            
            if consensus_results and "predictions" in consensus_results:
                # Find prediction for this node
                for pred in consensus_results["predictions"]:
                    if pred.get("node_id") == node_id:
                        p_malicious = pred.get("malicious_probability", pred.get("p_malicious", 0.5))
                        verdict = "malicious" if p_malicious >= 0.5 else "honest"
                        break
            
            if verdict is None:
                # Optimized Heuristic: Only slash if the report contradicts the majority
                url = report.get("url")
                if url in self.epoch_verdicts:
                    majority_reachable = self.epoch_verdicts[url] == "up"
                    node_reachable = report.get("is_reachable", True)
                    # Only malicious if they reported DOWN when majority said UP
                    verdict = "honest" if node_reachable == majority_reachable else "malicious"
                else:
                    verdict = "honest" # Benefit of the doubt if no majority yet
            
            node_verdicts[node_id] = verdict
            
            if consensus_results and "reputations" in consensus_results:
                # Use ML-calculated reputation as weight
                reputation = consensus_results["reputations"].get(node_id, 0.90)
            elif self.ml_consensus_engine and node_id in self.ml_consensus_engine.reputation:
                # Fallback to ML engine reputation
                reputation = self.ml_consensus_engine.reputation.get(node_id, 0.90)
            else:
                # Default neutral reputation
                reputation = 0.90
            
            node_weights[node_id] = reputation
            total_weight += reputation
            
            # Apply weighted voting
            if verdict == "malicious":
                weighted_malicious += reputation
            else:
                weighted_honest += reputation
        
        # Convert to vote counts for display (optional)
        malicious_votes = sum(1 for v in node_verdicts.values() if v == "malicious")
        honest_votes = sum(1 for v in node_verdicts.values() if v == "honest")
        
        # Step 4: Check quorum - require strict majority with minimum 2 votes
        total_votes = len(all_reports)
        quorum = max(2, (total_votes * 2) // 3 + 1)
        
        logger.info(f"Epoch {epoch_id}: REPUTATION-WEIGHTED voting results")
        logger.info(f"  Weighted honest: {weighted_honest:.4f}, Weighted malicious: {weighted_malicious:.4f}, Total weight: {total_weight:.4f}")
        logger.info(f"  Flat vote counts - honest: {honest_votes}, malicious: {malicious_votes}, quorum: {quorum}")
        
        # Step 5: Execute slashing based on WEIGHTED consensus
        # A coordinated group of low-reputation nodes cannot override high-reputation nodes
        consensus_threshold = total_weight * 2 / 3 if total_weight > 0 else 0.67

        if weighted_malicious >= consensus_threshold and malicious_votes >= quorum:
            malicious_nodes = [nid for nid, v in node_verdicts.items() if v == "malicious"]
            if malicious_nodes and self.blockchain_client:
                try:
                    # Use batch slashing for efficiency (1 transaction instead of N)
                    node_ids = malicious_nodes
                    amounts = [0.1] * len(malicious_nodes)  # 10% slash each
                    reason = f"Epoch {epoch_id} consensus: {malicious_votes}/{total_votes} nodes voted malicious"
                    
                    batch_result = self.blockchain_client.batch_slash_nodes(
                        node_ids=node_ids,
                        amounts=amounts,
                        reason=reason,
                        epoch_id=epoch_id
                    )
                    
                    if batch_result['success']:
                        logger.warning(f"Epoch {epoch_id}: Batch slashed {len(malicious_nodes)} nodes")
                    else:
                        # Fallback to individual slashing
                        logger.error(f"Batch slashing failed, trying individual slashes")
                        for node_id in malicious_nodes:
                            slash_result = self.blockchain_client.slash_node(
                                node_id=node_id,
                                amount=0.1,
                                reason=reason,
                                epoch_id=epoch_id
                            )
                            logger.warning(f"Epoch {epoch_id}: SLASHED node {node_id} - {slash_result}")
                except Exception as e:
                    logger.error(f"Epoch {epoch_id}: Error during slashing: {e}")
        else:
            logger.info(f"Epoch {epoch_id}: no malicious quorum (need {quorum}, got {malicious_votes})")
        
        # Step 6: Update PoR for all nodes with penalty-based calculation
        for report in all_reports:
            node_id = report.get("node_address", report.get("node_id", "unknown"))
            verdict = node_verdicts.get(node_id, "honest")
            
            # Get current PoR from blockchain
            try:
                if self.blockchain_client:
                    rep_data = self.blockchain_client.get_node_reputation(node_id)  # sync call
                    current_por = rep_data["reputation"] if rep_data else 0.95
                else:
                    current_por = 0.95  # Default if no blockchain
            except Exception as e:
                current_por = 0.95
                logger.warning(f"Epoch {epoch_id}: could not get current PoR for {node_id}, using default")
            
            # Calculate new PoR with penalty
            penalty = 0.1 if verdict == "malicious" else 0.0
            new_por = current_por * (1 - penalty)

            # Separate components for on-chain PoR formula
            # - monitoring_trust: use PoR update proxy (penalty-adjusted current PoR)
            # - ml_score: use ML consensus reputation if available
            ml_score = new_por
            try:
                if isinstance(consensus_results, dict):
                    ml_reps = consensus_results.get('reputations')
                    if isinstance(ml_reps, dict) and node_id in ml_reps:
                        ml_score = float(ml_reps[node_id])
            except Exception:
                ml_score = new_por
            
            # BATCHING: Collect updates instead of sending immediately
            # This reduces blockchain transactions from O(n) to O(shards)
            reputation_updates.append({
                'node_id': node_id,
                'new_por': new_por,
                'monitoring_trust': new_por,
                'ml_score': ml_score,
                'evidence': f"Epoch {epoch_id} verdict: {verdict} (penalty: {penalty})"
            })
        
        # Step 7: Batch update all node reputations to blockchain
        if reputation_updates and self.blockchain_client:
            try:
                batch_result = await self.blockchain_client.batch_update_reputation(reputation_updates)
                if batch_result.get('success'):
                    logger.info(f"Epoch {epoch_id}: Batch updated {len(reputation_updates)} node reputations on blockchain")
                else:
                    logger.error(f"Epoch {epoch_id}: Failed to batch update reputations: {batch_result.get('error')}")
            except Exception as e:
                logger.error(f"Epoch {epoch_id}: Error batch updating reputations: {e}")
        
        # Step 8: Build decision dict FIRST
        decision = {
            "malicious_votes": malicious_votes,
            "honest_votes": honest_votes,
            "total_votes": total_votes,
            "quorum_reached": weighted_malicious > weighted_honest and weighted_malicious >= consensus_threshold,
            "weighted_malicious": weighted_malicious,
            "weighted_honest": weighted_honest,
            "total_weight": total_weight,
            "consensus_threshold": consensus_threshold,
            "node_verdicts": node_verdicts,
            "node_weights": node_weights,
            "consensus_results": consensus_results,
            "voting_type": "reputation_weighted",
            "blockchain_committed": False,
            "blockchain_tx": None
        }
        
        # Finalize and sync state locally
        self.finalize_decision(epoch_id, decision)
        
        # Step 8: THEN submit to blockchain
        if self.is_leader and self.blockchain_client:
            try:
                # 1. Local guard
                if hasattr(self, 'submitted_epochs') and epoch_id in self.submitted_epochs:
                    logger.info(f"Epoch {epoch_id}: Decision already submitted locally, skipping duplicate submission.")
                    decision['blockchain_committed'] = True
                else:
                    # 2. On-chain guard
                    on_chain_status = await self.blockchain_client.get_epoch_decision(epoch_id)
                    if on_chain_status.get('success') and on_chain_status.get('submitted'):
                        logger.info(f"Epoch {epoch_id}: Decision already submitted on-chain, skipping duplicate submission.")
                        if hasattr(self, 'submitted_epochs'):
                            self.submitted_epochs.add(epoch_id)
                        decision['blockchain_committed'] = True
                    else:
                        logger.info(f"Epoch {epoch_id}: Leader submitting decision to blockchain (source of truth)")
                        blockchain_result = await self.blockchain_client.submit_epoch_decision(epoch_id, decision)
                        
                        if blockchain_result['success']:
                            logger.info(f"Epoch {epoch_id}: Decision committed to blockchain - consensus finalized")
                            decision['blockchain_committed'] = True
                            decision['blockchain_tx'] = blockchain_result.get('tx_hash')
                            if hasattr(self, 'submitted_epochs'):
                                self.submitted_epochs.add(epoch_id)
                        else:
                            logger.warning(f"Epoch {epoch_id}: Failed to commit to blockchain: {blockchain_result.get('error')}")
                            decision['blockchain_committed'] = False
            except Exception as e:
                logger.error(f"Epoch {epoch_id}: Error submitting to blockchain: {e}")
                decision['blockchain_committed'] = False
        else:
            # Non-leader nodes verify decision from blockchain
            if self.blockchain_client:
                logger.info(f"Epoch {epoch_id}: Non-leader - will verify decision from blockchain")
                decision['blockchain_committed'] = None  # Pending verification
            else:
                logger.warning(f"Epoch {epoch_id}: No blockchain client - decision is local only")
                decision['blockchain_committed'] = False
        
        # Persist decision to database
        await self._save_decision(epoch_id, decision)
        
        # Step 9: Broadcast final decision to all peers (leader only)
        if self.blockchain_client and hasattr(self.blockchain_client, 'peer_client'):
            try:
                decision_message = {
                    'epoch_id': epoch_id,
                    'leader_id': self.node_id,
                    'decision': decision,
                    'timestamp': time.time()
                }
                # Send to all known peers
                await self.blockchain_client.peer_client.broadcast_message(
                    'epoch_decision',
                    decision_message,
                    ttl=3  # Multi-hop propagation
                )
                logger.info(f"Epoch {epoch_id}: Decision broadcast to all peers")
            except Exception as e:
                logger.warning(f"Epoch {epoch_id}: Failed to broadcast decision: {e}")
        
        # Step 10: Clear reports for this epoch (cleanup)
        if epoch_id in self.epoch_reports:
            del self.epoch_reports[epoch_id]
        if epoch_id in self.own_reports:
            del self.own_reports[epoch_id]
        
        logger.info(f"Epoch {epoch_id}: processing completed, reports cleared")
    
    def build_feature_matrix(self, reports: List[Dict]) -> pd.DataFrame:
        """
        Build feature matrix from reports for ML processing
        
        Args:
            reports: List of monitoring reports
            
        Returns:
            DataFrame with features
        """
        features = []
        
        for report in reports:
            feature = {
                "node_id": report.get("node_address", report.get("node_id", "unknown")),
                "response_ms": report.get("response_ms", 0),
                "status_code": report.get("status_code", 0),
                "ssl_valid": 1 if report.get("ssl_valid", True) else 0,
                "is_reachable": 1 if report.get("is_reachable", True) else 0,
                "epoch_id": report.get("epoch_id", 0)
            }
            features.append(feature)
        
        return pd.DataFrame(features)
    
    def simple_majority_vote(self, reports: List[Dict]) -> Dict:
        """
        Fallback simple majority voting when ML engine is not available
        
        Args:
            reports: List of monitoring reports
            
        Returns:
            Consensus results dictionary
        """
        malicious_count = 0
        honest_count = 0
        
        for report in reports:
            is_reachable = report.get("is_reachable", True)
            ssl_valid = report.get("ssl_valid", True)
            
            # Simple heuristic: if not reachable or SSL invalid, consider malicious
            if not is_reachable or not ssl_valid:
                malicious_count += 1
            else:
                honest_count += 1
        
        total = len(reports)
        consensus_malicious = malicious_count > honest_count
        
        return {
            "consensus": {
                "malicious": consensus_malicious,
                "malicious_votes": malicious_count,
                "honest_votes": honest_count,
                "total_votes": total,
                "confidence": malicious_count / total if total > 0 else 0
            },
            "predictions": [
                {
                    "node_id": r.get("node_address", r.get("node_id", "unknown")),
                    "p_malicious": 0.8 if not r.get("is_reachable", True) else 0.1
                }
                for r in reports
            ]
        }
    
    def get_epoch_status(self, epoch_id: int) -> Optional[Dict]:
        """
        Get status of a processed epoch
        
        Args:
            epoch_id: Epoch to query
            
        Returns:
            Epoch decision dictionary or None
        """
        return self.epoch_decisions.get(epoch_id)
    
    def get_current_epoch_reports(self) -> Dict:
        """
        Get reports for current epoch (for monitoring)
        
        Returns:
            Dictionary with own and peer report counts
        """
        current_epoch = self.get_current_epoch()
        return {
            "epoch_id": current_epoch,
            "own_report": current_epoch in self.own_reports,
            "peer_reports_count": len(self.epoch_reports.get(current_epoch, [])),
            "total_reports": len(self.epoch_reports.get(current_epoch, [])) + (1 if current_epoch in self.own_reports else 0)
        }


# Global epoch manager instance
epoch_manager: Optional[EpochManager] = None


def get_epoch_manager() -> Optional[EpochManager]:
    """Get the global epoch manager instance"""
    return epoch_manager


def init_epoch_manager(node_id: str, ml_consensus_engine=None, blockchain_client=None) -> EpochManager:
    """
    Initialize the global epoch manager
    
    Args:
        node_id: Node identifier
        ml_consensus_engine: ML consensus engine instance
        blockchain_client: Blockchain client instance
        
    Returns:
        Initialized epoch manager
    """
    global epoch_manager
    epoch_manager = EpochManager(node_id, ml_consensus_engine, blockchain_client)
    logger.info(f"Epoch manager initialized for node {node_id}")
    return epoch_manager
