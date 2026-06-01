@echo off
echo ===================================================
echo     WhatsApp Background Service Force Killer
echo ===================================================
echo.

echo Killing WhatsApp Service (Port 9001)...
for /f "tokens=5" %%a in ('netstat -aon ^| findstr :9001 ^| findstr LISTENING') do taskkill /F /PID %%a >nul 2>&1

echo Killing Headless Chrome (Puppeteer) processes...
powershell -Command "Get-CimInstance Win32_Process -Filter \"Name = 'chrome.exe'\" | Where-Object { $_.CommandLine -match '--headless' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }" >nul 2>&1

echo.
echo ===================================================
echo ✅ WhatsApp Service & Headless Chrome Stopped!
echo ===================================================
pause
