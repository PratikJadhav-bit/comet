"""Scheduler Tools - Windows Task Scheduler Integration"""
import asyncio
import json
import os
import uuid
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field
from app.tools.registry import BaseTool, ToolSchema, ToolParameter, ToolResult, ToolCategory
from app.storage.repositories import ScheduledTaskRepository
from app.storage.database import get_session
from app.security.path_policy import path_policy
from app.security.risk import assess_risk
from app.security.permissions import ActionType
from app.security.prompt_injection import prompt_injection_defense


@dataclass
class ScheduledTaskConfig:
    schedule_id: str
    name: str
    description: str
    task_template: Dict[str, Any]
    trigger_type: str  # once, daily, weekly, interval
    trigger_config: Dict[str, Any]  # time, days, interval_seconds
    is_active: bool = True
    max_runs: Optional[int] = None
    run_count: int = 0
    created_at: datetime = field(default_factory=datetime.utcnow)
    last_run_at: Optional[datetime] = None
    next_run_at: Optional[datetime] = None
    permissions: Dict = field(default_factory=dict)


class SchedulerManager:
    """Manages scheduled tasks using Windows Task Scheduler"""
    
    def __init__(self):
        self.tasks: Dict[str, ScheduledTaskConfig] = {}
        self._running = False
    
    def _get_next_run(self, trigger_type: str, trigger_config: Dict) -> Optional[datetime]:
        """Calculate next run time based on trigger"""
        now = datetime.utcnow()
        
        if trigger_type == "once":
            run_time = trigger_config.get("run_at")
            if run_time:
                return datetime.fromisoformat(run_time)
            return None
        
        elif trigger_type == "daily":
            time_str = trigger_config.get("time", "09:00")
            hour, minute = map(int, time_str.split(":"))
            next_run = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
            if next_run <= now:
                next_run += timedelta(days=1)
            return next_run
        
        elif trigger_type == "weekly":
            time_str = trigger_config.get("time", "09:00")
            hour, minute = map(int, time_str.split(":"))
            days = trigger_config.get("days", [0])  # 0=Monday
            next_run = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
            while next_run.weekday() not in days or next_run <= now:
                next_run += timedelta(days=1)
            return next_run
        
        elif trigger_type == "interval":
            seconds = trigger_config.get("seconds", 3600)
            return now + timedelta(seconds=seconds)
        
        return None
    
    async def create_task(self, config: ScheduledTaskConfig) -> bool:
        """Create a Windows scheduled task"""
        try:
            import subprocess
            
            # Create task XML
            task_xml = self._generate_task_xml(config)
            
            # Save to temp file
            import tempfile
            with tempfile.NamedTemporaryFile(mode='w', suffix='.xml', delete=False) as f:
                f.write(task_xml)
                xml_path = f.name
            
            try:
                # Use schtasks to create task
                task_name = f"CometAgent_{config.schedule_id}"
                cmd = [
                    "schtasks", "/Create", "/TN", task_name,
                    "/XML", xml_path, "/F"
                ]
                
                process = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                stdout, stderr = await process.communicate()
                
                return process.returncode == 0
            finally:
                os.unlink(xml_path)
        except Exception as e:
            return False
    
    def _generate_task_xml(self, config: ScheduledTaskConfig) -> str:
        """Generate Windows Task Scheduler XML"""
        task_name = f"CometAgent_{config.schedule_id}"
        
        # Build trigger
        if config.trigger_type == "once":
            run_at = datetime.fromisoformat(config.trigger_config.get("run_at"))
            trigger = f"""
            <TimeTrigger>
                <StartBoundary>{run_at.isoformat()}Z</StartBoundary>
                <Enabled>true</Enabled>
            </TimeTrigger>
            """
        elif config.trigger_type == "daily":
            time_str = config.trigger_config.get("time", "09:00")
            trigger = f"""
            <DailyTrigger>
                <DaysInterval>1</DaysInterval>
                <StartBoundary>{datetime.now().date().isoformat()}T{time_str}:00</StartBoundary>
                <Enabled>true</Enabled>
            </DailyTrigger>
            """
        elif config.trigger_type == "weekly":
            time_str = config.trigger_config.get("time", "09:00")
            days = config.trigger_config.get("days", [0])
            days_of_week = ",".join(str(d) for d in days)
            trigger = f"""
            <WeeklyTrigger>
                <DaysOfWeek><Day>{days_of_week}</Day></DaysOfWeek>
                <WeeksInterval>1</WeeksInterval>
                <StartBoundary>{datetime.now().date().isoformat()}T{time_str}:00</StartBoundary>
                <Enabled>true</Enabled>
            </WeeklyTrigger>
            """
        elif config.trigger_type == "interval":
            seconds = config.trigger_config.get("seconds", 3600)
            trigger = f"""
            <TimeTrigger>
                <StartBoundary>{datetime.now().isoformat()}Z</StartBoundary>
                <Enabled>true</Enabled>
                <Repetition>
                    <Interval>PT{seconds}S</Interval>
                    <StopAtDurationEnd>false</StopAtDurationEnd>
                </Repetition>
            </TimeTrigger>
            """
        else:
            trigger = ""
        
        # Command to run
        python_exe = os.sys.executable
        script_path = os.path.abspath("scripts/run_scheduled_task.py")
        arguments = f'"{python_exe}" "{script_path}" "{config.schedule_id}"'
        
        xml = f"""<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.4" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo>
    <Date>{datetime.now().isoformat()}</Date>
    <Author>CometAgent</Author>
    <Description>{config.description}</Description>
  </RegistrationInfo>
  <Triggers>
    {trigger}
  </Triggers>
  <Principals>
    <Principal id="Author">
      <LogonType>InteractiveToken</LogonType>
      <RunLevel>LeastPrivilege</RunLevel>
    </Principal>
  </Principals>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <AllowHardTerminate>true</AllowHardTerminate>
    <StartWhenAvailable>true</StartWhenAvailable>
    <RunOnlyIfNetworkAvailable>false</RunOnlyIfNetworkAvailable>
    <IdleSettings>
      <StopOnIdleEnd>true</StopOnIdleEnd>
      <RestartOnIdle>false</RestartOnIdle>
    </IdleSettings>
    <AllowStartOnDemand>true</AllowStartOnDemand>
    <Enabled>true</Enabled>
    <Hidden>false</Hidden>
    <RunOnlyIfNetworkAvailable>false</RunOnlyIfNetworkAvailable>
    <IdleSettings>
      <StopOnIdleEnd>true</StopOnIdleEnd>
      <RestartOnIdle>false</RestartOnIdle>
    </IdleSettings>
  </Settings>
  <Actions Context="Author">
    <Exec>
      <Command>{python_exe}</Command>
      <Arguments>{arguments}</Arguments>
      <WorkingDirectory>{os.getcwd()}</WorkingDirectory>
    </Exec>
  </Actions>
</Task>"""
        return xml
    
    async def delete_task(self, schedule_id: str) -> bool:
        """Delete a Windows scheduled task"""
        try:
            import subprocess
            task_name = f"CometAgent_{schedule_id}"
            cmd = ["schtasks", "/Delete", "/TN", task_name, "/F"]
            
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await process.communicate()
            return process.returncode == 0
        except Exception:
            return False
    
    async def enable_task(self, schedule_id: str, enabled: bool) -> bool:
        """Enable or disable a Windows scheduled task"""
        try:
            import subprocess
            task_name = f"CometAgent_{schedule_id}"
            cmd = ["schtasks", "/Change", "/TN", task_name, "/Enable" if enabled else "/Disable"]
            
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await process.communicate()
            return process.returncode == 0
        except Exception:
            return False
    
    async def run_task_now(self, schedule_id: str) -> bool:
        """Run a scheduled task immediately"""
        try:
            import subprocess
            task_name = f"CometAgent_{schedule_id}"
            cmd = ["schtasks", "/Run", "/TN", task_name]
            
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await process.communicate()
            return process.returncode == 0
        except Exception:
            return False
    
    async def get_task_status(self, schedule_id: str) -> Dict[str, Any]:
        """Get status of a scheduled task"""
        try:
            import subprocess
            task_name = f"CometAgent_{schedule_id}"
            cmd = ["schtasks", "/Query", "/TN", task_name, "/FO", "LIST", "/V"]
            
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await process.communicate()
            
            if process.returncode != 0:
                return {"exists": False}
            
            # Parse output
            lines = stdout.decode().split('\n')
            info = {}
            for line in lines:
                if ':' in line:
                    key, value = line.split(':', 1)
                    info[key.strip()] = value.strip()
            
            return {"exists": True, "info": info}
        except Exception:
            return {"exists": False}


