"""Memory System Tools - Short-term, Long-term, and Task Memory"""
import asyncio
import json
import os
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field
from app.tools.registry import BaseTool, ToolSchema, ToolParameter, ToolResult, ToolCategory
from app.storage.repositories import MemoryRepository
from app.storage.database import get_session


@dataclass
class MemoryItem:
    key: str
    value: str
    category: str = "general"
    source: str = "user"
    confidence: int = 100
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    expires_at: Optional[datetime] = None
    is_user_approved: bool = False
    tags: List[str] = field(default_factory=list)
    metadata: Dict = field(default_factory=dict)


class MemoryManager:
    """Manages different types of memory"""
    
    def __init__(self):
        self.short_term: Dict[str, MemoryItem] = {}  # Current task context
        self.long_term: Dict[str, MemoryItem] = {}   # Persistent user preferences
        self.task_memory: Dict[int, Dict] = {}       # Per-task results
    
    async def store_short_term(self, key: str, value: str, task_id: int = None, 
                               category: str = "task", expires_in: int = 3600) -> MemoryItem:
        """Store in short-term memory (task context)"""
        item = MemoryItem(
            key=key,
            value=value,
            category=category,
            source="task" if task_id else "agent",
            expires_at=datetime.utcnow() + timedelta(seconds=expires_in)
        )
        self.short_term[key] = item
        
        # Also persist to database
        async with get_session() as session:
            repo = MemoryRepository(session)
            await repo.set(
                key=f"short_term:{task_id}:{key}" if task_id else f"short_term:{key}",
                value=value,
                category=category,
                source=item.source,
                expires_at=item.expires_at,
                metadata={"task_id": task_id} if task_id else {}
            )
        return item
    
    async def store_long_term(self, key: str, value: str, category: str = "preference",
                              is_user_approved: bool = False, tags: List[str] = None) -> MemoryItem:
        """Store in long-term memory (persistent)"""
        item = MemoryItem(
            key=key,
            value=value,
            category=category,
            source="user" if is_user_approved else "agent",
            is_user_approved=is_user_approved,
            tags=tags or []
        )
        self.long_term[key] = item
        
        # Persist to database
        async with get_session() as session:
            repo = MemoryRepository(session)
            await repo.set(
                key=f"long_term:{key}",
                value=value,
                category=category,
                source=item.source,
                is_user_approved=is_user_approved,
                metadata={"tags": tags or []}
            )
        return item
    
    async def store_task_memory(self, task_id: int, key: str, value: str) -> None:
        """Store task-specific memory"""
        if task_id not in self.task_memory:
            self.task_memory[task_id] = {}
        self.task_memory[task_id][key] = value
    
    async def get(self, key: str, task_id: int = None) -> Optional[str]:
        """Get from any memory store"""
        # Check short-term first (with task context)
        if task_id:
            st_key = f"short_term:{task_id}:{key}"
            if st_key in self.short_term:
                item = self.short_term[st_key]
                if item.expires_at and datetime.utcnow() > item.expires_at:
                    del self.short_term[st_key]
                else:
                    return item.value
        
        # Check general short-term
        gen_key = f"short_term:{key}"
        if gen_key in self.short_term:
            item = self.short_term[gen_key]
            if item.expires_at and datetime.utcnow() > item.expires_at:
                del self.short_term[gen_key]
            else:
                return item.value
        
        # Check long-term
        lt_key = f"long_term:{key}"
        if lt_key in self.long_term:
            return self.long_term[lt_key].value
        
        # Check task memory
        if task_id and task_id in self.task_memory:
            if key in self.task_memory[task_id]:
                return self.task_memory[task_id][key]
        
        # Fallback to database
        async with get_session() as session:
            repo = MemoryRepository(session)
            for prefix in ["short_term:", "long_term:"]:
                item = await repo.get(prefix + key)
                if item:
                    if item.expires_at and datetime.utcnow() > item.expires_at:
                        continue
                    return item.value
        
        return None
    
    async def search(self, query: str, memory_type: str = "all", limit: int = 10) -> List[MemoryItem]:
        """Search memory by content"""
        results = []
        query_lower = query.lower()
        
        sources = []
        if memory_type in ("all", "short_term"):
            sources.append(("short_term", self.short_term))
        if memory_type in ("all", "long_term"):
            sources.append(("long_term", self.long_term))
        
        for source_name, source in sources:
            for key, item in source.items():
                if query_lower in key.lower() or query_lower in item.value.lower():
                    results.append(item)
                    if len(results) >= limit:
                        return results
        
        return results
    
    async def delete(self, key: str, task_id: int = None, memory_type: str = "all") -> bool:
        """Delete from memory"""
        deleted = False
        
        if memory_type in ("all", "short_term"):
            st_key = f"short_term:{task_id}:{key}" if task_id else f"short_term:{key}"
            if st_key in self.short_term:
                del self.short_term[st_key]
                deleted = True
        
        if memory_type in ("all", "long_term"):
            lt_key = f"long_term:{key}"
            if lt_key in self.long_term:
                del self.long_term[lt_key]
                deleted = True
        
        if memory_type in ("all", "task") and task_id:
            if task_id in self.task_memory and key in self.task_memory[task_id]:
                del self.task_memory[task_id][key]
                deleted = True
        
        # Also delete from database
        async with get_session() as session:
            repo = MemoryRepository(session)
            for prefix in ["short_term:", "long_term:"]:
                await repo.delete(prefix + key)
        
        return deleted
    
    async def clear_expired(self) -> int:
        """Clear expired short-term memories"""
        now = datetime.utcnow()
        count = 0
        
        expired_keys = [
            k for k, v in self.short_term.items()
            if v.expires_at and now > v.expires_at
        ]
        for k in expired_keys:
            del self.short_term[k]
            count += 1
        
        # Also clean database
        async with get_session() as session:
            repo = MemoryRepository(session)
            count += await repo.cleanup_expired()
        
        return count
    
    async def get_stats(self) -> Dict[str, Any]:
        """Get memory statistics"""
        return {
            "short_term_count": len(self.short_term),
            "long_term_count": len(self.long_term),
            "task_memory_tasks": len(self.task_memory),
            "task_memory_total_items": sum(len(v) for v in self.task_memory.values())
        }


