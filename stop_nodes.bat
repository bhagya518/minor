@echo off
REM Stop all running node processes

echo Stopping all node processes...
taskkill /F /IM python.exe /FI "WINDOWTITLE eq node_*" 2>nul
taskkill /F /IM python.exe /FI "WINDOWTITLE eq node_a*" 2>nul
taskkill /F /IM python.exe /FI "WINDOWTITLE eq node_b*" 2>nul
taskkill /F /IM python.exe /FI "WINDOWTITLE eq node_c*" 2>nul
taskkill /F /IM python.exe /FI "WINDOWTITLE eq node_d*" 2>nul
taskkill /F /IM python.exe /FI "WINDOWTITLE eq node_e*" 2>nul
taskkill /F /IM python.exe /FI "WINDOWTITLE eq node_f*" 2>nul
taskkill /F /IM python.exe /FI "WINDOWTITLE eq node_g*" 2>nul
taskkill /F /IM python.exe /FI "WINDOWTITLE eq node_h*" 2>nul

echo.
echo All node processes stopped.
echo You can also close the terminal windows manually.
