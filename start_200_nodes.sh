#!/bin/bash
# ============================================================
# start_200_nodes.sh
# Launches 200 blockchain nodes
# ============================================================

set -e

TOTAL_NODES=200
BASE_PORT=8005

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
LOG_DIR="$PROJECT_DIR/node_logs"
PID_FILE="$PROJECT_DIR/node_pids.txt"

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN} PROOF OF REPUTATION : 200 NODE NETWORK ${NC}"
echo -e "${GREEN}========================================${NC}"

echo "Server: $(hostname)"
echo "CPUs: $(nproc)"
echo "RAM: $(free -h | awk '/Mem:/ {print $2}')"
echo ""

# ============================================================
# STEP 0 : SYSTEM LIMITS
# ============================================================

echo -e "${YELLOW}[STEP 0] Checking system limits...${NC}"

CURRENT_LIMIT=$(ulimit -n)

if [ "$CURRENT_LIMIT" -lt 200000 ]; then
    echo "Increasing open file limit..."
    ulimit -n 200000 || true
fi

echo "Open file limit : $(ulimit -n)"
echo "Max processes   : $(ulimit -u)"

# ============================================================
# CLEAN PREVIOUS RUNS
# ============================================================

echo -e "\n${YELLOW}[CLEANUP] Removing old processes...${NC}"

pkill -f "uvicorn node_service.main:app" || true
pkill -f "hardhat node" || true

sleep 3

rm -f "$PID_FILE"
mkdir -p "$LOG_DIR"

# ============================================================
# STEP 1 : START HARDHAT
# ============================================================

echo -e "\n${YELLOW}[STEP 1] Starting Hardhat blockchain...${NC}"

cd "$PROJECT_DIR/blockchain"

nohup npx hardhat node \
    > "$PROJECT_DIR/hardhat.log" 2>&1 &

HARDHAT_PID=$!

echo "$HARDHAT_PID" >> "$PID_FILE"

echo "Hardhat PID : $HARDHAT_PID"

sleep 8

if curl -s http://localhost:8545 > /dev/null; then
    echo -e "${GREEN}✅ Hardhat running on port 8545${NC}"
else
    echo -e "${RED}❌ Hardhat failed${NC}"
    exit 1
fi

# ============================================================
# DEPLOY CONTRACT
# ============================================================

if [ -f "$PROJECT_DIR/blockchain/scripts/deploy.js" ]; then
    echo "Deploying contract..."

    npx hardhat run scripts/deploy.js --network localhost \
        >> "$PROJECT_DIR/hardhat.log" 2>&1 || true

    echo -e "${GREEN}✅ Smart contract deployed${NC}"
fi

cd "$PROJECT_DIR"

# ============================================================
# STEP 2 : CREATE PEER LIST
# ============================================================

echo -e "\n${YELLOW}[STEP 2] Building peer list...${NC}"

ALL_PEERS=""

for i in $(seq 0 $((TOTAL_NODES - 1))); do
    PORT=$((BASE_PORT + i))
    ALL_PEERS="$ALL_PEERS http://127.0.0.1:$PORT"
done

echo "Peer list generated."

# ============================================================
# STEP 3 : DEFINE MALICIOUS NODES
# ============================================================

MALICIOUS_NODES=(4 13 42 77 128 175)

is_malicious() {
    local NODE=$1

    for M in "${MALICIOUS_NODES[@]}"; do
        if [ "$NODE" -eq "$M" ]; then
            return 0
        fi
    done

    return 1
}

# ============================================================
# STEP 4 : LAUNCH NODES
# ============================================================

echo -e "\n${YELLOW}[STEP 4] Launching $TOTAL_NODES nodes...${NC}"

LAUNCHED=0

for i in $(seq 0 $((TOTAL_NODES - 1))); do

    PORT=$((BASE_PORT + i))
    NODE_ID="node_$i"

    if is_malicious "$i"; then
        NODE_MODE="malicious"
        MODE="MAL"
    else
        NODE_MODE="honest"
        MODE="HON"
    fi

    echo "Launching $NODE_ID [$MODE] on port $PORT"

    nohup env \
        NODE_ID="$NODE_ID" \
        NODE_MODE="$NODE_MODE" \
        PYTHONPATH="$PROJECT_DIR:$PROJECT_DIR/node_service" \
        uvicorn node_service.main:app \
        --host 0.0.0.0 \
        --port "$PORT" \
        --workers 1 \
        > "$LOG_DIR/${NODE_ID}.log" 2>&1 &

    PID=$!

    echo "$PID" >> "$PID_FILE"

    LAUNCHED=$((LAUNCHED + 1))

    if [ $((LAUNCHED % 20)) -eq 0 ]; then
        echo -e "${GREEN}$LAUNCHED/$TOTAL_NODES nodes launched${NC}"
    fi

    sleep 0.05

done

echo -e "\n${GREEN}✅ All nodes launched${NC}"

# ============================================================
# STEP 5 : WAIT FOR INITIALIZATION
# ============================================================

echo -e "\n${YELLOW}[STEP 5] Waiting for initialization...${NC}"

sleep 30

# ============================================================
# STEP 6 : HEALTH CHECK
# ============================================================

echo -e "\n${YELLOW}[STEP 6] Running health checks...${NC}"

ONLINE=0
OFFLINE=0

for i in $(seq 0 $((TOTAL_NODES - 1))); do

    PORT=$((BASE_PORT + i))

    if curl -s "http://127.0.0.1:$PORT/health" > /dev/null; then
        ONLINE=$((ONLINE + 1))
    else
        OFFLINE=$((OFFLINE + 1))
    fi

done

echo -e "Online  : ${GREEN}$ONLINE${NC}"
echo -e "Offline : ${RED}$OFFLINE${NC}"

# ============================================================
# STEP 7 : NETWORK SETUP
# ============================================================

echo -e "\n${YELLOW}[STEP 7] Running setup_network.py...${NC}"

python3 "$PROJECT_DIR/setup_network.py"

# ============================================================
# FINAL SUMMARY
# ============================================================

echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN} DEPLOYMENT COMPLETE ${NC}"
echo -e "${GREEN}========================================${NC}"

echo "Total Nodes : $TOTAL_NODES"
echo "Online      : $ONLINE"
echo "Malicious   : ${#MALICIOUS_NODES[@]}"
echo "Ports       : $BASE_PORT - $((BASE_PORT + TOTAL_NODES - 1))"

echo ""
echo "Blockchain : http://localhost:8545"
echo "Logs       : $LOG_DIR"
echo "PID File   : $PID_FILE"

echo ""
echo "Run benchmark:"
echo "python3 live_benchmark_200.py"

echo ""
echo "Stop network:"
echo "bash stop_all_nodes.sh"