scheduler_manager = SchedulerManager()


class ScheduleTaskTool(BaseTool):
    def _define_schema(self) -> ToolSchema:
        return ToolSchema(
            name="scheduler.create",
            description="Create a scheduled task",
            category=ToolCategory.SYSTEM,
            parameters=[
                ToolParameter(name="name", type="string", description="Task name", required=True),
                ToolParameter(name="description", type="string", description="Task description", required=True),
                ToolParameter(name="trigger_type", type="string", description="Trigger type", required=True, enum=["once", "daily", "weekly", "interval"]),
                ToolParameter(name="trigger_config", type="object", description="Trigger configuration", required=True),
                ToolParameter(name="task_template", type="object", description="Task to execute (title, description, instruction)", required=True),
                ToolParameter(name="max_runs", type="integer", description="Maximum number of runs", required=False),
                ToolParameter(name="permissions", type="object", description="Task-specific permissions", required=False),
            ],
            risk_level="HIGH",
            requires_approval=True,
            idempotent=False,
            examples=[
                {
                    "name": "daily_backup",
                    "description": "Backup workspace daily",
                    "trigger_type": "daily",
                    "trigger_config": {"time": "02:00"},
                    "task_template": {"title": "Backup", "description": "Backup workspace", "instruction": "Copy files to backup folder"}
                }
            ]
        )
    
    async def execute(self, arguments: Dict[str, Any], context: Dict = None) -> ToolResult:
        name = arguments["name"]
        description = arguments["description"]
        trigger_type = arguments["trigger_type"]
        trigger_config = arguments["trigger_config"]
        task_template = arguments["task_template"]
        max_runs = arguments.get("max_runs")
        permissions = arguments.get("permissions", {})
        
        # Validate task template for prompt injection
        template_str = json.dumps(task_template)
        safe, threats = prompt_injection_defense.is_safe_for_model(template_str, "scheduled_task_template")
        if not safe:
            return ToolResult(success=False, error="Task template contains potential prompt injection")
        
        schedule_id = str(uuid.uuid4())[:8]
        next_run = scheduler_manager._get_next_run(trigger_type, trigger_config)
        
        config = ScheduledTaskConfig(
            schedule_id=schedule_id,
            name=name,
            description=description,
            task_template=task_template,
            trigger_type=trigger_type,
            trigger_config=trigger_config,
            max_runs=max_runs,
            next_run_at=next_run,
            permissions=permissions
        )
        
        # Save to database
        async with get_session() as session:
            repo = ScheduledTaskRepository(session)
            await repo.create(
                name=name,
                task_template=task_template,
                cron_expression=None,
                interval_seconds=trigger_config.get("seconds") if trigger_type == "interval" else None,
                timezone="UTC",
                max_runs=max_runs,
                permissions=permissions
            )
        
        # Create Windows task
        success = await scheduler_manager.create_task(config)
        
        if not success:
            return ToolResult(success=False, error="Failed to create Windows scheduled task")
        
        self.tasks[schedule_id] = config
        
        return ToolResult(success=True, data={
            "schedule_id": schedule_id,
            "name": name,
            "next_run": next_run.isoformat() if next_run else None
        })


