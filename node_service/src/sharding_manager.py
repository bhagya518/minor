# sharding_manager.py
"""Dynamic sharding utilities for the PoR network.

The idea is to split the set of participating nodes into a configurable
number of *shards* (also called *segments*).  Each epoch the leader
assigns a shard to every node based on a deterministic hash of the node
ID and the epoch number.  Nodes only need to exchange reports with peers
that belong to the same shard, which reduces the total number of
messages from O(N²) to O(N·log N) when the number of shards grows.

The implementation below is deliberately lightweight – it does not
touch the networking stack directly but provides a clean API that the
existing ``EpochManager`` and ``PeerClient`` can call.
"""

import hashlib
from typing import Dict


class ShardingManager:
    """Assign nodes to shards in a deterministic way.

    Parameters
    ----------
    shard_count: int
        Number of shards to split the network into.  Typical values are
        in the range 2‑10.  More shards mean fewer peers per node but also
        larger coordination overhead for the leader.
    """

    def __init__(self, shard_count: int = 5):
        if shard_count < 1:
            raise ValueError("shard_count must be >= 1")
        self.shard_count = shard_count

    def get_shard(self, node_id: str, epoch_id: int) -> int:
        """Return the shard index (0‑based) for *node_id* in *epoch_id*.

        The hash combines the epoch number with the node identifier so
        that a node may be reassigned to a different shard each epoch –
        this helps with load‑balancing and prevents a single shard from
        becoming a hotspot.
        """
        # Combine epoch and node ID, hash with SHA‑256 for uniformity
        hash_input = f"{epoch_id}:{node_id}".encode()
        digest = hashlib.sha256(hash_input).hexdigest()
        # Convert hex digest to int and take modulo shard count
        return int(digest, 16) % self.shard_count

    def filter_reports_by_shard(
        self, reports: list[Dict], node_id: str, epoch_id: int
    ) -> list[Dict]:
        """Keep only reports that belong to the same shard as *node_id*.

        ``reports`` is a list of monitoring‑report dictionaries that each
        contain a ``node_id`` (or ``node_address``) field.  The function
        calculates the shard for the current node and discards any report
        coming from a node that hashes to a different shard.
        """
        own_shard = self.get_shard(node_id, epoch_id)
        filtered = []
        for rpt in reports:
            other_id = rpt.get("node_address") or rpt.get("node_id")
            if other_id is None:
                continue
            if self.get_shard(other_id, epoch_id) == own_shard:
                filtered.append(rpt)
        return filtered

# Helper singleton that can be imported by the rest of the code base.
# Adjust ``shard_count`` here if you want a different default.
sharding_manager = ShardingManager(shard_count=5)
