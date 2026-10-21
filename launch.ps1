<# 
.SYNOPSIS
    Personal AI Agent Launcher
.DESCRIPTION
    Launches the Personal AI Agent backend server or runs maintenance commands.
.EXAMPLE
    .\launch.ps1
    .\launch.ps1 -Command test
    .\launch.ps1 -Command install
    .\launch.ps1 -Command init
#>

param(
    [ValidateSet('run', 'test', 'install', 'init')]
    [string]$Command = 'run'
)

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
Set-Location $ScriptDir

if (-not (Test-Path ".venv")) {
    Write-Host "Creating virtual environment..." -ForegroundColor Yellow
    python -m venv .venv
}

& .\.venv\Scripts\Activate.ps1

switch ($Command) {
    'run' {
        Write-Host "Starting Personal AI Agent..." -ForegroundColor Green
        python -m app.main
    }
    'test' {
        Write-Host "Running tests..." -ForegroundColor Green
        python scripts/run_tests.py
    }
    'install' {
        Write-Host "Installing dependencies..." -ForegroundColor Yellow
        pip install -r requirements.txt
        playwright install chromium
    }
    'init' {
        Write-Host "Initializing database..." -ForegroundColor Yellow
        python -c "import asyncio; from app.storage.database import init_db; asyncio.run(init_db()); print('Database initialized')"
    }
}