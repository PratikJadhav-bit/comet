from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, Callable, Awaitable
from enum import Enum
import inspect
import json
import re


class ToolCategory(str, Enum):
    FILE = "file"
    BROWSER = "browser"
    DESKTOP = "desktop"
    RESEARCH = "research"
    CODING = "coding"
    SYSTEM = "system"
    COMMUNICATION = "communication"
    MEMORY = "memory"
    TERMINAL = "terminal"


class ToolParameterType(str, Enum):
    STRING = "string"
    INTEGER = "integer"
    NUMBER = "number"
    BOOLEAN = "boolean"
    ARRAY = "array"
    OBJECT = "object"


@dataclass
class ToolParameter:
    name: str
    type: str  # Use string for flexibility with different providers
    description: str
    required: bool = True
    default: Any = None
    enum: List[Any] = field(default_factory=list)
    items: Optional["ToolParameter"] = None  # For array types
    properties: Optional[Dict[str, "ToolParameter"]] = None  # For object types
    
    def to_json_schema(self) -> Dict[str, Any]:
        """Convert to JSON Schema format"""
        schema = {"type": self.type, "description": self.description}
        if self.enum:
            schema["enum"] = self.enum
        if self.default is not None:
            schema["default"] = self.default
        if self.type == "array" and self.items:
            schema["items"] = self.items.to_json_schema()
        if self.type == "object" and self.properties:
            schema["properties"] = {k: v.to_json_schema() for k, v in self.properties.items()}
            schema["required"] = [k for k, v in self.properties.items() if v.required]
        return schema


@dataclass
class ToolSchema:
    name: str
    description: str
    category: ToolCategory
    parameters: List[ToolParameter] = field(default_factory=list)
    risk_level: str = "LOW"
    requires_approval: bool = False
    idempotent: bool = False
    examples: List[Dict] = field(default_factory=list)
    timeout_seconds: int = 30
    metadata: Dict = field(default_factory=dict)

    def to_openai_function(self) -> Dict:
        props = {}
        required = []
        for param in self.parameters:
            prop = param.to_json_schema()
            props[param.name] = prop
            if param.required:
                required.append(param.name)
        
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": props,
                    "required": required
                }
            }
        }
    
    def to_gemini_function(self) -> Dict:
        """Convert to Gemini function declaration format"""
        props = {}
        required = []
        for param in self.parameters:
            prop = param.to_json_schema()
            props[param.name] = prop
            if param.required:
                required.append(param.name)
        
        return {
            "name": self.name,
            "description": self.description,
            "parameters": {
                "type": "object",
                "properties": props,
                "required": required
            }
        }
    
    def to_anthropic_tool(self) -> Dict:
        """Convert to Anthropic tool format"""
        return self.to_openai_function()


@dataclass
class ToolResult:
    success: bool
    data: Any = None
    error: str = None
    metadata: Dict = field(default_factory=dict)


class BaseTool(ABC):
    def __init__(self):
        self.schema = self._define_schema()
    
    @abstractmethod
    def _define_schema(self) -> ToolSchema:
        pass
    
    @abstractmethod
    async def execute(self, arguments: Dict[str, Any], context: Dict = None) -> ToolResult:
        pass
    
    def validate_arguments(self, arguments: Dict[str, Any]) -> tuple[bool, str]:
        """Validate arguments against schema with type checking"""
        for param in self.schema.parameters:
            if param.required and param.name not in arguments:
                return False, f"Missing required parameter: {param.name}"
            
            if param.name in arguments:
                value = arguments[param.name]
                if param.enum and value not in param.enum:
                    return False, f"Invalid value for {param.name}: must be one of {param.enum}"
                
                # Type validation
                if not self._validate_type(value, param.type):
                    return False, f"Invalid type for {param.name}: expected {param.type}, got {type(value).__name__}"
        
        return True, ""
    
    def _validate_type(self, value: Any, expected_type: str) -> bool:
        """Validate value matches expected type"""
        type_map = {
            "string": str,
            "integer": int,
            "number": (int, float),
            "boolean": bool,
            "array": list,
            "object": dict,
        }
        
        expected = type_map.get(expected_type.lower())
        if expected is None:
            return True  # Unknown type, skip validation
        
        if isinstance(expected, tuple):
            return isinstance(value, expected)
        return isinstance(value, expected)
    
    def get_schema(self) -> ToolSchema:
        return self.schema


class ToolRegistry:
    def __init__(self):
        self._tools: Dict[str, BaseTool] = {}
        self._categories: Dict[ToolCategory, List[str]] = {}
    
    def register(self, tool: BaseTool) -> None:
        name = tool.schema.name
        if name in self._tools:
            raise ValueError(f"Tool already registered: {name}")
        self._tools[name] = tool
        category = tool.schema.category
        if category not in self._categories:
            self._categories[category] = []
        self._categories[category].append(name)
    
    def unregister(self, name: str) -> bool:
        tool = self._tools.pop(name, None)
        if tool:
            category = tool.schema.category
            if category in self._categories:
                self._categories[category] = [n for n in self._categories[category] if n != name]
            return True
        return False
    
    def get(self, name: str) -> Optional[BaseTool]:
        return self._tools.get(name)
    
    def list_tools(self, category: ToolCategory = None) -> List[ToolSchema]:
        if category:
            names = self._categories.get(category, [])
        else:
            names = list(self._tools.keys())
        return [self._tools[n].get_schema() for n in names]
    
    def get_openai_functions(self, category: ToolCategory = None) -> List[Dict]:
        return [t.to_openai_function() for t in self.list_tools(category)]
    
    def get_gemini_functions(self, category: ToolCategory = None) -> List[Dict]:
        return [t.to_gemini_function() for t in self.list_tools(category)]
    
    def get_anthropic_tools(self, category: ToolCategory = None) -> List[Dict]:
        return [t.to_anthropic_tool() for t in self.list_tools(category)]
    
    def get_functions_for_provider(self, provider: str, category: ToolCategory = None) -> List[Dict]:
        """Get functions formatted for specific provider"""
        if provider in ("openai", "nemotron"):
            return self.get_openai_functions(category)
        elif provider == "gemini":
            return self.get_gemini_functions(category)
        elif provider == "anthropic":
            return self.get_anthropic_tools(category)
        else:
            return self.get_openai_functions(category)
    
    async def execute(
        self,
        name: str,
        arguments: Dict[str, Any],
        context: Dict = None
    ) -> ToolResult:
        tool = self.get(name)
        if not tool:
            return ToolResult(success=False, error=f"Tool not found: {name}")
        
        valid, error = tool.validate_arguments(arguments)
        if not valid:
            return ToolResult(success=False, error=error)
        
        try:
            return await tool.execute(arguments, context)
        except Exception as e:
            return ToolResult(success=False, error=f"Tool execution failed: {str(e)}")


tool_registry = ToolRegistry()