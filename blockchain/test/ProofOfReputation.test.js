const { expect } = require("chai");
const { ethers } = require("hardhat");

describe("ProofOfReputation", function () {
  let proofOfReputation;
  let owner;
  let addr1;
  let addr2;
  let addrs;

  beforeEach(async function () {
    // Get the ContractFactory and Signers here.
    const ProofOfReputation = await ethers.getContractFactory("ProofOfReputation");
    [owner, addr1, addr2, ...addrs] = await ethers.getSigners();

    // To deploy our contract
    proofOfReputation = await ProofOfReputation.deploy();
    await proofOfReputation.deployed();
  });

  describe("Deployment", function () {
    it("Should set the right owner", async function () {
      expect(await proofOfReputation.owner()).to.equal(owner.address);
    });

    it("Should start with zero registered nodes", async function () {
      expect(await proofOfReputation.getNodeCount()).to.equal(0);
    });
  });

  describe("Node Registration", function () {
    it("Should register a new node", async function () {
      const nodeId = "node_test_1";
      await expect(proofOfReputation.registerNode(nodeId))
        .to.emit(proofOfReputation, "NodeRegistered")
        .withArgs(nodeId, owner.address);

      expect(await proofOfReputation.isNodeRegistered(nodeId)).to.be.true;
      expect(await proofOfReputation.getNodeCount()).to.equal(1);
    });

    it("Should not allow duplicate registration", async function () {
      const nodeId = "node_test_1";
      await proofOfReputation.registerNode(nodeId);
      
      await expect(proofOfReputation.registerNode(nodeId))
        .to.be.revertedWith("Node already registered");
    });

    it("Should not allow empty node ID", async function () {
      await expect(proofOfReputation.registerNode(""))
        .to.be.revertedWith("Node ID cannot be empty");
    });
  });

  describe("Reputation Management", function () {
    const nodeId = "node_test_1";
    const monitoringTrust = 800; // 0.8
    const mlScore = 900; // 0.9
    const expectedReputation = (monitoringTrust * 40 + mlScore * 60) / 100; // 860

    beforeEach(async function () {
      await proofOfReputation.registerNode(nodeId);
    });

    it("Should update node reputation correctly", async function () {
      await expect(proofOfReputation.updateReputation(nodeId, monitoringTrust, mlScore))
        .to.emit(proofOfReputation, "ReputationUpdated")
        .withArgs(nodeId, expectedReputation, monitoringTrust, mlScore);

      const reputation = await proofOfReputation.getNodeReputation(nodeId);
      expect(reputation.reputation).to.equal(expectedReputation);
      expect(reputation.monitoringTrust).to.equal(monitoringTrust);
      expect(reputation.mlScore).to.equal(mlScore);
    });

    it("Should calculate PoR formula correctly", async function () {
      // Test with different values
      const testCases = [
        { monitoringTrust: 1000, mlScore: 1000, expected: 1000 },
        { monitoringTrust: 0, mlScore: 0, expected: 0 },
        { monitoringTrust: 500, mlScore: 500, expected: 500 },
        { monitoringTrust: 800, mlScore: 900, expected: 860 }
      ];

      for (const testCase of testCases) {
        await proofOfReputation.updateReputation(nodeId, testCase.monitoringTrust, testCase.mlScore);
        const reputation = await proofOfReputation.getNodeReputation(nodeId);
        expect(reputation.reputation).to.equal(testCase.expected);
      }
    });

    it("Should not allow values > 1000", async function () {
      await expect(proofOfReputation.updateReputation(nodeId, 1001, mlScore))
        .to.be.revertedWith("Monitoring trust must be <= 1000");
      
      await expect(proofOfReputation.updateReputation(nodeId, monitoringTrust, 1001))
        .to.be.revertedWith("ML score must be <= 1000");
    });

    it("Should not allow reputation update for unregistered node", async function () {
      const unregisteredNodeId = "unregistered_node";
      await expect(proofOfReputation.updateReputation(unregisteredNodeId, monitoringTrust, mlScore))
        .to.be.revertedWith("Node must be registered");
    });
  });

  describe("Report Submission", function () {
    const nodeId = "node_test_1";

    beforeEach(async function () {
      await proofOfReputation.registerNode(nodeId);
    });

    it("Should submit reports and update statistics", async function () {
      // Submit some reports
      await proofOfReputation.submitReport(nodeId, true);
      await proofOfReputation.submitReport(nodeId, true);
      await proofOfReputation.submitReport(nodeId, false);

      const stats = await proofOfReputation.getNodeStats(nodeId);
      expect(stats.totalReports).to.equal(3);
      expect(stats.successfulReports).to.equal(2);
      expect(stats.successRate).to.equal(66); // 2/3 * 100 = 66.66, rounded down
    });

    it("Should emit ReportSubmitted event", async function () {
      await expect(proofOfReputation.submitReport(nodeId, true))
        .to.emit(proofOfReputation, "ReportSubmitted")
        .withArgs(nodeId, true);
    });

    it("Should not allow report submission for unregistered node", async function () {
      const unregisteredNodeId = "unregistered_node";
      await expect(proofOfReputation.submitReport(unregisteredNodeId, true))
        .to.be.revertedWith("Node must be registered");
    });
  });

  describe("Query Functions", function () {
    const nodeId1 = "node_test_1";
    const nodeId2 = "node_test_2";

    beforeEach(async function () {
      await proofOfReputation.registerNode(nodeId1);
      await proofOfReputation.registerNode(nodeId2);
      
      // Set different reputations
      await proofOfReputation.updateReputation(nodeId1, 800, 900); // 860
      await proofOfReputation.updateReputation(nodeId2, 600, 700); // 660
    });

    it("Should return all registered nodes", async function () {
      const allNodes = await proofOfReputation.getAllNodes();
      expect(allNodes.length).to.equal(2);
      expect(allNodes).to.include(nodeId1);
      expect(allNodes).to.include(nodeId2);
    });

    it("Should return top nodes by reputation", async function () {
      const [topNodeIds, topReputations] = await proofOfReputation.getTopNodes(2);
      expect(topNodeIds[0]).to.equal(nodeId1); // Higher reputation
      expect(topNodeIds[1]).to.equal(nodeId2);
      expect(topReputations[0]).to.equal(860);
      expect(topReputations[1]).to.equal(660);
    });

    it("Should limit top nodes to requested number", async function () {
      const [topNodeIds, topReputations] = await proofOfReputation.getTopNodes(1);
      expect(topNodeIds.length).to.equal(1);
      expect(topReputations.length).to.equal(1);
      expect(topNodeIds[0]).to.equal(nodeId1);
    });
  });

  describe("Owner Functions", function () {
    it("Should allow owner to transfer ownership", async function () {
      await proofOfReputation.transferOwnership(addr1.address);
      expect(await proofOfReputation.owner()).to.equal(addr1.address);
    });

    it("Should not allow non-owner to transfer ownership", async function () {
      await expect(proofOfReputation.connect(addr1).transferOwnership(addr2.address))
        .to.be.revertedWith("Only owner can call this function");
    });

    it("Should allow owner to remove node", async function () {
      const nodeId = "node_test_1";
      await proofOfReputation.registerNode(nodeId);
      
      await proofOfReputation.removeNode(nodeId);
      expect(await proofOfReputation.isNodeRegistered(nodeId)).to.be.false;
      expect(await proofOfReputation.getNodeCount()).to.equal(0);
    });

    it("Should not allow non-owner to remove node", async function () {
      const nodeId = "node_test_1";
      await proofOfReputation.registerNode(nodeId);
      
      await expect(proofOfReputation.connect(addr1).removeNode(nodeId))
        .to.be.revertedWith("Only owner can call this function");
    });
  });
});