class ListScheduledTasksTool(BaseTool):
    def _define_schema(self) -> ToolSchema:
        return ToolSchema(
            name="scheduler.list",
            description="List all scheduled tasks",
            category=ToolCategory.SYSTEM,
            parameters=[],
            risk_level="LOW",
            requires_approval=False,
            idempotent=True,
            examples=[{}]
        )
    
    async def execute(self, arguments: Dict[str, Any], context: Dict = None) -> ToolResult:
        async with get_session() as session:
            repo = ScheduledTaskRepository(session)
            tasks = await repo.get_due_tasks()  # This gets due tasks, need a list all method
        
        # Get from scheduler manager
        tasks = []
        for schedule_id, config in scheduler_manager.tasks.items():
            status = await scheduler_manager.get_task_status(config.schedule_id)
            tasks.append({
                "schedule_id": config.schedule_id,
                "name": config.name,
                "description": config.description,
                "trigger_type": config.trigger_type,
                "is_active": config.is_active,
                "run_count": config.run_count,
                "max_runs": config.max_runs,
                "next_run": config.next_run_at.isoformat() if config.next_run_at else None,
                "last_run": config.last_run_at.isoformat() if config.last_run_at else None,
                "windows_status": status
            })
        
        return ToolResult(success=True, data={"tasks": tasks, "count": len(tasks)})


