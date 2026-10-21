from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from app.agent.orchestrator import orchestrator, OrchestratorEvent
from app.storage.database import get_session
from app.storage.repositories import TaskRepository, AuditRepository
from app.storage.models import TaskStatus
from app.tools.registry import tool_registry
from app.models.base import model_registry
from app.config import settings
from app.security.approvals import approval_center
import asyncio


router = APIRouter()


class TaskCreate(BaseModel):
    title: str
    description: str = ""
    parent_task_id: Optional[int] = None
    metadata: Dict[str, Any] = {}


class TaskPlan(BaseModel):
    task_id: int
    instruction: str


class TaskExecute(BaseModel):
    task_id: int


class ApprovalResponse(BaseModel):
    approval_id: str
    approved: bool
    reason: str = ""


class TaskControl(BaseModel):
    task_id: int


@router.post("/tasks")
async def create_task(task: TaskCreate):
    result = await orchestrator.create_task(task.title, task.description, task.parent_task_id, task.metadata)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@router.get("/tasks")
async def list_tasks(status: Optional[str] = None, limit: int = 50, offset: int = 0):
    async with get_session() as session:
        task_repo = TaskRepository(session)
        task_status = TaskStatus(status) if status else None
        tasks = await task_repo.list_tasks(task_status, limit, offset)
        return [
            {
                "id": t.id,
                "task_id": t.task_id,
                "title": t.title,
                "status": t.status.value,
                "created_at": t.created_at.isoformat() if t.created_at else None,
                "completed_at": t.completed_at.isoformat() if t.completed_at else None,
            }
            for t in tasks
        ]


@router.get("/tasks/{task_id}")
async def get_task(task_id: int):
    async with get_session() as session:
        task_repo = TaskRepository(session)
        task = await task_repo.get_by_id(task_id)
        if not task:
            raise HTTPException(status_code=404, detail="Task not found")
        
        tool_calls = [
            {
                "id": tc.id,
                "call_id": tc.call_id,
                "tool_name": tc.tool_name,
                "status": tc.status.value,
                "arguments": tc.arguments,
                "result": tc.result,
                "error": tc.error_message,
            }
            for tc in task.tool_calls
        ]
        
        return {
            "id": task.id,
            "task_id": task.task_id,
            "title": task.title,
            "description": task.description,
            "status": task.status.value,
            "plan": task.plan,
            "result": task.result,
            "tool_calls": tool_calls,
            "created_at": task.created_at.isoformat() if task.created_at else None,
            "started_at": task.started_at.isoformat() if task.started_at else None,
            "completed_at": task.completed_at.isoformat() if task.completed_at else None,
        }


@router.post("/tasks/{task_id}/plan")
async def plan_task(task_id: int, plan: TaskPlan):
    result = await orchestrator.plan_task(task_id, plan.instruction)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@router.post("/tasks/{task_id}/execute")
async def execute_task(task_id: int, background_tasks: BackgroundTasks):
    status = await orchestrator.get_task_status(task_id)
    if "error" in status:
        raise HTTPException(status_code=400, detail=status["error"])
    
    if status["status"] in ("RUNNING", "WAITING_FOR_APPROVAL"):
        raise HTTPException(status_code=400, detail="Task already running")
    
    background_tasks.add_task(orchestrator.execute_task, task_id)
    return {"status": "started", "task_id": task_id}


@router.post("/tasks/{task_id}/pause")
async def pause_task(task_id: int):
    if orchestrator.pause_task(task_id):
        return {"status": "paused", "task_id": task_id}
    raise HTTPException(status_code=400, detail="Task not running")


@router.post("/tasks/{task_id}/resume")
async def resume_task(task_id: int):
    orchestrator.resume_task(task_id)
    return {"status": "resumed", "task_id": task_id}


@router.post("/tasks/{task_id}/cancel")
async def cancel_task(task_id: int):
    if orchestrator.cancel_task(task_id):
        return {"status": "cancelled", "task_id": task_id}
    raise HTTPException(status_code=400, detail="Task not running")


@router.get("/tasks/{task_id}/status")
async def task_status(task_id: int):
    return await orchestrator.get_task_status(task_id)


@router.post("/approvals/respond")
async def respond_approval(response: ApprovalResponse):
    success = approval_center.respond(response.approval_id, response.approved, response.reason)
    if not success:
        raise HTTPException(status_code=404, detail="Approval not found")
    return {"status": "responded", "approval_id": response.approval_id}


@router.get("/approvals/pending")
async def pending_approvals():
    return [{"approval_id": a.approval_id, "task_id": a.task_id, "title": a.title, "description": a.description, "risk_level": a.risk_level.value, "details": a.details, "expires_at": a.expires_at.isoformat() if a.expires_at else None} for a in approval_center.get_pending()]


@router.get("/tools")
async def list_tools(category: Optional[str] = None):
    from app.tools.registry import ToolCategory
    cat = ToolCategory(category) if category else None
    tools = tool_registry.list_tools(cat)
    return [{"name": t.name, "description": t.description, "category": t.category.value, "parameters": [{"name": p.name, "type": p.type, "description": p.description, "required": p.required} for p in t.parameters], "risk_level": t.risk_level, "requires_approval": t.requires_approval} for t in tools]


@router.get("/tools/{tool_name}/schema")
async def tool_schema(tool_name: str):
    tool = tool_registry.get(tool_name)
    if not tool:
        raise HTTPException(status_code=404, detail="Tool not found")
    schema = tool.get_schema()
    return {"name": schema.name, "description": schema.description, "parameters": [{"name": p.name, "type": p.type, "description": p.description, "required": p.required} for p in schema.parameters]}


@router.post("/tools/{tool_name}/execute")
async def execute_tool(tool_name: str, arguments: Dict[str, Any]):
    tool = tool_registry.get(tool_name)
    if not tool:
        raise HTTPException(status_code=404, detail="Tool not found")
    result = await tool_registry.execute(tool_name, arguments)
    if not result.success:
        raise HTTPException(status_code=400, detail=result.error)
    return result.data


@router.get("/config")
async def get_config():
    return {
        "app_name": settings.app_name,
        "app_version": settings.app_version,
        "model_provider": settings.model_provider,
        "model_name": settings.model_name,
        "browser_headless": settings.browser_headless,
        "allowed_directories": settings.allowed_directories,
        "max_file_size_mb": settings.max_file_size_mb,
        "max_task_duration_seconds": settings.max_task_duration_seconds,
        "max_tool_calls_per_task": settings.max_tool_calls_per_task,
    }


@router.get("/health")
async def health_check():
    provider = model_registry.get()
    model_healthy = False
    if provider:
        try:
            model_healthy = await provider.health_check()
        except Exception:
            pass
    
    return {
        "status": "healthy",
        "model_connected": model_healthy,
        "version": settings.app_version
    }