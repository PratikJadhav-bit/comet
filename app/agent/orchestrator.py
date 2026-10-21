from enum import Enum
from dataclasses import dataclass, field
from typing import Dict, Any, Optional, List, Callable, Awaitable
from datetime import datetime
import uuid
import asyncio
import json

from app.storage.models import TaskStatus, RiskLevel, ToolCallStatus
from app.storage.repositories import TaskRepository, ToolCallRepository, ApprovalRepository, AuditRepository
from app.storage.database import get_session
from app.tools.registry import tool_registry, ToolResult
from app.security.risk import assess_risk, RiskAssessment
from app.security.approvals import approval_center, ApprovalRequest, ApprovalResponse
from app.security.permissions import ActionType
from app.security.prompt_injection import prompt_injection_defense, content_trust_boundary, secret_redactor
from app.models.base import ModelProvider, ModelMessage, ModelResponse, ToolDefinition, model_registry
from app.config import settings


class OrchestratorEvent(str, Enum):
    TASK_CREATED = "task_created"
    TASK_PLANNING = "task_planning"
    TASK_PLAN_READY = "task_plan_ready"
    TASK_STARTED = "task_started"
    AGENT_REASONING = "agent_reasoning"
    AGENT_ACTION_SELECTED = "agent_action_selected"
    TOOL_CALL_STARTED = "tool_call_started"
    TOOL_CALL_COMPLETED = "tool_call_completed"
    TOOL_CALL_FAILED = "tool_call_failed"
    APPROVAL_REQUESTED = "approval_requested"
    APPROVAL_RECEIVED = "approval_received"
    APPROVAL_EXPIRED = "approval_expired"
    TASK_VERIFYING = "task_verifying"
    TASK_COMPLETED = "task_completed"
    TASK_FAILED = "task_failed"
    TASK_CANCELLED = "task_cancelled"
    TASK_PAUSED = "task_paused"
    AGENT_STEP_COMPLETE = "agent_step_complete"


@dataclass
class AgentStep:
    step_number: int
    reasoning: str
    action: Optional[Dict[str, Any]] = None
    tool_name: Optional[str] = None
    arguments: Optional[Dict[str, Any]] = None
    result: Optional[Dict[str, Any]] = None
    success: bool = False
    error: Optional[str] = None


@dataclass
class ExecutionContext:
    task_id: int
    task_title: str
    objective: str
    steps: List[AgentStep] = field(default_factory=list)
    variables: Dict[str, Any] = field(default_factory=dict)
    step_results: Dict[str, Any] = field(default_factory=dict)
    consecutive_failures: int = 0
    max_steps: int = 50
    max_consecutive_failures: int = 3


