# Decentralized Website Monitoring System - Setup Guide

## 🚀 Quick Start Guide

This guide will help you set up and run the complete decentralized website monitoring system with blockchain, nodes, and dashboard.

---

## 📋 Prerequisites

- Python 3.8+
- Node.js and npm installed
- Hardhat installed locally in blockchain directory

---

## 🌐 System Architecture

The system consists of:
- **Blockchain**: Ethereum-based reputation system (Hardhat local network)
- **4 Monitoring Nodes**: Distributed nodes that monitor websites and participate in consensus
- **Dashboard**: Real-time visualization of system status and node reputations
- **ML Consensus Engine**: Machine learning-based reputation scoring and malicious node detection

---

## 🚀 Step-by-Step Setup

### **Step 1: Start Blockchain Network**

Open **Terminal 1** and run:

```bash
cd blockchain
npx hardhat node
```

**Expected Output:**
- "Listening on 127.0.0.1:8545"
- You should see blocks being mined

**Keep this terminal open.**

---

### **Step 2: Start 4 Monitoring Nodes**

Open **4 separate terminals** and start each node:

#### **Terminal 2 - Node A:**
```bash
cd node_service
python main.py --port 8005 --node-id node_a
```

#### **Terminal 3 - Node B:**
```bash
cd node_service
python main.py --port 8006 --node-id node_b
```

#### **Terminal 4 - Node C:**
```bash
cd node_service
python main.py --port 8007 --node-id node_c
```

#### **Terminal 5 - Node D:**
```bash
cd node_service
python main.py --port 8008 --node-id node_d
```

**Expected Output for Each Node:**
- "Starting node node_X on 0.0.0.0:port"
- "Blockchain client imported successfully"
- "Enhanced ML components imported successfully"
- "Starting monitoring of 3 websites"
- "Monitoring completed: X/3 successful"

**Keep all 4 terminals open.**

---

### **Step 3: Setup Network Mesh**

After all 4 nodes are running (wait about 30 seconds for them to initialize), open **Terminal 6** and run:

```bash
python setup_network.py
```

**What This Script Does:**
1. Fetches each node's public key from `/health` endpoint
2. Registers every node with every other node (full mesh network)
3. Injects malicious reports from node_d to test consensus
4. Prints live consensus results

**Expected Output:**
- "STEP 1: Fetching public keys" - Shows public keys for all nodes
- "STEP 2: Full mesh peer registration" - Registers all peer connections
- "STEP 3: Verifying peer registration" - Confirms mesh network
- "STEP 4: Injecting malicious reports" - Tests consensus with malicious behavior
- "STEP 5: Live consensus results" - Shows reputation scores and verdicts

---

### **Step 4: Start Dashboard**

Open **Terminal 7** and run:

```bash
cd dashboard/src
streamlit run app.py
```

**Expected Output:**
- "You can now view your Streamlit app in your browser"
- "Local URL: http://localhost:8501"

**Access the dashboard at:** http://localhost:8501

---

## 📊 Dashboard Features

The dashboard provides:
- **System Health**: Real-time status of blockchain and nodes
- **Monitoring Results**: Website uptime and response times
- **Trust Analysis**: Node reputation scores and trust levels
- **ML Features**: Machine learning consensus indicators
- **Peer Information**: Network topology and peer connections

---

## 🔍 Verification Checklist

**System is working correctly when:**

- ✅ **Blockchain Terminal**: Shows "Listening on 127.0.0.1:8545" and mining blocks
- ✅ **Node Terminals**: Show "Monitoring completed" messages every 60 seconds
- ✅ **Setup Network**: Shows "Full mesh registered" and peer connections
- ✅ **Dashboard**: Opens in browser at http://localhost:8501
- ✅ **Dashboard**: Shows green status for blockchain and nodes
- ✅ **Consensus**: Shows reputation scores and consensus verdicts

---

## 🧪 Testing Malicious Node Detection

