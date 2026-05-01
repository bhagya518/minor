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
    
    // Modifiers
    modifier onlyOwner() {
        require(msg.sender == owner, "Only owner can call this function");
        _;
    }

    modifier onlyAggregator() {
        require(msg.sender == owner, "Only aggregator can call this function");
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
    
    constructor() {
        owner = msg.sender;
    }
    
    /**
     * @dev Register a new node in the system
     * @param nodeId Unique identifier for the node
     */
    function registerNode(string memory nodeId) 
        external 
        validNodeId(nodeId) 
    {
        require(!nodes[nodeId].isRegistered, "Node already registered");
        
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
    
    // ============ SPEC-COMPLIANT ADDITIONS ============
    
    // Store aggregated consensus reports
    struct AggregatedReport {
        string url;
        uint256 epochId;
        uint256 timestamp;
        bool consensusResult;  // true = UP, false = DOWN
        uint256 honestVotes;
        uint256 maliciousVotes;
        uint256 totalWeight;
        string[] participatingNodes;
    }
    
    // URL -> epoch_id -> report
    mapping(string => mapping(uint256 => AggregatedReport)) public websiteReports;
    mapping(string => uint256[]) public websiteEpochs;
    
    // Slashing records
    struct SlashRecord {
        string nodeId;
        uint256 amount;  // in basis points (10000 = 100%)
        string reason;
        uint256 timestamp;
        uint256 epochId;
    }
    
    SlashRecord[] public slashHistory;
    mapping(string => SlashRecord[]) public nodeSlashHistory;
    
    // Events
    event AggregatedReportSubmitted(string indexed url, uint256 indexed epochId, bool consensusResult, uint256 totalWeight);
    event NodeSlashed(string indexed nodeId, uint256 amount, string reason, uint256 indexed epochId);
    
    /**
     * @dev Submit an aggregated consensus report from an epoch
     * @param url The monitored URL
     * @param epochId The epoch identifier
     * @param consensusResult The consensus outcome (true=UP, false=DOWN)
     * @param honestVotes Number of honest votes
     * @param maliciousVotes Number of malicious votes
     * @param totalWeight Total reputation weight of participants
     * @param participatingNodes List of node IDs that participated
     */
    function submitAggregatedReport(
        string memory url,
        uint256 epochId,
        bool consensusResult,
        uint256 honestVotes,
        uint256 maliciousVotes,
        uint256 totalWeight,
        string[] memory participatingNodes
    ) external onlyAggregator {
        require(bytes(url).length > 0, "URL cannot be empty");
        require(epochId > 0, "Epoch ID must be > 0");
        
        AggregatedReport memory report = AggregatedReport({
            url: url,
            epochId: epochId,
            timestamp: block.timestamp,
            consensusResult: consensusResult,
            honestVotes: honestVotes,
            maliciousVotes: maliciousVotes,
            totalWeight: totalWeight,
            participatingNodes: participatingNodes
        });
        
        websiteReports[url][epochId] = report;
        websiteEpochs[url].push(epochId);
        
        emit AggregatedReportSubmitted(url, epochId, consensusResult, totalWeight);
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
            results[i] = websiteReports[url][epochId].consensusResult;
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
}