class AgentOrchestrator:
    def __init__(self):
        self._running_tasks: Dict[int, asyncio.Task] = {}
        self._event_handlers: Dict[OrchestratorEvent, List[Callable]] = {}
        self._paused_tasks: set = set()
        self._cancelled_tasks: set = set()

    def on_event(self, event: OrchestratorEvent, handler: Callable):
        if event not in self._event_handlers:
            self._event_handlers[event] = []
        self._event_handlers[event].append(handler)

    async def _emit(self, event: OrchestratorEvent, data: Dict):
        for handler in self._event_handlers.get(event, []):
            try:
                if asyncio.iscoroutinefunction(handler):
                    await handler(data)
                else:
                    handler(data)
            except Exception:
                pass

    async def create_task(self, title: str, description: str = "", 
                          parent_task_id: int = None, metadata: Dict = None) -> Dict:
        async with get_session() as session:
            task_repo = TaskRepository(session)
            audit_repo = AuditRepository(session)
            
            task = await task_repo.create(title, description, parent_task_id, metadata=metadata)
            await audit_repo.log("task_created", "INFO", f"Task created: {title}", task.id)
            
            await self._emit(OrchestratorEvent.TASK_CREATED, {"task_id": task.id, "title": title})
            
            return {"task_id": task.id, "task_uuid": task.task_id, "status": task.status.value}

    async def plan_task(self, task_id: int, user_instruction: str) -> Dict:
        async with get_session() as session:
            task_repo = TaskRepository(session)
            audit_repo = AuditRepository(session)
            
            task = await task_repo.get_by_id(task_id)
            if not task:
                return {"error": "Task not found"}
            
            await task_repo.update_status(task_id, TaskStatus.PLANNING)
            await audit_repo.log("planning_started", "INFO", f"Planning task: {task.title}", task_id)
            await self._emit(OrchestratorEvent.TASK_PLANNING, {"task_id": task_id})
            
            provider = model_registry.get()
            if not provider:
                await task_repo.update_status(task_id, TaskStatus.FAILED, error_message="No model provider configured")
                return {"error": "No model provider configured"}
            
            tools = tool_registry.list_tools()
            tool_defs = []
            for t in tools:
                tool_defs.append(ToolDefinition(
                    name=t.name,
                    description=t.description,
                    parameters={p.name: {"type": p.type, "description": p.description} for p in t.parameters},
                    required=[p.name for p in t.parameters if p.required]
                ))
            
            system_prompt = self._build_planning_prompt(tools)
            
            messages = [
                ModelMessage(role="system", content=system_prompt),
                ModelMessage(role="user", content=user_instruction)
            ]
            
            try:
                response = await provider.chat(messages, tools=tool_defs, temperature=0.1)
                
                plan_data = self._parse_plan(response.content)
                plan_data["objective"] = user_instruction
                
                risk_levels = [s.get("risk_level", "LOW") for s in plan_data.get("steps", [])]
                overall_risk = RiskLevel.HIGH if "HIGH" in risk_levels else (RiskLevel.MODERATE if "MODERATE" in risk_levels else RiskLevel.LOW)
                
                await task_repo.update_plan(task_id, plan_data)
                await task_repo.update_status(task_id, TaskStatus.READY)
                await audit_repo.log("planning_completed", "INFO", f"Plan created with {len(plan_data.get('steps', []))} steps", task_id)
                
                await self._emit(OrchestratorEvent.TASK_PLAN_READY, {"task_id": task_id, "plan": plan_data})
                
                return {"task_id": task_id, "plan": plan_data, "status": "READY"}
            except Exception as e:
                await task_repo.update_status(task_id, TaskStatus.FAILED, error_message=str(e))
                await audit_repo.log("planning_failed", "ERROR", f"Planning failed: {str(e)}", task_id)
                return {"error": f"Planning failed: {str(e)}"}

    def _build_planning_prompt(self, tools: List) -> str:
        tool_descriptions = []
        for t in tools:
            params = ", ".join([f"{p.name}: {p.description}" for p in t.parameters])
            tool_descriptions.append(f"- {t.name}: {t.description} (params: {params})")
        
        return f"""You are an AI agent planner. Create a structured plan to accomplish the user's goal.

Available tools:
{chr(10).join(tool_descriptions)}

Return a JSON object with:
{{
  "objective": "clear statement of the goal",
  "steps": [
    {{
      "tool": "tool_name",
      "arguments": {{"param": "value"}},
      "description": "what this step accomplishes",
      "risk_level": "LOW|MODERATE|HIGH"
    }}
  ],
  "estimated_tool_calls": number,
  "risk_level": "LOW|MODERATE|HIGH"
}}

Only return valid JSON. No extra text."""

    def _parse_plan(self, content: str) -> Dict:
        try:
            start = content.find("{")
            end = content.rfind("}") + 1
            if start >= 0 and end > start:
                return json.loads(content[start:end])
        except Exception:
            pass
        return {"steps": [], "estimated_tool_calls": 0, "risk_level": "LOW"}

    async def execute_task(self, task_id: int) -> Dict:
        if task_id in self._running_tasks:
            return {"error": "Task already running"}
        
        async with get_session() as session:
            task_repo = TaskRepository(session)
            task = await task_repo.get_by_id(task_id)
            if not task:
                return {"error": "Task not found"}
            
            if task.status not in (TaskStatus.READY, TaskStatus.PAUSED):
                return {"error": f"Task not ready for execution: {task.status.value}"}
            
            if task_id in self._cancelled_tasks:
                self._cancelled_tasks.discard(task_id)
                return {"error": "Task was cancelled"}
        
        execution_task = asyncio.create_task(self._run_agent_loop(task_id))
        self._running_tasks[task_id] = execution_task
        
        try:
            result = await execution_task
            return result
        finally:
            self._running_tasks.pop(task_id, None)

    async def _run_agent_loop(self, task_id: int) -> Dict:
        """Main agent reasoning loop: observe -> reason -> act -> verify"""
        async with get_session() as session:
            task_repo = TaskRepository(session)
            tool_repo = ToolCallRepository(session)
            approval_repo = ApprovalRepository(session)
            audit_repo = AuditRepository(session)
            
            task = await task_repo.get_by_id(task_id)
            if not task or not task.plan:
                return {"error": "Task or plan not found"}
            
            await task_repo.update_status(task_id, TaskStatus.RUNNING)
            await audit_repo.log("task_started", "INFO", f"Task execution started", task_id)
            await self._emit(OrchestratorEvent.TASK_STARTED, {"task_id": task_id})
            
            context = ExecutionContext(
                task_id=task_id,
                task_title=task.title,
                objective=task.plan.get("objective", "")
            )
            
            # Use initial plan steps if available
            initial_steps = task.plan.get("steps", [])
            step_index = 0
            
            while step_index < context.max_steps:
                if task_id in self._cancelled_tasks:
                    await task_repo.update_status(task_id, TaskStatus.CANCELLED)
                    await audit_repo.log("task_cancelled", "INFO", "Task cancelled by user", task_id)
                    await self._emit(OrchestratorEvent.TASK_CANCELLED, {"task_id": task_id})
                    return {"status": "CANCELLED", "completed_steps": step_index}
                
                while task_id in self._paused_tasks:
                    await asyncio.sleep(1)
                    if task_id in self._cancelled_tasks:
                        self._paused_tasks.discard(task_id)
                        await task_repo.update_status(task_id, TaskStatus.CANCELLED)
                        return {"status": "CANCELLED", "completed_steps": step_index}
                
                # Check if we should use initial plan or ask model for next action
                if step_index < len(initial_steps):
                    step = initial_steps[step_index]
                    tool_name = step.get("tool")
                    arguments = step.get("arguments", {})
                    description = step.get("description", "")
                    risk_str = step.get("risk_level", "LOW")
                    reasoning = f"Following planned step {step_index + 1}: {description}"
                else:
                    # Ask model for next action based on current state
                    reasoning, tool_name, arguments, description, risk_str = await self._reason_next_action(
                        task_id, context, step_index
                    )
                    if tool_name is None:
                        # Model indicates task is complete
                        break
                
                step_obj = AgentStep(
                    step_number=step_index + 1,
                    reasoning=reasoning,
                    tool_name=tool_name,
                    arguments=arguments
                )
                context.steps.append(step_obj)
                
                try:
                    risk_level = RiskLevel(risk_str)
                except ValueError:
                    risk_level = RiskLevel.LOW
                
                # Check approval requirements
                action_type = self._map_tool_to_action(tool_name)
                assessment = assess_risk(action_type, {"step": step_index, "description": description})
                
                if assessment.requires_approval:
                    approval = await approval_repo.create(
                        task_id=task_id,
                        risk_level=assessment.level,
                        title=f"Execute: {tool_name}",
                        description=f"{description}\n\nRisk: {assessment.description}",
                        details={"tool": tool_name, "arguments": arguments, "assessment": assessment.__dict__},
                        expires_in_seconds=settings.approval_timeout_seconds
                    )
                    
                    await self._emit(OrchestratorEvent.APPROVAL_REQUESTED, {
                        "task_id": task_id,
                        "approval_id": approval.approval_id,
                        "tool": tool_name,
                        "description": description
                    })
                    
                    await task_repo.update_status(task_id, TaskStatus.WAITING_FOR_APPROVAL)
                    
                    response = await approval_center.wait_for_approval(approval.approval_id)
                    
                    await approval_repo.respond(approval.id, 
                        ApprovalStatus.APPROVED if response.approved else ApprovalStatus.REJECTED,
                        response.reason)
                    
                    if not response.approved:
                        await task_repo.update_status(task_id, TaskStatus.PAUSED)
                        await audit_repo.log("approval_rejected", "WARNING", f"Approval rejected: {response.reason}", task_id)
                        await self._emit(OrchestratorEvent.APPROVAL_RECEIVED, {"approved": False, "reason": response.reason})
                        return {"status": "PAUSED", "completed_steps": step_index, "reason": response.reason}
                    
                    await audit_repo.log("approval_granted", "INFO", "Approval granted", task_id)
                    await self._emit(OrchestratorEvent.APPROVAL_RECEIVED, {"approved": True})
                
                # Execute the tool
                idempotency_key = f"{task_id}:{step_index}:{tool_name}:{hash(str(arguments))}"
                existing = await tool_repo.check_idempotency(idempotency_key)
                if existing and existing.status == ToolCallStatus.COMPLETED:
                    step_obj.result = existing.result
                    step_obj.success = True
                    context.step_results[f"step_{step_index}"] = existing.result
                    step_index += 1
                    context.consecutive_failures = 0
                    continue
                
                tool_call = await tool_repo.create(
                    task_id=task_id,
                    tool_name=tool_name,
                    arguments=arguments,
                    risk_level=risk_level,
                    idempotency_key=idempotency_key
                )
                
                await tool_repo.update_status(tool_call.id, ToolCallStatus.RUNNING)
                await audit_repo.log("tool_call_started", "INFO", f"Executing {tool_name}", task_id, {"tool": tool_name, "arguments": arguments})
                await self._emit(OrchestratorEvent.TOOL_CALL_STARTED, {"task_id": task_id, "tool": tool_name, "step": step_index})
                
                result = await tool_registry.execute(tool_name, arguments, context.__dict__)
                
                if result.success:
                    await tool_repo.update_status(tool_call.id, ToolCallStatus.COMPLETED, result=result.data)
                    step_obj.result = result.data
                    step_obj.success = True
                    context.step_results[f"step_{step_index}"] = result.data
                    await audit_repo.log("tool_call_completed", "INFO", f"Completed {tool_name}", task_id, {"result": result.data})
                    await self._emit(OrchestratorEvent.TOOL_CALL_COMPLETED, {"task_id": task_id, "tool": tool_name, "result": result.data})
                    context.consecutive_failures = 0
                else:
                    await tool_repo.update_status(tool_call.id, ToolCallStatus.FAILED, error_message=result.error)
                    step_obj.error = result.error
                    step_obj.success = False
                    await audit_repo.log("tool_call_failed", "ERROR", f"Failed {tool_name}: {result.error}", task_id, {"error": result.error})
                    await self._emit(OrchestratorEvent.TOOL_CALL_FAILED, {"task_id": task_id, "tool": tool_name, "error": result.error})
                    context.consecutive_failures += 1
                    
                    if context.consecutive_failures >= context.max_consecutive_failures:
                        await task_repo.update_status(task_id, TaskStatus.FAILED, error_message=f"Too many consecutive failures: {result.error}")
                        await self._emit(OrchestratorEvent.TASK_FAILED, {"task_id": task_id, "error": result.error})
                        return {"status": "FAILED", "completed_steps": step_index, "error": result.error}
                    
                    # Ask model for alternative approach
                    if tool_call.retry_count < settings.max_retries:
                        await tool_repo.increment_retry(tool_call.id)
                        continue
                    else:
                        # Try to get alternative from model
                        alt_reasoning, alt_tool, alt_args, alt_desc, alt_risk = await self._reason_next_action(
                            task_id, context, step_index, error=result.error
                        )
                        if alt_tool:
                            tool_name = alt_tool
                            arguments = alt_args
                            description = alt_desc
                            risk_str = alt_risk
                            reasoning = alt_reasoning
                            step_obj = AgentStep(
                                step_number=step_index + 1,
                                reasoning=reasoning,
                                tool_name=tool_name,
                                arguments=arguments
                            )
                            context.steps.append(step_obj)
                            continue
                        else:
                            await task_repo.update_status(task_id, TaskStatus.FAILED, error_message=f"Step {step_index} failed: {result.error}")
                            await self._emit(OrchestratorEvent.TASK_FAILED, {"task_id": task_id, "error": result.error})
                            return {"status": "FAILED", "completed_steps": step_index, "error": result.error}
                
                step_index += 1
                
                # Emit step completion event
                await self._emit(OrchestratorEvent.AGENT_STEP_COMPLETE, {
                    "task_id": task_id,
                    "step": step_index,
                    "tool": tool_name,
                    "success": True
                })
                
                # Check if we should continue - ask model if objective is achieved
                if step_index >= len(initial_steps) or step_index % 5 == 0:
                    should_continue = await self._evaluate_progress(task_id, context, step_index)
                    if not should_continue:
                        break
            
            await task_repo.update_status(task_id, TaskStatus.VERIFYING)
            await audit_repo.log("verifying", "INFO", "Verifying task completion", task_id)
            await self._emit(OrchestratorEvent.TASK_VERIFYING, {"task_id": task_id})
            
            # Final verification
            verified = await self._verify_completion(task_id, context)
            if verified:
                await task_repo.update_status(task_id, TaskStatus.COMPLETED, result={"steps_completed": step_index, "results": context.step_results})
                await audit_repo.log("task_completed", "INFO", "Task completed successfully", task_id)
                await self._emit(OrchestratorEvent.TASK_COMPLETED, {"task_id": task_id})
                return {"status": "COMPLETED", "steps_completed": step_index, "results": context.step_results}
            else:
                await task_repo.update_status(task_id, TaskStatus.FAILED, error_message="Verification failed - objective not achieved")
                await self._emit(OrchestratorEvent.TASK_FAILED, {"task_id": task_id, "error": "Verification failed"})
                return {"status": "FAILED", "error": "Verification failed - objective not achieved"}

    async def _reason_next_action(
        self, 
        task_id: int, 
        context: ExecutionContext, 
        step_index: int,
        error: Optional[str] = None
    ) -> tuple:
        """Ask model to reason about next action based on current state"""
        async with get_session() as session:
            task_repo = TaskRepository(session)
            task = await task_repo.get_by_id(task_id)
            if not task:
                return ("Task not found", None, None, None, None)
            
            provider = model_registry.get()
            if not provider:
                return ("No model provider", None, None, None, None)
            
            tools = tool_registry.list_tools()
            tool_defs = []
            for t in tools:
                tool_defs.append(ToolDefinition(
                    name=t.name,
                    description=t.description,
                    parameters={p.name: {"type": p.type, "description": p.description} for p in t.parameters},
                    required=[p.name for p in t.parameters if p.required]
                ))
            
            # Build context summary
            completed_steps = []
            for i, step in enumerate(context.steps):
                if step.success:
                    completed_steps.append(f"Step {i+1}: {step.tool_name} - SUCCESS: {json.dumps(step.result)[:200]}")
                else:
                    completed_steps.append(f"Step {i+1}: {step.tool_name} - FAILED: {step.error}")
            
            context_summary = "\n".join(completed_steps) if completed_steps else "No steps completed yet."
            
            system_prompt = f"""You are an AI agent executing a task. Reason about the next action.

Objective: {context.objective}

Completed steps:
{context_summary}

Available tools: {", ".join([t.name for t in tools])}

{"Previous error: " + error if error else ""}

Decide the next action. Return JSON:
{{
  "reasoning": "why this action",
  "tool": "tool_name or null if complete",
  "arguments": {{}},
  "description": "what this accomplishes",
  "risk_level": "LOW|MODERATE|HIGH",
  "is_complete": false
}}

If objective is achieved, set tool to null and is_complete to true."""

            messages = [
                ModelMessage(role="system", content=system_prompt),
                ModelMessage(role="user", content="What is the next action?")
            ]
            
            try:
                response = await provider.chat(messages, tools=tool_defs, temperature=0.1)
                
                # Scan model response for prompt injection
                safe, threats = prompt_injection_defense.is_safe_for_model(response.content, "model_response")
                if not safe:
                    threat_desc = "; ".join([t.description for t in threats])
                    await audit_repo.log("prompt_injection_detected", "WARNING", 
                        f"Prompt injection detected in model response: {threat_desc}", task_id)
                    return (f"Security: Model response blocked due to {len(threats)} threats", None, None, None, None)
                
                data = self._parse_plan(response.content)
                
                if data.get("is_complete") or data.get("tool") is None:
                    return (data.get("reasoning", "Task complete"), None, None, None, None)
                
                return (
                    data.get("reasoning", ""),
                    data.get("tool"),
                    data.get("arguments", {}),
                    data.get("description", ""),
                    data.get("risk_level", "LOW")
                )
            except Exception as e:
                return (f"Reasoning error: {e}", None, None, None, None)

    async def _evaluate_progress(self, task_id: int, context: ExecutionContext, step_index: int) -> bool:
        """Ask model if objective is achieved"""
        async with get_session() as session:
            task_repo = TaskRepository(session)
            task = await task_repo.get_by_id(task_id)
            if not task:
                return False
            
            provider = model_registry.get()
            if not provider:
                return True  # Continue if no model
            
            completed = "\n".join([
                f"Step {i+1}: {s.tool_name} - {'SUCCESS' if s.success else 'FAILED'}: {json.dumps(s.result)[:200] if s.result else s.error}"
                for i, s in enumerate(context.steps)
            ])
            
            system_prompt = f"""Evaluate if the objective has been achieved.

Objective: {context.objective}

Completed steps:
{completed}

Return JSON:
{{
  "objective_achieved": true/false,
  "reasoning": "explanation"
}}"""

            messages = [
                ModelMessage(role="system", content=system_prompt),
                ModelMessage(role="user", content="Is the objective achieved?")
            ]
            
            try:
                response = await provider.chat(messages, temperature=0.1)
                data = self._parse_plan(response.content)
                return not data.get("objective_achieved", False)
            except Exception:
                return True  # Continue on error

    async def _verify_completion(self, task_id: int, context: ExecutionContext) -> bool:
        """Final verification of task completion"""
        return await self._evaluate_progress(task_id, context, len(context.steps))

    def _map_tool_to_action(self, tool_name: str) -> ActionType:
        mapping = {
            "list_files": ActionType.LIST_FILES,
            "read_file": ActionType.READ_FILE,
            "write_file": ActionType.WRITE_FILE,
            "search_files": ActionType.SEARCH_FILES,
            "navigate": ActionType.NAVIGATE_WEB,
            "read_page": ActionType.READ_WEB,
            "click": ActionType.CLICK_WEB,
            "fill": ActionType.FILL_WEB,
            "screenshot": ActionType.READ_WEB,
            "extract": ActionType.READ_WEB,
        }
        return mapping.get(tool_name, ActionType.RUN_COMMAND)

    def pause_task(self, task_id: int) -> bool:
        if task_id in self._running_tasks:
            self._paused_tasks.add(task_id)
            return True
        return False

    def resume_task(self, task_id: int) -> bool:
        self._paused_tasks.discard(task_id)
        return True

    def cancel_task(self, task_id: int) -> bool:
        self._cancelled_tasks.add(task_id)
        if task_id in self._running_tasks:
            self._running_tasks[task_id].cancel()
            return True
        return False

    async def get_task_status(self, task_id: int) -> Dict:
        async with get_session() as session:
            task_repo = TaskRepository(session)
            task = await task_repo.get_by_id(task_id)
            if not task:
                return {"error": "Task not found"}
            return {
                "task_id": task.id,
                "task_uuid": task.task_id,
                "title": task.title,
                "status": task.status.value,
                "progress": len([tc for tc in task.tool_calls if tc.status == ToolCallStatus.COMPLETED]),
                "total_steps": len(task.plan.get("steps", [])) if task.plan else 0
            }


orchestrator = AgentOrchestrator()