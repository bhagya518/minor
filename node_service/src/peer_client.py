"""
Peer Communication Module
Handles P2P communication between monitoring nodes
Phase 2: Added support for broadcasting signed MonitoringReport objects
"""

import asyncio
import aiohttp
from aiohttp import web
import json
import logging
import time
import gzip
from typing import Dict, List, Optional, Set, Callable, Tuple
from datetime import datetime
import socket
from dataclasses import dataclass, asdict
import uuid

# Import signed report system (Phase 2)
try:
    from src.monitoring_report import MonitoringReport, NodeSigner, ReportVerifier
    REPORT_AVAILABLE = True
except ImportError:
    REPORT_AVAILABLE = False
    NodeSigner = None
    ReportVerifier = None

# Import epoch manager for decision handling
try:
    from src.epoch_manager import get_epoch_manager
    EPOCH_MANAGER_AVAILABLE = True
except ImportError:
    EPOCH_MANAGER_AVAILABLE = False
    get_epoch_manager = None

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Production limits
MAX_PEERS = 50

# Configurable timeouts
class PeerConfig:
    MESSAGE_TIMEOUT = 2.0
    REPORT_TIMEOUT = 5.0
    HEALTH_CHECK_TIMEOUT = 5.0
    DISCOVERY_TIMEOUT = 2.0
    CONNECTION_LIMIT = 100
    CONNECTION_PER_HOST = 10
    FANOUT = 3
    MAX_RETRIES = 3
    RETRY_BACKOFF_BASE = 0.5  # seconds
    RATE_LIMIT_PER_SECOND = 100
    COMPRESSION_THRESHOLD = 1024  # bytes - only compress payloads larger than this

@dataclass
class PeerNode:
    """Information about a peer node"""
    node_id: str
    host: str
    port: int
    last_seen: datetime
    trust_score: float = 0.5
    is_active: bool = True
    public_key_hex: Optional[str] = None

