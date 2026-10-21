"""Verification and observation tools for the agent"""
import asyncio
import os
import json
from typing import Dict, Any, List, Optional
from dataclasses import dataclass
from app.tools.registry import BaseTool, ToolSchema, ToolParameter, ToolResult, ToolCategory
from app.security.path_policy import path_policy


class VerificationManager:
    """Manages verification of agent actions"""
    
    @staticmethod
    async def verify_file_exists(path: str) -> Dict[str, Any]:
        """Verify a file exists and return details"""
        try:
            resolved = path_policy.validate_read(path)
            stat = os.stat(resolved)
            return {
                "verified": True,
                "path": resolved,
                "exists": True,
                "size": stat.st_size,
                "modified": stat.st_mtime,
                "is_file": os.path.isfile(resolved),
                "is_dir": os.path.isdir(resolved)
            }
        except Exception as e:
            return {"verified": False, "error": str(e)}
    
    @staticmethod
    async def verify_file_content(path: str, expected_content: str = None, 
                                  contains: str = None, pattern: str = None) -> Dict[str, Any]:
        """Verify file content matches expectations"""
        try:
            verified = await VerificationManager.verify_file_exists(path)
            if not verified.get("verified"):
                return verified
            
            with open(verified["path"], "r", encoding="utf-8") as f:
                content = f.read()
            
            result = {"verified": True, "path": verified["path"], "content_length": len(content)}
            
            if expected_content is not None:
                result["content_matches"] = content == expected_content
                if not result["content_matches"]:
                    result["verified"] = False
                    result["error"] = "Content does not match expected"
            
            if contains is not None:
                result["contains_text"] = contains in content
                if not result["contains_text"]:
                    result["verified"] = False
                    result["error"] = f"Content does not contain: {contains}"
            
            if pattern is not None:
                import re
                result["pattern_matches"] = bool(re.search(pattern, content))
                if not result["pattern_matches"]:
                    result["verified"] = False
                    result["error"] = f"Content does not match pattern: {pattern}"
            
            return result
        except Exception as e:
            return {"verified": False, "error": str(e)}
    
    @staticmethod
    async def verify_window_state(handle: int, expected_state: Dict = None) -> Dict[str, Any]:
        """Verify window state matches expectations"""
        try:
            import pywinauto
            from pywinauto import Desktop
            
            desktop = Desktop(backend="uia")
            win = desktop.window(handle=handle)
            
            if not win.exists():
                return {"verified": False, "error": "Window not found"}
            
            result = {
                "verified": True,
                "handle": handle,
                "title": win.window_text() or "",
                "is_visible": win.is_visible(),
                "is_enabled": win.is_enabled(),
                "is_maximized": win.is_maximized(),
                "is_minimized": win.is_minimized(),
                "has_focus": win.has_focus()
            }
            
            if expected_state:
                for key, expected_value in expected_state.items():
                    if key in result and result[key] != expected_value:
                        result["verified"] = False
                        result["error"] = f"State mismatch for {key}: expected {expected_value}, got {result[key]}"
                        break
            
            return result
        except Exception as e:
            return {"verified": False, "error": str(e)}
    
    @staticmethod
    async def verify_element_exists(handle: int, criteria: Dict) -> Dict[str, Any]:
        """Verify a UI element exists with given criteria"""
        try:
            import pywinauto
            from pywinauto import Desktop
            
            desktop = Desktop(backend="uia")
            win = desktop.window(handle=handle)
            
            if not win.exists():
                return {"verified": False, "error": "Window not found"}
            
            search_criteria = {}
            for key, value in criteria.items():
                if key == "control_type":
                    search_criteria["control_type"] = value
                elif key == "name":
                    search_criteria["title"] = value
                elif key == "automation_id":
                    search_criteria["auto_id"] = value
                elif key == "class_name":
                    search_criteria["class_name"] = value
            
            elements = win.descendants(**search_criteria)
            visible_elements = [e for e in elements if e.is_visible()]
            
            return {
                "verified": len(visible_elements) > 0,
                "count": len(visible_elements),
                "elements": [
                    {
                        "control_type": e.element_info.control_type,
                        "name": e.window_text() or "",
                        "automation_id": e.automation_id() or "",
                        "is_visible": e.is_visible(),
                        "is_enabled": e.is_enabled()
                    }
                    for e in visible_elements[:5]
                ]
            }
        except Exception as e:
            return {"verified": False, "error": str(e)}
    
    @staticmethod
    async def verify_process_running(process_id: int) -> Dict[str, Any]:
        """Verify a process is running"""
        try:
            import psutil
            
            if not psutil.pid_exists(process_id):
                return {"verified": False, "error": f"Process {process_id} not found"}
            
            proc = psutil.Process(process_id)
            return {
                "verified": True,
                "process_id": process_id,
                "name": proc.name(),
                "status": proc.status(),
                "cpu_percent": proc.cpu_percent(),
                "memory_mb": proc.memory_info().rss / 1024 / 1024
            }
        except Exception as e:
            return {"verified": False, "error": str(e)}
    
    @staticmethod
    async def verify_url_accessible(url: str) -> Dict[str, Any]:
        """Verify a URL is accessible"""
        try:
            import httpx
            
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.get(url, follow_redirects=True)
                
            return {
                "verified": response.status_code < 400,
                "url": str(response.url),
                "status_code": response.status_code,
                "content_type": response.headers.get("content-type"),
                "content_length": len(response.content)
            }
        except Exception as e:
            return {"verified": False, "error": str(e)}


