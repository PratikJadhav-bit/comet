from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, AsyncGenerator
from enum import Enum
import json


class ModelRole(str, Enum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


@dataclass
class ModelMessage:
    role: ModelRole
    content: str
    name: Optional[str] = None
    tool_calls: Optional[List[Dict]] = None
    tool_call_id: Optional[str] = None


@dataclass
class ToolDefinition:
    name: str
    description: str
    parameters: Dict[str, Any]
    required: List[str] = field(default_factory=list)


@dataclass
class ModelResponse:
    content: str
    tool_calls: List[Dict] = field(default_factory=list)
    finish_reason: str = "stop"
    usage: Dict[str, int] = field(default_factory=dict)
    raw_response: Any = None


@dataclass
class ModelCapabilities:
    supports_tool_calling: bool = False
    supports_streaming: bool = False
    supports_structured_output: bool = False
    max_context_tokens: int = 4096
    max_output_tokens: int = 2048


class ModelProvider(ABC):
    @abstractmethod
    async def initialize(self) -> bool:
        pass

    @abstractmethod
    async def close(self) -> None:
        pass

    @abstractmethod
    async def chat(
        self,
        messages: List[ModelMessage],
        tools: List[ToolDefinition] = None,
        temperature: float = 0.1,
        max_tokens: int = None,
        stream: bool = False
    ) -> ModelResponse:
        pass

    @abstractmethod
    async def chat_stream(
        self,
        messages: List[ModelMessage],
        tools: List[ToolDefinition] = None,
        temperature: float = 0.1,
        max_tokens: int = None
    ) -> AsyncGenerator[str, None]:
        pass

    @abstractmethod
    def get_capabilities(self) -> ModelCapabilities:
        pass

    @abstractmethod
    def get_model_name(self) -> str:
        pass

    @abstractmethod
    async def health_check(self) -> bool:
        pass


class ModelRegistry:
    def __init__(self):
        self._providers: Dict[str, ModelProvider] = {}
        self._default: Optional[str] = None

    def register(self, name: str, provider: ModelProvider, default: bool = False):
        self._providers[name] = provider
        if default or not self._default:
            self._default = name

    def get(self, name: str = None) -> Optional[ModelProvider]:
        name = name or self._default
        return self._providers.get(name)

    def list_providers(self) -> List[str]:
        return list(self._providers.keys())


model_registry = ModelRegistry()