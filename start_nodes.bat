@echo off
REM Start all 4 nodes in the background
REM Run this from the project root directory

echo Starting node_a on port 8005...
start "node_a" cmd /k "cd node_service && python main.py --port 8005 --node-id node_a"

timeout /t 2 /nobreak >nul

echo Starting node_b on port 8006...
start "node_b" cmd /k "cd node_service && python main.py --port 8006 --node-id node_b"

timeout /t 2 /nobreak >nul

echo Starting node_c on port 8007...
start "node_c" cmd /k "cd node_service && python main.py --port 8007 --node-id node_c"

timeout /t 2 /nobreak >nul

echo Starting node_d (malicious) on port 8008...
set NODE_MODE=malicious
start "node_d" cmd /k "cd node_service && set NODE_MODE=malicious && python main.py --port 8008 --node-id node_d"

timeout /t 2 /nobreak >nul

echo Starting node_e on port 8009...
start "node_e" cmd /k "cd node_service && python main.py --port 8009 --node-id node_e"

timeout /t 2 /nobreak >nul

echo Starting node_f on port 8010...
start "node_f" cmd /k "cd node_service && python main.py --port 8010 --node-id node_f"

timeout /t 2 /nobreak >nul

echo Starting node_g on port 8011...
start "node_g" cmd /k "cd node_service && python main.py --port 8011 --node-id node_g"

timeout /t 2 /nobreak >nul

echo Starting node_h on port 8012...
start "node_h" cmd /k "cd node_service && python main.py --port 8012 --node-id node_h"

echo.
echo All nodes started! Wait 10 seconds for initialization...
timeout /t 10 /nobreak >nul

echo Running setup_network.py to register peers...
python setup_network.py

echo.
echo Nodes are now running and registered.
echo Press any key to stop all nodes (close the terminal windows)...
pause