The setup_network.py script automatically tests malicious node detection:

1. **Honest Nodes** (node_a, node_b, node_c): Report websites as UP
2. **Malicious Node** (node_d): Injected reports claim websites are DOWN
3. **Consensus**: Majority vote determines actual status
4. **Result**: node_d reputation decreases, may get SLASHED

**Expected Results:**
- Honest nodes: Reputation ~0.97-0.99
- Malicious node_d: Reputation decreases, may show SLASH action
- Majority verdict: 'up'
- Slashed: ['node_d']

---

## 🛠️ Troubleshooting

### **Blockchain won't start:**
```bash
cd blockchain
npm install
npx hardhat node
```

### **Nodes won't start:**
- Check if Python dependencies are installed:
```bash
cd node_service
pip install -r requirements.txt
```

### **Dashboard won't start:**
- Check if Streamlit is installed:
```bash
pip install streamlit
```

### **Nodes not connecting:**
- Ensure all nodes are running before running setup_network.py
- Wait 30 seconds after starting nodes before running setup_network.py
- Check if ports 8005-8008 are available (no conflicts)

### **Dashboard shows disconnected nodes:**
- Verify all 4 node terminals are still running
- Check node health endpoints:
```bash
curl http://localhost:8005/health
curl http://localhost:8006/health
curl http://localhost:8007/health
curl http://localhost:8008/health
```

---

## 📝 System Components

### **Blockchain** (localhost:8545)
- Hardhat local Ethereum network
- Reputation smart contract
- Transaction logging

### **Monitoring Nodes** (localhost:8005-8008)
- Node A: http://localhost:8005
- Node B: http://localhost:8006
- Node C: http://localhost:8007
- Node D: http://localhost:8008

### **Dashboard** (localhost:8501)
- Streamlit-based visualization
- Real-time system monitoring
- Trust and reputation tracking

---

## 🔄 Resetting the System

To reset and start fresh:

1. **Stop all terminals** (Ctrl+C in each)
2. **Restart blockchain** (Step 1)
3. **Restart nodes** (Step 2)
4. **Run setup_network.py** (Step 3)
5. **Start dashboard** (Step 4)

---

## 📚 Additional Information

- **Monitored Websites**: google.com, github.com, httpbin.org (default)
- **Monitoring Interval**: Every 60 seconds
- **Consensus Epoch**: 1-minute epochs
- **Reputation Threshold**: Nodes with reputation < 0.6 may be slashed
- **Mesh Network**: Full peer-to-peer connectivity

---

## 🎯 Key API Endpoints

### **Node Health:**
```
GET http://localhost:8005/health
```

### **Peer Registration:**
```
POST http://localhost:8005/peers/register
```

### **Monitoring Results:**
```
GET http://localhost:8005/monitoring/results
```

### **Consensus Verdict:**
```
GET http://localhost:8005/verdict
```

### **Node Reputation:**
```
GET http://localhost:8005/consensus/reputations
```

---

## ✅ Success Indicators

The system is working correctly when:

1. **Blockchain**: Mining blocks continuously
2. **Nodes**: Showing monitoring results every 60 seconds
3. **Mesh Network**: All nodes registered with each other
4. **Consensus**: Reputation scores updating in real-time
5. **Dashboard**: Showing live data from actual system
6. **Malicious Detection**: node_d reputation decreases after setup_network.py

---

## 📞 Support

For issues or questions:
1. Check all terminals for error messages
2. Verify all components are running
3. Ensure ports 8545, 8005-8008, 8501 are available
4. Review logs in each terminal

---

## 🎉 You're Ready!

Once all steps are complete, your decentralized website monitoring system is fully operational with:
- ✅ Blockchain reputation system
- ✅ 4 monitoring nodes in mesh network
- ✅ ML-based consensus engine
- ✅ Malicious node detection
- ✅ Real-time dashboard visualization

**Dashboard URL:** http://localhost:8501