class GetScheduledTaskTool(BaseTool):
    def _define_schema(self) -> ToolSchema:
        return ToolSchema(
            name="scheduler.get",
            description="Get details of a scheduled task",
            category=ToolCategory.SYSTEM,
            parameters=[
                ToolParameter(name="schedule_id", type="string", description="Schedule ID", required=True),
            ],
            risk_level="LOW",
            requires_approval=False,
            idempotent=True,
            examples=[{"schedule_id": "abc123"}]
        )
    
    async def execute(self, arguments: Dict[str, Any], context: Dict = None) -> ToolResult:
        schedule_id = arguments["schedule_id"]
        status = await scheduler_manager.get_task_status(schedule_id)
        return ToolResult(success=True, data={"schedule_id": schedule_id, "status": status})


class DeleteScheduledTaskTool(BaseTool):
    def _define_schema(self) -> ToolSchema:
        return ToolSchema(
            name="scheduler.delete",
            description="Delete a scheduled task",
            category=ToolCategory.SYSTEM,
            parameters=[
                ToolParameter(name="schedule_id", type="string", description="Schedule ID to delete", required=True),
            ],
            risk_level="HIGH",
            requires_approval=True,
            idempotent=True,
            examples=[{"schedule_id": "abc123"}]
        )
    
    async def execute(self, arguments: Dict[str, Any], context: Dict = None) -> ToolResult:
        schedule_id = arguments["schedule_id"]
        
        # Delete from Windows
        success = await scheduler_manager.delete_task(schedule_id)
        
        if not success:
            return ToolResult(success=False, error="Failed to delete Windows task")
        
        # Remove from memory
        if schedule_id in scheduler_manager.tasks:
            del scheduler_manager.tasks[schedule_id]
        
        return ToolResult(success=True, data={"deleted": True, "schedule_id": schedule_id})


class EnableScheduledTaskTool(BaseTool):
    def _define_schema(self) -> ToolSchema:
        return ToolSchema(
            name="scheduler.enable",
            description="Enable or disable a scheduled task",
            category=ToolCategory.SYSTEM,
            parameters=[
                ToolParameter(name="schedule_id", type="string", description="Schedule ID", required=True),
                ToolParameter(name="enabled", type="boolean", description="Enable or disable", required=True),
            ],
            risk_level="MODERATE",
            requires_approval=True,
            idempotent=True,
            examples=[{"schedule_id": "abc123", "enabled": False}]
        )
    
    async def execute(self, arguments: Dict[str, Any], context: Dict = None) -> ToolResult:
        schedule_id = arguments["schedule_id"]
        enabled = arguments["enabled"]
        
        success = await scheduler_manager.enable_task(schedule_id, enabled)
        
        if not success:
            return ToolResult(success=False, error="Failed to change task state")
        
        if schedule_id in scheduler_manager.tasks:
            scheduler_manager.tasks[schedule_id].is_active = enabled
        
        return ToolResult(success=True, data={"schedule_id": schedule_id, "enabled": enabled})


class RunScheduledTaskTool(BaseTool):
    def _define_schema(self) -> ToolSchema:
        return ToolSchema(
            name="scheduler.run_now",
            description="Run a scheduled task immediately",
            category=ToolCategory.SYSTEM,
            parameters=[
                ToolParameter(name="schedule_id", type="string", description="Schedule ID to run", required=True),
            ],
            risk_level="MODERATE",
            requires_approval=True,
            idempotent=False,
            examples=[{"schedule_id": "abc123"}]
        )
    
    async def execute(self, arguments: Dict[str, Any], context: Dict = None) -> ToolResult:
        schedule_id = arguments["schedule_id"]
        
        success = await scheduler_manager.run_task_now(schedule_id)
        
        if not success:
            return ToolResult(success=False, error="Failed to run task")
        
        return ToolResult(success=True, data={"schedule_id": schedule_id, "triggered": True})


def register_scheduler_tools(registry):
    registry.register(ScheduleTaskTool())
    registry.register(ListScheduledTasksTool())
    registry.register(GetScheduledTaskTool())
    registry.register(DeleteScheduledTaskTool())
    registry.register(EnableScheduledTaskTool())
    registry.register(RunScheduledTaskTool())