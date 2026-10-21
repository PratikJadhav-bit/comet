import os
from pathlib import Path
from typing import List, Optional
from app.config import get_allowed_directories


class PathPolicy:
    def __init__(self, allowed_dirs: List[str] = None, blocked_dirs: List[str] = None):
        self.allowed_dirs = [os.path.abspath(d) for d in (allowed_dirs or get_allowed_directories())]
        self.blocked_dirs = [os.path.abspath(d) for d in (blocked_dirs or [])]
        self._add_default_blocked()

    def _add_default_blocked(self):
        home = os.path.expanduser("~")
        defaults = [
            os.path.join(os.environ.get("SystemRoot", "C:\\Windows"), "System32"),
            os.path.join(os.environ.get("SystemRoot", "C:\\Windows"), "SysWOW64"),
            os.path.join(home, ".ssh"),
            os.path.join(home, ".gnupg"),
            os.path.join(home, "AppData", "Local", "Microsoft", "Windows"),
            os.path.join(home, "AppData", "Roaming", "Microsoft", "Windows"),
        ]
        for d in defaults:
            abs_d = os.path.abspath(d)
            if abs_d not in self.blocked_dirs:
                self.blocked_dirs.append(abs_d)

    def resolve_path(self, path: str, base_dir: str = None) -> str:
        if base_dir:
            base = os.path.abspath(base_dir)
        else:
            base = os.path.abspath(".")
        
        if os.path.isabs(path):
            resolved = os.path.normpath(path)
        else:
            resolved = os.path.normpath(os.path.join(base, path))
        
        return resolved

    def is_allowed(self, path: str) -> bool:
        abs_path = os.path.abspath(path)
        
        for blocked in self.blocked_dirs:
            try:
                if os.path.commonpath([abs_path, blocked]) == blocked:
                    return False
            except ValueError:
                pass
        
        if not self.allowed_dirs:
            return True
        
        for allowed in self.allowed_dirs:
            try:
                if os.path.commonpath([abs_path, allowed]) == allowed:
                    return True
            except ValueError:
                pass
        
        return False

    def validate_read(self, path: str) -> str:
        resolved = self.resolve_path(path)
        if not self.is_allowed(resolved):
            raise PermissionError(f"Read access denied: {resolved} is outside allowed directories")
        if not os.path.exists(resolved):
            raise FileNotFoundError(f"Path does not exist: {resolved}")
        return resolved

    def validate_write(self, path: str, allow_create_dirs: bool = True) -> str:
        resolved = self.resolve_path(path)
        if not self.is_allowed(resolved):
            raise PermissionError(f"Write access denied: {resolved} is outside allowed directories")
        
        parent = os.path.dirname(resolved)
        if not os.path.exists(parent):
            if allow_create_dirs and self.is_allowed(parent):
                os.makedirs(parent, exist_ok=True)
            else:
                raise PermissionError(f"Parent directory not allowed or does not exist: {parent}")
        
        return resolved

    def validate_delete(self, path: str) -> str:
        resolved = self.resolve_path(path)
        if not self.is_allowed(resolved):
            raise PermissionError(f"Delete access denied: {resolved} is outside allowed directories")
        if not os.path.exists(resolved):
            raise FileNotFoundError(f"Path does not exist: {resolved}")
        return resolved

    def list_allowed_roots(self) -> List[str]:
        return self.allowed_dirs.copy()


path_policy = PathPolicy()