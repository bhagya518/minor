import pkg from "hardhat";
import "dotenv/config";
import fs from "fs";
import path from "path";
import { fileURLToPath } from "url";

const { ethers, network } = pkg;
const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

async function main() {
  console.log("Deploying ProofOfReputation contract...");
  
  // Get the contract factory
  const ProofOfReputation = await ethers.getContractFactory("ProofOfReputation");
  
  // Deploy the contract
  const proofOfReputation = await ProofOfReputation.deploy();
  
  // Wait for deployment to complete (ethers.js v6 syntax)
  await proofOfReputation.waitForDeployment();
  
  const contractAddress = await proofOfReputation.getAddress();
  const deploymentTx = proofOfReputation.deploymentTransaction();
  console.log("ProofOfReputation deployed to:", contractAddress);
  console.log("Transaction hash:", deploymentTx.hash);
  
  // Create deployment info
  const signer = await ethers.provider.getSigner();
  const deploymentInfo = {
    contractAddress,
    network: network.name,
    deployer: await signer.getAddress(),
    timestamp: new Date().toISOString(),
    transactionHash: deploymentTx.hash
  };
  
  // Save deployment info
  const deploymentPath = path.join(__dirname, "..", "deployment.json");
  fs.writeFileSync(deploymentPath, JSON.stringify(deploymentInfo, null, 2));
  
  // Save ABI
  const abiPath = path.join(__dirname, "..", "ProofOfReputation.json");
  fs.writeFileSync(abiPath, JSON.stringify({
    abi: ProofOfReputation.interface.format("json"),
    address: contractAddress
  }, null, 2));
  
  console.log("Deployment info saved to:", deploymentPath);
  console.log("ABI saved to:", abiPath);
  
  // Test the contract with sample data
  console.log("\nTesting contract with sample data...");
  
  // Register a sample node
  const nodeId = "node_sample_1";
  const txRegister = await proofOfReputation.registerNode(nodeId);
  await txRegister.wait();
  console.log(`Registered node: ${nodeId}`);
  
  // Update reputation
  const monitoringTrust = 800; // 0.8
  const mlScore = 900; // 0.9
  const txRep = await proofOfReputation.updateReputation(nodeId, monitoringTrust, mlScore);
  await txRep.wait();
  console.log(`Updated reputation for ${nodeId}`);
  
  // Get reputation
  const reputation = await proofOfReputation.getNodeReputation(nodeId);
  console.log(`Node ${nodeId} reputation:`, {
    reputation: reputation.reputation.toString(),
    monitoringTrust: reputation.monitoringTrust.toString(),
    mlScore: reputation.mlScore.toString(),
    lastUpdated: new Date(Number(reputation.lastUpdated) * 1000).toISOString()
  });
  
  // Submit some reports
  await (await proofOfReputation.submitReport(nodeId, true)).wait();
  await (await proofOfReputation.submitReport(nodeId, true)).wait();
  await (await proofOfReputation.submitReport(nodeId, false)).wait();
  
  // Get stats
  const stats = await proofOfReputation.getNodeStats(nodeId);
  console.log(`Node ${nodeId} stats:`, {
    totalReports: stats.totalReports.toString(),
    successfulReports: stats.successfulReports.toString(),
    successRate: stats.successRate.toString()
  });

  // Spec additions smoke test (aggregated report + batching)
  console.log("\nTesting spec additions (aggregated report + batching)...");

  const epochId = Math.floor(Date.now() / 1000);
  await (await proofOfReputation.submitAggregatedReport(
    "https://example.com",
    epochId,
    true,
    3,
    1,
    3000,
    [nodeId]
  )).wait();
  console.log("Aggregated report submitted");

  await (await proofOfReputation.batchUpdateReputation(
    [nodeId],
    [850],
    [920]
  )).wait();
  console.log("Batch reputation update submitted");

  await (await proofOfReputation.batchSlashNodes(
    [nodeId],
    [1000],
    "Malicious behavior",
    epochId
  )).wait();
  console.log("Batch slashing submitted");
  
  console.log("\nContract deployment and testing completed successfully!");
}

main()
  .then(() => process.exit(0))
  .catch((error) => {
    console.error("Deployment failed:", error);
    process.exit(1);
  });
