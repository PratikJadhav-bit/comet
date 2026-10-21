from dataclasses import dataclass, field
from typing import Dict, Any, Optional, List
from enum import Enum
from app.security.permissions import RiskLevel, ActionType, RISK_CLASSIFICATION


class RiskFactor(str, Enum):
    DESTRUCTIVE = "destructive"
    EXTERNAL_NETWORK = "external_network"
    AUTHENTICATION_REQUIRED = "authentication_required"
    FINANCIAL_IMPACT = "financial_impact"
    PRIVATE_DATA = "private_data"
    SYSTEM_MODIFICATION = "system_modification"
    IRREVERSIBLE = "irreversible"
    USER_DATA_MODIFICATION = "user_data_modification"
    EXECUTES_CODE = "executes_code"
    DOWNLOADS_FILE = "downloads_file"


@dataclass
class RiskAssessment:
    level: RiskLevel
    factors: List[RiskFactor] = field(default_factory=list)
    description: str = ""
    mitigation: str = ""
    requires_approval: bool = False
    reversible: bool = True


RISK_FACTORS: Dict[ActionType, List[RiskFactor]] = {
    ActionType.READ_FILE: [],
    ActionType.LIST_FILES: [],
    ActionType.SEARCH_FILES: [],
    ActionType.READ_WEB: [RiskFactor.EXTERNAL_NETWORK],
    ActionType.NAVIGATE_WEB: [RiskFactor.EXTERNAL_NETWORK],
    ActionType.WRITE_FILE: [RiskFactor.USER_DATA_MODIFICATION],
    ActionType.MOVE_FILE: [RiskFactor.USER_DATA_MODIFICATION, RiskFactor.IRREVERSIBLE],
    ActionType.CLICK_WEB: [RiskFactor.EXTERNAL_NETWORK, RiskFactor.USER_DATA_MODIFICATION],
    ActionType.FILL_WEB: [RiskFactor.EXTERNAL_NETWORK, RiskFactor.USER_DATA_MODIFICATION, RiskFactor.PRIVATE_DATA],
    ActionType.DOWNLOAD_WEB: [RiskFactor.EXTERNAL_NETWORK, RiskFactor.DOWNLOADS_FILE],
    ActionType.SUBMIT_FORM: [RiskFactor.EXTERNAL_NETWORK, RiskFactor.USER_DATA_MODIFICATION, RiskFactor.IRREVERSIBLE, RiskFactor.AUTHENTICATION_REQUIRED],
    ActionType.RUN_CODE: [RiskFactor.EXECUTES_CODE],
    ActionType.RUN_COMMAND: [RiskFactor.EXECUTES_CODE, RiskFactor.SYSTEM_MODIFICATION],
    ActionType.INSTALL_PACKAGE: [RiskFactor.EXECUTES_CODE, RiskFactor.SYSTEM_MODIFICATION, RiskFactor.EXTERNAL_NETWORK],
    ActionType.LAUNCH_APP: [RiskFactor.SYSTEM_MODIFICATION],
    ActionType.CLICK_DESKTOP: [RiskFactor.USER_DATA_MODIFICATION],
    ActionType.TYPE_DESKTOP: [RiskFactor.USER_DATA_MODIFICATION, RiskFactor.PRIVATE_DATA],
    ActionType.DELETE_FILE: [RiskFactor.DESTRUCTIVE, RiskFactor.IRREVERSIBLE, RiskFactor.USER_DATA_MODIFICATION],
    ActionType.SEND_EMAIL: [RiskFactor.EXTERNAL_NETWORK, RiskFactor.USER_DATA_MODIFICATION, RiskFactor.IRREVERSIBLE],
    ActionType.SEND_MESSAGE: [RiskFactor.EXTERNAL_NETWORK, RiskFactor.USER_DATA_MODIFICATION, RiskFactor.IRREVERSIBLE],
    ActionType.CALENDAR_WRITE: [RiskFactor.EXTERNAL_NETWORK, RiskFactor.USER_DATA_MODIFICATION, RiskFactor.AUTHENTICATION_REQUIRED],
    ActionType.FINANCIAL_ACTION: [RiskFactor.FINANCIAL_IMPACT, RiskFactor.IRREVERSIBLE, RiskFactor.AUTHENTICATION_REQUIRED, RiskFactor.EXTERNAL_NETWORK],
    ActionType.SYSTEM_CONFIG: [RiskFactor.SYSTEM_MODIFICATION, RiskFactor.IRREVERSIBLE],
    ActionType.SCHEDULE_TASK: [RiskFactor.SYSTEM_MODIFICATION, RiskFactor.EXECUTES_CODE],
}


def assess_risk(action: ActionType, context: Dict[str, Any] = None) -> RiskAssessment:
    base_level = RISK_CLASSIFICATION.get(action, RiskLevel.HIGH)
    factors = RISK_FACTORS.get(action, [RiskFactor.SYSTEM_MODIFICATION])
    
    description = f"Action: {action.value}"
    mitigation = ""
    reversible = True
    
    if RiskFactor.DESTRUCTIVE in factors:
        description += " - Permanently deletes data"
        reversible = False
    if RiskFactor.IRREVERSIBLE in factors:
        description += " - Cannot be automatically undone"
        reversible = False
    if RiskFactor.FINANCIAL_IMPACT in factors:
        description += " - May involve financial transactions"
        mitigation = "Require explicit user confirmation with amount verification"
    if RiskFactor.PRIVATE_DATA in factors:
        description += " - May access or transmit private/sensitive data"
        mitigation = "Review data being sent before approval"
    if RiskFactor.EXECUTES_CODE in factors:
        description += " - Executes arbitrary code or commands"
        mitigation = "Validate command against allowlist; run in isolated environment"
    if RiskFactor.EXTERNAL_NETWORK in factors:
        description += " - Communicates with external services"
        mitigation = "Verify destination domain is allowed"
    if RiskFactor.AUTHENTICATION_REQUIRED in factors:
        description += " - Requires authentication credentials"
        mitigation = "Never expose credentials to model; use secure credential store"
    
    if context:
        if context.get("is_bulk_operation"):
            factors.append(RiskFactor.USER_DATA_MODIFICATION)
            description += " - Bulk operation affecting multiple items"
        if context.get("target_system_path"):
            factors.append(RiskFactor.SYSTEM_MODIFICATION)
            description += " - Targets system directory"
    
    requires_approval = base_level in (RiskLevel.MODERATE, RiskLevel.HIGH)
    
    return RiskAssessment(
        level=base_level,
        factors=factors,
        description=description,
        mitigation=mitigation,
        requires_approval=requires_approval,
        reversible=reversible
    )