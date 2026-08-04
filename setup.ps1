# Maya AI Setup Script
# Installs all dependencies for backend and frontend

Write-Host "🚀 Setting up Maya AI..." -ForegroundColor Cyan
Write-Host ""

# Check Python
Write-Host "Checking Python..." -ForegroundColor Yellow
$pythonVersion = python --version 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host "❌ Python not found! Please install Python 3.10+ first." -ForegroundColor Red
    exit 1
}
Write-Host "✅ Found: $pythonVersion" -ForegroundColor Green

# Check Node.js
Write-Host "Checking Node.js..." -ForegroundColor Yellow
$nodeVersion = node --version 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host "❌ Node.js not found! Please install Node.js 18+ first." -ForegroundColor Red
    exit 1
}
Write-Host "✅ Found: Node $nodeVersion" -ForegroundColor Green
Write-Host ""

# Install root dependencies
Write-Host "📦 Installing root dependencies..." -ForegroundColor Cyan
npm install
if ($LASTEXITCODE -ne 0) {
    Write-Host "❌ Failed to install root dependencies!" -ForegroundColor Red
    exit 1
}
Write-Host "✅ Root dependencies installed" -ForegroundColor Green
Write-Host ""

# Setup backend
Write-Host "🐍 Setting up Python backend..." -ForegroundColor Cyan
Set-Location backend

# Create virtual environment if it doesn't exist
if (-not (Test-Path ".venv")) {
    Write-Host "Creating virtual environment..." -ForegroundColor Yellow
    python -m venv .venv
    if ($LASTEXITCODE -ne 0) {
        Write-Host "❌ Failed to create virtual environment!" -ForegroundColor Red
        Set-Location ..
        exit 1
    }
}

# Activate and install requirements
Write-Host "Installing Python packages..." -ForegroundColor Yellow
& ".venv\Scripts\python.exe" -m pip install --upgrade pip
& ".venv\Scripts\pip.exe" install -r requirements.txt
if ($LASTEXITCODE -ne 0) {
    Write-Host "❌ Failed to install Python packages!" -ForegroundColor Red
    Set-Location ..
    exit 1
}
Write-Host "✅ Backend setup complete" -ForegroundColor Green
Set-Location ..
Write-Host ""

# Setup frontend
Write-Host "⚛️ Setting up React frontend..." -ForegroundColor Cyan
Set-Location frontend
npm install
if ($LASTEXITCODE -ne 0) {
    Write-Host "❌ Failed to install frontend dependencies!" -ForegroundColor Red
    Set-Location ..
    exit 1
}
Write-Host "✅ Frontend setup complete" -ForegroundColor Green
Set-Location ..
Write-Host ""

# Create .env if it doesn't exist
if (-not (Test-Path ".env")) {
    Write-Host "📝 Creating .env file..." -ForegroundColor Yellow
    Copy-Item ".env.example" ".env"
    Write-Host "✅ Created .env file (please add your API keys!)" -ForegroundColor Green
} else {
    Write-Host "✅ .env file already exists" -ForegroundColor Green
}
Write-Host ""

Write-Host "✨ Setup complete! Next steps:" -ForegroundColor Green
Write-Host ""
Write-Host "1. Edit .env and add your GEMINI_API_KEY" -ForegroundColor White
Write-Host "2. Run: npm start" -ForegroundColor White
Write-Host ""
Write-Host "🎉 Maya AI is ready!" -ForegroundColor Cyan
