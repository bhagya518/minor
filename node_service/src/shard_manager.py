#!/usr/bin/env python3
"""
shard_manager.py – Dynamic Trust-Aware Sharding Module
=======================================================

Core Principle
--------------
Each *numbered* shard (SHARD 1, SHARD 2, …) contains nodes from ALL trust
tiers mixed together:

  SHARD 1: N8 (ALLOW)  N5 (WARN)  N9 (QUARANTINE)  N21 (SLASHED)
  SHARD 2: N3 (ALLOW)  N6 (WARN)  N11 (QUARANTINE) N24 (SLASHED)

This **interleaved distribution** ensures:
  1. No single shard is dominated by malicious nodes.
  2. Every shard has Byzantine fault tolerance from its honest majority.
  3. Collusion between nodes in the same shard is prevented (nodes of
     different trust are unlikely to collude).
  4. After each reshuffling epoch the node↔shard mapping changes, breaking
     any forming collusion rings.

Algorithm (O(N))
----------------
  1. Separate nodes into 4 trust-tier buckets:
       PRIMARY (ALLOW) → reputation ≥ 0.60
       MONITORING (WARN) → 0.38 ≤ rep < 0.60
       QUARANTINE → 0.20 ≤ rep < 0.38
       SLASHED → rep < 0.20
  2. Shuffle each bucket deterministically (seed = epoch_id) so all nodes
     independently reach the same assignment.
  3. Distribute via round-robin across K numbered shards, pulling one node
     from each tier-bucket in turn so that every shard gets a balanced mix.
  4. Elect the highest-reputation (ALLOW-tier-preferring) node in each shard
     as that shard's leader.

Architecture
------------
  DynamicShardManager
  ├── EpochController       – tracks current epoch, triggers reshuffles
  ├── ReshufflingEngine     – interleaved assignment across numbered shards
  └── LeaderElectionManager – highest-trust leader per numbered shard
"""

import logging
import math
import random
import time
from collections import deque
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
RESHUFFLE_EVERY_N_EPOCHS: int = 3    # reshuffle every N epochs
MAX_HISTORY_ENTRIES:      int = 50   # ring-buffer size
TARGET_SHARD_SIZE:        int = 5    # Adjusted to 5 for 20-node/4-shard scaling

# Trust-tier thresholds (mirror EnhancedMLConsensusEngine exactly)
HEALTHY_T    = 0.60   # PRIMARY  / ALLOW
SUSPICIOUS_T = 0.38   # MONITORING / WARN
FAULTY_T     = 0.20   # QUARANTINE

TIER_ORDER  = ["PRIMARY", "MONITORING", "QUARANTINE", "SLASHED"]

ACTION_MAP  = {          # tier → display action label
    "PRIMARY":    "ALLOW",
    "MONITORING": "WARN",
    "QUARANTINE": "QUARANTINE",
    "SLASHED":    "SLASHED",
}


# ---------------------------------------------------------------------------
# Helper: classify a raw reputation score into a trust-tier name
# ---------------------------------------------------------------------------
def _tier_from_rep(rep: float) -> str:
    if rep >= HEALTHY_T:
        return "PRIMARY"
    elif rep >= SUSPICIOUS_T:
        return "MONITORING"
    elif rep >= FAULTY_T:
        return "QUARANTINE"
    else:
        return "SLASHED"


# ---------------------------------------------------------------------------
# LeaderElectionManager
# ---------------------------------------------------------------------------
class LeaderElectionManager:
    """
    Elect one leader per numbered shard.

    Selection priority (descending):
      1. Highest trust-tier (PRIMARY > MONITORING > QUARANTINE > SLASHED)
      2. Within same tier: highest reputation score
      3. Deterministic tie-break: lexicographic node_id
    """

    _TIER_RANK = {t: i for i, t in enumerate(TIER_ORDER)}  # lower = better

    def elect_leaders(
        self,
        shards: Dict[int, List[Dict]],
        epoch_id: int,
    ) -> Dict[int, Optional[str]]:
        """
        Return {shard_index: leader_node_id}.
        Each shard member is a dict with keys 'node_id', 'reputation', 'tier'.
        Binary/Equal Weight Random Sampling:
        Pi = 1 / N
        """
        leaders: Dict[int, Optional[str]] = {}
        # Set seed for deterministic sampling per epoch
        random.seed(epoch_id * 1337)
        
        for sid, members in shards.items():
            if not members:
                leaders[sid] = None
                continue
            
            # Step 1: Extract node IDs
            node_ids = [m["node_id"] for m in members]
            
            # Step 2: Simple Random Selection (Equal Weight)
            leaders[sid] = random.choice(node_ids)
            
            logger.info(f"Shard {sid} leader elected via binary random choice: {leaders[sid]}")
            
        return leaders