verification_manager = VerificationManager()


class VerifyFileTool(BaseTool):
    def _define_schema(self) -> ToolSchema:
        return ToolSchema(
            name="verify.file_exists",
            description="Verify a file exists and get its details",
            category=ToolCategory.FILE,
            parameters=[
                ToolParameter(name="path", type="string", description="File path to verify", required=True),
            ],
            risk_level="LOW",
            requires_approval=False,
            idempotent=True,
            examples=[{"path": "./data/workspace/test.txt"}]
        )
    
    async def execute(self, arguments: Dict[str, Any], context: Dict = None) -> ToolResult:
        path = arguments["path"]
        result = await verification_manager.verify_file_exists(path)
        return ToolResult(success=result.get("verified", False), data=result, error=result.get("error"))


class VerifyFileContentTool(BaseTool):
    def _define_schema(self) -> ToolSchema:
        return ToolSchema(
            name="verify.file_content",
            description="Verify file content matches expectations",
            category=ToolCategory.FILE,
            parameters=[
                ToolParameter(name="path", type="string", description="File path", required=True),
                ToolParameter(name="expected_content", type="string", description="Exact content to match", required=False),
                ToolParameter(name="contains", type="string", description="Text that should be in the file", required=False),
                ToolParameter(name="pattern", type="string", description="Regex pattern to match", required=False),
            ],
            risk_level="LOW",
            requires_approval=False,
            idempotent=True,
            examples=[
                {"path": "./data/workspace/test.txt", "contains": "Hello"},
                {"path": "./data/workspace/test.txt", "pattern": "\\d{4}-\\d{2}-\\d{2}"}
            ]
        )
    
    async def execute(self, arguments: Dict[str, Any], context: Dict = None) -> ToolResult:
        path = arguments["path"]
        expected = arguments.get("expected_content")
        contains = arguments.get("contains")
        pattern = arguments.get("pattern")
        
        result = await verification_manager.verify_file_content(path, expected, contains, pattern)
        return ToolResult(success=result.get("verified", False), data=result, error=result.get("error"))


