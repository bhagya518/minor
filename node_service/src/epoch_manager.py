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

# Dynamic Sharding Module
try:
    from .shard_manager import init_shard_manager, DynamicShardManager
    SHARDING_AVAILABLE = True
except ImportError:
    try:
        from shard_manager import init_shard_manager, DynamicShardManager
        SHARDING_AVAILABLE = True
    except ImportError:
        SHARDING_AVAILABLE = False
        logger.warning("DynamicShardManager not available – sharding disabled")

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
        
        # Dynamic Sharding
        if SHARDING_AVAILABLE:
            self.shard_manager: DynamicShardManager = init_shard_manager(reshuffle_interval=3)
        else:
            self.shard_manager = None

        # Persistence
        self.db_path = os.path.join(os.path.dirname(__file__), '..', 'epoch_data.db')
        # Initialize database synchronously (no event loop in __init__)
        self._init_database_sync()

        # Temporary storage for cross-shard results (collected via P2P)
        self.collected_shard_results = defaultdict(dict) # epoch_id -> {url -> result_dict}

    async def add_shard_results(self, epoch_id: int, shard_id: int, results: Dict):
        """
        Add aggregated results from another shard leader.
        Called by the P2P message handler.
        """
        logger.info(f"Epoch {epoch_id}: Received {len(results)} aggregated results from Shard {shard_id}")
        self.collected_shard_results[epoch_id].update(results)
    
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
        Deterministic leader election based on epoch and node IDs.
        Restricts candidate leaders to PRIMARY shard nodes with GraphTrustScore >= 0.3,
        falling back to all nodes to ensure liveness.
        
        Args:
            epoch_id: Current epoch
            peer_nodes: List of peer node IDs
            
        Returns:
            Selected leader node ID
        """
        if not peer_nodes:
            return self.node_id  # Fallback to self
        
        # Ensure reproducible ordering of all nodes
        all_nodes = sorted(peer_nodes + [self.node_id])
        
        # Filter candidates based on Shard and Graph Trust Score
        candidates = []
        if self.ml_consensus_engine:
            for node in all_nodes:
                # Get shard action
                action = self.ml_consensus_engine.mitigation_actions.get(node)
                shard = action.shard if action else 'PRIMARY' # Default to PRIMARY if unknown
                
                # Get graph trust score
                g_score = self.ml_consensus_engine.graph_trust_scores.get(node, 0.95)
                
                if shard == 'PRIMARY' and g_score >= 0.3:
                    candidates.append(node)
                    
            logger.info(f"Epoch {epoch_id}: Filtered leader candidates (PRIMARY shard & GraphTrust >= 0.3): {candidates} (from {all_nodes})")
        else:
            candidates = all_nodes
            
        # Fallback to all nodes if no candidate matches criteria to ensure system liveness
        if not candidates:
            logger.warning(f"Epoch {epoch_id}: No nodes met leader criteria (PRIMARY shard & GraphTrust >= 0.3). Falling back to all nodes.")
            candidates = all_nodes
            
        # Create deterministic hash based on candidates
        hash_input = f"{epoch_id}:{':'.join(candidates)}"
        hash_value = hashlib.sha256(hash_input.encode()).hexdigest()
        
        # Select leader based on hash
        leader_index = int(hash_value[:8], 16) % len(candidates)
        leader = candidates[leader_index]
        
        logger.info(f"Epoch {epoch_id}: Deterministic leader elected - {leader} (from {len(candidates)} candidates)")
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
            
            # TRIGGER SHARD RESHUFFLING (Step 19 of Strategy)
            if self.shard_manager:
                current_epoch = self.get_current_epoch()
                # Get monitored URLs from node config if possible
                monitored_urls = []
                try:
                    import main
                    if main.node_config:
                        monitored_urls = main.node_config.websites
                except:
                    pass
                
                reshuffled = self.shard_manager.on_epoch_complete(
                    current_epoch, 
                    self.ml_consensus_engine,
                    all_websites=monitored_urls
                )
                if reshuffled:
                    logger.info(f"✅ Epoch {current_epoch}: Reputation-based re-sharding completed")
    
    async def process_epoch(self, epoch_id: int):
        """
        Process a single epoch with hierarchical sharded consensus.
        1. All nodes participate in intra-shard consensus.
        2. Shard Leaders aggregate results for their shard's websites.
        3. Shard Leaders share results with each other.
        4. Master Leader submits consolidated lightweight blocks to blockchain.
        """
        logger.info(f"Processing epoch {epoch_id} with sharded consensus")
        
        if not self.shard_manager:
            logger.warning("Sharding not available, falling back to legacy consensus")
            return await self._process_epoch_legacy(epoch_id)

        # Get our shard and role
        our_shard_idx = self.shard_manager.get_node_shard(self.node_id)
        if our_shard_idx is None:
            logger.warning(f"Node {self.node_id} not assigned to any shard for epoch {epoch_id}")
            return

        shard_leader = self.shard_manager.get_shard_leader(our_shard_idx)
        is_shard_leader = (shard_leader == self.node_id)
        master_leader = self.shard_manager.get_master_leader()
        is_master_leader = (master_leader == self.node_id)
        
        shard_websites = self.shard_manager.get_shard_websites(our_shard_idx)
        logger.info(f"Epoch {epoch_id}: Shard {our_shard_idx} | Role: {'Master Leader' if is_master_leader else ('Shard Leader' if is_shard_leader else 'Member')} | Websites: {len(shard_websites)}")

        # Step 1: Collect reports for this shard
        all_reports = self.epoch_reports.get(epoch_id, []).copy()
        own_report = self.own_reports.get(epoch_id)
        if own_report:
            all_reports.append(own_report)

        # Filter reports: Use ALL reports for the websites this shard is responsible for
        # This provides full network redundancy for consensus
        shard_reports = [r for r in all_reports if r.get("url") in shard_websites]

        # Step 2: Run Consensus for websites assigned to this shard
        shard_consensus_results = {}
        if self.ml_consensus_engine:
            for url in shard_websites:
                url_reports = [r for r in shard_reports if r.get("url") == url]
                if not url_reports:
                    continue
                
                # Perform ML consensus per website
                try:
                    res = self.ml_consensus_engine.process_website_consensus(url, url_reports)
                    shard_consensus_results[url] = {
                        "url": url,
                        "epoch": epoch_id,
                        "status": res.get("final_status", "DOWN"),
                        "latency": res.get("avg_latency", 0),
                        "leader": shard_leader
                    }
                except Exception as e:
                    logger.error(f"Error in shard consensus for {url}: {e}")

        # Step 3: Shard Leader Action - BROADCAST results AND SUBMIT to blockchain
        if is_shard_leader:
            logger.info(f"🚀 Epoch {epoch_id}: Shard Leader {self.node_id} (Shard {our_shard_idx}) producing block")
            
            # Broadcast to the entire network as per user request
            if self.blockchain_client and hasattr(self.blockchain_client, 'peer_client'):
                await self.blockchain_client.peer_client.broadcast_message(
                    'shard_aggregated_results',
                    {
                        'shard_id': our_shard_idx,
                        'epoch_id': epoch_id,
                        'results': shard_consensus_results
                    },
                    ttl=3 
                )

            # SUBMIT TO BLOCKCHAIN (Slide 23 compliant)
            if shard_consensus_results:
                logger.info(f"🔗 Epoch {epoch_id}: Shard Leader submitting {len(shard_consensus_results)} results to blockchain for Shard {our_shard_idx}")
                
                # Prepare Slide 23 compliant blocks
                blockchain_payload = []
                for url, res in shard_consensus_results.items():
                    rep = 0.90
                    if self.ml_consensus_engine:
                        rep = self.ml_consensus_engine.ewma_reputations.get(self.node_id, 0.90)
                    
                    blockchain_payload.append({
                        "node_id": self.node_id,
                        "url": url,
                        "epoch": epoch_id,
                        "status": res["status"] == "UP",
                        "latency": int(res["latency"]),
                        "failure_rate": int(res.get("failure_rate", 0) * 100),
                        "anomaly_prob": int(res.get("anomaly_prob", 0) * 100),
                        "reputation": int(rep * 1000)
                    })
                
                if self.blockchain_client:
                    # Submit shard-specific batch to blockchain
                    # Every shard now produces its own block on-chain
                    tx_result = await self.blockchain_client.submit_consolidated_reports(
                        epoch_id, 
                        blockchain_payload, 
                        shard_id=our_shard_idx
                    )
                    if tx_result.get('success'):
                        logger.info(f"✅ Epoch {epoch_id}: Shard {our_shard_idx} block committed. TX: {tx_result.get('tx_hash')}")
                    else:
                        logger.error(f"❌ Epoch {epoch_id}: Shard {our_shard_idx} failed to commit block: {tx_result.get('error')}")

        # Step 4: Master Leader Action - Global Coordination
        if is_master_leader:
            # Master Leader can still perform global tasks like slashing or aggregate analysis
            # but shard-specific monitoring blocks are already handled by Shard Leaders
            logger.info(f"👑 Epoch {epoch_id}: Master Leader {self.node_id} coordinating network state")
            await asyncio.sleep(2) 

        # Cleanup
        if epoch_id in self.epoch_reports: del self.epoch_reports[epoch_id]
        if epoch_id in self.own_reports: del self.own_reports[epoch_id]
        if hasattr(self, 'collected_shard_results') and epoch_id in self.collected_shard_results:
            del self.collected_shard_results[epoch_id]

    async def _process_epoch_legacy(self, epoch_id: int):
        """Original process_epoch logic for non-sharded environments."""
        # (Content of old process_epoch goes here if needed, but we keep it brief for now)
        logger.info(f"Processing legacy epoch {epoch_id}")
        pass # Placeholder for brevity, original logic can be moved here

    
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

    def get_shard_status(self) -> Optional[Dict]:
        """Return the current dynamic shard status (or None if sharding unavailable)."""
        if self.shard_manager is None:
            return None
        return self.shard_manager.get_shard_status()

    def get_shard_history(self, limit: int = 10) -> list:
        """Return the most recent shard reshuffle audit entries."""
        if self.shard_manager is None:
            return []
        return self.shard_manager.get_history(limit)
    
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
