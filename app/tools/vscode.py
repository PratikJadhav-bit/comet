"""VS Code Integration Tools"""
import asyncio
import os
import json
from typing import Dict, Any, List, Optional
from pathlib import Path
from app.tools.registry import BaseTool, ToolSchema, ToolParameter, ToolResult, ToolCategory
from app.security.path_policy import path_policy
from app.security.risk import assess_risk
from app.security.permissions import ActionType


class VSCodeManager:
    """Manages VS Code interactions"""
    
    @staticmethod
    def find_vscode() -> Optional[str]:
        """Find VS Code executable"""
        import platform
        if platform.system() == "Windows":
            paths = [
                os.path.expandvars(r"%LOCALAPPDATA%\Programs\Microsoft VS Code\bin\code.cmd"),
                os.path.expandvars(r"%PROGRAMFILES%\Microsoft VS Code\bin\code.cmd"),
                os.path.expandvars(r"%PROGRAMFILES(X86)%\Microsoft VS Code\bin\code.cmd"),
            ]
        else:
            paths = ["/usr/bin/code", "/usr/local/bin/code", "/opt/visual-studio-code/bin/code"]
        
        for path in paths:
            if os.path.exists(path):
                return path
        return None
    
    @staticmethod
    def is_vscode_running() -> bool:
        """Check if VS Code is running"""
        try:
            import psutil
            for proc in psutil.process_iter(['name']):
                if 'code' in proc.info['name'].lower():
                    return True
            return False
        except Exception:
            return False
    
    @staticmethod
    async def open_folder(folder_path: str) -> Dict[str, Any]:
        """Open a folder in VS Code"""
        code_path = VSCodeManager.find_vscode()
        if not code_path:
            return {"success": False, "error": "VS Code not found"}
        
        try:
            resolved = path_policy.validate_read(folder_path)
        except PermissionError as e:
            return {"success": False, "error": str(e)}
        except FileNotFoundError as e:
            return {"success": False, "error": str(e)}
        
        import platform
        if platform.system() == "Windows":
            cmd = f'"{code_path}" "{resolved}"'
            process = await asyncio.create_subprocess_shell(
                f'cmd /c {cmd}',
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
        else:
            process = await asyncio.create_subprocess_exec(
                code_path, resolved,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
        
        await process.communicate()
        return {"success": process.returncode == 0, "folder": resolved}
    
    @staticmethod
    async def open_file(file_path: str, line: int = None, column: int = None) -> Dict[str, Any]:
        """Open a specific file in VS Code"""
        code_path = VSCodeManager.find_vscode()
        if not code_path:
            return {"success": False, "error": "VS Code not found"}
        
        try:
            resolved = path_policy.validate_read(file_path)
        except PermissionError as e:
            return {"success": False, "error": str(e)}
        except FileNotFoundError as e:
            return {"success": False, "error": str(e)}
        
        # Build URI with line/column
        uri = f"file://{resolved}"
        if line:
            uri += f":{line}"
            if column:
                uri += f":{column}"
        
        import platform
        if platform.system() == "Windows":
            cmd = f'"{code_path}" -g "{uri}"'
            process = await asyncio.create_subprocess_shell(
                f'cmd /c {cmd}',
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
        else:
            process = await asyncio.create_subprocess_exec(
                code_path, "-g", uri,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
        
        await process.communicate()
        return {"success": process.returncode == 0, "file": resolved, "line": line, "column": column}


vscode_manager = VSCodeManager()


class VSCodeOpenFolderTool(BaseTool):
    def _define_schema(self) -> ToolSchema:
        return ToolSchema(
            name="vscode.open_folder",
            description="Open a folder in VS Code",
            category=ToolCategory.CODING,
            parameters=[
                ToolParameter(name="path", type="string", description="Folder path to open", required=True),
            ],
            risk_level="LOW",
            requires_approval=False,
            idempotent=True,
            examples=[{"path": "./data/workspace/my_project"}]
        )
    
    async def execute(self, arguments: Dict[str, Any], context: Dict = None) -> ToolResult:
        path = arguments["path"]
        result = await vscode_manager.open_folder(path)
        return ToolResult(success=result.get("success", False), data=result, error=result.get("error"))


class VSCodeOpenFileTool(BaseTool):
    def _define_schema(self) -> ToolSchema:
        return ToolSchema(
            name="vscode.open_file",
            description="Open a file in VS Code at specific location",
            category=ToolCategory.CODING,
            parameters=[
                ToolParameter(name="path", type="string", description="File path to open", required=True),
                ToolParameter(name="line", type="integer", description="Line number to navigate to", required=False),
                ToolParameter(name="column", type="integer", description="Column number", required=False),
            ],
            risk_level="LOW",
            requires_approval=False,
            idempotent=True,
            examples=[{"path": "./data/workspace/main.py", "line": 10}]
        )
    
    async def execute(self, arguments: Dict[str, Any], context: Dict = None) -> ToolResult:
        path = arguments["path"]
        line = arguments.get("line")
        column = arguments.get("column")
        result = await vscode_manager.open_file(path, line, column)
        return ToolResult(success=result.get("success", False), data=result, error=result.get("error"))


class VSCodeGetWorkspaceTool(BaseTool):
    def _define_schema(self) -> ToolSchema:
        return ToolSchema(
            name="vscode.get_workspace",
            description="Get current VS Code workspace folders",
            category=ToolCategory.CODING,
            parameters=[],
            risk_level="LOW",
            requires_approval=False,
            idempotent=True,
            examples=[{}]
        )
    
    async def execute(self, arguments: Dict[str, Any], context: Dict = None) -> ToolResult:
        # VS Code stores workspace in storage.json
        try:
            import platform
            if platform.system() == "Windows":
                storage_path = os.path.expandvars(r"%APPDATA%\Code\User\workspaceStorage")
            else:
                storage_path = os.path.expanduser("~/.config/Code/User/workspaceStorage")
            
            workspaces = []
            if os.path.exists(storage_path):
                for ws_id in os.listdir(storage_path):
                    workspace_json = os.path.join(storage_path, ws_id, "workspace.json")
                    if os.path.exists(workspace_json):
                        with open(workspace_json, "r") as f:
                            data = json.load(f)
                            if "folder" in data:
                                folder_uri = data["folder"]
                                if folder_uri.startswith("file://"):
                                    folder_path = folder_uri[7:]
                                    workspaces.append(folder_path)
            
            return ToolResult(success=True, data={"workspaces": workspaces, "count": len(workspaces)})
        except Exception as e:
            return ToolResult(success=False, error=f"Failed to get workspace: {str(e)}")


class VSCodeInstallExtensionTool(BaseTool):
    def _define_schema(self) -> ToolSchema:
        return ToolSchema(
            name="vscode.install_extension",
            description="Install a VS Code extension",
            category=ToolCategory.CODING,
            parameters=[
                ToolParameter(name="extension_id", type="string", description="Extension ID (e.g., ms-python.python)", required=True),
            ],
            risk_level="MODERATE",
            requires_approval=True,
            idempotent=False,
            examples=[{"extension_id": "ms-python.python"}]
        )
    
    async def execute(self, arguments: Dict[str, Any], context: Dict = None) -> ToolResult:
        extension_id = arguments["extension_id"]
        code_path = vscode_manager.find_vscode()
        if not code_path:
            return ToolResult(success=False, error="VS Code not found")
        
        import platform
        if platform.system() == "Windows":
            cmd = f'"{code_path}" --install-extension {extension_id}'
            process = await asyncio.create_subprocess_shell(
                f'cmd /c {cmd}',
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
        else:
            process = await asyncio.create_subprocess_exec(
                code_path, "--install-extension", extension_id,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
        
        stdout, stderr = await process.communicate()
        return ToolResult(
            success=process.returncode == 0,
            data={"extension": extension_id, "stdout": stdout.decode()},
            error=stderr.decode() if process.returncode != 0 else None
        )


class VSCodeListExtensionsTool(BaseTool):
    def _define_schema(self) -> ToolSchema:
        return ToolSchema(
            name="vscode.list_extensions",
            description="List installed VS Code extensions",
            category=ToolCategory.CODING,
            parameters=[],
            risk_level="LOW",
            requires_approval=False,
            idempotent=True,
            examples=[{}]
        )
    
    async def execute(self, arguments: Dict[str, Any], context: Dict = None) -> ToolResult:
        code_path = vscode_manager.find_vscode()
        if not code_path:
            return ToolResult(success=False, error="VS Code not found")
        
        import platform
        if platform.system() == "Windows":
            cmd = f'"{code_path}" --list-extensions'
            process = await asyncio.create_subprocess_shell(
                f'cmd /c {cmd}',
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
        else:
            process = await asyncio.create_subprocess_exec(
                code_path, "--list-extensions",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
        
        stdout, stderr = await process.communicate()
        if process.returncode != 0:
            return ToolResult(success=False, error=stderr.decode())
        
        extensions = stdout.decode().strip().split("\n") if stdout.decode().strip() else []
        return ToolResult(success=True, data={"extensions": extensions, "count": len(extensions)})


class VSCodeRunTaskTool(BaseTool):
    def _define_schema(self) -> ToolSchema:
        return ToolSchema(
            name="vscode.run_task",
            description="Run a VS Code task from tasks.json",
            category=ToolCategory.CODING,
            parameters=[
                ToolParameter(name="task", type="string", description="Task name from tasks.json", required=True),
                ToolParameter(name="folder", type="string", description="Workspace folder", required=True),
            ],
            risk_level="MODERATE",
            requires_approval=True,
            idempotent=False,
            examples=[{"task": "build", "folder": "./data/workspace/my_project"}]
        )
    
    async def execute(self, arguments: Dict[str, Any], context: Dict = None) -> ToolResult:
        task = arguments["task"]
        folder = arguments["folder"]
        code_path = vscode_manager.find_vscode()
        if not code_path:
            return ToolResult(success=False, error="VS Code not found")
        
        try:
            resolved = path_policy.validate_read(folder)
        except PermissionError as e:
            return ToolResult(success=False, error=str(e))
        except FileNotFoundError as e:
            return ToolResult(success=False, error=str(e))
        
        import platform
        if platform.system() == "Windows":
            cmd = f'"{code_path}" --folder-uri "file://{resolved}" --task "{task}"'
            process = await asyncio.create_subprocess_shell(
                f'cmd /c {cmd}',
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
        else:
            process = await asyncio.create_subprocess_exec(
                code_path, "--folder-uri", f"file://{resolved}", "--task", task,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
        
        stdout, stderr = await process.communicate()
        return ToolResult(
            success=process.returncode == 0,
            data={"task": task, "stdout": stdout.decode()},
            error=stderr.decode() if process.returncode != 0 else None
        )


def register_vscode_tools(registry):
    registry.register(VSCodeOpenFolderTool())
    registry.register(VSCodeOpenFileTool())
    registry.register(VSCodeGetWorkspaceTool())
    registry.register(VSCodeInstallExtensionTool())
    registry.register(VSCodeListExtensionsTool())
    registry.register(VSCodeRunTaskTool())