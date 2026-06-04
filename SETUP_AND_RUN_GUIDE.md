# Complete End-to-End Setup and Run Guide

This guide will walk you through setting up and running the entire decentralized website monitoring system from scratch.

## Prerequisites

Before starting, ensure you have:
- ✅ Python 3.8 or higher
- ✅ Node.js 16 or higher
- ✅ npm (comes with Node.js)
- ✅ Git
- ✅ A code editor (VS Code recommended)

### Check Prerequisites

```cmd
python --version
node --version
npm --version
git --version
```

---

## Part 1: Initial Setup (One-Time)

### Step 1: Install Python Dependencies

Open Command Prompt in the project root directory:

```cmd
cd c:\Users\bhagy\Downloads\minor-project-main

REM Create virtual environment
python -m venv venv

REM Activate virtual environment
venv\Scripts\activate

REM Install node_service dependencies
cd node_service
pip install -r requirements.txt
cd ..
```

### Step 2: Install Blockchain Dependencies

```cmd
REM Install Node.js packages for Hardhat
cd blockchain
npm install
cd ..
```

### Step 3: Create Environment Configuration

Create a `.env` file in the project root:

```cmd
copy .env.example .env
```

Edit `.env` with these settings:

```env
# Node Configuration
NODE_ID=node_1
NODE_HOST=127.0.0.1
NODE_PORT=8000
WEBSITES=https://httpbin.org/status/200,https://google.com,https://github.com
MONITORING_INTERVAL=60

# Blockchain Configuration (Local Hardhat)
ETHEREUM_RPC_URL=http://127.0.0.1:8545
PRIVATE_KEY=0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80
CONTRACT_ADDRESS=
CHAIN_ID=31337

# ML Configuration
MODEL_PATH=./ml/models
ML_CONFIDENCE_THRESHOLD=0.7
```

**Note**: The private key above is Hardhat's default test account #0. Never use this in production!

---

## Part 2: System Startup (Every Time)

You'll need **4 separate terminal windows** for a complete setup:
1. Terminal 1: Blockchain (Hardhat)
2. Terminal 2: Node 1
3. Terminal 3: Node 2
4. Terminal 4: Node 3 (optional)

### Terminal 1: Start Blockchain

```cmd
cd c:\Users\bhagy\Downloads\minor-project-main\blockchain

REM Start local Hardhat node
npm run node
```

**Expected output**:
```
Started HTTP and WebSocket JSON-RPC server at http://127.0.0.1:8545/

Accounts
========
Account #0: 0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266 (10000 ETH)
Private Key: 0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80
...
```

**Keep this terminal running!**

### Terminal 2: Deploy Smart Contract

Open a **new terminal**:

```cmd
cd c:\Users\bhagy\Downloads\minor-project-main\blockchain

REM Compile the smart contract
npm run compile

REM Deploy to local network
npm run deploy:local
```

**Expected output**:
```
Compiled 1 Solidity file successfully
Deploying ProofOfReputation...
ProofOfReputation deployed to: 0x5FbDB2315678afecb367f032d93F642f64180aa3
```

**IMPORTANT**: Copy the contract address (starts with `0x...`) and update your `.env` file:

```env
CONTRACT_ADDRESS=0x5FbDB2315678afecb367f032d93F642f64180aa3
```

### Terminal 3: Start Node 1

Open a **new terminal**:

```cmd
cd c:\Users\bhagy\Downloads\minor-project-main

REM Activate virtual environment
venv\Scripts\activate

REM Set environment variables for Node 1
set NODE_ID=node_1
set NODE_PORT=8000

REM Start the node
cd node_service
python main.py
```

**Expected output**:
```
INFO:     Started server process
INFO:     Waiting for application startup.
INFO:     WebsiteMonitor initialized with node_id: node_1
INFO:     Node public key: 04a1b2c3d4e5f6...
INFO:     Blockchain client initialized
INFO:     Node registered on blockchain with initial reputation: 1.0
INFO:     Started monitoring 3 websites
INFO:     Application startup complete.
INFO:     Uvicorn running on http://127.0.0.1:8000
```

**Keep this terminal running!**

### Terminal 4: Start Node 2

Open a **new terminal**:

```cmd
cd c:\Users\bhagy\Downloads\minor-project-main

REM Activate virtual environment
venv\Scripts\activate

REM Set environment variables for Node 2
set NODE_ID=node_2
set NODE_PORT=8001

REM Start Node 2 with peer connection to Node 1
cd node_service
python main.py --peers http://127.0.0.1:8000
```

**Expected output**:
```
INFO:     Started server process
INFO:     Node public key: 04d5e6f7a8b9c0...
INFO:     Auto-registering 1 peers from --peers flag
INFO:     Getting peer info from http://127.0.0.1:8000/health
INFO:     ✅ Auto-registered peer node_1 at http://127.0.0.1:8000
INFO:     ✅ Successfully registered with peer node_1
INFO:     Uvicorn running on http://127.0.0.1:8001
```

**Keep this terminal running!**

### Terminal 5: Start Node 3 (Optional)

If you want to run a 3-node network:

```cmd
cd c:\Users\bhagy\Downloads\minor-project-main
venv\Scripts\activate

set NODE_ID=node_3
set NODE_PORT=8002

cd node_service
python main.py --peers http://127.0.0.1:8000 http://127.0.0.1:8001
```

---

## Part 3: Verify System is Working

### Check Node Health

Open a web browser or use curl:

```cmd
REM Check Node 1
curl http://127.0.0.1:8000/health

REM Check Node 2
curl http://127.0.0.1:8001/health

REM Check Node 3
curl http://127.0.0.1:8002/health
```

**Expected response**:
```json
{
  "status": "healthy",
  "node_id": "node_1",
  "timestamp": "2024-12-08T10:30:45",
  "public_key_hex": "04a1b2c3d4e5f6...",
  "api_port": 8000,
  "p2p_port": 9000,
  "components": {
    "monitoring": "active",
    "trust_engine": "active",
    "peer_client": {
      "status": "active",
      "connected_peers": 2
    },
    "ml_classifier": "active",
    "blockchain": {
      "connected": true,
      "contract_address": "0x5FbDB2315678afecb367f032d93F642f64180aa3"
    }
  }
}
```

### Check Peer Connections

```cmd
curl http://127.0.0.1:8000/peers
```

**Expected response**:
```json
{
  "total_peers": 2,
  "peers": [
    {
      "node_id": "node_2",
      "url": "http://127.0.0.1:8001",
      "public_key_hex": "04d5e6f7...",
      "last_seen": "2024-12-08T10:31:00"
    },
    {
      "node_id": "node_3",
      "url": "http://127.0.0.1:8002",
      "public_key_hex": "04f1a2b3...",
      "last_seen": "2024-12-08T10:31:05"
    }
  ]
}
```

### Check Monitoring Results

```cmd
curl http://127.0.0.1:8000/statistics
```

**Expected response**:
```json
{
  "node_id": "node_1",
  "uptime": 300,
  "websites_monitored": 3,
  "total_checks": 15,
  "successful_checks": 14,
  "failed_checks": 1,
  "current_reputation": 0.95,
  "peer_count": 2,
  "epoch_id": 1234567890
}
```

### Check Blockchain Reputation

```cmd
curl http://127.0.0.1:8000/blockchain/reputation/node_1
```

**Expected response**:
```json
{
  "node_id": "node_1",
  "reputation": 0.95,
  "monitoring_trust": 0.96,
  "ml_score": 0.93,
  "last_update": 1234567890,
  "is_registered": true
}
```

---

## Part 4: Test Malicious Node Detection

### Start a Malicious Node

In a new terminal:

```cmd
cd c:\Users\bhagy\Downloads\minor-project-main
venv\Scripts\activate

set NODE_ID=malicious_node
set NODE_PORT=8003
set NODE_MODE=malicious

cd node_service
python main.py --peers http://127.0.0.1:8000 http://127.0.0.1:8001
```

