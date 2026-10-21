"""Controlled Terminal and Coding Tools"""
import asyncio
import os
import subprocess
import shlex
from typing import Dict, Any, List, Optional
from pathlib import Path
from app.tools.registry import BaseTool, ToolSchema, ToolParameter, ToolResult, ToolCategory
from app.security.path_policy import path_policy
from app.security.risk import assess_risk
from app.security.permissions import ActionType


# Command allowlist - only these commands can be executed
ALLOWED_COMMANDS = {
    "python": ["-m", "pytest", "pip", "-c"],
    "pytest": [],
    "pip": ["install", "list", "show", "uninstall"],
    "npm": ["install", "test", "run", "build", "lint"],
    "node": [],
    "git": ["status", "diff", "log", "add", "commit", "push", "pull", "branch", "checkout", "merge", "rebase"],
    "uv": ["pip", "sync", "lock", "tree"],
    "ruff": ["check", "format"],
    "black": [],
    "mypy": [],
    "echo": [],
    "cat": [],
    "ls": ["-la", "-l", "-a"],
    "dir": ["/b", "/s"],
    "type": [],
    "more": [],
    "find": [],
    "grep": [],
    "rg": [],
    "head": [],
    "tail": [],
    "wc": [],
}

# Blocked commands - never allowed
BLOCKED_COMMANDS = {
    "rm", "del", "rd", "rmdir", "format", "fdisk", "diskpart",
    "shutdown", "reboot", "poweroff", "halt",
    "kill", "pkill", "killall", "taskkill",
    "chmod", "chown", "chgrp", "attrib", "icacls",
    "sudo", "su", "runas",
    "passwd", "useradd", "userdel", "usermod",
    "mount", "umount", "fdisk", "parted",
    "dd", "mkfs", "fsck",
    "iptables", "firewall-cmd", "netsh",
    "systemctl", "service", "sc",
    "reg", "regedit", "regini",
    "bcdedit", "bootrec",
    "format", "cipher",
    "takeown", "icacls",
    "net", "netsh",
    "schtasks", "at",
    "wmic", "powershell", "pwsh",
}


class TerminalManager:
    """Manages terminal execution with safety controls"""
    
    @staticmethod
    def parse_command(command: str) -> tuple[str, List[str]]:
        """Parse command string into executable and arguments"""
        parts = shlex.split(command, posix=False)
        if not parts:
            raise ValueError("Empty command")
        return parts[0], parts[1:]
    
    @staticmethod
    def is_allowed(command: str) -> tuple[bool, str]:
        """Check if command is allowed"""
        try:
            executable, args = TerminalManager.parse_command(command)
            executable_lower = executable.lower()
            
            # Check blocked commands
            if executable_lower in BLOCKED_COMMANDS:
                return False, f"Command blocked: {executable}"
            
            # Check allowed commands
            if executable_lower not in ALLOWED_COMMANDS:
                return False, f"Command not in allowlist: {executable}"
            
            # For allowed commands, check if args are allowed (if specified)
            allowed_args = ALLOWED_COMMANDS[executable_lower]
            if allowed_args and args:
                # Check if first arg is in allowed subcommands
                first_arg = args[0] if args else ""
                if first_arg and first_arg not in allowed_args:
                    # Allow if it's a flag or path
                    if not first_arg.startswith("-") and not first_arg.startswith("/"):
                        return False, f"Subcommand not allowed: {first_arg} for {executable}"
            
            return True, "Allowed"
        except Exception as e:
            return False, f"Command parsing error: {str(e)}"
    
    @staticmethod
    def get_working_dir(cwd: str = None) -> str:
        """Get validated working directory"""
        from app.config import settings
        import os
        
        # Default to first allowed directory
        default_dir = settings.allowed_directories[0] if settings.allowed_directories else "./data/workspace"
        
        if cwd:
            try:
                return path_policy.validate_write(cwd, allow_create_dirs=False)
            except PermissionError:
                # If cwd is not in allowed directories, try to use it as-is if it's a subdirectory of project root
                project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
                if os.path.commonpath([os.path.abspath(cwd), project_root]) == project_root:
                    return os.path.abspath(cwd)
                pass
        return path_policy.validate_write(default_dir, allow_create_dirs=False)


terminal_manager = TerminalManager()