class VerifyWindowTool(BaseTool):
    def _define_schema(self) -> ToolSchema:
        return ToolSchema(
            name="verify.window_state",
            description="Verify window state matches expectations",
            category=ToolCategory.DESKTOP,
            parameters=[
                ToolParameter(name="handle", type="integer", description="Window handle", required=True),
                ToolParameter(name="expected_title", type="string", description="Expected window title", required=False),
                ToolParameter(name="should_be_visible", type="boolean", description="Should be visible", required=False),
                ToolParameter(name="should_have_focus", type="boolean", description="Should have focus", required=False),
            ],
            risk_level="LOW",
            requires_approval=False,
            idempotent=True,
            examples=[{"handle": 123456, "expected_title": "Notepad", "should_be_visible": True}]
        )
    
    async def execute(self, arguments: Dict[str, Any], context: Dict = None) -> ToolResult:
        handle = arguments["handle"]
        expected = {}
        
        if "expected_title" in arguments:
            expected["title"] = arguments["expected_title"]
        if "should_be_visible" in arguments:
            expected["is_visible"] = arguments["should_be_visible"]
        if "should_have_focus" in arguments:
            expected["has_focus"] = arguments["should_have_focus"]
        
        result = await verification_manager.verify_window_state(handle, expected if expected else None)
        return ToolResult(success=result.get("verified", False), data=result, error=result.get("error"))


class VerifyElementTool(BaseTool):
    def _define_schema(self) -> ToolSchema:
        return ToolSchema(
            name="verify.element_exists",
            description="Verify a UI element exists in a window",
            category=ToolCategory.DESKTOP,
            parameters=[
                ToolParameter(name="handle", type="integer", description="Window handle", required=True),
                ToolParameter(name="control_type", type="string", description="Control type (Button, Edit, Text, etc.)", required=False),
                ToolParameter(name="name", type="string", description="Element name/text", required=False),
                ToolParameter(name="automation_id", type="string", description="Automation ID", required=False),
            ],
            risk_level="LOW",
            requires_approval=False,
            idempotent=True,
            examples=[{"handle": 123456, "control_type": "Button", "name": "OK"}]
        )
    
    async def execute(self, arguments: Dict[str, Any], context: Dict = None) -> ToolResult:
        handle = arguments["handle"]
        criteria = {}
        
        if "control_type" in arguments:
            criteria["control_type"] = arguments["control_type"]
        if "name" in arguments:
            criteria["name"] = arguments["name"]
        if "automation_id" in arguments:
            criteria["automation_id"] = arguments["automation_id"]
        
        result = await verification_manager.verify_element_exists(handle, criteria)
        return ToolResult(success=result.get("verified", False), data=result, error=result.get("error"))


class VerifyProcessTool(BaseTool):
    def _define_schema(self) -> ToolSchema:
        return ToolSchema(
            name="verify.process_running",
            description="Verify a process is running",
            category=ToolCategory.SYSTEM,
            parameters=[
                ToolParameter(name="process_id", type="integer", description="Process ID to verify", required=True),
            ],
            risk_level="LOW",
            requires_approval=False,
            idempotent=True,
            examples=[{"process_id": 1234}]
        )
    
    async def execute(self, arguments: Dict[str, Any], context: Dict = None) -> ToolResult:
        process_id = arguments["process_id"]
        result = await verification_manager.verify_process_running(process_id)
        return ToolResult(success=result.get("verified", False), data=result, error=result.get("error"))


class VerifyUrlTool(BaseTool):
    def _define_schema(self) -> ToolSchema:
        return ToolSchema(
            name="verify.url_accessible",
            description="Verify a URL is accessible",
            category=ToolCategory.BROWSER,
            parameters=[
                ToolParameter(name="url", type="string", description="URL to verify", required=True),
            ],
            risk_level="LOW",
            requires_approval=False,
            idempotent=True,
            examples=[{"url": "https://example.com"}]
        )
    
    async def execute(self, arguments: Dict[str, Any], context: Dict = None) -> ToolResult:
        url = arguments["url"]
        result = await verification_manager.verify_url_accessible(url)
        return ToolResult(success=result.get("verified", False), data=result, error=result.get("error"))


def register_verification_tools(registry):
    registry.register(VerifyFileTool())
    registry.register(VerifyFileContentTool())
    registry.register(VerifyWindowTool())
    registry.register(VerifyElementTool())
    registry.register(VerifyProcessTool())
    registry.register(VerifyUrlTool())