memory_manager = MemoryManager()


class StoreMemoryTool(BaseTool):
    def _define_schema(self) -> ToolSchema:
        return ToolSchema(
            name="memory.store",
            description="Store information in memory (short-term or long-term)",
            category=ToolCategory.MEMORY,
            parameters=[
                ToolParameter(name="key", type="string", description="Memory key", required=True),
                ToolParameter(name="value", type="string", description="Value to store", required=True),
                ToolParameter(name="memory_type", type="string", description="Type: short_term, long_term, task", required=False, default="short_term", enum=["short_term", "long_term", "task"]),
                ToolParameter(name="category", type="string", description="Category for organization", required=False, default="general"),
                ToolParameter(name="task_id", type="integer", description="Task ID for task-scoped memory", required=False),
                ToolParameter(name="expires_in", type="integer", description="Expiration in seconds (short-term only)", required=False, default=3600),
                ToolParameter(name="is_user_approved", type="boolean", description="Mark as user-approved (long-term)", required=False, default=False),
                ToolParameter(name="tags", type="array", items={"type": "string"}, description="Tags for organization", required=False),
            ],
            risk_level="LOW",
            requires_approval=False,
            idempotent=False,
            examples=[
                {"key": "user_preference", "value": "prefers dark mode", "memory_type": "long_term", "is_user_approved": True},
                {"key": "current_file", "value": "main.py", "memory_type": "short_term", "task_id": 1}
            ]
        )
    
    async def execute(self, arguments: Dict[str, Any], context: Dict = None) -> ToolResult:
        key = arguments["key"]
        value = arguments["value"]
        memory_type = arguments.get("memory_type", "short_term")
        category = arguments.get("category", "general")
        task_id = arguments.get("task_id")
        expires_in = arguments.get("expires_in", 3600)
        is_user_approved = arguments.get("is_user_approved", False)
        tags = arguments.get("tags", [])
        
        try:
            if memory_type == "short_term":
                item = await memory_manager.store_short_term(key, value, task_id, category, expires_in)
            elif memory_type == "long_term":
                item = await memory_manager.store_long_term(key, value, category, is_user_approved, tags)
            elif memory_type == "task":
                if not task_id:
                    return ToolResult(success=False, error="task_id required for task memory")
                await memory_manager.store_task_memory(task_id, key, value)
                return ToolResult(success=True, data={"stored": True, "key": key, "type": "task"})
            else:
                return ToolResult(success=False, error=f"Unknown memory type: {memory_type}")
            
            return ToolResult(success=True, data={
                "stored": True,
                "key": key,
                "type": memory_type,
                "expires_at": item.expires_at.isoformat() if item.expires_at else None
            })
        except Exception as e:
            return ToolResult(success=False, error=f"Failed to store memory: {str(e)}")


