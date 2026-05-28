#!/bin/bash
echo "Starting Maya AI..."

if [ ! -d "backend/.venv" ]; then
    echo "Creating virtual environment..."
    cd backend
    python3 -m venv .venv
    source .venv/bin/activate
    echo "Installing dependencies..."
    pip install -r requirements.txt
    python database/migrations.py
    cd ..
fi

echo "Starting Backend API..."
cd backend && source .venv/bin/activate && uvicorn api.main:app --host 127.0.0.1 --port 8000 --reload &

echo "Starting Frontend..."
cd frontend && npm install && npm run dev &

echo "Maya AI is starting up! Press CTRL+C to stop all."
wait
