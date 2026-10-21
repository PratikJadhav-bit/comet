@echo off
REM Personal AI Agent Launcher
REM Usage: launch.bat [command]

set SCRIPT_DIR=%~dp0
cd /d "%SCRIPT_DIR%"

if not exist ".venv" (
    echo Creating virtual environment...
    python -m venv .venv
)

call .venv\Scripts\activate.bat

if "%1"=="" (
    echo Starting Personal AI Agent...
    python -m app.main
) else if "%1"=="test" (
    echo Running tests...
    python scripts/run_tests.py
) else if "%1"=="install" (
    echo Installing dependencies...
    pip install -r requirements.txt
    playwright install chromium
) else if "%1"=="init" (
    echo Initializing database...
    python -c "import asyncio; from app.storage.database import init_db; asyncio.run(init_db()); print('Database initialized')"
) else (
    echo Unknown command: %1
    echo Usage: launch.bat [test|install|init]
    exit /b 1
)