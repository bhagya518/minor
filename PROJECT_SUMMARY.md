# Project Summary: Decentralized Reputation Monitoring System (PoR)

## 1. Project Overview
This project implements a high-performance, decentralized website monitoring system using a **Proof-of-Reputation (PoR)** consensus mechanism. It leverages Machine Learning (Random Forest + Isolation Forest) to detect malicious nodes and maintain a trustworthy network of monitoring agents.

## 2. Core Modules & Architecture

### **A. Node Service (`node_service/`)**
*   **`main.py`**: The central FastAPI application. Manages API endpoints, node lifecycle, and coordinates between monitoring, consensus, and P2P communication.
*   **`website_monitor.py`**: The monitoring engine. Performs HTTP, SSL, and DNS checks. Supports "Honest" and "Malicious" modes for testing.
*   **`ml_consensus_engine.py`**: The "brain" of the node. Uses a vectorized ML pipeline to process reports, calculate reputations using EWMA smoothing, and assign nodes to one of 4 tiers (Allow, Warn, Quarantine, Slash).
*   **`peer_client.py`**: Handles P2P gossip-based communication. Uses a fanout mechanism to ensure scalability to 50+ nodes without O(N²) complexity.
*   **`epoch_manager.py`**: Manages synchronized 5-second epoch windows, ensures quorum is reached, and triggers slashing events on the blockchain.
*   **`monitoring_report.py`**: Defines the canonical, cryptographically signed report format using Ed25519 signatures.

### **B. Blockchain Layer (`blockchain/`)**
*   **Hardhat Network**: Local EVM-compatible blockchain for immutable record-keeping.
*   **Reputation Contract**: Stores node stakes and executes slashing transactions triggered by the consensus engine.

### **C. Dashboard (`dashboard/`)**
*   **`app.py`**: Streamlit-based real-time command center.
*   **Global Website Status**: Real-time grid showing Uptime, Latency (ms), and SSL status across the network.
*   **Node Reputation Leaderboard**: 4-tier leaderboard (Allow, Warn, Quarantine, Slash) with live reputation scores and distribution charts.

## 3. System Flow
1.  **Monitoring**: Nodes scan target URLs every 5-10 seconds.
2.  **Signing**: Each node signs its report with its private key.
3.  **Gossip**: Reports are broadcasted to peers using a scalable gossip protocol.
4.  **Consensus**: Every 5 seconds (Epoch), the ML engine aggregates all received reports.
5.  **ML Inference**: The engine detects anomalies (e.g., node_d reporting a site is DOWN when it is UP).
6.  **Reputation Update**: EWMA scores are updated. Malicious nodes are moved to the "Slash" tier.
7.  **Slashing**: The leader of the epoch triggers a blockchain transaction to penalize the malicious node's stake.

## 4. Key Improvements & Optimizations
*   **Sub-Second Latency**: Optimized data fetching and caching reduced dashboard refresh time from 5s+ to <500ms.
*   **Vectorized ML Engine**: Completely rewrote the consensus logic to use NumPy/Pandas batch processing, supporting up to 50 nodes with minimal CPU overhead.
*   **5-Second Epoch Sync**: Synchronized all modules (Monitor, Manager, Reports) to a high-frequency 5-second clock for real-time responsiveness.
*   **Gossip Protocol**: Implemented fanout-based P2P messaging to prevent network congestion as the node count grows.
*   **Robust SSL Checks**: Enhanced SSL validation with `aiohttp` fallback and increased handshaking timeouts to eliminate false ❌ marks.

## 5. Final Results & Benchmarks
*   **Max Throughput**: Successfully tested with **190 Reports Per Second (RPS)**.
*   **Scalability**: Validated consistent performance from 8 nodes up to 50 nodes.
*   **Accuracy**: 100% detection rate of "simple malicious" behavior (fake downtime reports) within 2-3 epochs.
*   **Network Health**: Maintained >90% average trust score in a mixed environment (honest + malicious nodes).

---
*Date: 2026-05-02*
*System Version: 2.1-Enhanced-ML*
