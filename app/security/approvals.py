from dataclasses import dataclass, field
from typing import Dict, Any, Optional, Callable, Awaitable
from datetime import datetime, timedelta
import uuid
import asyncio
from enum import Enum

from app.security.permissions import RiskLevel
from app.storage.models import ApprovalStatus


@dataclass
class ApprovalRequest:
    approval_id: str
    task_id: int
    tool_call_id: Optional[int]
    risk_level: RiskLevel
    title: str
    description: str
    details: Dict[str, Any] = field(default_factory=dict)
    requested_at: datetime = field(default_factory=datetime.utcnow)
    expires_at: Optional[datetime] = None
    callback: Optional[Callable[[bool, str], Awaitable[None]]] = None


@dataclass
class ApprovalResponse:
    approved: bool
    reason: str = ""
    responded_at: datetime = field(default_factory=datetime.utcnow)


class ApprovalCenter:
    def __init__(self, default_timeout: int = 300):
        self.pending: Dict[str, ApprovalRequest] = {}
        self.responses: Dict[str, ApprovalResponse] = {}
        self.default_timeout = default_timeout
        self._waiters: Dict[str, asyncio.Event] = {}

    def create_request(self, task_id: int, risk_level: RiskLevel, title: str,
                       description: str, details: Dict[str, Any] = None,
                       tool_call_id: int = None, timeout_seconds: int = None) -> ApprovalRequest:
        approval_id = str(uuid.uuid4())[:8]
        timeout = timeout_seconds or self.default_timeout
        expires_at = datetime.utcnow() + timedelta(seconds=timeout) if timeout > 0 else None
        
        request = ApprovalRequest(
            approval_id=approval_id,
            task_id=task_id,
            tool_call_id=tool_call_id,
            risk_level=risk_level,
            title=title,
            description=description,
            details=details or {},
            expires_at=expires_at
        )
        self.pending[approval_id] = request
        self._waiters[approval_id] = asyncio.Event()
        return request

    async def wait_for_approval(self, approval_id: str) -> ApprovalResponse:
        if approval_id not in self.pending:
            return ApprovalResponse(approved=False, reason="Approval request not found")
        
        request = self.pending[approval_id]
        
        if request.expires_at and datetime.utcnow() > request.expires_at:
            self.pending.pop(approval_id, None)
            self._waiters.pop(approval_id, None)
            return ApprovalResponse(approved=False, reason="Approval request expired")
        
        if approval_id in self.responses:
            response = self.responses.pop(approval_id)
            self.pending.pop(approval_id, None)
            self._waiters.pop(approval_id, None)
            return response
        
        waiter = self._waiters.get(approval_id)
        if waiter:
            try:
                await asyncio.wait_for(waiter.wait(), timeout=timeout or self.default_timeout)
            except asyncio.TimeoutError:
                pass
        
        if approval_id in self.responses:
            response = self.responses.pop(approval_id)
        else:
            response = ApprovalResponse(approved=False, reason="Approval timed out")
        
        self.pending.pop(approval_id, None)
        self._waiters.pop(approval_id, None)
        return response

    def respond(self, approval_id: str, approved: bool, reason: str = "") -> bool:
        if approval_id not in self.pending:
            return False
        
        response = ApprovalResponse(approved=approved, reason=reason)
        self.responses[approval_id] = response
        
        waiter = self._waiters.get(approval_id)
        if waiter:
            waiter.set()
        
        request = self.pending.get(approval_id)
        if request and request.callback:
            try:
                asyncio.create_task(request.callback(approved, reason))
            except Exception:
                pass
        
        return True

    def get_pending(self) -> list[ApprovalRequest]:
        now = datetime.utcnow()
        valid = []
        for req in self.pending.values():
            if req.expires_at and now > req.expires_at:
                continue
            valid.append(req)
        return valid

    def cancel(self, approval_id: str) -> bool:
        if approval_id in self.pending:
            self.pending.pop(approval_id, None)
            waiter = self._waiters.pop(approval_id, None)
            if waiter:
                waiter.set()
            return True
        return False


approval_center = ApprovalCenter()