class ExecuteCommandTool(BaseTool):
    def _define_schema(self) -> ToolSchema:
        return ToolSchema(
            name="terminal.execute",
            description="Execute a command in the terminal (restricted to allowlist)",
            category=ToolCategory.TERMINAL,
            parameters=[
                ToolParameter(name="command", type="string", description="Command to execute", required=True),
                ToolParameter(name="cwd", type="string", description="Working directory", required=False, default="."),
                ToolParameter(name="timeout", type="integer", description="Timeout in seconds", required=False, default=30),
                ToolParameter(name="env", type="object", description="Environment variables", required=False),
            ],
            risk_level="MODERATE",
            requires_approval=True,
            idempotent=False,
            examples=[
                {"command": "python -m pytest tests/", "cwd": "./data/workspace"},
                {"command": "git status", "cwd": "./data/workspace"},
                {"command": "npm test", "cwd": "./data/workspace"},
            ]
        )
    
    async def execute(self, arguments: Dict[str, Any], context: Dict = None) -> ToolResult:
        command = arguments["command"]
        cwd = arguments.get("cwd", ".")
        timeout = arguments.get("timeout", 30)
        env = arguments.get("env", {})
        
        # Check if command is allowed
        allowed, reason = terminal_manager.is_allowed(command)
        if not allowed:
            return ToolResult(success=False, error=f"Command not allowed: {reason}")
        
        try:
            work_dir = terminal_manager.get_working_dir(cwd)
            
            # Prepare environment
            full_env = os.environ.copy()
            full_env.update(env)
            
# Run command - use shell for builtins
            import platform
            if platform.system() == "Windows":
                # On Windows, use cmd /c for shell builtins
                shell_command = f'cmd /c {command}'
                process = await asyncio.create_subprocess_shell(
                    shell_command,
                    cwd=work_dir,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    env=full_env
                )
            else:
                process = await asyncio.create_subprocess_shell(
                    command,
                    cwd=work_dir,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    env=full_env
                )
            
            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(),
                    timeout=timeout
                )
            except asyncio.TimeoutError:
                process.kill()
                await process.wait()
                return ToolResult(success=False, error=f"Command timed out after {timeout} seconds")
            
            stdout_text = stdout.decode("utf-8", errors="replace")
            stderr_text = stderr.decode("utf-8", errors="replace")
            
            return ToolResult(success=process.returncode == 0, data={
                "command": command,
                "cwd": work_dir,
                "returncode": process.returncode,
                "stdout": stdout_text,
                "stderr": stderr_text,
                "truncated": len(stdout_text) > 10000 or len(stderr_text) > 10000
            })
            
        except Exception as e:
            return ToolResult(success=False, error=f"Command execution failed: {str(e)}")


class RunPythonTool(BaseTool):
    def _define_schema(self) -> ToolSchema:
        return ToolSchema(
            name="terminal.run_python",
            description="Run a Python script or command",
            category=ToolCategory.CODING,
            parameters=[
                ToolParameter(name="code", type="string", description="Python code to execute", required=False),
                ToolParameter(name="file", type="string", description="Python file to run", required=False),
                ToolParameter(name="args", type="array", items={"type": "string"}, description="Arguments to pass to script", required=False),
                ToolParameter(name="cwd", type="string", description="Working directory", required=False, default="."),
                ToolParameter(name="timeout", type="integer", description="Timeout in seconds", required=False, default=60),
            ],
            risk_level="MODERATE",
            requires_approval=True,
            idempotent=False,
            examples=[
                {"code": "print('Hello from Python')"},
                {"file": "./data/workspace/script.py", "args": ["arg1", "arg2"]}
            ]
        )
    
    async def execute(self, arguments: Dict[str, Any], context: Dict = None) -> ToolResult:
        code = arguments.get("code")
        file = arguments.get("file")
        args = arguments.get("args", [])
        cwd = arguments.get("cwd", ".")
        timeout = arguments.get("timeout", 60)
        
        if not code and not file:
            return ToolResult(success=False, error="Either code or file must be provided")
        
        try:
            work_dir = terminal_manager.get_working_dir(cwd)
            
            if code:
                # Write code to temp file
                import tempfile
                import os
                # Use allowed workspace directory
                from app.config import settings
                workspace = settings.allowed_directories[0] if settings.allowed_directories else "./data/workspace"
                # Ensure workspace is absolute
                workspace = os.path.abspath(workspace)
                with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False, dir=workspace) as f:
                    f.write(code)
                    temp_file = f.name
                file_to_run = temp_file
                cleanup_temp = True
            else:
                file_to_run = file
                cleanup_temp = False
            
            # Validate file path
            try:
                resolved_file = path_policy.validate_read(file_to_run)
            except PermissionError as e:
                return ToolResult(success=False, error=str(e))
            except FileNotFoundError as e:
                return ToolResult(success=False, error=str(e))
            
