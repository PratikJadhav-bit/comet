import os
import json
import shutil
from pathlib import Path
from typing import Dict, Any, List
from app.tools.registry import BaseTool, ToolSchema, ToolParameter, ToolResult, ToolCategory
from app.security.path_policy import path_policy
from app.security.risk import assess_risk, RiskFactor
from app.security.permissions import ActionType


class ListFilesTool(BaseTool):
    def _define_schema(self) -> ToolSchema:
        return ToolSchema(
            name="list_files",
            description="List files and directories in a given path",
            category=ToolCategory.FILE,
            parameters=[
                ToolParameter(name="path", type="string", description="Directory path to list", required=False, default="."),
                ToolParameter(name="recursive", type="boolean", description="List recursively", required=False, default=False),
                ToolParameter(name="pattern", type="string", description="Glob pattern to filter files", required=False),
            ],
            risk_level="LOW",
            requires_approval=False,
            idempotent=True,
            examples=[{"path": "./data/workspace", "recursive": True}]
        )

    async def execute(self, arguments: Dict[str, Any], context: Dict = None) -> ToolResult:
        path = arguments.get("path", ".")
        recursive = arguments.get("recursive", False)
        pattern = arguments.get("pattern")

        try:
            resolved = path_policy.validate_read(path)
        except PermissionError as e:
            return ToolResult(success=False, error=str(e))
        except FileNotFoundError as e:
            return ToolResult(success=False, error=str(e))

        try:
            if recursive:
                files = []
                for root, dirs, filenames in os.walk(resolved):
                    for f in filenames:
                        if not pattern or Path(f).match(pattern):
                            full = os.path.join(root, f)
                            rel = os.path.relpath(full, resolved)
                            stat = os.stat(full)
                            files.append({
                                "path": rel,
                                "size": stat.st_size,
                                "modified": stat.st_mtime,
                                "is_dir": False
                            })
                    for d in dirs:
                        full = os.path.join(root, d)
                        rel = os.path.relpath(full, resolved)
                        stat = os.stat(full)
                        files.append({
                            "path": rel + "/",
                            "size": 0,
                            "modified": stat.st_mtime,
                            "is_dir": True
                        })
            else:
                files = []
                for entry in os.scandir(resolved):
                    if not pattern or Path(entry.name).match(pattern):
                        stat = entry.stat()
                        files.append({
                            "path": entry.name + ("/" if entry.is_dir() else ""),
                            "size": stat.st_size,
                            "modified": stat.st_mtime,
                            "is_dir": entry.is_dir()
                        })

            return ToolResult(success=True, data={"files": files, "base_path": resolved})
        except Exception as e:
            return ToolResult(success=False, error=f"Failed to list files: {str(e)}")


class ReadFileTool(BaseTool):
    def _define_schema(self) -> ToolSchema:
        return ToolSchema(
            name="read_file",
            description="Read the contents of a file",
            category=ToolCategory.FILE,
            parameters=[
                ToolParameter(name="path", type="string", description="File path to read", required=True),
                ToolParameter(name="encoding", type="string", description="File encoding", required=False, default="utf-8"),
                ToolParameter(name="max_size", type="integer", description="Maximum file size in bytes", required=False, default=1048576),
            ],
            risk_level="LOW",
            requires_approval=False,
            idempotent=True,
            examples=[{"path": "./data/workspace/report.md"}]
        )

    async def execute(self, arguments: Dict[str, Any], context: Dict = None) -> ToolResult:
        path = arguments["path"]
        encoding = arguments.get("encoding", "utf-8")
        max_size = arguments.get("max_size", 1048576)

        try:
            resolved = path_policy.validate_read(path)
        except PermissionError as e:
            return ToolResult(success=False, error=str(e))
        except FileNotFoundError as e:
            return ToolResult(success=False, error=str(e))

        try:
            stat = os.stat(resolved)
            if stat.st_size > max_size:
                return ToolResult(success=False, error=f"File too large: {stat.st_size} bytes (max {max_size})")

            with open(resolved, "r", encoding=encoding) as f:
                content = f.read()

            return ToolResult(success=True, data={
                "content": content,
                "path": resolved,
                "size": stat.st_size,
                "encoding": encoding
            })
        except UnicodeDecodeError:
            return ToolResult(success=False, error=f"File is not valid {encoding} text")
        except Exception as e:
            return ToolResult(success=False, error=f"Failed to read file: {str(e)}")