**What happens**:
1. Malicious node reports false data (sites down when they're up, inflated latencies, etc.)
2. After 4-5 epochs (~5 minutes), ML consensus engine detects anomaly
3. Reputation drops below 0.2
4. Node gets slashed on blockchain
5. Node is banned from submitting future reports

### Monitor the Slashing

Watch Terminal 1 (Node 1) logs for:
```
WARNING: Node malicious_node flagged by ML with probability 0.87
WARNING: Node malicious_node reputation dropped to 0.18 - SLASHING
INFO: Successfully slashed node malicious_node on blockchain
INFO: Node malicious_node added to banned_nodes list
```

### Verify Banned Status

```cmd
curl -X POST http://127.0.0.1:8000/report ^
  -H "Content-Type: application/json" ^
  -d "{\"node_id\":\"malicious_node\",\"url\":\"https://example.com\",\"status\":\"success\"}"
```

**Expected response**:
```json
{
  "status": "rejected",
  "reason": "node is banned"
}
```

---

## Part 5: View Real-Time Dashboard (Optional)

If you have the dashboard installed:

```cmd
cd c:\Users\bhagy\Downloads\minor-project-main\dashboard\src
streamlit run app.py --server.port 8501
```

Open browser to: http://localhost:8501

---

## Troubleshooting

### Issue 1: "Port already in use"

**Problem**: Port 8000, 8001, or 8545 is already in use

**Solution**:
```cmd
REM Find process using port
netstat -ano | findstr :8000

REM Kill the process (replace PID with actual process ID)
taskkill /PID <PID> /F
```

### Issue 2: "ModuleNotFoundError"

**Problem**: Python dependencies not installed

**Solution**:
```cmd
venv\Scripts\activate
pip install -r node_service\requirements.txt
```

### Issue 3: "Blockchain connection failed"

**Problem**: Hardhat node not running or contract not deployed

**Solution**:
1. Check Terminal 1 - Hardhat should be running
2. Redeploy contract: `npm run deploy:local` in blockchain directory
3. Update CONTRACT_ADDRESS in .env file

### Issue 4: "Peers not connecting"

**Problem**: Peer nodes can't discover each other

**Solution**:
1. Check firewall settings
2. Verify NODE_PORT environment variables are different for each node
3. Check `curl http://127.0.0.1:8000/health` returns valid response with `public_key_hex`

### Issue 5: "ML model not found"

**Problem**: ML models not in expected directory

**Solution**:
```cmd
REM Check if models exist
dir ML_MINOR\models

REM If missing, models should be in:
REM - ML_MINOR\models\rf_backbone.joblib
REM - ML_MINOR\models\iso_backbone.joblib
REM - ML_MINOR\models\meta_learner.joblib
```

---

## System Architecture Overview

```
┌─────────────────────────────────────────────────────────┐
│                  Local Hardhat Blockchain               │
│          (Smart Contract: ProofOfReputation)            │
│              Port: 8545                                 │
└────────────┬────────────────────────────────────────────┘
             │
             │ Web3 Connection
             │
    ┌────────┴────────┬──────────────┬──────────────┐
    │                 │              │              │
┌───▼───┐        ┌───▼───┐     ┌───▼───┐     ┌───▼───┐
│Node 1 │◄──────►│Node 2 │◄───►│Node 3 │◄───►│ Node N│
│:8000  │  P2P   │:8001  │ P2P │:8002  │ P2P │ :800N │
└───┬───┘        └───┬───┘     └───┬───┘     └───┬───┘
    │                │              │              │
    │                │              │              │
    └────────────────┴──────────────┴──────────────┘
                     │
                     │ Monitoring
                     ▼
         ┌───────────────────────┐
         │   Monitored Websites  │
         │  - httpbin.org        │
         │  - google.com         │
         │  - github.com         │
         └───────────────────────┘
```

### Data Flow

1. **Monitoring Cycle** (every 60 seconds):
   - Each node probes configured websites
   - Measures: HTTP status, response time, SSL, DNS, content hash
   - Returns dict with spec-compliant keys

2. **P2P Broadcast**:
   - Node signs monitoring report with private key
   - Broadcasts to all peer nodes via POST /report
   - Peers verify signature with public key

3. **Epoch Processing** (every minute, wall-clock aligned):
   - Second 0: Assign nodes to 4 tiers based on reputation
   - Second 5: Wait for all reports to arrive
   - Second 55: ML engine extracts 8 RIPE Atlas features
   - Second 58: Run reputation-weighted consensus
   - Second 59: Update reputations, slash malicious nodes

4. **ML Detection**:
   - Extract 8 features: avg_latency, latency_var, std_latency, skewness, kurtosis, p95_latency, max_latency, failure_rate
   - Random Forest + Isolation Forest → Meta-learner
   - Output: Probability node is malicious (0.0 to 1.0)
   - Threshold: > 0.5 for 3+ consecutive epochs → quarantine

5. **Reputation Update**:
   - PoR = 0.6 × monitoring_trust + 0.4 × ml_score
   - EWMA smoothing: alpha=0.3 (30% new, 70% history)
   - Blockchain: batch_update_reputation(node_id, monitoring_trust, ml_score)

6. **4-Tier Mitigation**:
   - Tier 1 (PoR > 0.8): Full voting rights, can be leader
   - Tier 2 (0.5 - 0.8): Weighted voting, monitored by ML
   - Tier 3 (0.2 - 0.5): Zero voting, quarantined
   - Tier 4 (< 0.2): Slashed, banned, all reports rejected

---

## Quick Reference: Common Commands

### Start Everything (3 terminals)

**Terminal 1**: Blockchain
```cmd
cd blockchain
npm run node
```

**Terminal 2**: Deploy contract
```cmd
cd blockchain
npm run compile
npm run deploy:local
REM Copy contract address to .env
```

**Terminal 3**: Node 1
```cmd
venv\Scripts\activate
set NODE_ID=node_1
set NODE_PORT=8000
cd node_service
python main.py
```

**Terminal 4**: Node 2
```cmd
venv\Scripts\activate
set NODE_ID=node_2
set NODE_PORT=8001
cd node_service
python main.py --peers http://127.0.0.1:8000
```

### API Endpoints

- Health: `http://127.0.0.1:8000/health`
- Peers: `http://127.0.0.1:8000/peers`
- Statistics: `http://127.0.0.1:8000/statistics`
- Trust: `http://127.0.0.1:8000/trust`
- Reputation: `http://127.0.0.1:8000/blockchain/reputation/node_1`
- Reports: `http://127.0.0.1:8000/reports/latest?limit=10`

### Stop Everything

1. Press `Ctrl+C` in each terminal
2. Wait for graceful shutdown
3. Blockchain data is reset on next `npm run node`

---

## Production Deployment Notes

For production deployment:

1. **Replace Hardhat with real Ethereum network** (Sepolia testnet or Mainnet)
2. **Use real private keys** from secure key management (never commit to git)
3. **Configure firewall** to allow P2P ports (9000+)
4. **Set up monitoring** with proper logging and alerting
5. **Use environment-specific .env files** (.env.prod, .env.staging)
6. **Deploy with Docker** for easier management
7. **Use reverse proxy** (nginx) for API endpoints
8. **Enable HTTPS** for all communications
9. **Implement rate limiting** on API endpoints
10. **Set up automated backups** of node state

---

## Success Checklist

✅ Hardhat blockchain running on port 8545  
✅ Smart contract deployed and address in .env  
✅ Node 1 running on port 8000  
✅ Node 2 running on port 8001  
✅ Node 3 running on port 8002 (optional)  
✅ All nodes connected to blockchain  
✅ Peer connections established (check /peers endpoint)  
✅ Monitoring cycle running (check /statistics)  
✅ Reputations updating on blockchain (check logs)  
✅ ML models loaded successfully (check logs)  
✅ Epoch manager running on wall-clock schedule (check logs)  

**Congratulations! Your decentralized monitoring system is now fully operational!** 🎉

---

## Next Steps

1. **Test malicious behavior**: Start a node with `NODE_MODE=malicious`
2. **Monitor reputation changes**: Watch logs for ML detection and slashing
3. **Add more websites**: Update WEBSITES in .env
4. **Scale to more nodes**: Start additional nodes on different ports
5. **Measure performance**: Run `python ML_MINOR/measure_real_tps.py`
6. **Explore API**: Try all endpoints documented above
7. **Read architecture docs**: Check ARCHITECTURE.md for deep dive

---

For questions or issues, check:
- BUGS_FIXED.md - List of all fixed bugs
- ARCHITECTURE.md - Detailed system design
- README.md - Project overview
- GitHub issues - Community support
