# Quick Start Guide - 5 Minutes to Running System

This is the **fastest** way to get the system running. For detailed instructions, see `SETUP_AND_RUN_GUIDE.md`.

---

## ⚡ Prerequisites (2 minutes)

Install these if you haven't already:
- Python 3.8+ → https://www.python.org/downloads/
- Node.js 16+ → https://nodejs.org/

---

## 🚀 Setup (3 minutes)

Open Command Prompt and run:

```cmd
cd c:\Users\bhagy\Downloads\minor-project-main

REM 1. Create Python virtual environment
python -m venv venv
venv\Scripts\activate

REM 2. Install Python dependencies (takes ~2 minutes)
cd node_service
pip install -r requirements.txt
cd ..

REM 3. Install blockchain dependencies (takes ~1 minute)
cd blockchain
npm install
cd ..

REM 4. Create .env file
copy .env.example .env
```

Edit `.env` and set:
```env
CONTRACT_ADDRESS=
ETHEREUM_RPC_URL=http://127.0.0.1:8545
```

✅ **Setup Complete!**

---

## 🎯 Run System (4 Terminals)

### Terminal 1: Blockchain

```cmd
cd c:\Users\bhagy\Downloads\minor-project-main\blockchain
npm run node
```

**Wait for**: `Started HTTP and WebSocket JSON-RPC server at http://127.0.0.1:8545/`

---

### Terminal 2: Deploy Contract

**New terminal**:

```cmd
cd c:\Users\bhagy\Downloads\minor-project-main\blockchain
npm run compile
npm run deploy:local
```

**Copy the contract address** (looks like `0x5FbDB2315678...`) and paste it in `.env`:

```env
CONTRACT_ADDRESS=0x5FbDB2315678afecb367f032d93F642f64180aa3
```

---

### Terminal 3: Node 1

**New terminal**:

```cmd
cd c:\Users\bhagy\Downloads\minor-project-main
venv\Scripts\activate
set NODE_ID=node_1
set NODE_PORT=8000
cd node_service
python main.py
```

**Wait for**: `Uvicorn running on http://127.0.0.1:8000`

---

### Terminal 4: Node 2

**New terminal**:

```cmd
cd c:\Users\bhagy\Downloads\minor-project-main
venv\Scripts\activate
set NODE_ID=node_2
set NODE_PORT=8001
cd node_service
python main.py --peers http://127.0.0.1:8000
```

**Wait for**: `✅ Auto-registered peer node_1`

---

## ✅ Verify It's Working

Open browser or new terminal:

```cmd
REM Check Node 1 health
curl http://127.0.0.1:8000/health

REM Check peers are connected
curl http://127.0.0.1:8000/peers

REM Check monitoring stats
curl http://127.0.0.1:8000/statistics
```

**Expected**: JSON responses showing nodes are running and connected!

---

## 🎉 Success!

You should see:
- ✅ Blockchain running on port 8545
- ✅ Node 1 monitoring websites on port 8000
- ✅ Node 2 monitoring websites on port 8001
- ✅ Nodes connected to each other
- ✅ Reputations updating on blockchain

---

## 🧪 Test Malicious Node Detection

**New terminal**:

```cmd
cd c:\Users\bhagy\Downloads\minor-project-main
venv\Scripts\activate
set NODE_ID=malicious_node
set NODE_PORT=8003
set NODE_MODE=malicious
cd node_service
python main.py --peers http://127.0.0.1:8000
```

**Watch Node 1 logs** - after 4-5 minutes you'll see:
```
WARNING: Node malicious_node flagged by ML with probability 0.87
WARNING: Node malicious_node reputation dropped to 0.18 - SLASHING
INFO: Successfully slashed node malicious_node on blockchain
```

---

## 🛠️ Troubleshooting

| Problem | Solution |
|---------|----------|
| "Port already in use" | Use different port: `set NODE_PORT=8005` |
| "Blockchain connection failed" | Check Terminal 1 is running Hardhat |
| "Module not found" | Run `pip install -r node_service\requirements.txt` |
| "Contract not deployed" | Run `npm run deploy:local` in blockchain folder |
| Peers not connecting | Check `.env` has `CONTRACT_ADDRESS` set |

---

## 📊 Useful Endpoints

Once running, you can access:

| Endpoint | Description |
|----------|-------------|
| `http://127.0.0.1:8000/` | Node info |
| `http://127.0.0.1:8000/health` | Health check with public key |
| `http://127.0.0.1:8000/peers` | Connected peers list |
| `http://127.0.0.1:8000/statistics` | Monitoring statistics |
| `http://127.0.0.1:8000/trust` | Trust engine status |
| `http://127.0.0.1:8000/reports/latest` | Recent monitoring reports |
| `http://127.0.0.1:8000/blockchain/reputation/node_1` | Blockchain reputation |

---

## 📚 Next Steps

1. ✅ **Read full guide**: `SETUP_AND_RUN_GUIDE.md` - Complete documentation
2. 📖 **Understand architecture**: `ARCHITECTURE.md` - System design
3. 🐛 **Check fixes**: `BUGS_FIXED.md` - All resolved issues
4. 🧪 **Run tests**: See testing section in README.md
5. 📈 **Measure performance**: `python ML_MINOR/measure_real_tps.py`

---

## 🎯 System Architecture (Simple View)

```
┌──────────────┐
│  Blockchain  │ ← Reputation storage (Hardhat)
│   :8545      │
└──────┬───────┘
       │
   ┌───┴───┬───────┬───────┐
   │       │       │       │
┌──▼──┐ ┌──▼──┐ ┌──▼──┐ ┌──▼──┐
│Node1│ │Node2│ │Node3│ │NodeN│ ← Monitor websites
│:8000│ │:8001│ │:8002│ │:800N│   Detect malicious
└──┬──┘ └──┬──┘ └──┬──┘ └──┬──┘   Update reputation
   │       │       │       │
   └───────┴───────┴───────┘
         P2P Network
```

---

## 🔥 Pro Tips

- **Use batch script**: Run `start_node.bat` for easier node startup
- **Test system**: Run `quick_test.bat` to verify all nodes
- **Monitor logs**: Watch Terminal 1 (Node 1) for consensus and slashing events
- **Check contract**: View in Hardhat with `npx hardhat console --network localhost`
- **Reset blockchain**: Stop and restart Hardhat to reset all data

---

## 💡 What's Happening?

Every 60 seconds:
1. 📊 **Nodes monitor** websites (HTTP, SSL, DNS, response time)
2. 📡 **Broadcast reports** to all peers with cryptographic signatures
3. 🤖 **ML engine** extracts 8 latency features and detects anomalies
4. ⚖️ **Consensus** runs reputation-weighted voting
5. 📈 **Update reputation** based on PoR = 0.6×monitoring + 0.4×ML
6. ⛓️ **Write to blockchain** for permanent record
7. 🚫 **Slash malicious nodes** if reputation < 0.2

---

**That's it! Your decentralized monitoring system is now running!** 🚀

For detailed explanations, troubleshooting, and advanced features, see:
- 📖 `SETUP_AND_RUN_GUIDE.md` - Full guide with all details
- 🏗️ `ARCHITECTURE.md` - System design and data flow
- 🐛 `BUGS_FIXED.md` - All 17 bugs that were fixed