class WriteFileTool(BaseTool):
    def _define_schema(self) -> ToolSchema:
        return ToolSchema(
            name="write_file",
            description="Write content to a file (creates new or overwrites)",
            category=ToolCategory.FILE,
            parameters=[
                ToolParameter(name="path", type="string", description="File path to write", required=True),
                ToolParameter(name="content", type="string", description="Content to write", required=True),
                ToolParameter(name="encoding", type="string", description="File encoding", required=False, default="utf-8"),
                ToolParameter(name="create_dirs", type="boolean", description="Create parent directories if needed", required=False, default=True),
            ],
            risk_level="MODERATE",
            requires_approval=True,
            idempotent=False,
            examples=[{"path": "./data/workspace/output.txt", "content": "Hello World"}]
        )

    async def execute(self, arguments: Dict[str, Any], context: Dict = None) -> ToolResult:
        path = arguments["path"]
        content = arguments["content"]
        encoding = arguments.get("encoding", "utf-8")
        create_dirs = arguments.get("create_dirs", True)

        try:
            resolved = path_policy.validate_write(path, allow_create_dirs=create_dirs)
        except PermissionError as e:
            return ToolResult(success=False, error=str(e))

        try:
            with open(resolved, "w", encoding=encoding) as f:
                f.write(content)

            stat = os.stat(resolved)
            return ToolResult(success=True, data={
                "path": resolved,
                "size": stat.st_size,
                "bytes_written": len(content.encode(encoding))
            })
        except Exception as e:
            return ToolResult(success=False, error=f"Failed to write file: {str(e)}")


class CopyFileTool(BaseTool):
    def _define_schema(self) -> ToolSchema:
        return ToolSchema(
            name="copy_file",
            description="Copy a file or directory to a new location",
            category=ToolCategory.FILE,
            parameters=[
                ToolParameter(name="source", type="string", description="Source file/directory path", required=True),
                ToolParameter(name="destination", type="string", description="Destination path", required=True),
                ToolParameter(name="overwrite", type="boolean", description="Overwrite if destination exists", required=False, default=False),
            ],
            risk_level="MODERATE",
            requires_approval=True,
            idempotent=False,
            examples=[{"source": "./data/workspace/file.txt", "destination": "./data/workspace/file_copy.txt"}]
        )

    async def execute(self, arguments: Dict[str, Any], context: Dict = None) -> ToolResult:
        source = arguments["source"]
        destination = arguments["destination"]
        overwrite = arguments.get("overwrite", False)

        try:
            src_resolved = path_policy.validate_read(source)
        except PermissionError as e:
            return ToolResult(success=False, error=str(e))
        except FileNotFoundError as e:
            return ToolResult(success=False, error=str(e))

        try:
            dst_resolved = path_policy.validate_write(destination, allow_create_dirs=True)
        except PermissionError as e:
            return ToolResult(success=False, error=str(e))

        if os.path.exists(dst_resolved) and not overwrite:
            return ToolResult(success=False, error=f"Destination already exists: {dst_resolved}")

        try:
            if os.path.isdir(src_resolved):
                shutil.copytree(src_resolved, dst_resolved, dirs_exist_ok=overwrite)
            else:
                shutil.copy2(src_resolved, dst_resolved)
            
            stat = os.stat(dst_resolved)
            return ToolResult(success=True, data={
                "source": src_resolved,
                "destination": dst_resolved,
                "size": stat.st_size,
                "copied": True
            })
        except Exception as e:
            return ToolResult(success=False, error=f"Failed to copy: {str(e)}")


class MoveFileTool(BaseTool):
    def _define_schema(self) -> ToolSchema:
        return ToolSchema(
            name="move_file",
            description="Move/rename a file or directory",
            category=ToolCategory.FILE,
            parameters=[
                ToolParameter(name="source", type="string", description="Source file/directory path", required=True),
                ToolParameter(name="destination", type="string", description="Destination path", required=True),
                ToolParameter(name="overwrite", type="boolean", description="Overwrite if destination exists", required=False, default=False),
            ],
            risk_level="HIGH",
            requires_approval=True,
            idempotent=False,
            examples=[{"source": "./data/workspace/file.txt", "destination": "./data/workspace/moved_file.txt"}]
        )

    async def execute(self, arguments: Dict[str, Any], context: Dict = None) -> ToolResult:
        source = arguments["source"]
        destination = arguments["destination"]
        overwrite = arguments.get("overwrite", False)

        try:
            src_resolved = path_policy.validate_read(source)
        except PermissionError as e:
            return ToolResult(success=False, error=str(e))
        except FileNotFoundError as e:
            return ToolResult(success=False, error=str(e))

        try:
            dst_resolved = path_policy.validate_write(destination, allow_create_dirs=True)
        except PermissionError as e:
            return ToolResult(success=False, error=str(e))

        if os.path.exists(dst_resolved) and not overwrite:
            return ToolResult(success=False, error=f"Destination already exists: {dst_resolved}")

        try:
            shutil.move(src_resolved, dst_resolved)
            return ToolResult(success=True, data={
                "source": src_resolved,
                "destination": dst_resolved,
                "moved": True
            })
        except Exception as e:
            return ToolResult(success=False, error=f"Failed to move: {str(e)}")


