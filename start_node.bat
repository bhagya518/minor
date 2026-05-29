@echo off
setlocal enabledelayedexpansion

rem ------------------------------------------------------------
rem Single‑node launch script – creates logs folder and starts one node
rem ------------------------------------------------------------

rem ---- 1️⃣  Create logs folder (if missing)
if not exist "%~dp0logs" mkdir "%~dp0logs"

rem ---- 2️⃣  Define node ID, port and mode
set "NODE_ID=node_a"
set "PORT=8005"
rem Change NODE_MODE to "malicious" if you want to test a bad node
set "NODE_MODE=honest"

rem ---- 3️⃣  Optional: build a peers list (empty for a single node)
set "ALL_PEERS="

rem ---- 4️⃣  Launch the node – output is written to a dedicated log file
echo Starting %NODE_ID% on port %PORT% ...
start "%NODE_ID%" cmd /c "cd /d \"%~dp0node_service\" ^&^& set NODE_MODE=%NODE_MODE% ^&^& python main.py --port %PORT% --node-id %NODE_ID% --peers %ALL_PEERS% ^> "%~dp0logs\%NODE_ID%.log" 2^>^&1"

rem ---- 5️⃣  Give the node a moment to initialise
timeout /t 5 /nobreak >nul

rem ---- 6️⃣  Run the network registration script (setup_network.py)
rem This will register the single node with the blockchain / discovery service
python setup_network.py

rem ---- 7️⃣  Finished – keep the console open so you can read any messages
echo.
echo Node %NODE_ID% has been launched and registration attempted.
echo Press any key to close this window and stop the node.
pause
