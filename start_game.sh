#!/bin/bash

echo "Activate Cloudflare tunnel..."


cd "$(dirname "$0")"

echo "[1/3] Activating backend server..."

./venv/bin/uvicorn main:app --host 0.0.0.0 --port 8000 > backend.log 2>&1 &
BACKEND_PID=$!

sleep 1

echo "[2/3] Establishing connection tunnel..."

cloudflared tunnel --url http://localhost:8000 > tunnel.log 2>&1 &
TUNNEL_PID=$!

echo "[3/3] Opening browser..."

xdg-open http://localhost:8000/admin
xdg-open http://localhost:8000/

echo "Server is running in background."
echo "Press Ctrl+C to stop both server and tunnel."


trap "kill $BACKEND_PID $TUNNEL_PID; exit" INT


wait