class DeleteFileTool(BaseTool):
    def _define_schema(self) -> ToolSchema:
        return ToolSchema(
            name="delete_file",
            description="Delete a file or directory (HIGH RISK - irreversible)",
            category=ToolCategory.FILE,
            parameters=[
                ToolParameter(name="path", type="string", description="File/directory path to delete", required=True),
                ToolParameter(name="recursive", type="boolean", description="Delete directories recursively", required=False, default=False),
            ],
            risk_level="HIGH",
            requires_approval=True,
            idempotent=False,
            examples=[{"path": "./data/workspace/old_file.txt"}]
        )

    async def execute(self, arguments: Dict[str, Any], context: Dict = None) -> ToolResult:
        path = arguments["path"]
        recursive = arguments.get("recursive", False)

        try:
            resolved = path_policy.validate_delete(path)
        except PermissionError as e:
            return ToolResult(success=False, error=str(e))
        except FileNotFoundError as e:
            return ToolResult(success=False, error=str(e))

        try:
            if os.path.isdir(resolved):
                if recursive:
                    shutil.rmtree(resolved)
                else:
                    os.rmdir(resolved)
            else:
                os.remove(resolved)
            
            return ToolResult(success=True, data={
                "path": resolved,
                "deleted": True
            })
        except Exception as e:
            return ToolResult(success=False, error=f"Failed to delete: {str(e)}")


class CreateDirectoryTool(BaseTool):
    def _define_schema(self) -> ToolSchema:
        return ToolSchema(
            name="create_directory",
            description="Create a new directory (and parent directories if needed)",
            category=ToolCategory.FILE,
            parameters=[
                ToolParameter(name="path", type="string", description="Directory path to create", required=True),
            ],
            risk_level="LOW",
            requires_approval=False,
            idempotent=True,
            examples=[{"path": "./data/workspace/new_folder/subfolder"}]
        )

    async def execute(self, arguments: Dict[str, Any], context: Dict = None) -> ToolResult:
        path = arguments["path"]

        try:
            resolved = path_policy.validate_write(path, allow_create_dirs=True)
        except PermissionError as e:
            return ToolResult(success=False, error=str(e))

        try:
            os.makedirs(resolved, exist_ok=True)
            return ToolResult(success=True, data={
                "path": resolved,
                "created": True
            })
        except Exception as e:
            return ToolResult(success=False, error=f"Failed to create directory: {str(e)}")


class GetFileInfoTool(BaseTool):
    def _define_schema(self) -> ToolSchema:
        return ToolSchema(
            name="get_file_info",
            description="Get detailed information about a file or directory",
            category=ToolCategory.FILE,
            parameters=[
                ToolParameter(name="path", type="string", description="File/directory path", required=True),
            ],
            risk_level="LOW",
            requires_approval=False,
            idempotent=True,
            examples=[{"path": "./data/workspace/test.txt"}]
        )

    async def execute(self, arguments: Dict[str, Any], context: Dict = None) -> ToolResult:
        path = arguments["path"]

        try:
            resolved = path_policy.validate_read(path)
        except PermissionError as e:
            return ToolResult(success=False, error=str(e))
        except FileNotFoundError as e:
            return ToolResult(success=False, error=str(e))

        try:
            stat = os.stat(resolved)
            return ToolResult(success=True, data={
                "path": resolved,
                "name": os.path.basename(resolved),
                "size": stat.st_size,
                "modified": stat.st_mtime,
                "created": stat.st_ctime,
                "is_file": os.path.isfile(resolved),
                "is_dir": os.path.isdir(resolved),
                "extension": os.path.splitext(resolved)[1] if os.path.isfile(resolved) else "",
                "permissions": oct(stat.st_mode)[-3:],
            })
        except Exception as e:
            return ToolResult(success=False, error=f"Failed to get file info: {str(e)}")


def register_file_tools(registry):
    registry.register(ListFilesTool())
    registry.register(ReadFileTool())
    registry.register(WriteFileTool())
    registry.register(CopyFileTool())
    registry.register(MoveFileTool())
    registry.register(DeleteFileTool())
    registry.register(CreateDirectoryTool())
    registry.register(GetFileInfoTool())