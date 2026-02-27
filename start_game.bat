@echo off
chcp 65001 >nul
echo Starting Industrial Oligarchs Server and Ngrok Tunnel...

:: Change to the directory where this .bat file is located
cd /d "%~dp0"

:: Kill any existing ngrok processes in the background to prevent conflicts
echo Cleaning up old processes...
taskkill /F /IM ngrok.exe >nul 2>&1

:: 1. Start the Uvicorn backend server in a new window
echo [1/3] Starting backend server...
start "Game Server" cmd /k "uvicorn main:app --host 0.0.0.0 --port 8000"

:: Wait for 3 seconds to ensure the server starts properly
timeout /t 3 >nul

:: 2. Start the tunneling service using Ngrok
echo [2/3] Establishing external tunnel via Ngrok...
start "Ngrok Tunnel" cmd /k "ngrok http 8000"

:: 3. Automatically open the browser for the admin console and player UI
echo [3/3] Opening browser...
start http://localhost:8000/admin
start http://localhost:8000/

echo.
echo ===================================================
echo Server and Tunnel are up and running!
echo.
echo Look at the new "Ngrok Tunnel" command prompt window.
echo Find the "Forwarding" URL (looks like https://xxxx-xx-xx.ngrok-free.app).
echo Copy that URL and share it with your friends to play!
echo ===================================================
echo.
pause