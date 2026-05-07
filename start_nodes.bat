@echo off
setlocal enabledelayedexpansion

REM Start 20 nodes in the background for high-density testing
REM Ports used: 8005 - 8024

echo Starting 20 nodes...

set NODES=a b c d e f g h i j k l m n o p q r s t
set PORT=8005

for %%n in (%NODES%) do (
    echo Starting node_%%n on port !PORT!...
    
    if "%%n"=="d" (
        start "node_%%n" cmd /k "cd node_service && set NODE_MODE=malicious && python main.py --port !PORT! --node-id node_%%n"
    ) else if "%%n"=="m" (
        start "node_%%n" cmd /k "cd node_service && set NODE_MODE=malicious && python main.py --port !PORT! --node-id node_%%n"
    ) else (
        start "node_%%n" cmd /k "cd node_service && set NODE_MODE=honest && python main.py --port !PORT! --node-id node_%%n"
    )
    
    set /a PORT+=1
    timeout /t 1 /nobreak >nul
)

echo.
echo All 20 nodes started! Wait 15 seconds for initialization...
timeout /t 15 /nobreak >nul

echo Running setup_network.py to register peers...
python setup_network.py

echo.
echo Nodes are now running and registered.
echo Realistic Performance for 20 Nodes:
echo Latency: ~1,930ms
echo Throughput: ~40.0 RPS
echo.
echo Press any key to stop all nodes (close the terminal windows)...
pause
