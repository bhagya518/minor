# Proof-of-Reputation (PoR) System — Execution Guide

Follow these steps in order to start the entire decentralized monitoring system.

## 1. Setup & Installation
Ensure you have all dependencies installed for both the blockchain and node services.

```bash
# Install Blockchain dependencies
npm install

# Install Node Service dependencies
pip install -r node_service/requirements.txt

# Install Dashboard dependencies
pip install -r dashboard/requirements.txt
```

---

## 2. Start the Blockchain Network
In a new terminal, start the local Ethereum network:

```bash
npx hardhat node
```
*Leave this terminal running.*

---

## 3. Deploy Smart Contracts
In another terminal, deploy the PoR contract to the local network:

```bash
npx hardhat run scripts/deploy.js --network localhost
```
*Note: This will automatically update the `contract_info.json` and ABI files used by the nodes.*

---

## 4. Start the Monitoring Node Cluster (8 Nodes)
Start the 8-node cluster (7 honest, 1 malicious). This script handles port assignments (8005-8012) and peer registration automatically.

```bash
python start_8_nodes.py
```
*Individual node logs will be saved in the `logs/` directory.*

---

## 5. Start the Live Dashboard
Launch the Streamlit dashboard to visualize the network, ML features, and blockchain transactions.

```bash
streamlit run dashboard/src/app.py
```
*Access via [http://localhost:8501](http://localhost:8501). Use any string as the API key to login.*

---

## 6. (Optional) Run Attack Simulation
Trigger an automated attack to see the ML Consensus Engine detect and slash malicious behavior in real-time.

```bash
python attack_simulation.py
```

---

## System Architecture Summary
- **Blockchain:** Hardhat (Localhost:8545)
- **Nodes:** 8 instances running on ports 8005-8012
- **P2P Ports:** 9005-9012
- **Dashboard:** Streamlit (Localhost:8501)
- **ML Engine:** Random Forest + Isolation Forest (Hybrid Consensus)