# Build command - use shell form with proper Windows path handling
            cmd_parts = ["python", resolved_file] + args
            # On Windows, use shell with proper quoting
            import platform
            if platform.system() == "Windows":
                # Windows needs quoted paths with spaces
                command = " ".join(f'"{p}"' if " " in p else p for p in cmd_parts)
                process = await asyncio.create_subprocess_shell(
                    command,
                    cwd=work_dir,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    env=os.environ.copy()
                )
            else:
                command = cmd_parts  # Use list form
                process = await asyncio.create_subprocess_exec(
                    *command,
                    cwd=work_dir,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    env=os.environ.copy()
                )
            
            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(),
                    timeout=timeout
                )
            except asyncio.TimeoutError:
                process.kill()
                await process.wait()
                return ToolResult(success=False, error=f"Python script timed out after {timeout} seconds")
            
            stdout_text = stdout.decode("utf-8", errors="replace")
            stderr_text = stderr.decode("utf-8", errors="replace")
            
            # Cleanup temp file
            if cleanup_temp:
                try:
                    os.unlink(temp_file)
                except Exception:
                    pass
            
            return ToolResult(success=process.returncode == 0, data={
                "command": command,
                "cwd": work_dir,
                "returncode": process.returncode,
                "stdout": stdout_text,
                "stderr": stderr_text,
            })
            
        except Exception as e:
            return ToolResult(success=False, error=f"Python execution failed: {str(e)}")


class RunTestsTool(BaseTool):
    def _define_schema(self) -> ToolSchema:
        return ToolSchema(
            name="terminal.run_tests",
            description="Run tests using pytest",
            category=ToolCategory.CODING,
            parameters=[
                ToolParameter(name="path", type="string", description="Test path (file or directory)", required=False, default="."),
                ToolParameter(name="pattern", type="string", description="Test pattern (e.g., 'test_*.py')", required=False),
                ToolParameter(name="cwd", type="string", description="Working directory", required=False, default="."),
                ToolParameter(name="timeout", type="integer", description="Timeout in seconds", required=False, default=120),
                ToolParameter(name="verbose", type="boolean", description="Verbose output", required=False, default=True),
            ],
            risk_level="MODERATE",
            requires_approval=True,
            idempotent=True,
            examples=[{"path": "./data/workspace/tests", "verbose": True}]
        )
    
    async def execute(self, arguments: Dict[str, Any], context: Dict = None) -> ToolResult:
        path = arguments.get("path", ".")
        pattern = arguments.get("pattern")
        cwd = arguments.get("cwd", ".")
        timeout = arguments.get("timeout", 120)
        verbose = arguments.get("verbose", True)
        
        try:
            work_dir = terminal_manager.get_working_dir(cwd)
            
            # Build pytest command
            cmd = ["python", "-m", "pytest"]
            if verbose:
                cmd.append("-v")
            if pattern:
                cmd.extend(["-k", pattern])
            cmd.append(path)
            
            command = " ".join(shlex.quote(p) for p in cmd)
            
            process = await asyncio.create_subprocess_shell(
                command,
                cwd=work_dir,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=os.environ.copy()
            )
            
            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(),
                    timeout=timeout
                )
            except asyncio.TimeoutError:
                process.kill()
                await process.wait()
                return ToolResult(success=False, error=f"Tests timed out after {timeout} seconds")
            
            stdout_text = stdout.decode("utf-8", errors="replace")
            stderr_text = stderr.decode("utf-8", errors="replace")
            
            return ToolResult(success=process.returncode == 0, data={
                "command": command,
                "cwd": work_dir,
                "returncode": process.returncode,
                "stdout": stdout_text,
                "stderr": stderr_text,
                "passed": process.returncode == 0
            })
            
        except Exception as e:
            return ToolResult(success=False, error=f"Test execution failed: {str(e)}")