class PeerClient:
    """Client for P2P communication between monitoring nodes"""
    
    def __init__(self, node_id: str, host: str = "localhost", port: int = 8000):
        """
        Initialize peer client
        
        Args:
            node_id: Unique identifier for this node
            host: Host address for this node
            port: Port for this node (API port)
        """
        self.node_id = node_id
        self.host = host
        self.port = port
        self.p2p_port = port + 1000  # Separate P2P port to avoid conflicts
        self.peers: Dict[str, PeerNode] = {}
        self.session = None
        self.server = None
        self.message_handlers = {}
        self.public_key_hex = None  # Will be set when keys are generated
        self._seen_message_ids: Set[str] = set()
        self._seen_message_order: List[str] = []
        self._seen_message_max = 5000
        self._connector = None  # Connection pool
        self._node_signer = None  # Will be set from main.py
        self._message_timestamps: List[float] = []  # For rate limiting
        
        # Message types
        self.MESSAGE_TYPES = {
            'HEARTBEAT': 'heartbeat',
            'MONITORING_RESULT': 'monitoring_result',
            'TRUST_UPDATE': 'trust_update',
            'PEER_DISCOVERY': 'peer_discovery',
            'CONTENT_HASH': 'content_hash',
            'ML_PREDICTION': 'ml_prediction',
            'EPOCH_DECISION': 'epoch_decision'
        }
        
        logger.info(f"Peer client initialized for node {node_id} on {host}:{port}")
    
    async def start_server(self):
        """Start the P2P server"""
        try:
            # Create connection pool for outgoing requests
            self._connector = aiohttp.TCPConnector(
                limit=PeerConfig.CONNECTION_LIMIT,
                limit_per_host=PeerConfig.CONNECTION_PER_HOST
            )
            self.session = aiohttp.ClientSession(
                connector=self._connector
            )
            
            # Create aiohttp server
            app = web.Application()
            
            # Add routes
            app.router.add_post('/peer/message', self.handle_message)
            app.router.add_get('/peer/info', self.handle_info_request)
            app.router.add_post('/peer/discovery', self.handle_peer_discovery)
            
            # Start server
            runner = web.AppRunner(app)
            await runner.setup()
            
            site = web.TCPSite(runner, self.host, self.p2p_port)
            await site.start()
            
            self.server = runner
            logger.info(f"P2P server started on {self.host}:{self.p2p_port}")
            
        except Exception as e:
            logger.error(f"Failed to start P2P server: {e}")
            raise
    
    async def close_session(self):
        """Close the aiohttp session"""
        if self.session:
            await self.session.close()
            self.session = None
        if self._connector:
            await self._connector.close()
            self._connector = None
    
    async def stop_server(self):
        """Stop the P2P server"""
        if self.server:
            await self.server.cleanup()
        await self.close_session()
        logger.info("P2P server stopped")
    
    async def __aenter__(self):
        """Async context manager entry"""
        self.session = aiohttp.ClientSession()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        if self.session:
            await self.session.close()
        await self.stop_server()
    
    def set_node_signer(self, signer):
        """Set the node signer for message authentication"""
        self._node_signer = signer
        logger.info("Node signer set for message authentication")
    
    def _sign_message(self, message: Dict) -> Dict:
        """Sign a message with Ed25519"""
        if not self._node_signer:
            logger.warning("No node signer available, message not signed")
            return message
        
        # Create canonical string for signing
        message_copy = message.copy()
        message_copy.pop('signature', None)  # Remove signature if present
        canonical = json.dumps(message_copy, sort_keys=True)
        
        # Sign the canonical string
        signature = self._node_signer.sign(canonical)
        message['signature'] = signature
        
        return message
    
    def _verify_message(self, message: Dict, sender_pubkey: str) -> bool:
        """Verify a message signature"""
        if not ReportVerifier:
            logger.warning("ReportVerifier not available, skipping verification")
            return True  # Skip verification if not available
        
        signature = message.get('signature')
        if not signature:
            logger.warning("Message has no signature")
            return False
        
        # Create canonical string for verification
        message_copy = message.copy()
        message_copy.pop('signature', None)
        canonical = json.dumps(message_copy, sort_keys=True)
        
        # Verify signature
        try:
            is_valid = ReportVerifier.verify(signature, canonical, sender_pubkey)
            if not is_valid:
                logger.warning(f"Invalid signature from sender {message.get('sender_id')}")
            return is_valid
        except Exception as e:
            logger.error(f"Error verifying message signature: {e}")
            return False
    
    def _check_rate_limit(self) -> bool:
        """Check if rate limit is exceeded"""
        now = time.time()
        
        # Remove timestamps older than 1 second
        self._message_timestamps = [ts for ts in self._message_timestamps if now - ts < 1.0]
        
        # Check if limit exceeded
        if len(self._message_timestamps) >= PeerConfig.RATE_LIMIT_PER_SECOND:
            logger.warning(f"Rate limit exceeded: {len(self._message_timestamps)} messages/sec")
            return False
        
        # Add current timestamp
        self._message_timestamps.append(now)
        return True
    
    def _compress_message(self, data: Dict) -> Tuple[Dict, bool]:
        """Compress message data if it exceeds threshold"""
        json_str = json.dumps(data)
        if len(json_str.encode('utf-8')) > PeerConfig.COMPRESSION_THRESHOLD:
            compressed = gzip.compress(json_str.encode('utf-8'))
            return {'compressed': True, 'data': compressed.decode('latin1')}, True
        return data, False
    
    def _decompress_message(self, data: Dict) -> Dict:
        """Decompress message data if compressed"""
        if data.get('compressed'):
            try:
                compressed_bytes = data['data'].encode('latin1')
                decompressed = gzip.decompress(compressed_bytes).decode('utf-8')
                return json.loads(decompressed)
            except Exception as e:
                logger.error(f"Error decompressing message: {e}")
                return data
        return data
    
    def register_message_handler(self, message_type: str, handler: Callable):
        """
        Register a handler for specific message types
        
        Args:
            message_type: Type of message
            handler: Async function to handle the message
        """
        self.message_handlers[message_type] = handler
        logger.debug(f"Registered handler for message type: {message_type}")
    
    async def add_peer(self, node_id: str, host: str, port: int, public_key_hex: Optional[str] = None):
        """
        Add a peer node with public key for identity binding
        
        Args:
            node_id: Peer node ID
            host: Peer host address
            port: Peer port
            public_key_hex: Optional public key for signature verification
        """
        # Check peer limit
        if len(self.peers) >= MAX_PEERS:
            logger.warning("Peer limit reached, cannot add more peers")
            return
        
        peer = PeerNode(
            node_id=node_id,
            host=host,
            port=port,
            last_seen=datetime.now(),
            public_key_hex=public_key_hex
        )
        
        self.peers[node_id] = peer
        logger.info(f"Added peer: {node_id} at {host}:{port} (public_key: {public_key_hex[:16] + '...' if public_key_hex else 'None'})")
    
    async def remove_peer(self, node_id: str):
        """
        Remove a peer node
        
        Args:
            node_id: Peer node ID to remove
        """
        if node_id in self.peers:
            del self.peers[node_id]
            logger.info(f"Removed peer: {node_id}")
    
    async def send_message(self, target_node_id: str, message_type: str, data: Dict, message_id: Optional[str] = None, ttl: Optional[int] = None) -> bool:
        """
        Send a message to a specific peer with retry mechanism and exponential backoff
        
        Args:
            target_node_id: Target node ID
            message_type: Type of message
            data: Message data
            message_id: Optional message ID
            ttl: Time-to-live for gossip
            
        Returns:
            True if successful, False otherwise
        """
        try:
            if target_node_id not in self.peers:
                logger.error(f"Peer {target_node_id} not found")
                return False
            
            peer = self.peers[target_node_id]
            if not peer.is_active:
                logger.warning(f"Peer {target_node_id} is not active")
                return False
            
            # Prepare message
            message = {
                'id': message_id or str(uuid.uuid4()),
                'sender_id': self.node_id,
                'type': message_type,
                'timestamp': datetime.now().isoformat(),
                'data': data
            }

            if ttl is not None:
                message['ttl'] = int(ttl)
            
            # Sign the message
            message = self._sign_message(message)
            
            # Compress message data if large
            message['data'], was_compressed = self._compress_message(message['data'])
            if was_compressed:
                logger.debug(f"Compressed message data for {target_node_id}")
            
            # Send message with retry to the actual P2P port (port + 1000)
            peer_p2p_port = peer.port + 1000
            url = f"http://{peer.host}:{peer_p2p_port}/peer/message"
            
            for attempt in range(PeerConfig.MAX_RETRIES):
                try:
                    async with self.session.post(url, json=message, timeout=aiohttp.ClientTimeout(total=PeerConfig.MESSAGE_TIMEOUT)) as response:
                        if response.status == 200:
                            peer.last_seen = datetime.now()
                            logger.debug(f"Message sent to {target_node_id}: {message_type} (attempt {attempt + 1})")
                            return True
                        else:
                            logger.warning(f"Failed to send message to {target_node_id}: HTTP {response.status} (attempt {attempt + 1})")
                            if attempt < PeerConfig.MAX_RETRIES - 1:
                                backoff = PeerConfig.RETRY_BACKOFF_BASE * (2 ** attempt)
                                await asyncio.sleep(backoff)
                            else:
                                return False
                except asyncio.TimeoutError:
                    logger.warning(f"Timeout sending message to {target_node_id} (attempt {attempt + 1})")
                    if attempt < PeerConfig.MAX_RETRIES - 1:
                        backoff = PeerConfig.RETRY_BACKOFF_BASE * (2 ** attempt)
                        await asyncio.sleep(backoff)
                    else:
                        return False
                except Exception as e:
                    logger.error(f"Error sending message to {target_node_id}: {e} (attempt {attempt + 1})")
                    if attempt < PeerConfig.MAX_RETRIES - 1:
                        backoff = PeerConfig.RETRY_BACKOFF_BASE * (2 ** attempt)
                        await asyncio.sleep(backoff)
                    else:
                        return False
            
            return False
                    
        except Exception as e:
            logger.error(f"Fatal error sending message to {target_node_id}: {e}")
            return False
    
    async def broadcast_message(self, message_type: str, data: Dict, message_id: Optional[str] = None, ttl: Optional[int] = 2, exclude_peers: Optional[Set[str]] = None) -> Dict[str, bool]:
        """
        Broadcast a message using gossip protocol (fanout=3) to reduce O(n²) complexity
        
        Instead of sending to all peers (full mesh), we send to a random subset (fanout=3).
        This reduces complexity from O(n²) to O(n log n) for better scalability.
        
        Args:
            message_type: Type of message
            data: Message data
            
        Returns:
            Dictionary mapping node_id to success status
        """
        results = {}

        # GOSSIP PROTOCOL: Limit fanout to reduce O(n²) complexity
        FANOUT = min(PeerConfig.FANOUT, len(self.peers))
        
        exclude_peers = exclude_peers or set()

        # Select peers for gossip based on trust score (higher trust = higher priority)
        active_peers = [(node_id, peer) for node_id, peer in self.peers.items() if peer.is_active and node_id not in exclude_peers]
        
        # Sort by trust score (descending)
        active_peers.sort(key=lambda x: x[1].trust_score, reverse=True)
        
        if len(active_peers) > FANOUT:
            selected_peers = [node_id for node_id, _ in active_peers[:FANOUT]]
        else:
            selected_peers = [node_id for node_id, _ in active_peers]
        
        logger.debug(f"Gossip broadcast: sending to {len(selected_peers)}/{len(active_peers)} peers (fanout={FANOUT})")
        
        tasks = []
        node_ids = []

        for node_id in selected_peers:
            tasks.append(self.send_message(node_id, message_type, data, message_id=message_id, ttl=ttl))
            node_ids.append(node_id)

        if tasks:
            responses = await asyncio.gather(*tasks, return_exceptions=True)

            for node_id, response in zip(node_ids, responses):
                if isinstance(response, Exception):
                    logger.error(f"Gossip broadcast to {node_id} failed: {response}")
                    results[node_id] = False
                else:
                    results[node_id] = response

        logger.info(f"Broadcast completed: {sum(results.values())}/{len(results)} successful")
        return results
    
    # Phase 2: Broadcast signed monitoring report using sharded gossip fanout
    async def broadcast_report(self, report: 'MonitoringReport', peer_urls: List[str]) -> Dict[str, bool]:
        """
        Broadcast a signed MonitoringReport to a subset of peers using Sharded Gossip.
        Prioritizes peers in the same shard, with a bridge to other shards.
        """
        logger.info(f"broadcast_report called with {len(peer_urls)} peers")
        
        if not REPORT_AVAILABLE or not peer_urls:
            return {}

        payload = asdict(report)
        results = {}
        
        # ── DYNAMIC SHARDING LOGIC ──
        # Consistent hashing for shard assignment (prevents infinite migration loops)
        def get_shard_id(url: str, num_shards: int = 4) -> int:
            try:
                # Use SHA-256 for consistent hashing
                import hashlib
                hash_val = int(hashlib.sha256(url.encode()).hexdigest(), 16)
                return hash_val % num_shards
            except Exception: 
                return 0

        our_shard = get_shard_id(f"http://localhost:{self.port}")
        
        shard_peers = [u for u in peer_urls if get_shard_id(u) == our_shard]
        external_peers = [u for u in peer_urls if get_shard_id(u) != our_shard]
        
        # Gossip Fanout Selection:
        # Pick 2 peers from same shard + 1 peer from a different shard (The "Bridge")
        selected_urls = []
        import random
        
        if shard_peers:
            selected_urls.extend(random.sample(shard_peers, min(2, len(shard_peers))))
        if external_peers:
            selected_urls.extend(random.sample(external_peers, min(1, len(external_peers))))
            
        # Fallback if shards are empty
        if not selected_urls and peer_urls:
            selected_urls = random.sample(peer_urls, min(3, len(peer_urls)))

        logger.info(f"Sharded Gossip: shard={our_shard} | local={len(shard_peers)} | ext={len(external_peers)}")
        logger.info(f"Selected Targets: {selected_urls}")
        
        async with aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=PeerConfig.REPORT_TIMEOUT),
            connector=aiohttp.TCPConnector(limit=PeerConfig.CONNECTION_LIMIT, limit_per_host=PeerConfig.CONNECTION_PER_HOST)
        ) as session:
            tasks = []
            
            for peer_url in selected_urls:
                try:
                    # Add sender header to identify who sent this report
                    headers = {
                        "X-Node-ID": self.node_id,
                        "Content-Type": "application/json"
                    }
                    
                    task = session.post(
                        f"{peer_url}/report",
                        json=payload,
                        headers=headers
                    )
                    tasks.append((peer_url, task))
                except Exception as e:
                    logger.warning(f"Failed to create broadcast task for {peer_url}: {e}")
                    results[peer_url] = False
            
            # Execute all broadcasts concurrently
            if tasks:
                responses = await asyncio.gather(
                    *[task for _, task in tasks],
                    return_exceptions=True
                )
                
                for i, (peer_url, _) in enumerate(tasks):
                    response = responses[i]
                    
                    if isinstance(response, Exception):
                        results[peer_url] = False
                    else:
                        try:
                            if response.status == 200:
                                results[peer_url] = True
                            else:
                                results[peer_url] = False
                        finally:
                            await response.release()
        
        success_count = sum(results.values())
        logger.info(f"Report broadcast completed: {success_count}/{len(selected_urls)} peers received report for {report.url} (epoch {report.epoch_id})")
        
        return results
    
    async def handle_message(self, request):
        """Handle incoming messages from peers with rate limiting"""
        try:
            # Check rate limit
            if not self._check_rate_limit():
                return web.json_response(
                    {'error': 'Rate limit exceeded'},
                    status=429
                )
            
            message = await request.json()
            
            # Decompress message data if compressed
            message['data'] = self._decompress_message(message['data'])
            
            # Validate message
            required_fields = ['id', 'sender_id', 'type', 'timestamp', 'data']
            for field in required_fields:
                if field not in message:
                    return web.json_response(
                        {'error': f'Missing required field: {field}'},
                        status=400
                    )
            
            # Update peer info
            sender_id = message['sender_id']
            if sender_id in self.peers:
                self.peers[sender_id].last_seen = datetime.now()

            msg_id = message.get('id')
            if msg_id:
                if msg_id in self._seen_message_ids:
                    return web.json_response({'status': 'received'})
                self._seen_message_ids.add(msg_id)
                self._seen_message_order.append(msg_id)
                if len(self._seen_message_order) > self._seen_message_max:
                    old = self._seen_message_order.pop(0)
                    self._seen_message_ids.discard(old)
            
            # Verify message signature if available
            if sender_id in self.peers and self.peers[sender_id].node_id:
                # Get sender's public key from peer registry if available
                sender_pubkey = getattr(self.peers[sender_id], 'public_key_hex', None)
                if sender_pubkey and message.get('signature'):
                    if not self._verify_message(message, sender_pubkey):
                        logger.warning(f"Rejected message from {sender_id}: invalid signature")
                        return web.json_response(
                            {'error': 'Invalid signature'},
                            status=403
                        )
            
            # Handle message based on type
            message_type = message['type']
            
            if message_type == self.MESSAGE_TYPES['HEARTBEAT']:
                await self._handle_heartbeat(message)
            elif message_type == self.MESSAGE_TYPES['MONITORING_RESULT']:
                await self._handle_monitoring_result(message)
            elif message_type == self.MESSAGE_TYPES['TRUST_UPDATE']:
                await self._handle_trust_update(message)
            elif message_type == self.MESSAGE_TYPES['CONTENT_HASH']:
                await self._handle_content_hash(message)
            elif message_type == self.MESSAGE_TYPES['ML_PREDICTION']:
                await self._handle_ml_prediction(message)
            elif message_type == self.MESSAGE_TYPES['EPOCH_DECISION']:
                await self._handle_epoch_decision(message)
            
            # Use custom handler if registered
            if message_type in self.message_handlers:
                await self.message_handlers[message_type](message)
            else:
                logger.warning(f"Unknown message type: {message_type}")

            ttl = message.get('ttl')
            if ttl is not None and message_type != self.MESSAGE_TYPES['HEARTBEAT']:
                try:
                    ttl_val = int(ttl)
                except Exception:
                    ttl_val = 0

                if ttl_val > 0:
                    await self.broadcast_message(
                        message_type,
                        message.get('data', {}),
                        message_id=message.get('id'),
                        ttl=ttl_val - 1,
                        exclude_peers={sender_id},
                    )
            
            return web.json_response({'status': 'received'})
            
        except Exception as e:
            logger.error(f"Error handling message: {e}")
            return web.json_response(
                {'error': str(e)},
                status=500
            )
    
    async def handle_info_request(self, request):
        """Handle peer info requests"""
        try:
            info = {
                'node_id': self.node_id,
                'host': self.host,
                'port': self.port,
                'timestamp': datetime.now().isoformat(),
                'active_peers': len([p for p in self.peers.values() if p.is_active])
            }
            
            return web.json_response(info)
            
        except Exception as e:
            logger.error(f"Error handling info request: {e}")
            return web.json_response(
                {'error': str(e)},
                status=500
            )
    
    async def handle_peer_discovery(self, request):
        """Handle peer discovery requests with public key exchange"""
        try:
            data = await request.json()
            
            # Add the requesting peer if not already known
            peer_info = data.get('peer_info')
            if peer_info:
                await self.add_peer(
                    peer_info['node_id'],
                    peer_info['host'],
                    peer_info['port'],
                    public_key_hex=peer_info.get('public_key_hex')
                )
            
            # Return list of known peers with public keys
            peers_list = []
            for peer in self.peers.values():
                if peer.is_active and peer.node_id != data.get('requester_id'):
                    peers_list.append({
                        'node_id': peer.node_id,
                        'host': peer.host,
                        'port': peer.port,
                        'trust_score': peer.trust_score,
                        'public_key_hex': peer.public_key_hex
                    })
            
            return web.json_response({'peers': peers_list})
            
        except Exception as e:
            logger.error(f"Error handling peer discovery: {e}")
            return web.json_response(
                {'error': str(e)},
                status=500
            )
    
    async def _handle_heartbeat(self, message: Dict):
        """Handle heartbeat messages"""
        sender_id = message['sender_id']
        logger.debug(f"Received heartbeat from {sender_id}")
    
    async def _handle_monitoring_result(self, message: Dict):
        """Handle monitoring result messages"""
        sender_id = message['sender_id']
        data = message['data']
        
        logger.debug(f"Received monitoring result from {sender_id}")
        
        # Store or process the monitoring result
        # This would typically be handled by the main application
        if 'monitoring_result' in self.message_handlers:
            await self.message_handlers['monitoring_result'](message)
    
    async def _handle_trust_update(self, message: Dict):
        """Handle trust update messages"""
        sender_id = message['sender_id']
        data = message['data']
        
        logger.debug(f"Received trust update from {sender_id}")
        
        # Update peer trust score
        if sender_id in self.peers:
            self.peers[sender_id].trust_score = data.get('trust_score', 0.5)
    
    async def _handle_content_hash(self, message: Dict):
        """Handle content hash messages"""
        sender_id = message['sender_id']
        data = message['data']
        
        logger.debug(f"Received content hash from {sender_id}")
        
        # Process content hash for consistency checking
        if 'content_hash' in self.message_handlers:
            await self.message_handlers['content_hash'](message)
    
    async def _handle_ml_prediction(self, message: Dict):
        """Handle ML prediction messages"""
        sender_id = message['sender_id']
        data = message['data']
        
        logger.debug(f"Received ML prediction from {sender_id}")
        
        # Process ML prediction
        if 'ml_prediction' in self.message_handlers:
            await self.message_handlers['ml_prediction'](message)
    
    async def _handle_epoch_decision(self, message: Dict):
        """Handle epoch decision messages from leader"""
        sender_id = message['sender_id']
        data = message['data']
        
        epoch_id = data.get('epoch_id')
        leader_id = data.get('leader_id')
        decision = data.get('decision')
        
        logger.info(f"Received epoch decision for epoch {epoch_id} from leader {leader_id}")
        
        # Store the decision locally for consistency
        if epoch_manager := get_epoch_manager():
            epoch_manager.epoch_decisions[epoch_id] = decision
            logger.info(f"Epoch {epoch_id}: Decision stored from leader {leader_id}")
        
        # Forward to any registered handlers
        if 'epoch_decision' in self.message_handlers:
            await self.message_handlers['epoch_decision'](message)
    
    async def send_heartbeat(self):
        """Send heartbeat to all peers"""
        await self.broadcast_message(
            self.MESSAGE_TYPES['HEARTBEAT'],
            {'status': 'active'}
        )
    
    async def send_monitoring_result(self, result: Dict):
        """Send monitoring result to peers"""
        await self.broadcast_message(
            self.MESSAGE_TYPES['MONITORING_RESULT'],
            result
        )
    
    async def send_trust_update(self, trust_score: float):
        """Send trust score update to peers"""
        await self.broadcast_message(
            self.MESSAGE_TYPES['TRUST_UPDATE'],
            {'trust_score': trust_score}
        )
    
    async def send_content_hash(self, url: str, content_hash: str):
        """Send content hash to peers"""
        await self.broadcast_message(
            self.MESSAGE_TYPES['CONTENT_HASH'],
            {
                'url': url,
                'content_hash': content_hash,
                'timestamp': datetime.now().isoformat()
            }
        )
    
    async def discover_peers(self, seed_nodes: List[Tuple[str, str, int]]):
        """
        Discover peers from seed nodes with public key exchange
        
        Args:
            seed_nodes: List of (node_id, host, port) tuples
        """
        for node_id, host, port in seed_nodes:
            try:
                if node_id == self.node_id:
                    continue  # Skip self
                
                # Add seed node (public key will be updated from discovery response)
                await self.add_peer(node_id, host, port)
                
                # Request peer list
                url = f"http://{host}:{port}/peer/discovery"
                
                if not self.session:
                    self.session = aiohttp.ClientSession()
                
                data = {
                    'requester_id': self.node_id,
                    'peer_info': {
                        'node_id': self.node_id,
                        'host': self.host,
                        'port': self.port,
                        'public_key_hex': self.public_key_hex
                    }
                }
                
                async with self.session.post(url, json=data, timeout=aiohttp.ClientTimeout(total=PeerConfig.DISCOVERY_TIMEOUT)) as response:
                    if response.status == 200:
                        result = await response.json()
                        peers = result.get('peers', [])
                        
                        for peer in peers:
                            await self.add_peer(
                                peer['node_id'],
                                peer['host'],
                                peer['port'],
                                public_key_hex=peer.get('public_key_hex')
                            )
                        
                        logger.info(f"Discovered {len(peers)} peers from {node_id}")
                    
            except Exception as e:
                logger.error(f"Failed to discover peers from {node_id}: {e}")
    
    async def send_ml_prediction(self, prediction: Dict):
        """Send ML prediction to peers"""
        await self.broadcast_message(
            self.MESSAGE_TYPES['ML_PREDICTION'],
            prediction
        )
    
    async def _check_single_peer(self, node_id: str, peer: PeerNode) -> Tuple[str, bool]:
        """Check health of a single peer"""
        try:
            url = f"http://{peer.host}:{peer.port}/peer/info"
            
            async with self.session.get(url, timeout=aiohttp.ClientTimeout(total=PeerConfig.HEALTH_CHECK_TIMEOUT)) as response:
                if response.status == 200:
                    peer.is_active = True
                    peer.last_seen = datetime.now()
                    return (node_id, True)
                else:
                    peer.is_active = False
                    logger.warning(f"Peer {node_id} returned status {response.status}")
                    return (node_id, False)
                    
        except asyncio.TimeoutError:
            peer.is_active = False
            logger.warning(f"Peer {node_id} health check timeout")
            return (node_id, False)
        except Exception as e:
            peer.is_active = False
            logger.warning(f"Peer {node_id} health check failed: {e}")
            return (node_id, False)
    
    async def check_peer_health(self):
        """Check health of all peers in parallel and update status"""
        if not self.peers:
            return
        
        tasks = []
        for node_id, peer in list(self.peers.items()):
            tasks.append(self._check_single_peer(node_id, peer))
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        healthy_count = sum(1 for result in results if isinstance(result, tuple) and result[1])
        logger.info(f"Health check completed: {healthy_count}/{len(self.peers)} peers healthy")
    
    async def get_peer_statistics(self) -> Dict:
        """Get statistics about connected peers"""
        active_peers = [p for p in self.peers.values() if p.is_active]
        
        return {
            'total_peers': len(self.peers),
            'active_peers': len(active_peers),
            'inactive_peers': len(self.peers) - len(active_peers),
            'average_trust_score': sum(p.trust_score for p in active_peers) / len(active_peers) if active_peers else 0,
            'peer_list': [
                {
                    'node_id': p.node_id,
                    'host': p.host,
                    'port': p.port,
                    'trust_score': p.trust_score,
                    'is_active': p.is_active,
                    'last_seen': p.last_seen.isoformat()
                }
                for p in self.peers.values()
            ]
        }

if __name__ == "__main__":
    # Test the peer client
    async def test_peer_communication():
        # Create two peer clients
        node1 = PeerClient("node_1", "localhost", 8001)
        node2 = PeerClient("node_2", "localhost", 8002)
        
        try:
            # Start servers
            await node1.start_server()
            await node2.start_server()
            
            # Add each other as peers
            await node1.add_peer("node_2", "localhost", 8002)
            await node2.add_peer("node_1", "localhost", 8001)
            
            # Test message sending
            success = await node1.send_message("node_2", "test_message", {"data": "hello"})
            print(f"Message sent: {success}")
            
            # Test broadcasting
            results = await node1.broadcast_message("broadcast_test", {"data": "broadcast"})
            print(f"Broadcast results: {results}")
            
            # Get statistics
            stats = await node1.get_peer_statistics()
            print("Node 1 statistics:")
            print(json.dumps(stats, indent=2))
            
            # Wait a bit
            await asyncio.sleep(2)
            
        finally:
            await node1.stop_server()
            await node2.stop_server()
    
    asyncio.run(test_peer_communication())
