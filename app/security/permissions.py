from enum import Enum
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Any
from pathlib import Path
import os


class RiskLevel(str, Enum):
    LOW = "LOW"
    MODERATE = "MODERATE"
    HIGH = "HIGH"


class ActionType(str, Enum):
    READ_FILE = "read_file"
    WRITE_FILE = "write_file"
    LIST_FILES = "list_files"
    SEARCH_FILES = "search_files"
    DELETE_FILE = "delete_file"
    MOVE_FILE = "move_file"
    READ_WEB = "read_web"
    NAVIGATE_WEB = "navigate_web"
    CLICK_WEB = "click_web"
    FILL_WEB = "fill_web"
    DOWNLOAD_WEB = "download_web"
    SUBMIT_FORM = "submit_form"
    RUN_CODE = "run_code"
    RUN_COMMAND = "run_command"
    INSTALL_PACKAGE = "install_package"
    LAUNCH_APP = "launch_app"
    CLICK_DESKTOP = "click_desktop"
    TYPE_DESKTOP = "type_desktop"
    SEND_EMAIL = "send_email"
    SEND_MESSAGE = "send_message"
    CALENDAR_WRITE = "calendar_write"
    FINANCIAL_ACTION = "financial_action"
    SYSTEM_CONFIG = "system_config"
    SCHEDULE_TASK = "schedule_task"


RISK_CLASSIFICATION: Dict[ActionType, RiskLevel] = {
    ActionType.READ_FILE: RiskLevel.LOW,
    ActionType.LIST_FILES: RiskLevel.LOW,
    ActionType.SEARCH_FILES: RiskLevel.LOW,
    ActionType.READ_WEB: RiskLevel.LOW,
    ActionType.NAVIGATE_WEB: RiskLevel.LOW,
    ActionType.WRITE_FILE: RiskLevel.MODERATE,
    ActionType.MOVE_FILE: RiskLevel.MODERATE,
    ActionType.CLICK_WEB: RiskLevel.MODERATE,
    ActionType.FILL_WEB: RiskLevel.MODERATE,
    ActionType.DOWNLOAD_WEB: RiskLevel.MODERATE,
    ActionType.RUN_CODE: RiskLevel.MODERATE,
    ActionType.RUN_COMMAND: RiskLevel.MODERATE,
    ActionType.INSTALL_PACKAGE: RiskLevel.MODERATE,
    ActionType.LAUNCH_APP: RiskLevel.MODERATE,
    ActionType.CLICK_DESKTOP: RiskLevel.MODERATE,
    ActionType.TYPE_DESKTOP: RiskLevel.MODERATE,
    ActionType.DELETE_FILE: RiskLevel.HIGH,
    ActionType.SUBMIT_FORM: RiskLevel.HIGH,
    ActionType.SEND_EMAIL: RiskLevel.HIGH,
    ActionType.SEND_MESSAGE: RiskLevel.HIGH,
    ActionType.CALENDAR_WRITE: RiskLevel.HIGH,
    ActionType.FINANCIAL_ACTION: RiskLevel.HIGH,
    ActionType.SYSTEM_CONFIG: RiskLevel.HIGH,
    ActionType.SCHEDULE_TASK: RiskLevel.HIGH,
}


@dataclass
class PermissionPolicy:
    allowed_directories: List[str] = field(default_factory=list)
    blocked_directories: List[str] = field(default_factory=list)
    allowed_tools: Set[str] = field(default_factory=set)
    blocked_tools: Set[str] = field(default_factory=set)
    allowed_domains: List[str] = field(default_factory=list)
    blocked_domains: List[str] = field(default_factory=list)
    allowed_commands: List[str] = field(default_factory=list)
    max_file_size_mb: int = 50
    require_approval_level2: bool = True
    require_approval_level3: bool = True
    approval_timeout_seconds: int = 300

    def is_directory_allowed(self, path: str) -> bool:
        abs_path = os.path.abspath(path)
        for blocked in self.blocked_directories:
            if abs_path.startswith(os.path.abspath(blocked)):
                return False
        if not self.allowed_directories:
            return True
        for allowed in self.allowed_directories:
            if abs_path.startswith(os.path.abspath(allowed)):
                return True
        return False

    def is_tool_allowed(self, tool_name: str) -> bool:
        if tool_name in self.blocked_tools:
            return False
        if not self.allowed_tools:
            return True
        return tool_name in self.allowed_tools

    def is_domain_allowed(self, domain: str) -> bool:
        domain = domain.lower()
        for blocked in self.blocked_domains:
            if domain.endswith(blocked.lower()):
                return False
        if not self.allowed_domains:
            return True
        for allowed in self.allowed_domains:
            if domain.endswith(allowed.lower()):
                return True
        return False

    def get_risk_level(self, action: ActionType) -> RiskLevel:
        return RISK_CLASSIFICATION.get(action, RiskLevel.HIGH)

    def requires_approval(self, action: ActionType) -> bool:
        risk = self.get_risk_level(action)
        if risk == RiskLevel.HIGH:
            return self.require_approval_level3
        if risk == RiskLevel.MODERATE:
            return self.require_approval_level2
        return False


DEFAULT_POLICY = PermissionPolicy(
    allowed_directories=["./data/workspace"],
    blocked_directories=[
        "C:\\Windows", "C:\\Program Files", "C:\\Program Files (x86)",
        "C:\\Users\\*\\AppData\\Local\\Microsoft\\Windows",
        "C:\\Users\\*\\.ssh", "C:\\Users\\*\\.gnupg"
    ],
    allowed_commands=["python", "pytest", "npm", "node", "git"],
    max_file_size_mb=50,
)


def get_default_policy() -> PermissionPolicy:
    return DEFAULT_POLICY