class GetMemoryTool(BaseTool):
    def _define_schema(self) -> ToolSchema:
        return ToolSchema(
            name="memory.get",
            description="Retrieve information from memory",
            category=ToolCategory.MEMORY,
            parameters=[
                ToolParameter(name="key", type="string", description="Memory key to retrieve", required=True),
                ToolParameter(name="task_id", type="integer", description="Task ID for task-scoped memory", required=False),
            ],
            risk_level="LOW",
            requires_approval=False,
            idempotent=True,
            examples=[{"key": "user_preference", "task_id": 1}]
        )
    
    async def execute(self, arguments: Dict[str, Any], context: Dict = None) -> ToolResult:
        key = arguments["key"]
        task_id = arguments.get("task_id")
        
        value = await memory_manager.get(key, task_id)
        if value is None:
            return ToolResult(success=False, error=f"Memory key not found: {key}", data={"found": False})
        
        return ToolResult(success=True, data={"found": True, "key": key, "value": value})


class SearchMemoryTool(BaseTool):
    def _define_schema(self) -> ToolSchema:
        return ToolSchema(
            name="memory.search",
            description="Search memory by query",
            category=ToolCategory.MEMORY,
            parameters=[
                ToolParameter(name="query", type="string", description="Search query", required=True),
                ToolParameter(name="memory_type", type="string", description="Memory type to search", required=False, default="all", enum=["all", "short_term", "long_term"]),
                ToolParameter(name="limit", type="integer", description="Maximum results", required=False, default=10),
            ],
            risk_level="LOW",
            requires_approval=False,
            idempotent=True,
            examples=[{"query": "user preference", "memory_type": "long_term"}]
        )
    
    async def execute(self, arguments: Dict[str, Any], context: Dict = None) -> ToolResult:
        query = arguments["query"]
        memory_type = arguments.get("memory_type", "all")
        limit = arguments.get("limit", 10)
        
        results = await memory_manager.search(query, memory_type, limit)
        
        return ToolResult(success=True, data={
            "results": [
                {
                    "key": r.key,
                    "value": r.value[:200] + "..." if len(r.value) > 200 else r.value,
                    "category": r.category,
                    "source": r.source,
                    "tags": r.tags,
                    "created_at": r.created_at.isoformat()
                }
                for r in results
            ],
            "count": len(results)
        })


class DeleteMemoryTool(BaseTool):
    def _define_schema(self) -> ToolSchema:
        return ToolSchema(
            name="memory.delete",
            description="Delete a memory entry",
            category=ToolCategory.MEMORY,
            parameters=[
                ToolParameter(name="key", type="string", description="Memory key to delete", required=True),
                ToolParameter(name="task_id", type="integer", description="Task ID for task-scoped memory", required=False),
                ToolParameter(name="memory_type", type="string", description="Memory type to delete from", required=False, default="all", enum=["all", "short_term", "long_term", "task"]),
            ],
            risk_level="MODERATE",
            requires_approval=True,
            idempotent=True,
            examples=[{"key": "old_preference", "memory_type": "long_term"}]
        )
    
    async def execute(self, arguments: Dict[str, Any], context: Dict = None) -> ToolResult:
        key = arguments["key"]
        task_id = arguments.get("task_id")
        memory_type = arguments.get("memory_type", "all")
        
        deleted = await memory_manager.delete(key, task_id, memory_type)
        
        return ToolResult(success=True, data={
            "deleted": deleted,
            "key": key,
            "type": memory_type
        })


class MemoryStatsTool(BaseTool):
    def _define_schema(self) -> ToolSchema:
        return ToolSchema(
            name="memory.stats",
            description="Get memory usage statistics",
            category=ToolCategory.MEMORY,
            parameters=[],
            risk_level="LOW",
            requires_approval=False,
            idempotent=True,
            examples=[{}]
        )
    
    async def execute(self, arguments: Dict[str, Any], context: Dict = None) -> ToolResult:
        stats = await memory_manager.get_stats()
        return ToolResult(success=True, data=stats)


class ClearExpiredMemoryTool(BaseTool):
    def _define_schema(self) -> ToolSchema:
        return ToolSchema(
            name="memory.clear_expired",
            description="Clear expired short-term memories",
            category=ToolCategory.MEMORY,
            parameters=[],
            risk_level="LOW",
            requires_approval=False,
            idempotent=True,
            examples=[{}]
        )
    
    async def execute(self, arguments: Dict[str, Any], context: Dict = None) -> ToolResult:
        count = await memory_manager.clear_expired()
        return ToolResult(success=True, data={"cleared": count})


def register_memory_tools(registry):
    registry.register(StoreMemoryTool())
    registry.register(GetMemoryTool())
    registry.register(SearchMemoryTool())
    registry.register(DeleteMemoryTool())
    registry.register(MemoryStatsTool())
    registry.register(ClearExpiredMemoryTool())