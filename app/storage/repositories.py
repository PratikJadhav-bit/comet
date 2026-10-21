from sqlalchemy import select, update, delete, func, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta
import uuid

from app.storage.models import (
    Task, ToolCall, Approval, MemoryItem, ScheduledTask, AuditLog,
    TaskStatus, RiskLevel, ApprovalStatus, ToolCallStatus
)


class TaskRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, title: str, description: str = None, 
                     parent_task_id: int = None, risk_level: RiskLevel = RiskLevel.LOW,
                     metadata: Dict = None) -> Task:
        task = Task(
            task_id=str(uuid.uuid4())[:8],
            title=title,
            description=description,
            parent_task_id=parent_task_id,
            risk_level=risk_level,
            metadata=metadata or {},
            status=TaskStatus.CREATED
        )
        self.session.add(task)
        await self.session.flush()
        return task

    async def get_by_id(self, task_id: int) -> Optional[Task]:
        result = await self.session.execute(
            select(Task).where(Task.id == task_id).options(selectinload(Task.tool_calls))
        )
        return result.scalar_one_or_none()

    async def get_by_task_id(self, task_id: str) -> Optional[Task]:
        result = await self.session.execute(
            select(Task).where(Task.task_id == task_id).options(selectinload(Task.tool_calls))
        )
        return result.scalar_one_or_none()

    async def update_status(self, task_id: int, status: TaskStatus, 
                            error_message: str = None, result: Dict = None) -> Optional[Task]:
        task = await self.get_by_id(task_id)
        if not task:
            return None
        task.status = status
        if error_message:
            task.error_message = error_message
        if result:
            task.result = result
        if status in (TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED):
            task.completed_at = datetime.utcnow()
        elif status == TaskStatus.RUNNING and not task.started_at:
            task.started_at = datetime.utcnow()
        await self.session.flush()
        return task

    async def update_plan(self, task_id: int, plan: Dict) -> Optional[Task]:
        task = await self.get_by_id(task_id)
        if not task:
            return None
        task.plan = plan
        task.status = TaskStatus.READY
        await self.session.flush()
        return task

    async def list_tasks(self, status: TaskStatus = None, limit: int = 50, 
                         offset: int = 0) -> List[Task]:
        query = select(Task).order_by(Task.created_at.desc()).limit(limit).offset(offset)
        if status:
            query = query.where(Task.status == status)
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def get_active_tasks(self) -> List[Task]:
        result = await self.session.execute(
            select(Task).where(Task.status.in_([
                TaskStatus.PLANNING, TaskStatus.READY, TaskStatus.RUNNING,
                TaskStatus.WAITING_FOR_APPROVAL, TaskStatus.VERIFYING
            ]))
        )
        return list(result.scalars().all())


class ToolCallRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, task_id: int, tool_name: str, arguments: Dict,
                     risk_level: RiskLevel = RiskLevel.LOW,
                     idempotency_key: str = None) -> ToolCall:
        call = ToolCall(
            call_id=str(uuid.uuid4())[:8],
            task_id=task_id,
            tool_name=tool_name,
            arguments=arguments,
            risk_level=risk_level,
            idempotency_key=idempotency_key
        )
        self.session.add(call)
        await self.session.flush()
        return call

    async def get_by_id(self, call_id: int) -> Optional[ToolCall]:
        result = await self.session.execute(
            select(ToolCall).where(ToolCall.id == call_id)
        )
        return result.scalar_one_or_none()

    async def get_by_call_id(self, call_id: str) -> Optional[ToolCall]:
        result = await self.session.execute(
            select(ToolCall).where(ToolCall.call_id == call_id)
        )
        return result.scalar_one_or_none()

    async def update_status(self, call_id: int, status: ToolCallStatus,
                            result: Dict = None, error_message: str = None) -> Optional[ToolCall]:
        call = await self.get_by_id(call_id)
        if not call:
            return None
        call.status = status
        if result:
            call.result = result
        if error_message:
            call.error_message = error_message
        if status == ToolCallStatus.RUNNING and not call.started_at:
            call.started_at = datetime.utcnow()
        elif status in (ToolCallStatus.COMPLETED, ToolCallStatus.FAILED, ToolCallStatus.CANCELLED):
            call.completed_at = datetime.utcnow()
        await self.session.flush()
        return call

    async def increment_retry(self, call_id: int) -> Optional[ToolCall]:
        call = await self.get_by_id(call_id)
        if not call:
            return None
        call.retry_count += 1
        call.status = ToolCallStatus.PENDING
        await self.session.flush()
        return call

    async def get_by_task(self, task_id: int) -> List[ToolCall]:
        result = await self.session.execute(
            select(ToolCall).where(ToolCall.task_id == task_id).order_by(ToolCall.created_at)
        )
        return list(result.scalars().all())

    async def check_idempotency(self, key: str) -> Optional[ToolCall]:
        if not key:
            return None
        result = await self.session.execute(
            select(ToolCall).where(ToolCall.idempotency_key == key)
        )
        return result.scalar_one_or_none()


class ApprovalRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, task_id: int, risk_level: RiskLevel, title: str,
                     description: str, details: Dict = None,
                     tool_call_id: int = None, expires_in_seconds: int = 300) -> Approval:
        approval = Approval(
            approval_id=str(uuid.uuid4())[:8],
            task_id=task_id,
            tool_call_id=tool_call_id,
            risk_level=risk_level,
            title=title,
            description=description,
            details=details or {},
            expires_at=datetime.utcnow() + timedelta(seconds=expires_in_seconds)
        )
        self.session.add(approval)
        await self.session.flush()
        return approval

    async def get_by_id(self, approval_id: int) -> Optional[Approval]:
        result = await self.session.execute(
            select(Approval).where(Approval.id == approval_id)
        )
        return result.scalar_one_or_none()

    async def get_by_approval_id(self, approval_id: str) -> Optional[Approval]:
        result = await self.session.execute(
            select(Approval).where(Approval.approval_id == approval_id)
        )
        return result.scalar_one_or_none()

    async def get_pending_for_task(self, task_id: int) -> List[Approval]:
        result = await self.session.execute(
            select(Approval).where(
                and_(Approval.task_id == task_id, Approval.status == ApprovalStatus.PENDING)
            )
        )
        return list(result.scalars().all())

    async def respond(self, approval_id: int, status: ApprovalStatus, 
                      reason: str = None) -> Optional[Approval]:
        approval = await self.get_by_id(approval_id)
        if not approval or approval.status != ApprovalStatus.PENDING:
            return None
        approval.status = status
        approval.responded_at = datetime.utcnow()
        approval.response_reason = reason
        await self.session.flush()
        return approval

    async def expire_old(self) -> int:
        result = await self.session.execute(
            update(Approval)
            .where(
                and_(
                    Approval.status == ApprovalStatus.PENDING,
                    Approval.expires_at < datetime.utcnow()
                )
            )
            .values(status=ApprovalStatus.EXPIRED, responded_at=datetime.utcnow())
        )
        return result.rowcount


class MemoryRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def set(self, key: str, value: str, category: str = None,
                  source: str = None, confidence: int = 100,
                  is_user_approved: bool = False, metadata: Dict = None,
                  expires_at: datetime = None) -> MemoryItem:
        existing = await self.get(key)
        if existing:
            existing.value = value
            existing.category = category
            existing.source = source
            existing.confidence = confidence
            existing.is_user_approved = is_user_approved
            existing.metadata = metadata or {}
            existing.expires_at = expires_at
            existing.updated_at = datetime.utcnow()
            await self.session.flush()
            return existing
        
        item = MemoryItem(
            key=key,
            value=value,
            category=category,
            source=source,
            confidence=confidence,
            is_user_approved=is_user_approved,
            metadata=metadata or {},
            expires_at=expires_at
        )
        self.session.add(item)
        await self.session.flush()
        return item

    async def get(self, key: str) -> Optional[MemoryItem]:
        result = await self.session.execute(
            select(MemoryItem).where(MemoryItem.key == key)
        )
        return result.scalar_one_or_none()

    async def get_by_category(self, category: str) -> List[MemoryItem]:
        result = await self.session.execute(
            select(MemoryItem).where(MemoryItem.category == category)
        )
        return list(result.scalars().all())

    async def list_all(self, limit: int = 100, offset: int = 0) -> List[MemoryItem]:
        result = await self.session.execute(
            select(MemoryItem).order_by(MemoryItem.updated_at.desc()).limit(limit).offset(offset)
        )
        return list(result.scalars().all())

    async def delete(self, key: str) -> bool:
        result = await self.session.execute(
            delete(MemoryItem).where(MemoryItem.key == key)
        )
        return result.rowcount > 0

    async def cleanup_expired(self) -> int:
        result = await self.session.execute(
            delete(MemoryItem).where(
                and_(MemoryItem.expires_at.isnot(None), MemoryItem.expires_at < datetime.utcnow())
            )
        )
        return result.rowcount


class ScheduledTaskRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, name: str, task_template: Dict, 
                     cron_expression: str = None, interval_seconds: int = None,
                     timezone: str = "UTC", max_runs: int = None,
                     permissions: Dict = None) -> ScheduledTask:
        task = ScheduledTask(
            schedule_id=str(uuid.uuid4())[:8],
            name=name,
            task_template=task_template,
            cron_expression=cron_expression,
            interval_seconds=interval_seconds,
            timezone=timezone,
            max_runs=max_runs,
            permissions=permissions or {}
        )
        self.session.add(task)
        await self.session.flush()
        return task

    async def get_due_tasks(self) -> List[ScheduledTask]:
        result = await self.session.execute(
            select(ScheduledTask).where(
                and_(
                    ScheduledTask.is_active == True,
                    or_(
                        ScheduledTask.next_run_at.is_(None),
                        ScheduledTask.next_run_at <= datetime.utcnow()
                    ),
                    or_(
                        ScheduledTask.max_runs.is_(None),
                        ScheduledTask.run_count < ScheduledTask.max_runs
                    )
                )
            )
        )
        return list(result.scalars().all())

    async def update_run_time(self, schedule_id: int, next_run: datetime) -> Optional[ScheduledTask]:
        task = await self.session.get(ScheduledTask, schedule_id)
        if not task:
            return None
        task.last_run_at = datetime.utcnow()
        task.next_run_at = next_run
        task.run_count += 1
        await self.session.flush()
        return task


class AuditRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def log(self, event_type: str, level: str, message: str,
                  task_id: int = None, details: Dict = None) -> AuditLog:
        log = AuditLog(
            event_id=str(uuid.uuid4())[:8],
            task_id=task_id,
            event_type=event_type,
            level=level,
            message=message,
            details=details or {}
        )
        self.session.add(log)
        await self.session.flush()
        return log

    async def get_for_task(self, task_id: int, limit: int = 100) -> List[AuditLog]:
        result = await self.session.execute(
            select(AuditLog)
            .where(AuditLog.task_id == task_id)
            .order_by(AuditLog.created_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())