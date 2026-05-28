@echo off
echo Shutting down Maya AI processes...

echo Killing Backend (Port 8000)...
for /f "tokens=5" %%a in ('netstat -aon ^| findstr :8000 ^| findstr LISTENING') do taskkill /F /PID %%a >nul 2>&1

echo Killing Frontend (Port 1420)...
for /f "tokens=5" %%a in ('netstat -aon ^| findstr :1420 ^| findstr LISTENING') do taskkill /F /PID %%a >nul 2>&1

echo Killing Voice Engine (Port 9880)...
for /f "tokens=5" %%a in ('netstat -aon ^| findstr :9880 ^| findstr LISTENING') do taskkill /F /PID %%a >nul 2>&1

echo All Maya AI processes have been stopped!
pause
