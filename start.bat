@echo off
echo Starting Maya AI...

echo Checking/creating virtual environment...
if not exist "backend\.venv\" (
    echo Creating virtual environment...
    cd backend
    python -m venv .venv
    call .venv\Scripts\activate.bat
    echo Installing dependencies...
    pip install -r requirements.txt
    python database\migrations.py
    cd ..
)

echo Starting Backend API...
start cmd /k "cd backend && call .venv\Scripts\activate.bat && uvicorn api.main:app --host 127.0.0.1 --port 8000"

echo Starting Frontend...
start cmd /k "cd frontend && npm install && npm run dev"

echo Maya AI is starting up!
