"""
Blockchain Finality Module
Ensures blockchain is the source of truth for consensus decisions
"""

import asyncio
import logging
import time
from typing import Dict, Optional, List
from dataclasses import dataclass

logger = logging.getLogger(__name__)

@dataclass
class BlockchainState:
    """Represents the state of blockchain commitment"""
    committed: bool = False
    tx_hash: Optional[str] = None
    block_number: Optional[int] = None
    timestamp: Optional[float] = None
    verified_by: List[str] = None
    
    def __post_init__(self):
        if self.verified_by is None:
            self.verified_by = []

class BlockchainFinalityManager:
    """
    Manages blockchain finality for consensus decisions
    Ensures decisions are only valid after blockchain commit
    """
    
    def __init__(self, node_id: str, blockchain_client):
        self.node_id = node_id
        self.blockchain_client = blockchain_client
        self.pending_decisions = {}  # epoch_id -> decision
        self.committed_decisions = {}  # epoch_id -> BlockchainState
        self.verification_queue = asyncio.Queue()
        self.verification_task = None
        
    async def start_verification_loop(self):
        """Start background verification task"""
        if not self.verification_task:
            self.verification_task = asyncio.create_task(self._verification_loop())
            logger.info("Blockchain verification loop started")
    
    async def stop_verification_loop(self):
        """Stop background verification task"""
        if self.verification_task:
            self.verification_task.cancel()
            try:
                await self.verification_task
            except asyncio.CancelledError:
                pass
            logger.info("Blockchain verification loop stopped")
    
    async def submit_decision(self, epoch_id: int, decision: Dict, is_leader: bool) -> bool:
        """
        Submit decision for blockchain finality
        
        Args:
            epoch_id: Epoch identifier
            decision: Decision dictionary
            is_leader: Whether this node is the leader
            
        Returns:
            True if decision will be committed/verified, False otherwise
        """
        if is_leader:
            # Leader commits to blockchain
            try:
                result = await self.blockchain_client.submit_epoch_decision(epoch_id, decision)
                if result['success']:
                    self.committed_decisions[epoch_id] = BlockchainState(
                        committed=True,
                        tx_hash=result.get('tx_hash'),
                        block_number=result.get('block_number'),
                        timestamp=time.time(),
                        verified_by=[self.node_id]
                    )
                    logger.info(f"Epoch {epoch_id}: Leader committed decision to blockchain")
                    return True
                else:
                    logger.error(f"Epoch {epoch_id}: Leader failed to commit: {result.get('error')}")
                    return False
            except Exception as e:
                logger.error(f"Epoch {epoch_id}: Error committing to blockchain: {e}")
                return False
        else:
            # Non-leader queues for verification
            self.pending_decisions[epoch_id] = decision
            await self.verification_queue.put(epoch_id)
            logger.info(f"Epoch {epoch_id}: Non-leader queued for verification")
            return True
    
    async def verify_decision(self, epoch_id: int) -> bool:
        """
        Verify decision from blockchain
        
        Args:
            epoch_id: Epoch identifier to verify
            
        Returns:
            True if verified, False otherwise
        """
        try:
            # Check if already verified
            if epoch_id in self.committed_decisions:
                return self.committed_decisions[epoch_id].committed
            
            # Query blockchain for epoch decision
            if hasattr(self.blockchain_client, 'get_epoch_decision'):
                result = await self.blockchain_client.get_epoch_decision(epoch_id)
                if result['success']:
                    self.committed_decisions[epoch_id] = BlockchainState(
                        committed=True,
                        tx_hash=result.get('tx_hash'),
                        block_number=result.get('block_number'),
                        timestamp=time.time(),
                        verified_by=[self.node_id]
                    )
                    logger.info(f"Epoch {epoch_id}: Verified from blockchain")
                    return True
            
            # Fallback: verify individual reputations
            if epoch_id in self.pending_decisions:
                decision = self.pending_decisions[epoch_id]
                node_verdicts = decision.get('node_verdicts', {})
                
                # Verify each node's reputation on-chain
                all_verified = True
                for node_id in node_verdicts.keys():
                    try:
                        on_chain_rep = await self.blockchain_client.get_reputation(node_id)
                        if not on_chain_rep['success']:
                            all_verified = False
                            break
                    except Exception as e:
                        logger.error(f"Error verifying {node_id}: {e}")
                        all_verified = False
                        break
                
                if all_verified:
                    self.committed_decisions[epoch_id] = BlockchainState(
                        committed=True,
                        timestamp=time.time(),
                        verified_by=[self.node_id]
                    )
                    logger.info(f"Epoch {epoch_id}: Verified via individual reputations")
                    return True
            
            logger.warning(f"Epoch {epoch_id}: Could not verify from blockchain")
            return False
            
        except Exception as e:
            logger.error(f"Epoch {epoch_id}: Error during verification: {e}")
            return False
    
    async def _verification_loop(self):
        """Background loop for verifying pending decisions"""
        while True:
            try:
                # Get next epoch to verify
                epoch_id = await asyncio.wait_for(
                    self.verification_queue.get(), 
                    timeout=5.0
                )
                
                # Verify the decision
                await self.verify_decision(epoch_id)
                
                # Remove from pending if verified
                if epoch_id in self.committed_decisions:
                    self.pending_decisions.pop(epoch_id, None)
                
            except asyncio.TimeoutError:
                # No pending verifications, continue
                continue
            except Exception as e:
                logger.error(f"Error in verification loop: {e}")
                await asyncio.sleep(1)
    
    def is_decision_final(self, epoch_id: int) -> bool:
        """
        Check if decision is final (committed to blockchain)
        
        Args:
            epoch_id: Epoch identifier
            
        Returns:
            True if final, False otherwise
        """
        if epoch_id in self.committed_decisions:
            return self.committed_decisions[epoch_id].committed
        return False
    
    def get_decision_state(self, epoch_id: int) -> Optional[BlockchainState]:
        """
        Get blockchain state for decision
        
        Args:
            epoch_id: Epoch identifier
            
        Returns:
            BlockchainState or None
        """
        return self.committed_decisions.get(epoch_id)
    
    async def wait_for_finality(self, epoch_id: int, timeout: float = 30.0) -> bool:
        """
        Wait for decision to achieve finality
        
        Args:
            epoch_id: Epoch identifier
            timeout: Maximum time to wait
            
        Returns:
            True if finality achieved, False on timeout
        """
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            if self.is_decision_final(epoch_id):
                return True
            await asyncio.sleep(0.5)
        
        logger.warning(f"Epoch {epoch_id}: Finality timeout after {timeout}s")
        return False
