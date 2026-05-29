@echo off
setlocal enabledelayedexpansion

rem ==== HARDHAT ACCOUNT MAPPING ====
rem Replace these keys with the ones from your Hardhat node if different
set "ACCOUNT_A=0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80"
set "ACCOUNT_B=0x59c6995e998f97a5a0044966f0945389dc9e86dae88c7a8412f4603b6b78690d"
set "ACCOUNT_C=0x5de4111afa1a4b94908f83103eb1f1706365c2e68ca8203584777aa33827d5d8"
set "ACCOUNT_D=0x7c852118294e51e653712a81e05800f419141751be58f605c371e15141b007a6"
set "ACCOUNT_E=0x47e179ec197488593b187f80a00eb0da91f1b9d0b13f8733639f19c30a34926a"
set "ACCOUNT_F=0x8b3a350cf5c34c9194ca85829a2df0ec3153be0318b5e2d3348e872092edffba"
set "ACCOUNT_G=0x92db14e403b83dfe3df233f83dfa3a0d7096f21ca9b0d6d6b8d88b2b4ec1564e"
set "ACCOUNT_H=0x4bbbf85ce3377467afe5d46f804f221813b2bb87f24d81f60f1fcdbf7cbf4356"

rem Start 8 nodes for testing
rem Ports used: 8005 - 8012

echo Starting 8 nodes...

set NODES=a b c d e f g h
set PORT=8005

for %%n in (%NODES%) do (
    echo Starting node_%%n on port !PORT!...
    if "%%n"=="a" set "PRIVATE_KEY=%ACCOUNT_A%"
    if "%%n"=="b" set "PRIVATE_KEY=%ACCOUNT_B%"
    if "%%n"=="c" set "PRIVATE_KEY=%ACCOUNT_C%"
    if "%%n"=="d" set "PRIVATE_KEY=%ACCOUNT_D%"
    if "%%n"=="e" set "PRIVATE_KEY=%ACCOUNT_E%"
    if "%%n"=="f" set "PRIVATE_KEY=%ACCOUNT_F%"
    if "%%n"=="g" set "PRIVATE_KEY=%ACCOUNT_G%"
    if "%%n"=="h" set "PRIVATE_KEY=%ACCOUNT_H%"
    if "%%n"=="d" (
        start "node_%%n" cmd /k "cd node_service && set NODE_MODE=malicious && set PRIVATE_KEY=!PRIVATE_KEY! && python main.py --port !PORT! --node-id node_%%n"
    ) else (
        start "node_%%n" cmd /k "cd node_service && set NODE_MODE=honest && set PRIVATE_KEY=!PRIVATE_KEY! && python main.py --port !PORT! --node-id node_%%n"
    )
    set /a PORT+=1
    timeout /t 1 /nobreak >nul
)

echo.
echo All 8 nodes started! Wait 10 seconds for initialization...
timeout /t 10 /nobreak >nul

echo Running setup_network.py to register peers...
python setup_network.py

echo.
echo Nodes are now running and registered.
echo Press any key to stop all nodes (close the terminal windows)...
pause