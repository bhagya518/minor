@echo off
setlocal enabledelayedexpansion

REM ============================================================
REM START COMPLETE PoR NETWORK
REM Starts:
REM  - 4 monitoring nodes
REM  - setup_network.py
REM ============================================================

title Proof of Reputation Network Launcher

echo.
echo ============================================
echo   STARTING PROOF OF REPUTATION NETWORK
echo ============================================
echo.

REM ------------------------------------------------------------
REM Create logs directory
REM ------------------------------------------------------------

if not exist logs mkdir logs

REM ------------------------------------------------------------
REM Start Node A
REM ------------------------------------------------------------

echo Starting node_a on port 8005...

start "node_a" cmd /k ^
"cd /d %~dp0node_service && ^
set NODE_MODE=honest && ^
python main.py --port 8005 --node-id node_a ^
> ..\logs\node_a.log 2>&1"

timeout /t 2 /nobreak >nul

REM ------------------------------------------------------------
REM Start Node B
REM ------------------------------------------------------------

echo Starting node_b on port 8006...

start "node_b" cmd /k ^
"cd /d %~dp0node_service && ^
set NODE_MODE=honest && ^
python main.py --port 8006 --node-id node_b ^
> ..\logs\node_b.log 2>&1"

timeout /t 2 /nobreak >nul

REM ------------------------------------------------------------
REM Start Node C
REM ------------------------------------------------------------

echo Starting node_c on port 8007...

start "node_c" cmd /k ^
"cd /d %~dp0node_service && ^
set NODE_MODE=honest && ^
python main.py --port 8007 --node-id node_c ^
> ..\logs\node_c.log 2>&1"

timeout /t 2 /nobreak >nul

REM ------------------------------------------------------------
REM Start Node D (Malicious)
REM ------------------------------------------------------------

echo Starting node_d on port 8008...

start "node_d" cmd /k ^
"cd /d %~dp0node_service && ^
set NODE_MODE=malicious && ^
python main.py --port 8008 --node-id node_d ^
> ..\logs\node_d.log 2>&1"

timeout /t 2 /nobreak >nul

echo.
echo ============================================
echo All 4 nodes started successfully!
echo ============================================
echo.

REM ------------------------------------------------------------
REM Wait for initialization
REM ------------------------------------------------------------

echo Waiting 30 seconds for node initialization...
timeout /t 30 /nobreak

REM ------------------------------------------------------------
REM Run setup_network.py
REM ------------------------------------------------------------

echo.
echo Running setup_network.py...
echo.

python setup_network.py

echo.
echo ============================================
echo NETWORK SETUP COMPLETE
echo ============================================
echo.

echo Dashboard command:
echo cd dashboard\src
echo streamlit run app.py

echo.
pause