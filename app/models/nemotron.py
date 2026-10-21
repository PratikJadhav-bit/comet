import httpx
import json
import os
from typing import List, Dict, Any, Optional, AsyncGenerator
from app.models.base import (
    ModelProvider, ModelMessage, ModelResponse, ToolDefinition,
    ModelCapabilities, ModelRole
)
from app.config import settings
from app.security.secrets import secret_manager


class NemotronProvider(ModelProvider):
    def __init__(self):
        self.base_url = settings.model_base_url
        self.api_key = secret_manager.get_api_key()
        self.model_name = settings.model_name
        self.timeout = settings.model_timeout
        self.max_tokens = settings.model_max_tokens
        self.temperature = settings.model_temperature
        self._client: Optional[httpx.AsyncClient] = None
        self._capabilities = ModelCapabilities(
            supports_tool_calling=True,
            supports_streaming=True,
            supports_structured_output=True,
            max_context_tokens=128000,
            max_output_tokens=8192
        )

    async def initialize(self) -> bool:
        if not self.base_url:
            raise ValueError("MODEL_BASE_URL not configured")
        
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        
        self._client = httpx.AsyncClient(
            base_url=self.base_url.rstrip("/"),
            headers=headers,
            timeout=self.timeout
        )
        
        # Don't fail initialization if health check fails
        # The health check will be retried on first use
        try:
            return await self.health_check()
        except Exception:
            return False

    async def close(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None

    def get_capabilities(self) -> ModelCapabilities:
        return self._capabilities

    def get_model_name(self) -> str:
        return self.model_name

    async def health_check(self) -> bool:
        if not self._client:
            return False
        try:
            response = await self._client.get("/health", timeout=10)
            return response.status_code == 200
        except Exception:
            try:
                response = await self._client.post(
                    "/v1/chat/completions",
                    json={
                        "model": self.model_name,
                        "messages": [{"role": "user", "content": "ping"}],
                        "max_tokens": 5
                    },
                    timeout=10
                )
                return response.status_code == 200
            except Exception:
                return False

    def _format_messages(self, messages: List[ModelMessage]) -> List[Dict]:
        formatted = []
        for msg in messages:
            m = {"role": msg.role.value, "content": msg.content}
            if msg.name:
                m["name"] = msg.name
            if msg.tool_calls:
                m["tool_calls"] = msg.tool_calls
            if msg.tool_call_id:
                m["tool_call_id"] = msg.tool_call_id
            formatted.append(m)
        return formatted

    def _format_tools(self, tools: List[ToolDefinition]) -> List[Dict]:
        return [
            {
                "type": "function",
                "function": {
                    "name": t.name,
                    "description": t.description,
                    "parameters": {
                        "type": "object",
                        "properties": t.parameters,
                        "required": t.required
                    }
                }
            }
            for t in tools
        ] if tools else None

    async def chat(
        self,
        messages: List[ModelMessage],
        tools: List[ToolDefinition] = None,
        temperature: float = 0.1,
        max_tokens: int = None,
        stream: bool = False
    ) -> ModelResponse:
        if not self._client:
            raise RuntimeError("Provider not initialized")

        payload = {
            "model": self.model_name,
            "messages": self._format_messages(messages),
            "temperature": temperature,
            "stream": stream
        }

        if max_tokens:
            payload["max_tokens"] = min(max_tokens, self.max_tokens)
        else:
            payload["max_tokens"] = self.max_tokens

        if tools:
            payload["tools"] = self._format_tools(tools)
            payload["tool_choice"] = "auto"

        response = await self._client.post("/v1/chat/completions", json=payload)
        response.raise_for_status()
        data = response.json()

        choice = data["choices"][0]
        message = choice["message"]

        tool_calls = []
        if message.get("tool_calls"):
            for tc in message["tool_calls"]:
                tool_calls.append({
                    "id": tc["id"],
                    "name": tc["function"]["name"],
                    "arguments": json.loads(tc["function"]["arguments"])
                })

        return ModelResponse(
            content=message.get("content", ""),
            tool_calls=tool_calls,
            finish_reason=choice.get("finish_reason", "stop"),
            usage=data.get("usage", {}),
            raw_response=data
        )

    async def chat_stream(
        self,
        messages: List[ModelMessage],
        tools: List[ToolDefinition] = None,
        temperature: float = 0.1,
        max_tokens: int = None
    ) -> AsyncGenerator[str, None]:
        if not self._client:
            raise RuntimeError("Provider not initialized")

        payload = {
            "model": self.model_name,
            "messages": self._format_messages(messages),
            "temperature": temperature,
            "stream": True
        }

        if max_tokens:
            payload["max_tokens"] = min(max_tokens, self.max_tokens)
        else:
            payload["max_tokens"] = self.max_tokens

        if tools:
            payload["tools"] = self._format_tools(tools)
            payload["tool_choice"] = "auto"

        async with self._client.stream("POST", "/v1/chat/completions", json=payload) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                if line.startswith("data: "):
                    data_str = line[6:]
                    if data_str.strip() == "[DONE]":
                        break
                    try:
                        data = json.loads(data_str)
                        delta = data["choices"][0].get("delta", {})
                        if "content" in delta and delta["content"]:
                            yield delta["content"]
                    except json.JSONDecodeError:
                        continue


async def create_nemotron_provider() -> NemotronProvider:
    provider = NemotronProvider()
    await provider.initialize()
    return provider