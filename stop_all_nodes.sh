#!/bin/bash
# stop_all_nodes.sh — Kill all node processes cleanly
PID_FILE="$(cd "$(dirname "$0")" && pwd)/node_pids.txt"

if [ ! -f "$PID_FILE" ]; then
    echo "No PID file found. Trying pkill..."
    pkill -f "main.py --port" || true
    exit 0
fi

echo "Stopping all node processes..."
while read -r pid; do
    if kill -0 "$pid" 2>/dev/null; then
        kill "$pid" 2>/dev/null
    fi
done < "$PID_FILE"

# Also kill any stragglers
pkill -f "main.py --port" 2>/dev/null || true
pkill -f "hardhat node" 2>/dev/null || true

rm -f "$PID_FILE"
echo "All nodes stopped."
