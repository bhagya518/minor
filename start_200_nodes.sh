#!/bin/bash
# ============================================================
# start_200_nodes.sh
# Launches 200 real node processes on a Linux server
# Usage: bash start_200_nodes.sh
# ============================================================

set -e

TOTAL_NODES=200
BASE_PORT=8005
PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
LOG_DIR="$PROJECT_DIR/node_logs"
PID_FILE="$PROJECT_DIR/node_pids.txt"

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${GREEN}=== PROOF OF REPUTATION: 200-NODE DEPLOYMENT ===${NC}"
echo "Server: $(hostname)"
echo "CPUs: $(nproc)"
echo "RAM: $(free -h | awk '/Mem:/ {print $2}')"
echo ""

# ── Step 0: Check system limits ──────────────────────────────
echo -e "${YELLOW}[STEP 0] Checking system limits...${NC}"
OPEN_FILES=$(ulimit -n)
if [ "$OPEN_FILES" -lt 100000 ]; then
    echo "Increasing open file limit from $OPEN_FILES to 200000..."
    ulimit -n 200000 2>/dev/null || echo "WARNING: Could not increase ulimit. Run: ulimit -n 200000"
fi
echo "  Open files limit: $(ulimit -n)"
echo "  Max processes: $(ulimit -u)"

# ── Step 1: Start Hardhat blockchain ─────────────────────────
echo -e "\n${YELLOW}[STEP 1] Starting Hardhat blockchain...${NC}"
cd "$PROJECT_DIR/blockchain"
npx hardhat node > "$PROJECT_DIR/hardhat.log" 2>&1 &
HARDHAT_PID=$!
echo "$HARDHAT_PID" > "$PID_FILE"
echo "  Hardhat PID: $HARDHAT_PID (port 8545)"
sleep 5

# Verify hardhat is running
if curl -s http://localhost:8545 > /dev/null 2>&1; then
    echo -e "  ${GREEN}✅ Hardhat is LIVE${NC}"
else
    echo -e "  ${RED}❌ Hardhat failed to start. Check hardhat.log${NC}"
    exit 1
fi

# Deploy contract if needed
if [ -f "$PROJECT_DIR/blockchain/scripts/deploy.js" ]; then
    echo "  Deploying smart contract..."
    npx hardhat run scripts/deploy.js --network localhost >> "$PROJECT_DIR/hardhat.log" 2>&1 || true
    echo -e "  ${GREEN}✅ Contract deployed${NC}"
fi

cd "$PROJECT_DIR"

# ── Step 2: Create log directory ─────────────────────────────
echo -e "\n${YELLOW}[STEP 2] Creating log directory...${NC}"
mkdir -p "$LOG_DIR"
echo "  Logs will be in: $LOG_DIR"

# ── Step 3: Launch 200 nodes ─────────────────────────────────
echo -e "\n${YELLOW}[STEP 3] Launching $TOTAL_NODES nodes...${NC}"

# Define malicious nodes (nodes 4, 13, 42, 77, 128, 175 — scattered across shards)
MALICIOUS_NODES=(4 13 42 77 128 175)

is_malicious() {
    local node_num=$1
    for m in "${MALICIOUS_NODES[@]}"; do
        if [ "$node_num" -eq "$m" ]; then
            return 0
        fi
    done
    return 1
}

LAUNCHED=0
FAILED=0

for i in $(seq 0 $((TOTAL_NODES - 1))); do
    PORT=$((BASE_PORT + i))
    NODE_ID="node_$i"

    # Set node mode
    if is_malicious $i; then
        NODE_MODE="malicious"
        MODE_LABEL="MAL"
    else
        NODE_MODE="honest"
        MODE_LABEL="HON"
    fi

    # Start the node process
    NODE_ID="$NODE_ID" NODE_MODE="$NODE_MODE" uvicorn node_service.main:app \
        --host 0.0.0.0 --port $PORT \
        > "$LOG_DIR/${NODE_ID}.log" 2>&1 &


    NODE_PID=$!
    echo "$NODE_PID" >> "$PID_FILE"

    LAUNCHED=$((LAUNCHED + 1))

    # Print progress every 10 nodes
    if [ $((LAUNCHED % 10)) -eq 0 ]; then
        echo -e "  Launched ${GREEN}$LAUNCHED${NC}/$TOTAL_NODES nodes... (last: $NODE_ID [$MODE_LABEL] port $PORT)"
    fi

    # Small delay to prevent port conflicts (50ms between launches)
    sleep 0.05
done

echo -e "\n  ${GREEN}✅ $LAUNCHED nodes launched successfully${NC}"
if [ $FAILED -gt 0 ]; then
    echo -e "  ${RED}❌ $FAILED nodes failed to launch${NC}"
fi

# ── Step 4: Wait for initialization ──────────────────────────
echo -e "\n${YELLOW}[STEP 4] Waiting 30 seconds for nodes to initialize...${NC}"
sleep 30

# ── Step 5: Verify nodes are online ──────────────────────────
echo -e "\n${YELLOW}[STEP 5] Verifying node health...${NC}"
ONLINE=0
OFFLINE=0

for i in $(seq 0 $((TOTAL_NODES - 1))); do
    PORT=$((BASE_PORT + i))
    if curl -s "http://localhost:$PORT/health" > /dev/null 2>&1; then
        ONLINE=$((ONLINE + 1))
    else
        OFFLINE=$((OFFLINE + 1))
    fi
done

echo -e "  Online: ${GREEN}$ONLINE${NC}/$TOTAL_NODES"
if [ $OFFLINE -gt 0 ]; then
    echo -e "  Offline: ${RED}$OFFLINE${NC}/$TOTAL_NODES"
fi

# ── Step 6: Run network setup (sharding + gossip) ────────────
echo -e "\n${YELLOW}[STEP 6] Running setup_network.py (sharding + gossip registration)...${NC}"
python3 "$PROJECT_DIR/setup_network.py"

# ── Step 7: Summary ──────────────────────────────────────────
echo -e "\n${GREEN}=============================================${NC}"
echo -e "${GREEN}  DEPLOYMENT COMPLETE${NC}"
echo -e "${GREEN}=============================================${NC}"
echo "  Total Nodes: $TOTAL_NODES"
echo "  Online: $ONLINE"
echo "  Malicious: ${#MALICIOUS_NODES[@]} (nodes: ${MALICIOUS_NODES[*]})"
echo "  Ports: $BASE_PORT - $((BASE_PORT + TOTAL_NODES - 1))"
echo "  Blockchain: http://localhost:8545"
echo "  PID file: $PID_FILE"
echo ""
echo "  To collect metrics:  python3 live_benchmark_200.py"
echo "  To stop all nodes:   bash stop_all_nodes.sh"
echo ""
