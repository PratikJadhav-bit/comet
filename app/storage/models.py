from sqlalchemy import (
    Column, Integer, String, Text, DateTime, Enum, ForeignKey, 
    Boolean, JSON, Index
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.storage.database import Base
import enum
from datetime import datetime
from typing import Optional, Dict, Any


class TaskStatus(str, enum.Enum):
    CREATED = "CREATED"
    PLANNING = "PLANNING"
    READY = "READY"
    RUNNING = "RUNNING"
    WAITING_FOR_APPROVAL = "WAITING_FOR_APPROVAL"
    VERIFYING = "VERIFYING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    PAUSED = "PAUSED"


class RiskLevel(str, enum.Enum):
    LOW = "LOW"
    MODERATE = "MODERATE"
    HIGH = "HIGH"


class ApprovalStatus(str, enum.Enum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"
    CANCELLED = "CANCELLED"


class ToolCallStatus(str, enum.Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class Task(Base):
    __tablename__ = "tasks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    task_id = Column(String(64), unique=True, nullable=False, index=True)
    title = Column(String(256), nullable=False)
    description = Column(Text, nullable=True)
    status = Column(Enum(TaskStatus), default=TaskStatus.CREATED, nullable=False, index=True)
    risk_level = Column(Enum(RiskLevel), default=RiskLevel.LOW, nullable=False)
    parent_task_id = Column(Integer, ForeignKey("tasks.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    error_message = Column(Text, nullable=True)
    plan = Column(JSON, nullable=True)
    result = Column(JSON, nullable=True)
    metadata = Column(JSON, nullable=True)

    tool_calls = relationship("ToolCall", back_populates="task", cascade="all, delete-orphan")
    approvals = relationship("Approval", back_populates="task", cascade="all, delete-orphan")
    subtasks = relationship("Task", back_populates="parent_task")
    parent_task = relationship("Task", back_populates="subtasks", remote_side=[id])

    __table_args__ = (
        Index("ix_tasks_status_created", "status", "created_at"),
    )


class ToolCall(Base):
    __tablename__ = "tool_calls"

    id = Column(Integer, primary_key=True, autoincrement=True)
    call_id = Column(String(64), unique=True, nullable=False, index=True)
    task_id = Column(Integer, ForeignKey("tasks.id"), nullable=False, index=True)
    tool_name = Column(String(128), nullable=False)
    arguments = Column(JSON, nullable=False)
    risk_level = Column(Enum(RiskLevel), default=RiskLevel.LOW, nullable=False)
    status = Column(Enum(ToolCallStatus), default=ToolCallStatus.PENDING, nullable=False)
    result = Column(JSON, nullable=True)
    error_message = Column(Text, nullable=True)
    retry_count = Column(Integer, default=0, nullable=False)
    idempotency_key = Column(String(128), nullable=True, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)

    task = relationship("Task", back_populates="tool_calls")
    approval = relationship("Approval", back_populates="tool_call", uselist=False)

    __table_args__ = (
        Index("ix_tool_calls_task_status", "task_id", "status"),
    )


class Approval(Base):
    __tablename__ = "approvals"

    id = Column(Integer, primary_key=True, autoincrement=True)
    approval_id = Column(String(64), unique=True, nullable=False, index=True)
    task_id = Column(Integer, ForeignKey("tasks.id"), nullable=False, index=True)
    tool_call_id = Column(Integer, ForeignKey("tool_calls.id"), nullable=True, unique=True)
    risk_level = Column(Enum(RiskLevel), nullable=False)
    title = Column(String(256), nullable=False)
    description = Column(Text, nullable=False)
    details = Column(JSON, nullable=True)
    status = Column(Enum(ApprovalStatus), default=ApprovalStatus.PENDING, nullable=False)
    requested_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    responded_at = Column(DateTime(timezone=True), nullable=True)
    expires_at = Column(DateTime(timezone=True), nullable=True)
    response_reason = Column(Text, nullable=True)

    task = relationship("Task", back_populates="approvals")
    tool_call = relationship("ToolCall", back_populates="approval")


class MemoryItem(Base):
    __tablename__ = "memory_items"

    id = Column(Integer, primary_key=True, autoincrement=True)
    key = Column(String(256), unique=True, nullable=False, index=True)
    value = Column(Text, nullable=False)
    category = Column(String(64), nullable=True, index=True)
    source = Column(String(64), nullable=True)
    confidence = Column(Integer, default=100, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=True)
    is_user_approved = Column(Boolean, default=False, nullable=False)
    metadata = Column(JSON, nullable=True)


class ScheduledTask(Base):
    __tablename__ = "scheduled_tasks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    schedule_id = Column(String(64), unique=True, nullable=False, index=True)
    name = Column(String(256), nullable=False)
    description = Column(Text, nullable=True)
    task_template = Column(JSON, nullable=False)
    cron_expression = Column(String(128), nullable=True)
    interval_seconds = Column(Integer, nullable=True)
    timezone = Column(String(64), default="UTC", nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    max_runs = Column(Integer, nullable=True)
    run_count = Column(Integer, default=0, nullable=False)
    last_run_at = Column(DateTime(timezone=True), nullable=True)
    next_run_at = Column(DateTime(timezone=True), nullable=True, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    permissions = Column(JSON, nullable=True)


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    event_id = Column(String(64), unique=True, nullable=False, index=True)
    task_id = Column(Integer, ForeignKey("tasks.id"), nullable=True, index=True)
    event_type = Column(String(64), nullable=False, index=True)
    level = Column(String(16), nullable=False)
    message = Column(Text, nullable=False)
    details = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)

    __table_args__ = (
        Index("ix_audit_logs_task_created", "task_id", "created_at"),
    )