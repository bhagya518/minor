@echo off
setlocal enabledelayedexpansion

REM Start 8 nodes in the background for high-density testing and save logs to files
REM Ports used: 8005 - 8012

echo Starting 8 nodes with file logging enabled...

if not exist "node_service\logs" mkdir "node_service\logs"

set NODES=a b c d e f g h
set PORT=8005

for %%n in (%NODES%) do (
    echo Starting node_%%n on port !PORT!...
    
    if "%%n"=="d" (
        start "node_%%n" cmd /k "cd node_service && set NODE_MODE=malicious && python main.py --port !PORT! --node-id node_%%n > logs\node_%%n.log 2>&1"
    ) else (
        start "node_%%n" cmd /k "cd node_service && set NODE_MODE=honest && python main.py --port !PORT! --node-id node_%%n > logs\node_%%n.log 2>&1"
    )
    
    set /a PORT+=1
    timeout /t 1 /nobreak >nul
)

echo.
echo All 8 nodes started! Wait 15 seconds for initialization...
timeout /t 15 /nobreak >nul

echo Running setup_network.py to register peers...
python setup_network.py

echo.
echo Nodes are now running and registered.
echo Logs are being saved to node_service\logs\ folder.
echo Press any key to stop all nodes (close the terminal windows)...
pause
