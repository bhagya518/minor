@echo off
setlocal enabledelayedexpansion

rem Start 8 nodes for testing
rem Ports used: 8005 - 8012

echo Starting 8 nodes...

set NODES=a b c d e f g h
set PORT=8005

for %%n in (%NODES%) do (
    echo Starting node_%%n on port !PORT!...
    if "%%n"=="d" (
        start "node_%%n" cmd /k "cd node_service && set NODE_MODE=malicious && python main.py --port !PORT! --node-id node_%%n"
    ) else (
        start "node_%%n" cmd /k "cd node_service && set NODE_MODE=honest && python main.py --port !PORT! --node-id node_%%n"
    )
    set /a PORT+=1
    timeout /t 1 /nobreak >nul
)

echo.
echo All 8 nodes started! Wait 25 seconds for initialization...
timeout /t 25 /nobreak >nul

echo Running setup_network.py to register peers...
python setup_network.py

echo.
echo Nodes are now running and registered.
echo Press any key to stop all nodes (close the terminal windows)...
pause