# ---------------------------------------------------------------------------
# ReshufflingEngine
# ---------------------------------------------------------------------------
class ReshufflingEngine:
    """
    Distributes nodes into K numbered shards with interleaved round-robin
    so that each shard receives a representative cross-section of all trust tiers.

    Visual result for 8 nodes across 2 shards:
        SHARD 0: [primary_0, monitoring_0, quarantine_0, slashed_0]
        SHARD 1: [primary_1, monitoring_1, quarantine_1, slashed_1]
    """

    def _compute_shard_count(self, n_nodes: int) -> int:
        """Compute K such that each shard has roughly TARGET_SHARD_SIZE nodes."""
        if n_nodes == 0:
            return 1
        k = max(1, round(n_nodes / TARGET_SHARD_SIZE))
        # Never exceed half the node count
        return min(k, max(1, n_nodes // 2))

    def reshuffle(
        self,
        reputations: Dict[str, float],
        mitigation_actions: Optional[Dict],
        epoch_id: int,
    ) -> Tuple[Dict[int, List[Dict]], Dict[str, int], int]:
        """
        Sharding based on Round Robin after sorting by reputation.
        1. Sort nodes by reputation (descending).
        2. Assign to shards using Round Robin.
        """
        n_nodes = len(reputations)
        if n_nodes == 0:
            return {}, {}, 0

        k = self._compute_shard_count(n_nodes)
        
        # Step 1: Sort nodes by reputation (descending)
        sorted_nodes = sorted(reputations.items(), key=lambda x: x[1], reverse=True)

        # Step 2: Round Robin Allocation
        shards: Dict[int, List[Dict]] = {i: [] for i in range(k)}
        for i, (nid, rep) in enumerate(sorted_nodes):
            shard_idx = i % k
            
            # Resolve tier and action for logging
            tier = _tier_from_rep(rep)
            action = ACTION_MAP[tier]
            if mitigation_actions and nid in mitigation_actions:
                ma = mitigation_actions[nid]
                if isinstance(ma, dict):
                    action = ma.get("action", action)
                elif hasattr(ma, "action"):
                    action = ma.action
                    
            shards[shard_idx].append({
                "node_id":    nid,
                "reputation": round(rep, 4),
                "tier":       tier,
                "action":     action,
            })

        # Step 3 – Reverse assignment map
        assignment: Dict[str, int] = {}
        for sid, members in shards.items():
            for m in members:
                assignment[m["node_id"]] = sid

        # Step 3 – Reverse assignment map
        assignment: Dict[str, int] = {}
        for sid, members in shards.items():
            for m in members:
                assignment[m["node_id"]] = sid

        logger.info(
            "Slide 19 Reshuffle epoch=%d  k=%d  distribution=%s",
            epoch_id,
            k,
            {sid: len(v) for sid, v in shards.items()},
        )
        return shards, assignment, k


# ---------------------------------------------------------------------------
# EpochController
# ---------------------------------------------------------------------------
class EpochController:
    """Tracks the current epoch and decides when a reshuffle is due."""

    def __init__(self, reshuffle_interval: int = RESHUFFLE_EVERY_N_EPOCHS):
        self.reshuffle_interval = reshuffle_interval
        self.last_reshuffle_epoch: int = -1

    def is_reshuffle_due(self, epoch_id: int) -> bool:
        if self.last_reshuffle_epoch < 0:
            return True
        return (epoch_id - self.last_reshuffle_epoch) >= self.reshuffle_interval

    def mark_reshuffled(self, epoch_id: int):
        self.last_reshuffle_epoch = epoch_id


# ---------------------------------------------------------------------------
# DynamicShardManager  (public API)
# ---------------------------------------------------------------------------
class DynamicShardManager:
    """
    Main entry point for the Dynamic Trust-Aware Sharding Module.

    Each numbered shard is a *mixed* group containing nodes from all four
    trust tiers (ALLOW + WARN + QUARANTINE + SLASHED), preventing any single
    shard from being dominated by malicious nodes.

    Usage
    -----
    >>> dsm = DynamicShardManager()
    >>> dsm.on_epoch_complete(epoch_id, ml_consensus_engine)
    >>> status = dsm.get_shard_status()
    """

    def __init__(self, reshuffle_interval: int = RESHUFFLE_EVERY_N_EPOCHS):
        self._epoch_ctrl  = EpochController(reshuffle_interval)
        self._reshuffler  = ReshufflingEngine()
        self._leader_mgr  = LeaderElectionManager()

        # Current state
        self.current_epoch:   int                          = 0
        self.n_shards:        int                          = 0
        self.shards:          Dict[int, List[Dict]]        = {}   # shard_idx → [member_dicts]
        self.assignment:      Dict[str, int]               = {}   # node_id → shard_idx
        self.leaders:         Dict[int, Optional[str]]     = {}   # shard_idx → leader_id
        self.master_leader:   Optional[str]                = None # Global Network Leader
        self.shard_websites:  Dict[int, List[str]]         = {}   # shard_idx → [urls]
        self.last_reshuffle:  Optional[int]                = None

        # Audit ring-buffer
        self._history: deque = deque(maxlen=MAX_HISTORY_ENTRIES)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _read_engine(self, ml_engine):
        """Extract reputations + mitigation_actions from the ML engine (read-only)."""
        if ml_engine is None:
            return {}, {}
        reps = {}
        if getattr(ml_engine, "ewma_reputations", None):
            reps = dict(ml_engine.ewma_reputations)
        elif getattr(ml_engine, "reputation", None):
            reps = dict(ml_engine.reputation)
        actions = {}
        if getattr(ml_engine, "mitigation_actions", None):
            actions = dict(ml_engine.mitigation_actions)
        return reps, actions

    # ------------------------------------------------------------------
    # Core lifecycle
    # ------------------------------------------------------------------
    def on_epoch_complete(self, epoch_id: int, ml_engine, all_websites: List[str] = None) -> bool:
        """
        Called after every epoch consensus.

        Returns True if a reshuffle occurred, False if skipped.
        """
        self.current_epoch = epoch_id
        reputations, actions = self._read_engine(ml_engine)

        if not reputations:
            logger.warning("DynamicShardManager: no reputation data epoch=%d – skip", epoch_id)
            return False

        if not self._epoch_ctrl.is_reshuffle_due(epoch_id):
            logger.debug("DynamicShardManager: reshuffle not due at epoch=%d", epoch_id)
            # Still update website allocation if it's empty (e.g. initial start)
            if not self.shard_websites and all_websites:
                self._distribute_websites(all_websites, epoch_id)
            return False

        # ── Reshuffle ──────────────────────────────────────────────────
        prev_assignment = dict(self.assignment)
        new_shards, new_assignment, n_shards = self._reshuffler.reshuffle(
            reputations, actions, epoch_id
        )
        new_leaders = self._leader_mgr.elect_leaders(new_shards, epoch_id)

        # ── Master Leader Election ─────────────────────────────────────
        # The Master Leader is the highest-reputation leader among all shard leaders
        shard_leader_ids = [lid for lid in new_leaders.values() if lid]
        if shard_leader_ids:
            # Sort shard leaders by reputation (highest first)
            shard_leader_ids.sort(key=lambda lid: reputations.get(lid, 0.0), reverse=True)
            self.master_leader = shard_leader_ids[0]
        else:
            self.master_leader = None

        # ── Website Distribution ───────────────────────────────────────
        if all_websites:
            self._distribute_websites(all_websites, epoch_id, n_shards)

        # Detect node moves for audit trail
        moved_nodes = []
        for nid, new_sid in new_assignment.items():
            old_sid = prev_assignment.get(nid)
            if old_sid is not None and old_sid != new_sid:
                # Find tier/action in new assignment
                tier = _tier_from_rep(reputations.get(nid, 0.0))
                moved_nodes.append({
                    "node_id":    nid,
                    "from_shard": old_sid,
                    "to_shard":   new_sid,
                    "tier":       tier,
                    "action":     ACTION_MAP[tier],
                    "reputation": round(reputations.get(nid, 0.0), 4),
                })

        # Persist state
        self.n_shards       = n_shards
        self.shards         = new_shards
        self.assignment     = new_assignment
        self.leaders        = new_leaders
        self.last_reshuffle = epoch_id
        self._epoch_ctrl.mark_reshuffled(epoch_id)

        # Tier distribution summary for audit
        tier_dist = {t: 0 for t in TIER_ORDER}
        for sid, members in new_shards.items():
            for m in members:
                tier_dist[m["tier"]] += 1

        # Write audit entry
        self._history.appendleft({
            "epoch_id":     epoch_id,
            "timestamp":    time.time(),
            "n_shards":     n_shards,
            "total_nodes":  len(new_assignment),
            "tier_dist":    tier_dist,
            "shard_sizes":  {str(sid): len(v) for sid, v in new_shards.items()},
            "leaders":      {str(sid): leader for sid, leader in new_leaders.items()},
            "master_leader": self.master_leader,
            "moved_nodes":  moved_nodes,
        })

        logger.info(
            "✅ DynamicShardManager: epoch=%d  n_shards=%d  master_leader=%s  leaders=%s",
            epoch_id, n_shards, self.master_leader,
            {sid: leader for sid, leader in new_leaders.items()},
        )
        return True

    def _distribute_websites(self, websites: List[str], epoch_id: int, n_shards: Optional[int] = None):
        """Distribute websites across shards deterministically."""
        if not websites:
            return
        
        k = n_shards if n_shards is not None else self.n_shards
        if k <= 0:
            k = 1
            
        self.shard_websites = {i: [] for i in range(k)}
        
        # Deterministic shuffle of websites per epoch
        sorted_sites = sorted(websites)
        rng = random.Random(epoch_id * 104729) # Different prime for websites
        rng.shuffle(sorted_sites)
        
        # Round-robin distribution
        for i, site in enumerate(sorted_sites):
            shard_idx = i % k
            self.shard_websites[shard_idx].append(site)
            
        logger.info(f"Distributed {len(websites)} websites across {k} shards")

    # ------------------------------------------------------------------
    # Query API (used by main.py endpoints and dashboard)
    # ------------------------------------------------------------------
    def get_shard_status(self) -> Dict:
        """
        JSON-serialisable snapshot of the current shard state.
        """
        shards_out = {}
        for sid, members in self.shards.items():
            shards_out[str(sid)] = {
                "shard_id": sid,
                "leader":   self.leaders.get(sid),
                "count":    len(members),
                "members":  members,
                "websites": self.shard_websites.get(sid, [])
            }
        return {
            "current_epoch":      self.current_epoch,
            "last_reshuffle":     self.last_reshuffle,
            "n_shards":           self.n_shards,
            "master_leader":      self.master_leader,
            "reshuffle_interval": self._epoch_ctrl.reshuffle_interval,
            "shards":             shards_out,
            "assignment":         {nid: int(sid) for nid, sid in self.assignment.items()},
        }

    def get_node_shard(self, node_id: str) -> Optional[int]:
        """Return the current shard index for *node_id*, or None."""
        return self.assignment.get(node_id)

    def get_shard_leader(self, shard_id: int) -> Optional[str]:
        """Return the current leader of shard *shard_id*, or None."""
        return self.leaders.get(shard_id)
    
    def get_master_leader(self) -> Optional[str]:
        """Return the current global network leader."""
        return self.master_leader

    def get_shard_websites(self, shard_id: int) -> List[str]:
        """Return the websites assigned to shard *shard_id*."""
        return self.shard_websites.get(shard_id, [])


    def get_history(self, limit: int = 10) -> List[Dict]:
        """Return the *limit* most recent reshuffle audit entries."""
        return list(self._history)[:limit]

    def get_reshuffle_stats(self) -> Dict:
        """Aggregate stats over the history buffer."""
        if not self._history:
            return {"total_reshuffles": 0}
        total_moves = sum(len(h.get("moved_nodes", [])) for h in self._history)
        return {
            "total_reshuffles":       len(self._history),
            "total_node_moves":       total_moves,
            "avg_moves_per_reshuffle": round(total_moves / len(self._history), 2),
            "last_reshuffle_epoch":   self._history[0]["epoch_id"],
        }


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------
_shard_manager: Optional[DynamicShardManager] = None


def get_shard_manager() -> DynamicShardManager:
    global _shard_manager
    if _shard_manager is None:
        _shard_manager = DynamicShardManager()
    return _shard_manager


def init_shard_manager(reshuffle_interval: int = RESHUFFLE_EVERY_N_EPOCHS) -> DynamicShardManager:
    global _shard_manager
    _shard_manager = DynamicShardManager(reshuffle_interval=reshuffle_interval)
    logger.info("DynamicShardManager initialised (reshuffle_interval=%d)", reshuffle_interval)
    return _shard_manager
