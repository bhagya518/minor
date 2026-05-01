# Decentralized Website Monitoring System - Complete Startup Guide

## System Architecture Overview
`
Blockchain (Hardhat) -> Smart Contract -> Node Services -> Dashboard
     |                        |              |             |
  Ethereum Network     ProofOfReputation   FastAPI      Streamlit
  (localhost:8545)    Contract (0x5Fb...)  (8005-8008)   (8501)
`

## Prerequisites Installation

### 1. Python Dependencies
`ash
pip install fastapi uvicorn streamlit requests pandas plotly
pip install aiohttp cryptography web3 eth-account
pip install scikit-learn networkx numpy joblib
pip install aiofiles python-multipart httpx
`

### 2. Node.js Dependencies (Blockchain)
`ash
cd blockchain
npm install
`

## Complete System Startup Procedure

### Step 1: Start Blockchain Network
`ash
# Open Terminal 1
cd blockchain
npx hardhat node
`

### Step 2: Deploy Smart Contract
`ash
# Open Terminal 2 (keep Step 1 running)
cd blockchain
npx hardhat run scripts/deploy.js --network localhost
`

### Step 3: Start Monitoring Nodes

#### Node 1 (Port 8005) - Primary Node
`ash
# Open Terminal 3
cd node_service
python main.py --port 8005 --node-id node_8005 --websites https://httpbin.org/get https://httpbin.org/status/200
`

#### Node 2 (Port 8006) - Secondary Node
`ash
# Open Terminal 4
cd node_service
python main.py --port 8006 --node-id node_8006 --websites https://httpbin.org/get https://httpbin.org/status/200 --peers http://localhost:8005
`

#### Node 3 (Port 8007) - Additional Node
`ash
# Open Terminal 5
cd node_service
python main.py --port 8007 --node-id node_8007 --websites https://httpbin.org/get https://httpbin.org/status/200 --peers http://localhost:8005 http://localhost:8006
`

#### Node 4 (Port 8008) - Additional Node
`ash
# Open Terminal 6
cd node_service
python main.py --port 8008 --node-id node_8008 --websites https://httpbin.org/get https://httpbin.org/status/200 --peers http://localhost:8005 http://localhost:8006 http://localhost:8007
`

### Step 4: Start Dashboard
`ash
# Open Terminal 7
cd dashboard/src
streamlit run app.py --server.port 8501
`

## System Verification Commands

### 1. Test Blockchain Connection
`ash
curl http://localhost:8005/health
`

### 2. Test Node Health
`ash
curl http://localhost:8005/health
curl http://localhost:8006/health
curl http://localhost:8007/health
curl http://localhost:8008/health
`

### 3. Test P2P Communication
`ash
curl http://localhost:8005/peers
curl http://localhost:8006/peers
`

### 4. Trigger Monitoring
`ash
curl -X POST http://localhost:8005/monitor -H  Content-Type: application/json -d '{urls: [https://httpbin.org/get]}'
`

### 5. Check Monitoring Results
`ash
curl http://localhost:8005/monitoring/results
curl http://localhost:8005/reports/latest
`

### 6. Test ML Consensus
`ash
curl http://localhost:8005/consensus/reputations
curl http://localhost:8005/verdict
`

### 7. Test Blockchain Integration
`ash
curl http://localhost:8005/blockchain/reputation/node_8005
`

## Dashboard Features Testing

### 1. Authentication
- Visit http://localhost:8501
- Enter any API key (e.g., test123)

### 2. Dynamic Node Discovery
- Dashboard should auto-discover all 4 nodes
- Check sidebar: Discovered 4 nodes

### 3. Monitor System Overview
- Check component status
- Verify trust scores
- View shard distribution

### 4. Test Consensus Voting
- Go to Consensus Voting tab
- View vote breakdown per node
- Check reputation-weighted voting

### 5. Test ML Features
- Go to ML Features tab
- View feature contributions
- Check ML explainability

### 6. Test Blockchain Integration
- Go to Overview tab
- View blockchain details
- Check contract status

## Quick Start Summary

`ash
# Terminal 1: Blockchain
cd blockchain && npx hardhat node

# Terminal 2: Contract
cd blockchain && npx hardhat run scripts/deploy.js --network localhost

# Terminal 3-6: Nodes (8005-8008)
cd node_service && python main.py --port 8005 --node-id node_8005 --websites https://httpbin.org/get
cd node_service && python main.py --port 8006 --node-id node_8006 --websites https://httpbin.org/get --peers http://localhost:8005
cd node_service && python main.py --port 8007 --node-id node_8007 --websites https://httpbin.org/get --peers http://localhost:8005 http://localhost:8006
cd node_service && python main.py --port 8008 --node-id node_8008 --websites https://httpbin.org/get --peers http://localhost:8005 http://localhost:8006 http://localhost:8007

# Terminal 7: Dashboard
cd dashboard/src && streamlit run app.py --server.port 8501
`

Visit http://localhost:8501 to access the dashboard!
