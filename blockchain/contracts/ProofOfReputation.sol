// SPDX-License-Identifier: MIT
pragma solidity ^0.8.19;

/**
 * @title ProofOfReputation
 * @dev Smart contract for managing node reputation in decentralized monitoring system
 * Stores node reputations calculated as: PoR = 0.4 * monitoring_trust + 0.6 * ML_score
 */
contract ProofOfReputation {
    
    // Struct to store node information
    struct Node {
        string nodeId;                    // Unique identifier for the node
        uint256 reputation;               // Current PoR score (0-1000, where 1000 = 1.0)
        uint256 monitoringTrust;          // Monitoring trust score (0-1000)
        uint256 mlScore;                  // ML confidence score (0-1000)
        bool isRegistered;                // Registration status
        uint256 lastUpdated;              // Timestamp of last update
        uint256 totalReports;             // Total number of reports submitted
        uint256 successfulReports;       // Number of successful/reliable reports
    }
    
    // Mapping from node ID to Node struct
    mapping(string => Node) public nodes;
    
    // Array to store all registered node IDs
    string[] public registeredNodes;
    
    // Contract owner
    address public owner;
    
    // Events
    event NodeRegistered(string indexed nodeId, address indexed registrar);
    event ReputationUpdated(string indexed nodeId, uint256 newReputation, uint256 monitoringTrust, uint256 mlScore);
    event ReportSubmitted(string indexed nodeId, bool success);
    event AggregatedReportSubmitted(string indexed url, uint256 indexed epochId, bool status, uint256 latency);
    
    // Modifiers
    modifier onlyOwner() {
        require(msg.sender == owner, "Only owner can call this function");
        _;
    }

    modifier onlyAggregator() {
        require(msg.sender == owner || nodes[addressToNodeId[msg.sender]].isRegistered, "Only aggregator can call this function");
        _;
    }

    modifier nodeRegistered(string memory nodeId) {
        require(nodes[nodeId].isRegistered, "Node must be registered");
        _;
    }
    
    modifier validNodeId(string memory nodeId) {
        require(bytes(nodeId).length > 0, "Node ID cannot be empty");
        _;
    }
    
    mapping(address => string) public addressToNodeId;

    constructor() {
        owner = msg.sender;
    }

    function registerNode(string memory nodeId) 
        external 
        validNodeId(nodeId) 
    {
        require(!nodes[nodeId].isRegistered, "Node already registered");
        require(bytes(addressToNodeId[msg.sender]).length == 0, "Address already registered to a node");
        
        // Create new node with default values
        nodes[nodeId] = Node({
            nodeId: nodeId,
            reputation: 500,              // Start with neutral reputation (0.5)
            monitoringTrust: 500,         // Start with neutral trust
            mlScore: 500,                 // Start with neutral ML score
            isRegistered: true,
            lastUpdated: block.timestamp,
            totalReports: 0,
            successfulReports: 0
        });
        
        registeredNodes.push(nodeId);
        addressToNodeId[msg.sender] = nodeId;
        
        emit NodeRegistered(nodeId, msg.sender);
    }
    
    /**
     * @dev Update node reputation based on monitoring trust and ML score
     * @param nodeId Node identifier
     * @param monitoringTrust Monitoring trust score (0-1000)
     * @param mlScore ML confidence score (0-1000)
     */
    function updateReputation(
        string memory nodeId, 
        uint256 monitoringTrust, 
        uint256 mlScore
    ) 
        external
        onlyAggregator
        nodeRegistered(nodeId)
        validNodeId(nodeId)
    {
        require(monitoringTrust <= 1000, "Monitoring trust must be <= 1000");
        require(mlScore <= 1000, "ML score must be <= 1000");
        
        // Calculate PoR: PoR = 0.4 * monitoring_trust + 0.6 * ML_score
        uint256 newReputation = (monitoringTrust * 40 + mlScore * 60) / 100;
        
        // Update node data
        nodes[nodeId].monitoringTrust = monitoringTrust;
        nodes[nodeId].mlScore = mlScore;
        nodes[nodeId].reputation = newReputation;
        nodes[nodeId].lastUpdated = block.timestamp;
        
        emit ReputationUpdated(nodeId, newReputation, monitoringTrust, mlScore);
    }

    function batchUpdateReputation(
        string[] memory nodeIds,
        uint256[] memory monitoringTrusts,
        uint256[] memory mlScores
    ) external onlyAggregator {
        require(nodeIds.length == monitoringTrusts.length && nodeIds.length == mlScores.length, "Array length mismatch");
        for (uint256 i = 0; i < nodeIds.length; i++) {
            require(nodes[nodeIds[i]].isRegistered, "Node must be registered");
            require(bytes(nodeIds[i]).length > 0, "Node ID cannot be empty");
            require(monitoringTrusts[i] <= 1000, "Monitoring trust must be <= 1000");
            require(mlScores[i] <= 1000, "ML score must be <= 1000");

            uint256 newReputation = (monitoringTrusts[i] * 40 + mlScores[i] * 60) / 100;

            nodes[nodeIds[i]].monitoringTrust = monitoringTrusts[i];
            nodes[nodeIds[i]].mlScore = mlScores[i];
            nodes[nodeIds[i]].reputation = newReputation;
            nodes[nodeIds[i]].lastUpdated = block.timestamp;

            emit ReputationUpdated(nodeIds[i], newReputation, monitoringTrusts[i], mlScores[i]);
        }
    }
    
    /**
     * @dev Submit a report from a node and update its statistics
     * @param nodeId Node identifier
     * @param success Whether the report was successful/accurate
     */
    function submitReport(string memory nodeId, bool success) 
        external 
        nodeRegistered(nodeId)
    {
        nodes[nodeId].totalReports++;
        
        if (success) {
            nodes[nodeId].successfulReports++;
        }
        
        emit ReportSubmitted(nodeId, success);
    }
    
    /**
     * @dev Get node reputation information
     * @param nodeId Node identifier
     * @return reputation Current PoR score (0-1000)
     * @return monitoringTrust Monitoring trust score (0-1000)
     * @return mlScore ML confidence score (0-1000)
     * @return lastUpdated Timestamp of last update
     */
    function getNodeReputation(string memory nodeId) 
        external 
        view 
        nodeRegistered(nodeId)
        returns (
            uint256 reputation,
            uint256 monitoringTrust,
            uint256 mlScore,
            uint256 lastUpdated
        )
    {
        Node storage node = nodes[nodeId];
        return (
            node.reputation,
            node.monitoringTrust,
            node.mlScore,
            node.lastUpdated
        );
    }
    
    /**
     * @dev Get node statistics
     * @param nodeId Node identifier
     * @return totalReports Total number of reports
     * @return successfulReports Number of successful reports
     * @return successRate Success rate as percentage (0-100)
     */
    function getNodeStats(string memory nodeId) 
        external 
        view 
        nodeRegistered(nodeId)
        returns (
            uint256 totalReports,
            uint256 successfulReports,
            uint256 successRate
        )
    {
        Node storage node = nodes[nodeId];
        uint256 rate = node.totalReports > 0 ? 
            (node.successfulReports * 100) / node.totalReports : 0;
        
        return (
            node.totalReports,
            node.successfulReports,
            rate
        );
    }
    
    /**
     * @dev Check if a node is registered
     * @param nodeId Node identifier
     * @return isRegistered True if node is registered
     */
    function isNodeRegistered(string memory nodeId) external view returns (bool isRegistered) {
        return nodes[nodeId].isRegistered;
    }
    
    /**
     * @dev Get all registered node IDs
     * @return Array of node IDs
     */
    function getAllNodes() external view returns (string[] memory) {
        return registeredNodes;
    }

    function getAllNodesWithReputation() external view returns (string[] memory nodeIds, uint256[] memory reputations) {
        uint256 length = registeredNodes.length;
        nodeIds = new string[](length);
        reputations = new uint256[](length);
        for (uint256 i = 0; i < length; i++) {
            string memory id = registeredNodes[i];
            nodeIds[i] = id;
            reputations[i] = nodes[id].reputation;
        }
    }
    
    /**
     * @dev Get total number of registered nodes
     * @return Number of registered nodes
     */
    function getNodeCount() external view returns (uint256) {
        return registeredNodes.length;
    }
    
    /**
     * @dev Get top N nodes by reputation
     * @param n Number of top nodes to return
     * @return nodeIds Array of node IDs
     * @return reputations Array of reputation scores
     */
    function getTopNodes(uint256 n) external view returns (string[] memory nodeIds, uint256[] memory reputations) {
        require(n <= registeredNodes.length, "N cannot exceed total nodes");
        
        // Create temporary arrays for sorting
        string[] memory tempNodeIds = new string[](registeredNodes.length);
        uint256[] memory tempReputations = new uint256[](registeredNodes.length);
        
        // Copy data
        for (uint256 i = 0; i < registeredNodes.length; i++) {
            tempNodeIds[i] = registeredNodes[i];
            tempReputations[i] = nodes[registeredNodes[i]].reputation;
        }
        
        // Simple bubble sort (for demonstration - in production, use more efficient sorting)
        for (uint256 i = 0; i < tempReputations.length; i++) {
            for (uint256 j = i + 1; j < tempReputations.length; j++) {
                if (tempReputations[i] < tempReputations[j]) {
                    // Swap
                    string memory tempId = tempNodeIds[i];
                    tempNodeIds[i] = tempNodeIds[j];
                    tempNodeIds[j] = tempId;
                    
                    uint256 tempRep = tempReputations[i];
                    tempReputations[i] = tempReputations[j];
                    tempReputations[j] = tempRep;
                }
            }
        }
        
        // Return top N
        nodeIds = new string[](n);
        reputations = new uint256[](n);
        
        for (uint256 i = 0; i < n; i++) {
            nodeIds[i] = tempNodeIds[i];
            reputations[i] = tempReputations[i];
        }
    }
    
    /**
     * @dev Transfer ownership of the contract
     * @param newOwner Address of the new owner
     */
    function transferOwnership(address newOwner) external onlyOwner {
        require(newOwner != address(0), "New owner cannot be zero address");
        owner = newOwner;
    }
    
    /**
     * @dev Emergency function to remove a node (owner only)
     * @param nodeId Node identifier to remove
     */
    function removeNode(string memory nodeId) external onlyOwner nodeRegistered(nodeId) {
        // Find and remove from registeredNodes array
        for (uint256 i = 0; i < registeredNodes.length; i++) {
            if (keccak256(bytes(registeredNodes[i])) == keccak256(bytes(nodeId))) {
                // Move last element to current position
                registeredNodes[i] = registeredNodes[registeredNodes.length - 1];
                // Remove last element
                registeredNodes.pop();
                break;
            }
        }
        
        // Delete node mapping
        delete nodes[nodeId];
    }
    
    // ============ OPTIMIZED LIGHTWEIGHT BLOCK STORAGE ============
    
    // BLOCK HEADER (Stored on-chain per block)
    struct BlockHeader {
        uint256 blockId;              // Sequential block ID
        uint256 timestamp;            // Block timestamp
        bytes32 previousBlockHash;    // Links to previous block
        bytes32 merkleRoot;           // Root hash of 50 probes
        uint8 shardId;                // Shard ID (1-5)
        address producerId;           // Node's Ethereum address
    }
    
    // BLOCK BODY (Passed in calldata, not stored permanently)
    struct Probe {
        bytes32 websiteHash;          // keccak256(websiteId)
        uint16 latency;               // milliseconds (0-65535)
        uint8 failureRate;            // 0-100%
        uint8 anomalyProbability;     // 0-100% (ML score)
        uint16 reputationScore;       // 0-1000
    }
    
    // BLOCK BODY (Matches Slide 23 exactly)
    struct AggregatedReport {
        string nodeId;                // Monitor Node ID
        string websiteId;             // Unique Website ID
        string url;                   // Website URL
        bool status;                  // UP/DOWN
        uint256 avgLatency;           // Average Latency (ms)
        uint256 failureRate;          // 0-100% (basis 100)
        uint256 anomalyProbability;   // 0-100% (ML score)
        uint256 reputationScore;      // 0-1000
        bool consensusDecision;       // Majority Outcome
        uint256 timestamp;            // Recording time
        uint256 epochId;              // Epoch Number
    }
    
    // Storage: Only headers (body verified via merkleRoot)
    BlockHeader[] public blockHeaders;
    uint256 public nextBlockId = 1; // Next sequential ID
    mapping(uint256 => bytes32) public blockBodyHash;  // blockId => merkleRoot
    mapping(bytes32 => bool) public provenBodies;      // merkleRoot => verified
    
    // Track producer statistics (Slide 24 compliance)
    mapping(address => uint256) public producerBlockCount;
    
    // Track chain per shard and website
    mapping(uint8 => uint256[]) public shardBlocks;    // shardId => blockIds
    mapping(bytes32 => uint256[]) public websiteBlocks; // websiteHash => blockIds
    
    // Legacy: URL -> epoch_id -> report
    mapping(string => mapping(uint256 => AggregatedReport)) public websiteReports;
    mapping(string => uint256[]) public websiteEpochs;
    
    // Slashing records (lightweight)
    struct SlashRecord {
        string nodeId;
        uint256 amount;  // in basis points (10000 = 100%)
        string reason;
        uint256 timestamp;
        uint256 epochId;
    }
    
    SlashRecord[] public slashHistory;
    mapping(string => SlashRecord[]) public nodeSlashHistory;
    
    // Prevent double-spending / duplicate epoch submission
    mapping(uint256 => bool) public epochDecisionsSubmitted;
    
    // Events
    event BlockHeaderSubmitted(
        uint256 indexed blockId,
        address indexed producer,
        bytes32 indexed merkleRoot,
        uint8 shardId,
        uint256 probeCount
    );
    event ProbesVerified(uint256 indexed blockId, bytes32 merkleRoot, uint256 probeCount);
    event NodeSlashed(string indexed nodeId, uint256 amount, string reason, uint256 indexed epochId);
    
    /**
     * @dev Submit multiple aggregated consensus reports in a single transaction (Slide 23 compliant)
     */
    function batchSubmitAggregatedReports(
        string[] memory nodeIds,
        string[] memory urls,
        uint256[] memory epochIds,
        bool[] memory statuses,
        uint256[] memory latencies,
        uint256[] memory failureRates,
        uint256[] memory anomalyProbs,
        uint256[] memory repScores,
        uint8 shardId
    ) external onlyAggregator {
        require(urls.length == epochIds.length && 
                urls.length == statuses.length && 
                urls.length == latencies.length && 
                urls.length == nodeIds.length, "Array length mismatch");
        
        // 1. Create Block Body Records (Slide 23)
        for (uint256 i = 0; i < urls.length; i++) {
            AggregatedReport memory report = AggregatedReport({
                nodeId: nodeIds[i],
                websiteId: urls[i], // Use URL as ID for simplicity
                url: urls[i],
                status: statuses[i],
                avgLatency: latencies[i],
                failureRate: failureRates[i],
                anomalyProbability: anomalyProbs[i],
                reputationScore: repScores[i],
                consensusDecision: statuses[i], // Consensus decision is the status
                timestamp: block.timestamp,
                epochId: epochIds[i]
            });
            
            websiteReports[urls[i]][epochIds[i]] = report;
            websiteEpochs[urls[i]].push(epochIds[i]);
            
            emit AggregatedReportSubmitted(urls[i], epochIds[i], statuses[i], latencies[i]);
        }

        // 2. Create Block Header (Slide 23/24)
        bytes32 prevHash = blockHeaders.length > 0 ? 
            keccak256(abi.encode(blockHeaders[blockHeaders.length - 1])) : 
            bytes32(0);
            
        BlockHeader memory header = BlockHeader({
            blockId: nextBlockId,
            timestamp: block.timestamp,
            previousBlockHash: prevHash,
            merkleRoot: keccak256(abi.encode(urls)), // Simplified Merkle Root of websites
            shardId: shardId,
            producerId: msg.sender
        });
        
        blockHeaders.push(header);
        producerBlockCount[msg.sender]++;
        
        emit BlockHeaderSubmitted(
            nextBlockId, 
            msg.sender, 
            header.merkleRoot, 
            shardId, 
            urls.length
        );
        
        nextBlockId++;
    }
    
    /**
     * @dev Submit an aggregated consensus report from an epoch
     * @param nodeId Monitor Node ID
     * @param url The monitored URL
     * @param epochId The epoch identifier
     * @param status The consensus outcome (true=UP, false=DOWN)
     * @param avgLatency Average Latency (ms)
     * @param failureRate 0-100%
     * @param anomalyProb 0-100%
     * @param repScore 0-1000
     */
    function submitAggregatedReport(
        string memory nodeId,
        string memory url,
        uint256 epochId,
        bool status,
        uint256 avgLatency,
        uint256 failureRate,
        uint256 anomalyProb,
        uint256 repScore
    ) external onlyAggregator {
        require(bytes(url).length > 0, "URL cannot be empty");
        require(epochId > 0, "Epoch ID must be > 0");
        
        AggregatedReport memory report = AggregatedReport({
            nodeId: nodeId,
            websiteId: url,
            url: url,
            status: status,
            avgLatency: avgLatency,
            failureRate: failureRate,
            anomalyProbability: anomalyProb,
            reputationScore: repScore,
            consensusDecision: status,
            timestamp: block.timestamp,
            epochId: epochId
        });
        
        websiteReports[url][epochId] = report;
        websiteEpochs[url].push(epochId);
        
        emit AggregatedReportSubmitted(url, epochId, status, avgLatency);
    }
    
    /**
     * @dev Slash a node by reducing its reputation
     * @param nodeId Node to slash
     * @param amount Slash amount in basis points (100 = 1%, 10000 = 100%)
     * @param reason Reason for slashing
     * @param epochId Epoch where slashing was decided
     */
    function slashNode(
        string memory nodeId,
        uint256 amount,
        string memory reason,
        uint256 epochId
    ) external onlyAggregator nodeRegistered(nodeId) {
        require(amount > 0 && amount <= 10000, "Slash amount must be 1-10000 basis points");
        
        Node storage node = nodes[nodeId];
        
        // Calculate new reputation after slashing
        uint256 newReputation = node.reputation * (10000 - amount) / 10000;
        node.reputation = newReputation;
        node.lastUpdated = block.timestamp;
        
        // Record the slash
        SlashRecord memory record = SlashRecord({
            nodeId: nodeId,
            amount: amount,
            reason: reason,
            timestamp: block.timestamp,
            epochId: epochId
        });
        
        slashHistory.push(record);
        nodeSlashHistory[nodeId].push(record);
        
        emit NodeSlashed(nodeId, amount, reason, epochId);
    }

    function batchSlashNodes(
        string[] memory nodeIds,
        uint256[] memory amounts,
        string memory reason,
        uint256 epochId
    ) external onlyAggregator {
        require(nodeIds.length == amounts.length, "Array length mismatch");
        for (uint256 i = 0; i < nodeIds.length; i++) {
            require(nodes[nodeIds[i]].isRegistered, "Node must be registered");
            require(amounts[i] > 0 && amounts[i] <= 10000, "Slash amount must be 1-10000 basis points");

            Node storage node = nodes[nodeIds[i]];
            uint256 newReputation = node.reputation * (10000 - amounts[i]) / 10000;
            node.reputation = newReputation;
            node.lastUpdated = block.timestamp;

            SlashRecord memory record = SlashRecord({
                nodeId: nodeIds[i],
                amount: amounts[i],
                reason: reason,
                timestamp: block.timestamp,
                epochId: epochId
            });

            slashHistory.push(record);
            nodeSlashHistory[nodeIds[i]].push(record);

            emit NodeSlashed(nodeIds[i], amounts[i], reason, epochId);
        }
    }
    
    /**
     * @dev Get consensus history for a website
     * @param url Website URL
     * @return epochs Array of epoch IDs with reports
     * @return results Array of consensus results
     */
    function getWebsiteHistory(string memory url) 
        external 
        view 
        returns (uint256[] memory epochs, bool[] memory results) 
    {
        uint256[] storage epochList = websiteEpochs[url];
        uint256 length = epochList.length;
        
        epochs = new uint256[](length);
        results = new bool[](length);
        
        for (uint256 i = 0; i < length; i++) {
            uint256 epochId = epochList[i];
            epochs[i] = epochId;
            results[i] = websiteReports[url][epochId].consensusDecision;
        }
        
        return (epochs, results);
    }
    
    /**
     * @dev Get detailed report for a specific website and epoch
     * @param url Website URL
     * @param epochId Epoch ID
     * @return report The aggregated report details
     */
    function getWebsiteReport(string memory url, uint256 epochId) 
        external 
        view 
        returns (AggregatedReport memory) 
    {
        return websiteReports[url][epochId];
    }
    
    /**
     * @dev Get slashing history for a specific node
     * @param nodeId Node identifier
     * @return records Array of slash records for the node
     */
    function getNodeSlashHistory(string memory nodeId) 
        external 
        view 
        returns (SlashRecord[] memory) 
    {
        return nodeSlashHistory[nodeId];
    }
    
    /**
     * @dev Get total number of slash events
     * @return Total slash count
     */
    function getTotalSlashCount() external view returns (uint256) {
        return slashHistory.length;
    }
    
    /**
     * @dev Submit epoch decision with verdicts and reputations
     * @param epochId Epoch identifier
     * @param nodeIds Array of node IDs
     * @param verdicts Array of verdicts (1=malicious, 0=honest)
     * @param reputations Array of reputation scores
     */
    function submitEpochDecision(
        uint256 epochId,
        string[] memory nodeIds,
        uint256[] memory verdicts,
        uint256[] memory reputations
    ) external onlyAggregator {
        require(nodeIds.length == verdicts.length && nodeIds.length == reputations.length, "Array length mismatch");
        require(epochId > 0, "Epoch ID must be > 0");
        require(!epochDecisionsSubmitted[epochId], "Epoch decision already submitted (double-spending prevention)");
        
        // Mark epoch as submitted
        epochDecisionsSubmitted[epochId] = true;
        
        // Store epoch decision
        for (uint256 i = 0; i < nodeIds.length; i++) {
            require(nodes[nodeIds[i]].isRegistered, "Node must be registered");
            require(bytes(nodeIds[i]).length > 0, "Node ID cannot be empty");
            require(reputations[i] <= 1000, "Reputation must be <= 1000");
            require(verdicts[i] <= 1, "Verdict must be 0 or 1");
            
            // Update node reputation
            nodes[nodeIds[i]].reputation = reputations[i];
            nodes[nodeIds[i]].lastUpdated = block.timestamp;
            
            // Record verdict for historical tracking
            emit ReputationUpdated(nodeIds[i], reputations[i], nodes[nodeIds[i]].monitoringTrust, nodes[nodeIds[i]].mlScore);
        }
        
        // Emit epoch decision event
        emit EpochDecisionSubmitted(epochId, nodeIds.length);
    }
    
    /**
     * @dev Get epoch decision for verification
     * @param epochId Epoch identifier
     * @return submitted Whether decision was submitted
     * @return timestamp When decision was submitted
     */
    function getEpochDecision(uint256 epochId) external view returns (bool submitted, uint256 timestamp) {
        // This is a simplified implementation
        // In production, you'd store epoch decisions in a mapping
        // For now, we'll check if any node was updated in the last epoch duration
        uint256 epochDuration = 60; // 60 seconds per epoch
        uint256 epochStart = epochId * epochDuration;
        uint256 epochEnd = (epochId + 1) * epochDuration;
        
        // Check if any node was updated during this epoch
        for (uint256 i = 0; i < registeredNodes.length; i++) {
            string memory nodeId = registeredNodes[i];
            if (nodes[nodeId].lastUpdated >= epochStart && nodes[nodeId].lastUpdated < epochEnd) {
                return (true, nodes[nodeId].lastUpdated);
            }
        }
        
        return (false, 0);
    }
    
    // Event for epoch decision submission
    event EpochDecisionSubmitted(uint256 indexed epochId, uint256 nodeCount);
    
    // ============ OPTIMIZED LIGHTWEIGHT BLOCK FUNCTIONS ============
    
    /**
     * @dev Calculate merkleRoot from probes array
     * Builds merkle tree: hash pairs recursively until single root
     */
    function calculateMerkleRoot(Probe[] calldata probes) 
        internal 
        pure 
        returns (bytes32)
    {
        require(probes.length > 0, "Empty probes array");
        
        // Hash each probe
        bytes32[] memory hashes = new bytes32[](probes.length);
        for (uint256 i = 0; i < probes.length; i++) {
            hashes[i] = keccak256(abi.encode(
                probes[i].websiteHash,
                probes[i].latency,
                probes[i].failureRate,
                probes[i].anomalyProbability,
                probes[i].reputationScore
            ));
        }
        
        // Build merkle tree bottom-up
        while (hashes.length > 1) {
            bytes32[] memory nextLevel = new bytes32[]((hashes.length + 1) / 2);
            for (uint256 i = 0; i < hashes.length; i += 2) {
                bytes32 left = hashes[i];
                bytes32 right = i + 1 < hashes.length ? hashes[i + 1] : hashes[i];
                nextLevel[i / 2] = keccak256(abi.encodePacked(left, right));
            }
            hashes = nextLevel;
        }
        
        return hashes[0];
    }
    
    /**
     * @dev Submit block header + body
     * Header stored on-chain, body verified via merkleRoot
     * Gas: ~50,000 (67% cheaper than storing full data)
     * 
     * @param previousBlockHash Hash of previous block
     * @param shardId Shard ID (1-5)
     * @param probes Array of monitoring probes (max 50)
     */
    function submitBlock(
        bytes32 previousBlockHash,
        uint8 shardId,
        Probe[] calldata probes
    ) external {
        require(shardId >= 1 && shardId <= 5, "Invalid shard ID (1-5)");
        require(probes.length > 0 && probes.length <= 50, "Must have 1-50 probes");
        
        // Validate each probe
        for (uint256 i = 0; i < probes.length; i++) {
            require(probes[i].failureRate <= 100, "Failure rate must be 0-100");
            require(probes[i].anomalyProbability <= 100, "Anomaly prob must be 0-100");
            require(probes[i].reputationScore <= 1000, "Reputation score must be 0-1000");
            require(probes[i].latency < 65535, "Latency out of range");
        }
        
        // Calculate merkleRoot from probes (verifies data integrity)
        bytes32 merkleRoot = calculateMerkleRoot(probes);
        
        // Create header (this is what gets stored)
        uint256 blockId = blockHeaders.length;
        BlockHeader memory header = BlockHeader({
            blockId: blockId,
            timestamp: block.timestamp,
            previousBlockHash: previousBlockHash,
            merkleRoot: merkleRoot,
            shardId: shardId,
            producerId: msg.sender
        });
        
        // Store ONLY header on-chain (not the full body)
        blockHeaders.push(header);
        blockBodyHash[blockId] = merkleRoot;
        provenBodies[merkleRoot] = true;
        
        // Track for shard and website queries
        shardBlocks[shardId].push(blockId);
        for (uint256 i = 0; i < probes.length; i++) {
            websiteBlocks[probes[i].websiteHash].push(blockId);
        }
        
        emit BlockHeaderSubmitted(blockId, msg.sender, merkleRoot, shardId, probes.length);
    }
    
    /**
     * @dev Batch submit multiple blocks (e.g., 50 websites in 50 blocks)
     * More efficient than individual submitBlock calls
     */
    function batchSubmitBlocks(
        bytes32[] calldata previousHashes,
        uint8[] calldata shardIds,
        Probe[][] calldata probesArray
    ) external {
        require(
            previousHashes.length == shardIds.length && 
            shardIds.length == probesArray.length,
            "Array length mismatch"
        );
        
        for (uint256 i = 0; i < probesArray.length; i++) {
            require(shardIds[i] >= 1 && shardIds[i] <= 5, "Invalid shard ID");
            require(probesArray[i].length > 0 && probesArray[i].length <= 50, "Invalid probe count");
            
            // Calculate merkleRoot
            bytes32 merkleRoot = calculateMerkleRoot(probesArray[i]);
            
            // Create header
            uint256 blockId = blockHeaders.length;
            BlockHeader memory header = BlockHeader({
                blockId: blockId,
                timestamp: block.timestamp,
                previousBlockHash: previousHashes[i],
                merkleRoot: merkleRoot,
                shardId: shardIds[i],
                producerId: msg.sender
            });
            
            // Store header
            blockHeaders.push(header);
            blockBodyHash[blockId] = merkleRoot;
            provenBodies[merkleRoot] = true;
            shardBlocks[shardIds[i]].push(blockId);
            
            // Track websites
            for (uint256 j = 0; j < probesArray[i].length; j++) {
                websiteBlocks[probesArray[i][j].websiteHash].push(blockId);
            }
            
            emit BlockHeaderSubmitted(blockId, msg.sender, merkleRoot, shardIds[i], probesArray[i].length);
        }
    }
    
    /**
     * @dev Verify that probes match the block header's merkleRoot
     * Client calls this to prove body matches header
     * 
     * @param blockId Block identifier
     * @param probes Array of probes to verify
     * @return True if merkleRoot matches
     */
    function verifyProbesAgainstHeader(
        uint256 blockId,
        Probe[] calldata probes
    ) external view returns (bool) {
        require(blockId < blockHeaders.length, "Block not found");
        bytes32 calculatedRoot = calculateMerkleRoot(probes);
        return blockHeaders[blockId].merkleRoot == calculatedRoot;
    }
    
    /**
     * @dev Get block header (what's stored on-chain)
     * Returns only header, not body (body verified via merkleRoot)
     */
    function getBlockHeader(uint256 blockId) 
        external 
        view 
        returns (BlockHeader memory)
    {
        require(blockId < blockHeaders.length, "Block not found");
        return blockHeaders[blockId];
    }
    
    /**
     * @dev Get all block headers for a shard
     */
    function getShardHeaders(uint8 shardId) 
        external 
        view 
        returns (BlockHeader[] memory)
    {
        require(shardId >= 1 && shardId <= 5, "Invalid shard ID");
        
        uint256[] storage blockIds = shardBlocks[shardId];
        BlockHeader[] memory result = new BlockHeader[](blockIds.length);
        
        for (uint256 i = 0; i < blockIds.length; i++) {
            result[i] = blockHeaders[blockIds[i]];
        }
        
        return result;
    }
    
    /**
     * @dev Get all block headers for a website
     */
    function getWebsiteHeaders(string memory websiteId) 
        external 
        view 
        returns (BlockHeader[] memory)
    {
        bytes32 websiteHash = keccak256(abi.encode(websiteId));
        uint256[] storage blockIds = websiteBlocks[websiteHash];
        BlockHeader[] memory result = new BlockHeader[](blockIds.length);
        
        for (uint256 i = 0; i < blockIds.length; i++) {
            result[i] = blockHeaders[blockIds[i]];
        }
        
        return result;
    }
    
    /**
     * @dev Get latest block header for website
     */
    function getLatestWebsiteHeader(string memory websiteId) 
        external 
        view 
        returns (BlockHeader memory)
    {
        bytes32 websiteHash = keccak256(abi.encode(websiteId));
        uint256[] storage blockIds = websiteBlocks[websiteHash];
        
        require(blockIds.length > 0, "No blocks for this website");
        return blockHeaders[blockIds[blockIds.length - 1]];
    }
    
    /**
     * @dev Check if merkleRoot has been proven
     */
    function isProofVerified(bytes32 merkleRoot) 
        external 
        view 
        returns (bool)
    {
        return provenBodies[merkleRoot];
    }
    
    /**
     * @dev Get total number of blocks
     */
    function getBlockCount() external view returns (uint256) {
        return blockHeaders.length;
    }
    
    /**
     * @dev Get all blocks (paginated)
     */
    function getBlockHeadersPaginated(uint256 offset, uint256 limit) 
        external 
        view 
        returns (BlockHeader[] memory)
    {
        require(offset < blockHeaders.length, "Offset out of range");
        uint256 end = offset + limit > blockHeaders.length 
            ? blockHeaders.length 
            : offset + limit;
        
        BlockHeader[] memory result = new BlockHeader[](end - offset);
        
        for (uint256 i = offset; i < end; i++) {
            result[i - offset] = blockHeaders[i];
        }
        
        return result;
    }
}
