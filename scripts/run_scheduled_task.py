#!/usr/bin/env python3
"""Run a scheduled task by ID"""
import asyncio
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.tools.registry import tool_registry
from app.tools.files import register_file_tools
from app.tools.browser import register_browser_tools
from app.tools.desktop import register_desktop_tools
from app.tools.verification import register_verification_tools
from app.tools.terminal import register_terminal_tools
from app.tools.vscode import register_vscode_tools
from app.tools.memory import register_memory_tools
from app.agent.orchestrator import orchestrator
from app.storage.database import init_db


async def run_scheduled_task(schedule_id: str):
    """Execute a scheduled task"""
    print(f"Running scheduled task: {schedule_id}")
    
    # Initialize database
    await init_db()
    
    # Register all tools
    register_file_tools(tool_registry)
    register_browser_tools(tool_registry)
    register_desktop_tools(tool_registry)
    register_verification_tools(tool_registry)
    register_terminal_tools(tool_registry)
    register_memory_tools(tool_registry)
    
    # Get the scheduled task from database
    from app.storage.database import get_session
    from app.storage.repositories import ScheduledTaskRepository
    
    async with get_session() as session:
        repo = ScheduledTaskRepository(session)
        # We'd need a get_by_schedule_id method, for now just use a placeholder
        pass
    
    # For now, just log that we would run it
    print(f"Would execute scheduled task {schedule_id}")
    print("Note: Full implementation requires task template retrieval from database")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python run_scheduled_task.py <schedule_id>")
        sys.exit(1)
    
    schedule_id = sys.argv[1]
    asyncio.run(run_scheduled_task(schedule_id))