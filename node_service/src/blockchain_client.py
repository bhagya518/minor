"""
Blockchain Integration Client
Handles interaction with Ethereum blockchain for Proof of Reputation system
"""

import json
import os
import logging
from typing import Dict, List, Optional, Tuple
from web3 import Web3
from eth_account import Account
import time
from datetime import datetime
import threading

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class BlockchainClient:
    """Client for interacting with Proof of Reputation smart contract"""
    
    def __init__(self, config: Dict = None):
        """
        Initialize blockchain client
        
        Args:
            config: Configuration dictionary with blockchain settings
        """
        self.config = config or self._load_config()
        
        # Robust Hex Normalization for passed config dictionary
        if self.config.get('private_key'):
            self.config['private_key'] = str(self.config['private_key']).strip().strip('"').strip("'")
            if self.config['private_key'] and not self.config['private_key'].startswith('0x'):
                self.config['private_key'] = '0x' + self.config['private_key']
                
        if self.config.get('contract_address'):
            self.config['contract_address'] = str(self.config['contract_address']).strip().strip('"').strip("'")
            if self.config['contract_address'] and not self.config['contract_address'].startswith('0x'):
                self.config['contract_address'] = '0x' + self.config['contract_address']

        self.w3 = None
        self.contract = None
        self.account = None
        self.contract_address = None
        self.contract_abi = None
        
        self._connect()
        self._load_contract()
    
    def _load_config(self) -> Dict:
        """Load blockchain configuration from environment or config file"""
        config = {
            'rpc_url': os.getenv('ETHEREUM_RPC_URL', 'http://127.0.0.1:8545'),
            # Strip whitespace and ensure hex prefix for private key
            'private_key': (os.getenv('PRIVATE_KEY') or '').strip(),
            # Strip whitespace
            'contract_address': (os.getenv('CONTRACT_ADDRESS') or '').strip(),
            'chain_id': int(os.getenv('CHAIN_ID', '31337')),
            'gas_limit': int(os.getenv('GAS_LIMIT', '3000000')),
            'gas_price_gwei': int(os.getenv('GAS_PRICE_GWEI', '20'))
        }
        # Normalize hex strings (add 0x prefix if missing)
        if config['private_key'] and not config['private_key'].startswith('0x'):
            config['private_key'] = '0x' + config['private_key']
        if config['contract_address'] and not config['contract_address'].startswith('0x'):
            config['contract_address'] = '0x' + config['contract_address']      
        
        # Try to load from deployment file if contract address not in env
        if not config['contract_address']:
            deployment_file = os.path.join(os.path.dirname(__file__), '..', 'deployment.json')
            if os.path.exists(deployment_file):
                with open(deployment_file, 'r') as f:
                    deployment = json.load(f)
                    config['contract_address'] = deployment.get('contractAddress')
        
        return config
    
    def _connect(self):
        """Connect to Ethereum network"""
        try:
            logger.info(f"Connecting to Ethereum network: {self.config['rpc_url']}")
            
            self.w3 = Web3(Web3.HTTPProvider(self.config['rpc_url'], request_kwargs={'timeout': 2.0}))
            
            # Check connection
            if not self.w3.is_connected():
                raise ConnectionError("Failed to connect to Ethereum network")
            
            logger.info("✅ Successfully connected to blockchain")
            
            # Set up account if private key provided
            if self.config['private_key']:
                # Validate if it's a valid 64-character hex string before trying to parse
                is_valid = False
                clean_key = self.config['private_key'][2:] if self.config['private_key'].startswith('0x') else self.config['private_key']
                if len(clean_key) == 64:
                    try:
                        int(clean_key, 16)
                        is_valid = True
                    except ValueError:
                        pass
                
                if is_valid:
                    try:
                        self.account = Account.from_key(self.config['private_key'])
                        logger.info(f"Using account from PRIVATE_KEY: {self.account.address}")
                    except Exception as e:
                        logger.error(f"Invalid PRIVATE_KEY format: {e}. Falling back to default account.")
                        self.account = None
                else:
                    logger.error(f"Invalid PRIVATE_KEY format: '{self.config['private_key']}' is not a valid 64-character hex string. Falling back to default account.")
                    self.config['private_key'] = None
                    self.account = None
            if not self.account:
                # Use the first unlocked account from the node if available
                accounts = self.w3.eth.accounts
                if accounts:
                    # Attempt to use the account without a private key (read‑only calls)
                    self.account = Account.from_key('0x' + '0' * 64)
                    logger.warning("Using placeholder account for read‑only operations. Set a valid PRIVATE_KEY for transaction signing.")
            
            logger.info("Connected to Ethereum network successfully")
            
        except Exception as e:
            logger.error(f"Failed to connect to blockchain: {e}")
            # Re‑raise to allow caller to handle retry logic
            raise
    
    def is_blockchain_available(self) -> bool:
        """
        Check if blockchain is available and healthy
        
        Returns:
            bool: True if blockchain is available, False otherwise
        """
        try:
            if not self.w3 or not self.w3.is_connected():
                return False
            
            # Try to get latest block number as health check
            latest_block = self.w3.eth.block_number
            if latest_block is None:
                return False
            
            # Check if contract is loaded and accessible
            if self.contract:
                try:
                    # Try to call a simple contract method
                    chain_id = self.w3.eth.chain_id
                    return True
                except Exception:
                    return False
            
            return True
            
        except Exception as e:
            logger.error(f"Blockchain health check failed: {e}")
            return False
    
    def _load_contract(self):
        """Load smart contract ABI and address"""
        try:
            # ── 1. Load ABI ─────────────────────────────────────────────
            # Prefer compiled Hardhat artifact (has the fullest ABI)
            artifacts_dir = os.path.join(os.path.dirname(__file__), '..', '..', 'blockchain', 'artifacts', 'contracts', 'ProofOfReputation.sol')
            contract_artifact = os.path.join(artifacts_dir, 'ProofOfReputation.json')
            simple_abi_file = os.path.join(os.path.dirname(__file__), '..', '..', 'blockchain', 'ProofOfReputation.json')
            deployment_file = os.path.join(os.path.dirname(__file__), '..', '..', 'blockchain', 'deployment.json')

            if os.path.exists(contract_artifact):
                with open(contract_artifact, 'r') as f:
                    artifact = json.load(f)
                    self.contract_abi = artifact.get('abi')
                    logger.info(f"Loaded ABI from Hardhat artifact ({len(self.contract_abi or [])} entries)")
            elif os.path.exists(simple_abi_file):
                with open(simple_abi_file, 'r') as f:
                    contract_data = json.load(f)
                    self.contract_abi = contract_data.get('abi')
                    logger.info(f"Loaded ABI from simple JSON ({len(self.contract_abi or [])} entries)")
            else:
                raise FileNotFoundError("Contract ABI not found in either compiled artifact or simple JSON path.")

            # ── 2. Resolve contract address (priority order) ────────────
            # Priority: config dict > deployment.json > simple JSON > artifact
            address = self.config.get('contract_address')

            # Try to load from deployment file if contract address not in env
            if not address and os.path.exists(deployment_file):
                with open(deployment_file, 'r') as f:
                    deployment = json.load(f)
                    address = deployment.get('contractAddress') or deployment.get('address')
                    if address:
                        logger.info(f"Got contract address from deployment.json (src dir): {address}")
            
            # New fallback: look in the top-level blockchain folder
            if not address:
                alt_deployment = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'blockchain', 'deployment.json'))
                if os.path.exists(alt_deployment):
                    with open(alt_deployment, 'r') as f:
                        deployment = json.load(f)
                        address = deployment.get('contractAddress') or deployment.get('address')
                        if address:
                            logger.info(f"Got contract address from blockchain/deployment.json: {address}")

            if not address and os.path.exists(simple_abi_file):
                with open(simple_abi_file, 'r') as f:
                    contract_data = json.load(f)
                    address = contract_data.get('address')
                    if address:
                        logger.info(f"Got contract address from ProofOfReputation.json: {address}")

            # ── 3. Validate address ─────────────────────────────────────
            if not address:
                raise ValueError(
                    "Contract address not found! Ensure you have:\n"
                    "  1. Deployed the contract (npx hardhat run scripts/deploy.js --network localhost)\n"
                    "  2. deployment.json or ProofOfReputation.json exists in blockchain/ with an 'address' field\n"
                    "  3. Or set CONTRACT_ADDRESS environment variable"
                )

            # Checksum the address
            self.contract_address = Web3.to_checksum_address(address)
            self.config['contract_address'] = self.contract_address

            # ── 4. Create contract instance ─────────────────────────────
            self.contract = self.w3.eth.contract(
                address=self.contract_address,
                abi=self.contract_abi
            )

            logger.info(f"✅ Contract loaded at address: {self.contract_address}")

        except Exception as e:
            logger.error(f"Failed to load contract: {e}")
            raise

    def _ensure_ready(self):
        """Guard: abort early if blockchain or contract is not available"""
        if not self.w3 or not self.w3.is_connected():
            raise ConnectionError("Web3 provider not connected")
        if not self.contract or not getattr(self.contract, 'address', None):
            raise RuntimeError(
                f"Contract not initialized (address={self.contract_address}). "
                "Deploy the contract first and ensure the address is saved."
            )

    
    def _send_transaction(self, function_call, value: int = 0) -> Dict:
        """Send transaction to blockchain with local nonce safety and 5 retries with 3-second delays"""
        self._ensure_ready()
        
        if not hasattr(self, '_nonce_lock'):
            self._nonce_lock = threading.Lock()
        if not hasattr(self, '_local_nonce'):
            self._local_nonce = None
            
        with self._nonce_lock:
            for attempt in range(5):  # 5 retries as per spec
                try:
                    # Fetch fresh pending count if local nonce is not initialized or lower
                    pending_nonce = self.w3.eth.get_transaction_count(self.account.address, 'pending')
                    if self._local_nonce is None or self._local_nonce < pending_nonce:
                        self._local_nonce = pending_nonce
                        
                    nonce = self._local_nonce
                    
                    transaction = function_call.build_transaction({
                        'from': self.account.address,
                        'value': value,
                        'gas': self.config['gas_limit'],
                        'gasPrice': self.w3.to_wei(self.config['gas_price_gwei'], 'gwei'),
                        'nonce': nonce,
                        'chainId': self.config['chain_id']
                    })
                    
                    # Sign transaction
                    signed_txn = self.account.sign_transaction(transaction)
                    
                    # Send transaction
                    tx_hash = self.w3.eth.send_raw_transaction(signed_txn.raw_transaction)
                    
                    # Increment local nonce immediately for subsequent transactions
                    self._local_nonce += 1
                    
                    # Wait for receipt
                    receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash, timeout=5)
                    
                    if receipt.status == 1:
                        logger.info(f"Transaction successful: {tx_hash.hex()}")
                        return {
                            'success': True,
                            'tx_hash': tx_hash.hex(),
                            'block_number': receipt.blockNumber,
                            'gas_used': receipt.gasUsed
                        }
                    else:
                        logger.error(f"Transaction failed: {tx_hash.hex()}")
                        return {
                            'success': False,
                            'tx_hash': tx_hash.hex(),
                            'error': 'Transaction reverted'
                        }
                        
                except Exception as e:
                    err_msg = str(e)
                    logger.warning(f"Transaction attempt {attempt + 1}/5 failed: {err_msg}")
                    # If nonce is too low or transaction is already known, reset local nonce and retry
                    if any(x in err_msg.lower() for x in ["nonce too low", "already known", "underpriced"]):
                        self._local_nonce = None
                        if attempt < 4:  # Don't sleep on last attempt
                            time.sleep(3)  # 3-second delay as per spec
                        continue
                    else:
                        self._local_nonce = None
                        return {
                            'success': False,
                            'error': err_msg
                        }
            
            return {
                'success': False,
                'error': "Failed to send transaction after 5 attempts due to nonce/network issues"
            }
    
    def register_node(self, node_id: str) -> Dict:
        """
        Register a new node in the blockchain
        
        Args:
            node_id: Unique identifier for the node
            
        Returns:
            Transaction result
        """
        try:
            logger.info(f"Registering node: {node_id}")
            
            # Check if already registered
            if self.is_node_registered(node_id):
                logger.warning(f"Node {node_id} already registered")
                return {
                    'success': True,
                    'error': 'Node already registered'
                }
            
            # Call registerNode function
            function_call = self.contract.functions.registerNode(node_id)
            result = self._send_transaction(function_call)
            
            if result['success']:
                logger.info(f"Node {node_id} registered successfully")
            
            return result
            
        except Exception as e:
            logger.error(f"Failed to register node {node_id}: {e}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def update_reputation(self, node_id: str, monitoring_trust: float, ml_score: float, evidence: str = "") -> Dict:
        """
        Update node reputation on blockchain
        
        Args:
            node_id: Node identifier
            monitoring_trust: Monitoring trust score (0-1)
            ml_score: ML confidence score (0-1)
            evidence: Optional evidence string for the update
            
        Returns:
            Transaction result
        """
        try:
            logger.info(f"Updating reputation for node: {node_id}")
            
            # Convert to blockchain format (0-1000)
            monitoring_trust_scaled = int(monitoring_trust * 1000)
            ml_score_scaled = int(ml_score * 1000)
            
            # Call updateReputation function
            function_call = self.contract.functions.updateReputation(
                node_id, 
                monitoring_trust_scaled, 
                ml_score_scaled
            )
            result = self._send_transaction(function_call)
            
            if result['success']:
                logger.info(f"Reputation updated for node {node_id}")
            
            return result
            
        except Exception as e:
            logger.error(f"Failed to update reputation for node {node_id}: {e}")
            return {
                'success': False,
                'error': str(e)
            }
    
    async def batch_update_reputation(self, updates: List[Dict]) -> Dict:
        """
        Batch update multiple node reputations in a single transaction
        This reduces blockchain transactions from O(n) to O(1) per epoch
        
        Args:
            updates: List of dicts with keys: node_id, monitoring_trust, ml_score
            
        Returns:
            Transaction result
        """
        try:
            logger.info(f"Batch updating {len(updates)} reputation updates")
            
            # If contract supports batch updates, use it
            if hasattr(self.contract.functions, 'batchUpdateReputation'):
                # Prepare batch data
                node_ids = [u['node_id'] for u in updates]
                monitoring_trusts = [int(u['monitoring_trust'] * 1000) for u in updates]
                ml_scores = [int(u['ml_score'] * 1000) for u in updates]
                
                function_call = self.contract.functions.batchUpdateReputation(node_ids, monitoring_trusts, ml_scores)
                result = self._send_transaction(function_call)
                
                if result['success']:
                    logger.info(f"Batch reputation update completed for {len(updates)} nodes")
                
                return result
            else:
                # Fallback: sequential updates using monitoring_trust and ml_score keys
                results = []
                for update in updates:
                    result = self.update_reputation(
                        update['node_id'],
                        update['monitoring_trust'],
                        update['ml_score'],
                        evidence=update.get('evidence', '')
                    )
                    results.append(result)
                
                success_count = sum(1 for r in results if r.get('success'))
                logger.info(f"Batch update completed: {success_count}/{len(updates)} successful")
                
                return {
                    'success': success_count == len(updates),
                    'total': len(updates),
                    'successful': success_count,
                    'results': results
                }
                
        except Exception as e:
            logger.error(f"Failed to batch update reputations: {e}")
            return {
                'success': False,
                'error': str(e)
            }
    
    async def submit_epoch_decision(self, epoch_id: int, decision: Dict) -> Dict:
        """
        Submit final epoch decision to blockchain
        Only leader should call this - this makes blockchain the source of truth
        
        Args:
            epoch_id: Epoch identifier
            decision: Epoch decision dictionary with verdicts and reputations
            
        Returns:
            Transaction result
        """
        try:
            logger.info(f"Submitting epoch {epoch_id} decision to blockchain")
            
            # Extract key decision data
            node_verdicts = decision.get('node_verdicts', {})
            node_weights = decision.get('node_weights', {})
            
            # Prepare blockchain-compatible data
            node_ids = list(node_verdicts.keys())
            verdicts = [1 if node_verdicts[nid] == 'malicious' else 0 for nid in node_ids]
            reputations = [int(node_weights.get(nid, 0.5) * 1000) for nid in node_ids]
            
            # Use contract's submitEpochDecision function
            function_call = self.contract.functions.submitEpochDecision(
                epoch_id,
                node_ids,
                verdicts,
                reputations
            )
            result = self._send_transaction(function_call)
            
            if result['success']:
                logger.info(f"Epoch {epoch_id} decision committed to blockchain")
                
                # PHASE 3: Broadcast decision to peers if peer_client is attached
                # This ensures followers sync their local state immediately
                if hasattr(self, 'peer_client') and self.peer_client:
                    try:
                        broadcast_data = {
                            'epoch_id': epoch_id,
                            'node_ids': node_ids,
                            'verdicts': verdicts,
                            'reputations': reputations,
                            'timestamp': time.time()
                        }
                        # We use a non-blocking way to broadcast if possible, or just await it
                        import asyncio
                        asyncio.create_task(self.peer_client.broadcast_message(
                            'epoch_decision',
                            broadcast_data
                        ))
                        logger.info(f"Epoch {epoch_id} decision broadcasted to network via P2P")
                    except Exception as e:
                        logger.warning(f"Failed to broadcast epoch decision: {e}")
            
            return result
                
        except Exception as e:
            logger.error(f"Failed to submit epoch decision: {e}")
            return {
                'success': False,
                'error': str(e)
            }
    
    async def get_epoch_decision(self, epoch_id: int) -> Dict:
        """
        Get epoch decision from blockchain for verification
        
        Args:
            epoch_id: Epoch identifier
            
        Returns:
            Epoch decision status
        """
        try:
            # Call getEpochDecision function
            submitted, timestamp = self.contract.functions.getEpochDecision(epoch_id).call()
            
            return {
                'success': True,
                'epoch_id': epoch_id,
                'submitted': submitted,
                'timestamp': timestamp,
                'verified': submitted  # Decision is verified if submitted
            }
            
        except Exception as e:
            logger.error(f"Failed to get epoch decision {epoch_id}: {e}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def slash_node(self, node_id: str, amount: float, reason: str, epoch_id: int) -> Dict:
        """
        Slash a node by reducing its reputation
        
        Args:
            node_id: Node identifier
            amount: Slash amount as percentage (0.1 = 10%)
            reason: Reason for slashing
            epoch_id: Current epoch ID
            
        Returns:
            Transaction result
        """
        try:
            logger.info(f"Slashing node {node_id} by {amount*100}% for: {reason}")
            
            # Convert percentage to basis points (10000 = 100%)
            basis_points = int(amount * 10000)
            
            # Call slashNode function
            function_call = self.contract.functions.slashNode(
                node_id,
                basis_points,
                reason,
                epoch_id
            )
            result = self._send_transaction(function_call)
            
            if result['success']:
                logger.warning(f"Successfully slashed node {node_id} by {amount*100}%")
            
            return result
            
        except Exception as e:
            logger.error(f"Failed to slash node {node_id}: {e}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def batch_slash_nodes(self, node_ids: List[str], amounts: List[float], reason: str, epoch_id: int) -> Dict:
        """
        Slash multiple nodes in a single transaction
        
        Args:
            node_ids: List of node identifiers
            amounts: List of slash amounts as percentages
            reason: Reason for slashing
            epoch_id: Current epoch ID
            
        Returns:
            Transaction result
        """
        try:
            logger.info(f"Batch slashing {len(node_ids)} nodes")
            
            # Convert percentages to basis points
            basis_points = [int(amount * 10000) for amount in amounts]
            
            # Call batchSlashNodes function
            function_call = self.contract.functions.batchSlashNodes(
                node_ids,
                basis_points,
                reason,
                epoch_id
            )
            result = self._send_transaction(function_call)
            
            if result['success']:
                logger.info(f"Successfully batch slashed {len(node_ids)} nodes")
            
            return result
            
        except Exception as e:
            logger.error(f"Failed to batch slash nodes: {e}")
            return {
                'success': False,
                'error': str(e)
            }
    
    async def submit_consolidated_reports(self, epoch_id: int, reports: List[Dict], shard_id: int = 1) -> Dict:
        """
        Submit consolidated monitoring results for an epoch in a single batch.
        Complies with Slide 23 block body structure.
        """
        try:
            logger.info(f"Submitting {len(reports)} consolidated reports for epoch {epoch_id} (Shard {shard_id})")
            
            # Prepare data for Slide 23 compliant batchSubmitAggregatedReports
            node_ids = [r.get('node_id', self.account.address) for r in reports]
            urls = [r['url'] for r in reports]
            epoch_ids = [int(r['epoch']) for r in reports]
            statuses = [bool(r['status']) for r in reports]
            latencies = [int(r['latency']) for r in reports]
            failure_rates = [int(r.get('failure_rate', 0)) for r in reports]
            anomaly_probs = [int(r.get('anomaly_prob', 0)) for r in reports]
            rep_scores = [int(r.get('reputation', 500)) for r in reports]
            
            # Check if contract has batchSubmitAggregatedReports
            if hasattr(self.contract.functions, 'batchSubmitAggregatedReports'):
                function_call = self.contract.functions.batchSubmitAggregatedReports(
                    node_ids,
                    urls,
                    epoch_ids,
                    statuses,
                    latencies,
                    failure_rates,
                    anomaly_probs,
                    rep_scores,
                    int(shard_id)
                )
                result = self._send_transaction(function_call)
                return result
            else:
                # Fallback to individual submissions if batch not available
                results = []
                for r in reports:
                    res = self.submit_aggregated_report(
                        node_id=r.get('node_id', self.account.address),
                        url=r['url'],
                        epoch_id=int(r['epoch']),
                        status=bool(r['status']),
                        avg_latency=int(r['latency']),
                        failure_rate=int(r.get('failure_rate', 0)),
                        anomaly_prob=int(r.get('anomaly_prob', 0)),
                        rep_score=int(r.get('reputation', 500))
                    )
                    results.append(res)
                
                success_count = sum(1 for res in results if res.get('success'))
                return {
                    'success': success_count > 0,
                    'total': len(reports),
                    'successful': success_count,
                    'results': results
                }
                
        except Exception as e:
            logger.error(f"Failed to submit consolidated reports: {e}")
            return {'success': False, 'error': str(e)}

    def submit_aggregated_report(self, node_id: str, url: str, epoch_id: int, status: bool,
                                 avg_latency: int, failure_rate: int, anomaly_prob: int,
                                 rep_score: int) -> Dict:
        """
        Submit an aggregated consensus report for an epoch (Slide 23 compliant)
        """
        try:
            logger.info(f"Submitting Slide 23 compliant report for {url}, epoch {epoch_id}")

            # Call submitAggregatedReport function with new parameters
            function_call = self.contract.functions.submitAggregatedReport(
                node_id,
                url,
                epoch_id,
                status,
                avg_latency,
                failure_rate,
                anomaly_prob,
                rep_score
            )
            result = self._send_transaction(function_call)

            if result['success']:
                logger.info(f"✅ Slide 23 report submitted for {url}")

            return result

        except Exception as e:
            logger.error(f"❌ Failed to submit aggregated report: {e}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def get_node_slash_history(self, node_id: str) -> Dict:
        """
        Get slashing history for a specific node
        
        Args:
            node_id: Node identifier
            
        Returns:
            Slashing history
        """
        try:
            # Call getNodeSlashHistory function
            slash_records = self.contract.functions.getNodeSlashHistory(node_id).call()
            
            # Format records
            history = []
            for record in slash_records:
                history.append({
                    'node_id': record[0],
                    'amount': record[1] / 10000.0,  # Convert basis points to percentage
                    'reason': record[2],
                    'timestamp': record[3],
                    'epoch_id': record[4]
                })
            
            return {
                'success': True,
                'history': history,
                'total_slashes': len(history)
            }
            
        except Exception as e:
            logger.error(f"Failed to get slash history for {node_id}: {e}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def get_website_history(self, url: str) -> Dict:
        """
        Get consensus history for a website
        
        Args:
            url: Website URL
            
        Returns:
            Website monitoring history
        """
        try:
            # Call getWebsiteHistory function
            epochs, results = self.contract.functions.getWebsiteHistory(url).call()
            
            # Format history
            history = []
            for i in range(len(epochs)):
                history.append({
                    'epoch_id': epochs[i],
                    'result': results[i],  # True=UP, False=DOWN
                    'timestamp': None  # Would need additional call to get timestamp
                })
            
            return {
                'success': True,
                'url': url,
                'history': history,
                'total_checks': len(history)
            }
            
        except Exception as e:
            logger.error(f"Failed to get website history for {url}: {e}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def submit_report(self, node_id: str, success: bool) -> Dict:
        """
        Submit a report from a node
        
        Args:
            node_id: Node identifier
            success: Whether the report was successful/accurate
            
        Returns:
            Transaction result
        """
        try:
            logger.info(f"Submitting report for node: {node_id}, success: {success}")
            
            # Call submitReport function
            function_call = self.contract.functions.submitReport(node_id, success)
            result = self._send_transaction(function_call)
            
            if result['success']:
                logger.info(f"Report submitted for node {node_id}")
            
            return result
            
        except Exception as e:
            logger.error(f"Failed to submit report for node {node_id}: {e}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def get_node_reputation(self, node_id: str) -> Optional[Dict]:
        """
        Get node reputation from blockchain
        
        Args:
            node_id: Node identifier
            
        Returns:
            Node reputation data or None if not found
        """
        try:
            if not self.is_node_registered(node_id):
                return None
            
            # Call getNodeReputation function
            reputation_data = self.contract.functions.getNodeReputation(node_id).call()
            
            # Convert to readable format
            result = {
                'node_id': node_id,
                'reputation': reputation_data[0] / 1000.0,  # Convert from 0-1000 to 0-1
                'monitoring_trust': reputation_data[1] / 1000.0,
                'ml_score': reputation_data[2] / 1000.0,
                'last_updated': datetime.fromtimestamp(reputation_data[3]).isoformat(),
                'is_registered': True
            }
            
            return result
            
        except Exception as e:
            logger.error(f"Failed to get reputation for node {node_id}: {e}")
            return None
    
    def get_node_stats(self, node_id: str) -> Optional[Dict]:
        """
        Get node statistics from blockchain
        
        Args:
            node_id: Node identifier
            
        Returns:
            Node statistics or None if not found
        """
        try:
            if not self.is_node_registered(node_id):
                return None
            
            # Call getNodeStats function
            stats_data = self.contract.functions.getNodeStats(node_id).call()
            
            # Convert to readable format
            result = {
                'node_id': node_id,
                'total_reports': stats_data[0],
                'successful_reports': stats_data[1],
                'success_rate': stats_data[2]  # Already in percentage
            }
            
            return result
            
        except Exception as e:
            logger.error(f"Failed to get stats for node {node_id}: {e}")
            return None
    
    def is_node_registered(self, node_id: str) -> bool:
        """Check if node is registered on blockchain"""
        try:
            self._ensure_ready()
            return self.contract.functions.isNodeRegistered(node_id).call()
        except Exception as e:
            logger.error(f"Failed to check registration for node {node_id}: {e}")
            return False
    
    def get_all_nodes(self) -> List[str]:
        """Get all registered node IDs"""
        try:
            return self.contract.functions.getAllNodes().call()
        except Exception as e:
            logger.error(f"Failed to get all nodes: {e}")
            return []
    
    def get_top_nodes(self, n: int = 10) -> List[Dict]:
        """Get top N nodes by reputation"""
        try:
            node_ids, reputations = self.contract.functions.getTopNodes(n).call()
            
            result = []
            for i in range(len(node_ids)):
                result.append({
                    'node_id': node_ids[i],
                    'reputation': reputations[i] / 1000.0  # Convert to 0-1 scale
                })
            
            return result
            
        except Exception as e:
            logger.error(f"Failed to get top nodes: {e}")
            return []
    
    def get_node_count(self) -> int:
        """Get total number of registered nodes"""
        try:
            return self.contract.functions.getNodeCount().call()
        except Exception as e:
            logger.error(f"Failed to get node count: {e}")
            return 0
    
    def calculate_por_score(self, monitoring_trust: float, ml_score: float) -> float:
        """
        Calculate Proof of Reputation score
        
        Args:
            monitoring_trust: Monitoring trust score (0-1)
            ml_score: ML confidence score (0-1)
            
        Returns:
            PoR score (0-1)
        """
        return 0.6 * monitoring_trust + 0.4 * ml_score
    
    def health_check(self) -> Dict:
        """Check blockchain connection and contract availability"""
        try:
            # Check web3 connection
            if not self.w3.is_connected():
                return {
                    'status': 'unhealthy',
                    'error': 'Not connected to blockchain'
                }
            
            # Check contract
            if not self.contract:
                return {
                    'status': 'unhealthy',
                    'error': 'Contract not loaded'
                }
            
            # Try to call a view function
            node_count = self.get_node_count()
            latest_block = self.w3.eth.block_number
            
            return {
                'status': 'healthy',
                'blockchain': {
                    'connected': True,
                    'latest_block': latest_block,
                    'chain_id': self.config['chain_id']
                },
                'contract': {
                    'address': self.contract_address,
                    'node_count': node_count
                }
            }
            
        except Exception as e:
            logger.error(f"Health check failed: {e}")
            return {
                'status': 'unhealthy',
                'error': str(e)
            }

# Singleton instance for global use
_blockchain_client = None

def get_blockchain_client(config: Dict = None) -> BlockchainClient:
    """Get or create blockchain client instance"""
    global _blockchain_client
    
    if _blockchain_client is None:
        _blockchain_client = BlockchainClient(config)
    
    return _blockchain_client

if __name__ == "__main__":
    # Test the blockchain client
    import json
    
    try:
        client = get_blockchain_client()
        
        # Health check
        health = client.health_check()
        print("Health Check:")
        print(json.dumps(health, indent=2))
        
        # Get node count
        node_count = client.get_node_count()
        print(f"\nTotal nodes: {node_count}")
        
        # Get all nodes
        all_nodes = client.get_all_nodes()
        print(f"All nodes: {all_nodes}")
        
        # Get top nodes
        top_nodes = client.get_top_nodes(5)
        print("\nTop 5 nodes:")
        for node in top_nodes:
            print(f"  {node['node_id']}: {node['reputation']:.3f}")
            
    except Exception as e:
        print(f"Error: {e}")
        print("Make sure blockchain node is running and contract is deployed")
