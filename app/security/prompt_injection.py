"""Prompt injection defense and security utilities"""
import re
import hashlib
from typing import Dict, Any, List, Optional, Set
from dataclasses import dataclass, field
from enum import Enum


class ThreatType(str, Enum):
    PROMPT_INJECTION = "prompt_injection"
    COMMAND_INJECTION = "command_injection"
    PATH_TRAVERSAL = "path_traversal"
    SSRF = "ssrf"
    DATA_EXFILTRATION = "data_exfiltration"
    PRIVILEGE_ESCALATION = "privilege_escalation"
    SENSITIVE_DATA_EXPOSURE = "sensitive_data_exposure"


class RiskLevel(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


@dataclass
class SecurityThreat:
    threat_type: ThreatType
    risk_level: RiskLevel
    description: str
    indicators: List[str] = field(default_factory=list)
    mitigated: bool = False
    mitigation: str = ""


# Known prompt injection patterns
PROMPT_INJECTION_PATTERNS = [
    r"ignore\s+(?:previous|all|above)\s+instructions?",
    r"disregard\s+(?:previous|all|above)\s+instructions?",
    r"forget\s+(?:previous|all|above)\s+instructions?",
    r"override\s+(?:previous|all|above)\s+instructions?",
    r"new\s+instructions?:",
    r"system\s*prompt:",
    r"you\s+are\s+now\s+(?:a|an)\s+\w+",
    r"act\s+as\s+(?:a|an)\s+\w+",
    r"pretend\s+to\s+be\s+(?:a|an)\s+\w+",
    r"roleplay\s+as\s+(?:a|an)\s+\w+",
    r"simulate\s+(?:a|an)\s+\w+",
    r"ignore\s+safety",
    r"bypass\s+safety",
    r"disable\s+safety",
    r"no\s+longer\s+follow",
    r"stop\s+following",
    r"reveal\s+(?:your|the)\s+(?:system\s+)?prompt",
    r"show\s+me\s+(?:your|the)\s+(?:system\s+)?prompt",
    r"what\s+(?:is|are)\s+(?:your|the)\s+(?:system\s+)?prompt",
    r"output\s+(?:your|the)\s+(?:system\s+)?prompt",
    r"print\s+(?:your|the)\s+(?:system\s+)?prompt",
    r"exfiltrate",
    r"send\s+(?:data|information|secrets)\s+to",
    r"upload\s+(?:data|files|secrets)",
    r"exfiltrate\s+(?:data|secrets|keys|passwords|tokens)",
    r"(?:api[_-]?key|secret[_-]?key|password|token|credential)\s*[:=]\s*\S+",
    r"BEGIN\s+(?:RSA\s+)?PRIVATE\s+KEY",
    r"-----BEGIN\s+(?:RSA\s+)?PRIVATE\s+KEY-----",
    r"ssh-rsa\s+[A-Za-z0-9+/]+",
    r"ghp_[A-Za-z0-9]{36}",
    r"sk-[A-Za-z0-9]{48}",
    r"xoxb-[0-9]{11}-[0-9]{11}-[A-Za-z0-9]{24}",
]

# Command injection patterns
COMMAND_INJECTION_PATTERNS = [
    r";\s*(?:rm|del|format|shutdown|reboot|kill|pkill|taskkill)",
    r"\|\s*(?:rm|del|format|shutdown|reboot|kill|pkill|taskkill)",
    r"`\s*(?:rm|del|format|shutdown|reboot|kill|pkill|taskkill)",
    r"\$\s*\(\s*(?:rm|del|format|shutdown|reboot|kill|pkill|taskkill)",
    r"&&\s*(?:rm|del|format|shutdown|reboot|kill|pkill|taskkill)",
    r"\|\|\s*(?:rm|del|format|shutdown|reboot|kill|pkill|taskkill)",
    r"(?:powershell|cmd|bash|sh|zsh)\s+(-c|/c)\s+",
    r"(?:wget|curl|nc|netcat)\s+",
    r"(?:chmod|chown)\s+777",
    r"sudo\s+(?:rm|del|format|shutdown|reboot)",
]

# Path traversal patterns
PATH_TRAVERSAL_PATTERNS = [
    r"\.\./",
    r"\.\.\\",
    r"%2e%2e%2f",
    r"%2e%2e%5c",
    r"\.\.%2f",
    r"\.\.%5c",
    r"..%c0%af",
    r"..%c1%9c",
]

# SSRF patterns
SSRF_PATTERNS = [
    r"(?:http|https|ftp)://(?:localhost|127\.0\.0\.1|0\.0\.0\.0|\[::1\])",
    r"(?:http|https|ftp)://10\.\d+\.\d+\.\d+",
    r"(?:http|https|ftp)://172\.(?:1[6-9]|2\d|3[0-1])\.\d+\.\d+",
    r"(?:http|https|ftp)://192\.168\.\d+\.\d+",
    r"(?:http|https|ftp)://169\.254\.\d+\.\d+",
    r"(?:http|https|ftp)://(?:metadata|metadata\.google\.internal|169\.254\.169\.254)",
    r"(?:http|https|ftp)://(?:instance-data|instance-data\.google\.internal)",
]

# Sensitive data patterns
SENSITIVE_DATA_PATTERNS = [
    r"(?:api[_-]?key|secret[_-]?key|password|token|credential|auth[_-]?token)\s*[:=]\s*\S{8,}",
    r"-----BEGIN\s+(?:RSA\s+)?PRIVATE\s+KEY-----",
    r"ssh-rsa\s+[A-Za-z0-9+/]+={0,2}",
    r"ghp_[A-Za-z0-9]{36}",
    r"sk-[A-Za-z0-9]{32,}",
    r"xoxb-[0-9]{11}-[0-9]{11}-[A-Za-z0-9]{24}",
    r"ya29\.[A-Za-z0-9_-]+",
    r"Bearer\s+[A-Za-z0-9_.-]{20,}",
    r"\b\d{4}[-\s]?\d{4}[-\s]?\d{4}[-\s]?\d{4}\b",  # Credit card
    r"\b\d{3}-\d{2}-\d{4}\b",  # SSN
]


class PromptInjectionDefense:
    """Detects and mitigates prompt injection attacks"""
    
    def __init__(self):
        self.compiled_patterns = {
            ThreatType.PROMPT_INJECTION: [re.compile(p, re.IGNORECASE) for p in PROMPT_INJECTION_PATTERNS],
            ThreatType.COMMAND_INJECTION: [re.compile(p, re.IGNORECASE) for p in COMMAND_INJECTION_PATTERNS],
            ThreatType.PATH_TRAVERSAL: [re.compile(p, re.IGNORECASE) for p in PATH_TRAVERSAL_PATTERNS],
            ThreatType.SSRF: [re.compile(p, re.IGNORECASE) for p in SSRF_PATTERNS],
            ThreatType.SENSITIVE_DATA_EXPOSURE: [re.compile(p, re.IGNORECASE) for p in SENSITIVE_DATA_PATTERNS],
        }
    
    def scan(self, text: str, context: str = "input") -> List[SecurityThreat]:
        """Scan text for security threats"""
        threats = []
        
        for threat_type, patterns in self.compiled_patterns.items():
            for pattern in patterns:
                matches = pattern.findall(text)
                if matches:
                    risk = self._assess_risk(threat_type, matches, context)
                    threats.append(SecurityThreat(
                        threat_type=threat_type,
                        risk_level=risk,
                        description=f"{threat_type.value} detected in {context}",
                        indicators=[str(m)[:100] for m in matches[:5]],
                        mitigation=self._get_mitigation(threat_type)
                    ))
        
        return threats
    
    def _assess_risk(self, threat_type: ThreatType, matches: List, context: str) -> RiskLevel:
        """Assess risk level based on threat type and context"""
        if threat_type in (ThreatType.PROMPT_INJECTION, ThreatType.COMMAND_INJECTION):
            return RiskLevel.CRITICAL
        elif threat_type in (ThreatType.SENSITIVE_DATA_EXPOSURE, ThreatType.PRIVILEGE_ESCALATION):
            return RiskLevel.HIGH
        elif threat_type == ThreatType.SSRF:
            return RiskLevel.HIGH
        elif threat_type == ThreatType.PATH_TRAVERSAL:
            return RiskLevel.MEDIUM
        return RiskLevel.LOW
    
    def _get_mitigation(self, threat_type: ThreatType) -> str:
        """Get mitigation strategy for threat type"""
        mitigations = {
            ThreatType.PROMPT_INJECTION: "Input sanitized; instruction hierarchy enforced; external content treated as data only",
            ThreatType.COMMAND_INJECTION: "Command allowlist enforced; shell injection prevented; arguments validated",
            ThreatType.PATH_TRAVERSAL: "Path canonicalization and allowlist validation applied",
            ThreatType.SSRF: "URL allowlist enforced; private IP ranges blocked; DNS rebinding protection",
            ThreatType.DATA_EXFILTRATION: "Output filtering; data loss prevention; no unauthorized external requests",
            ThreatType.PRIVILEGE_ESCALATION: "Role-based access control; principle of least privilege; action approval required",
            ThreatType.SENSITIVE_DATA_EXPOSURE: "Automatic redaction; secret scanning; secure credential storage",
        }
        return mitigations.get(threat_type, "Standard security controls applied")
    
    def sanitize_for_logging(self, text: str) -> str:
        """Redact sensitive information for safe logging"""
        sanitized = text
        for pattern in self.compiled_patterns[ThreatType.SENSITIVE_DATA_EXPOSURE]:
            sanitized = pattern.sub("[REDACTED]", sanitized)
        return sanitized
    
    def is_safe_for_model(self, text: str, context: str = "input") -> tuple[bool, List[SecurityThreat]]:
        """Check if text is safe to send to model"""
        threats = self.scan(text, context)
        critical_threats = [t for t in threats if t.risk_level == RiskLevel.CRITICAL]
        return len(critical_threats) == 0, threats


class ContentTrustBoundary:
    """Enforces trust boundaries between different content sources"""
    
    def __init__(self):
        self.defense = PromptInjectionDefense()
        self.trust_levels = {
            "system": 100,      # Highest trust - system prompts
            "user": 90,         # High trust - direct user input
            "tool_output": 70,  # Medium trust - tool results
            "web_content": 30,  # Low trust - scraped web content
            "file_content": 50, # Medium trust - local files
            "external": 10,     # Lowest trust - external APIs, emails, etc.
        }
    
    def get_trust_level(self, source: str) -> int:
        return self.trust_levels.get(source, 0)
    
    def can_override(self, source_a: str, source_b: str) -> bool:
        """Check if source_a can override instructions from source_b"""
        return self.get_trust_level(source_a) > self.get_trust_level(source_b)
    
    def sanitize_external_content(self, content: str, source: str) -> str:
        """Sanitize content from external sources"""
        if source in ("web_content", "external", "file_content"):
            safe, threats = self.defense.is_safe_for_model(content, source)
            if not safe:
                # Log threats but don't expose them
                return "[CONTENT FILTERED - Potential security threat detected]"
        return content


class SecretRedactor:
    """Redacts secrets from logs and outputs"""
    
    def __init__(self):
        self.patterns = [
            (re.compile(r'(api[_-]?key|secret[_-]?key|password|token|credential)\s*[:=]\s*\S+', re.IGNORECASE), 
             lambda m: f"{m.group(1)}=[REDACTED]"),
            (re.compile(r'(password|passwd|pwd)\s*[:=]\s*\S+', re.IGNORECASE), 
             lambda m: f"{m.group(1)}=[REDACTED]"),
            (re.compile(r'password\s+is\s+\S+', re.IGNORECASE), 
             lambda m: "password is [REDACTED]"),
            (re.compile(r'Bearer\s+[A-Za-z0-9_.-]{10,}'), lambda m: "Bearer [REDACTED]"),
            (re.compile(r'ghp_[A-Za-z0-9]{36}'), lambda m: "[REDACTED_GITHUB_TOKEN]"),
            (re.compile(r'sk-[A-Za-z0-9]{10,}'), lambda m: "[REDACTED_OPENAI_KEY]"),
            (re.compile(r'xoxb-[0-9]{11}-[0-9]{11}-[A-Za-z0-9]{24}'), lambda m: "[REDACTED_SLACK_TOKEN]"),
            (re.compile(r'-----BEGIN\s+(?:RSA\s+)?PRIVATE\s+KEY-----[\s\S]*?-----END\s+(?:RSA\s+)?PRIVATE\s+KEY-----'), 
             lambda m: "[REDACTED_PRIVATE_KEY]"),
            (re.compile(r'\b\d{4}[-\s]?\d{4}[-\s]?\d{4}[-\s]?\d{4}\b'), lambda m: "[REDACTED_CARD]"),
            (re.compile(r'\b\d{3}-\d{2}-\d{4}\b'), lambda m: "[REDACTED_SSN]"),
        ]
    
    def redact(self, text: str) -> str:
        """Redact secrets from text"""
        result = text
        for pattern, replacer in self.patterns:
            result = pattern.sub(replacer, result)
        return result
    
    def redact_dict(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Recursively redact secrets from dict"""
        if isinstance(data, dict):
            result = {}
            for k, v in data.items():
                # Check if key indicates secret
                key_lower = k.lower()
                if any(s in key_lower for s in ['password', 'secret', 'token', 'key', 'credential', 'auth']):
                    result[k] = "[REDACTED]"
                else:
                    result[k] = self.redact_dict(v)
            return result
        elif isinstance(data, list):
            return [self.redact_dict(v) for v in data]
        elif isinstance(data, str):
            return self.redact(data)
        return data


class URLValidator:
    """Validates URLs for SSRF protection"""
    
    PRIVATE_IP_RANGES = [
        "10.0.0.0/8",
        "172.16.0.0/12",
        "192.168.0.0/16",
        "127.0.0.0/8",
        "169.254.0.0/16",
        "::1/128",
        "fc00::/7",
    ]
    
    BLOCKED_HOSTS = {
        "localhost",
        "127.0.0.1",
        "0.0.0.0",
        "[::1]",
        "metadata",
        "metadata.google.internal",
        "169.254.169.254",
        "instance-data",
        "instance-data.google.internal",
    }
    
    def __init__(self, allowed_domains: List[str] = None, blocked_domains: List[str] = None):
        self.allowed_domains = set(allowed_domains or [])
        self.blocked_domains = set(blocked_domains or [])
    
    def is_valid(self, url: str) -> tuple[bool, str]:
        """Validate URL for SSRF protection"""
        try:
            from urllib.parse import urlparse
            import ipaddress
            
            parsed = urlparse(url)
            
            if parsed.scheme not in ("http", "https"):
                return False, f"Invalid scheme: {parsed.scheme}"
            
            hostname = parsed.hostname
            if not hostname:
                return False, "No hostname"
            
            # Check blocked hosts
            if hostname.lower() in self.BLOCKED_HOSTS:
                return False, f"Blocked host: {hostname}"
            
            # Check if IP address is private
            try:
                ip = ipaddress.ip_address(hostname)
                if ip.is_private or ip.is_loopback or ip.is_link_local:
                    return False, f"Private IP not allowed: {hostname}"
            except ValueError:
                # Not an IP, check domain
                pass
            
            # Check allowed/blocked domains
            if self.allowed_domains:
                allowed = any(hostname.endswith(d) for d in self.allowed_domains)
                if not allowed:
                    return False, f"Domain not in allowlist: {hostname}"
            
            if any(hostname.endswith(d) for d in self.blocked_domains):
                return False, f"Domain in blocklist: {hostname}"
            
            return True, "Valid"
            
        except Exception as e:
            return False, f"Validation error: {str(e)}"


# Global instances
prompt_injection_defense = PromptInjectionDefense()
content_trust_boundary = ContentTrustBoundary()
secret_redactor = SecretRedactor()
url_validator = URLValidator()