class LintTool(BaseTool):
    def _define_schema(self) -> ToolSchema:
        return ToolSchema(
            name="terminal.lint",
            description="Run linting/formatting tools",
            category=ToolCategory.CODING,
            parameters=[
                ToolParameter(name="tool", type="string", description="Linting tool (ruff, black, mypy)", required=True, enum=["ruff", "black", "mypy"]),
                ToolParameter(name="path", type="string", description="Path to lint", required=False, default="."),
                ToolParameter(name="fix", type="boolean", description="Auto-fix issues (for ruff/black)", required=False, default=False),
                ToolParameter(name="cwd", type="string", description="Working directory", required=False, default="."),
                ToolParameter(name="timeout", type="integer", description="Timeout in seconds", required=False, default=60),
            ],
            risk_level="MODERATE",
            requires_approval=True,
            idempotent=False,
            examples=[{"tool": "ruff", "path": "./data/workspace", "fix": True}]
        )
    
    async def execute(self, arguments: Dict[str, Any], context: Dict = None) -> ToolResult:
        tool = arguments["tool"]
        path = arguments.get("path", ".")
        fix = arguments.get("fix", False)
        cwd = arguments.get("cwd", ".")
        timeout = arguments.get("timeout", 60)
        
        try:
            work_dir = terminal_manager.get_working_dir(cwd)
            
            if tool == "ruff":
                cmd = ["ruff", "check"]
                if fix:
                    cmd.append("--fix")
                cmd.append(path)
            elif tool == "black":
                cmd = ["black"]
                if not fix:
                    cmd.append("--check")
                cmd.append(path)
            elif tool == "mypy":
                cmd = ["mypy", path]
            else:
                return ToolResult(success=False, error=f"Unknown linting tool: {tool}")
            
            command = " ".join(shlex.quote(p) for p in cmd)
            
            process = await asyncio.create_subprocess_shell(
                command,
                cwd=work_dir,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=os.environ.copy()
            )
            
            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(),
                    timeout=timeout
                )
            except asyncio.TimeoutError:
                process.kill()
                await process.wait()
                return ToolResult(success=False, error=f"Linting timed out after {timeout} seconds")
            
            stdout_text = stdout.decode("utf-8", errors="replace")
            stderr_text = stderr.decode("utf-8", errors="replace")
            
            return ToolResult(success=process.returncode == 0, data={
                "tool": tool,
                "command": command,
                "cwd": work_dir,
                "returncode": process.returncode,
                "stdout": stdout_text,
                "stderr": stderr_text,
            })
            
        except Exception as e:
            return ToolResult(success=False, error=f"Linting failed: {str(e)}")


class GitTool(BaseTool):
    def _define_schema(self) -> ToolSchema:
        return ToolSchema(
            name="terminal.git",
            description="Execute Git commands (restricted to safe operations)",
            category=ToolCategory.CODING,
            parameters=[
                ToolParameter(name="subcommand", type="string", description="Git subcommand", required=True, enum=["status", "diff", "log", "add", "commit", "push", "pull", "branch", "checkout", "show", "status"]),
                ToolParameter(name="args", type="array", items={"type": "string"}, description="Additional arguments", required=False),
                ToolParameter(name="cwd", type="string", description="Working directory (must be a git repo)", required=False, default="."),
                ToolParameter(name="timeout", type="integer", description="Timeout in seconds", required=False, default=30),
            ],
            risk_level="MODERATE",
            requires_approval=True,
            idempotent=False,
            examples=[{"subcommand": "status"}, {"subcommand": "diff", "args": ["HEAD~1"]}]
        )
    
    async def execute(self, arguments: Dict[str, Any], context: Dict = None) -> ToolResult:
        subcommand = arguments["subcommand"]
        args = arguments.get("args", [])
        cwd = arguments.get("cwd", ".")
        timeout = arguments.get("timeout", 30)
        
        # Restrict dangerous git operations
        dangerous = ["reset", "rebase", "cherry-pick", "filter-branch", "gc", "prune", "clean"]
        if subcommand in dangerous:
            return ToolResult(success=False, error=f"Git subcommand not allowed: {subcommand}")
        
        # Commit requires message
        if subcommand == "commit":
            has_message = any(a.startswith("-m") or a.startswith("--message") for a in args)
            if not has_message:
                return ToolResult(success=False, error="Git commit requires -m message")
        
        try:
            work_dir = terminal_manager.get_working_dir(cwd)
            
            cmd = ["git", subcommand] + args
            command = " ".join(shlex.quote(p) for p in cmd)
            
            process = await asyncio.create_subprocess_shell(
                command,
                cwd=work_dir,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=os.environ.copy()
            )
            
            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(),
                    timeout=timeout
                )
            except asyncio.TimeoutError:
                process.kill()
                await process.wait()
                return ToolResult(success=False, error=f"Git command timed out after {timeout} seconds")
            
            stdout_text = stdout.decode("utf-8", errors="replace")
            stderr_text = stderr.decode("utf-8", errors="replace")
            
            return ToolResult(success=process.returncode == 0, data={
                "command": command,
                "cwd": work_dir,
                "returncode": process.returncode,
                "stdout": stdout_text,
                "stderr": stderr_text,
            })
            
        except Exception as e:
            return ToolResult(success=False, error=f"Git command failed: {str(e)}")


def register_terminal_tools(registry):
    registry.register(ExecuteCommandTool())
    registry.register(RunPythonTool())
    registry.register(RunTestsTool())
    registry.register(LintTool())
    registry.register(GitTool())