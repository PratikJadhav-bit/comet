import google.generativeai as genai
from google.generativeai.types import GenerationConfig
from typing import List, Dict, Any, Optional, AsyncGenerator
from app.models.base import (
    ModelProvider, ModelMessage, ModelResponse, ToolDefinition,
    ModelCapabilities, ModelRole
)
from app.config import settings
from app.security.secrets import secret_manager
import json
import logging

logger = logging.getLogger(__name__)


class GeminiProvider(ModelProvider):
    def __init__(self):
        self.api_key = secret_manager.get_secret("GEMINI_API_KEY") or settings.gemini_api_key
        self.model_name = settings.gemini_model
        self.timeout = settings.gemini_timeout
        self.max_retries = settings.gemini_max_retries
        self._model = None
        self._capabilities = ModelCapabilities(
            supports_tool_calling=True,
            supports_streaming=True,
            supports_structured_output=True,
            max_context_tokens=1048576,
            max_output_tokens=8192
        )

    async def initialize(self) -> bool:
        if not self.api_key:
            logger.warning("GEMINI_API_KEY not configured")
            return False

        try:
            genai.configure(api_key=self.api_key)
            self._model = genai.GenerativeModel(
                model_name=self.model_name,
                generation_config=GenerationConfig(
                    temperature=settings.model_temperature,
                    max_output_tokens=settings.model_max_tokens,
                )
            )
            return await self.health_check()
        except Exception as e:
            logger.error(f"Failed to initialize Gemini provider: {e}")
            return False

    async def close(self) -> None:
        self._model = None

    def get_capabilities(self) -> ModelCapabilities:
        return self._capabilities

    def get_model_name(self) -> str:
        return self.model_name

    async def health_check(self) -> bool:
        if not self._model:
            return False
        try:
            response = await self._model.generate_content_async(
                "ping",
                generation_config=GenerationConfig(max_output_tokens=5)
            )
            return bool(response.text)
        except Exception as e:
            logger.warning(f"Gemini health check failed: {e}")
            return False

    def _format_messages(self, messages: List[ModelMessage]) -> List[Dict]:
        formatted = []
        for msg in messages:
            if msg.role == ModelRole.SYSTEM:
                formatted.append({"role": "user", "parts": [f"System: {msg.content}"]})
                formatted.append({"role": "model", "parts": ["Understood."]})
            elif msg.role == ModelRole.USER:
                formatted.append({"role": "user", "parts": [msg.content]})
            elif msg.role == ModelRole.ASSISTANT:
                if msg.tool_calls:
                    formatted.append({"role": "model", "parts": [msg.content or ""]})
                else:
                    formatted.append({"role": "model", "parts": [msg.content]})
            elif msg.role == ModelRole.TOOL:
                formatted.append({
                    "role": "user",
                    "parts": [f"Tool result ({msg.name}): {msg.content}"]
                })
        return formatted

    def _format_tools(self, tools: List[ToolDefinition]) -> List[Dict]:
        if not tools:
            return None
        
        function_declarations = []
        for t in tools:
            function_declarations.append({
                "name": t.name,
                "description": t.description,
                "parameters": {
                    "type": "object",
                    "properties": t.parameters,
                    "required": t.required
                }
            })
        
        return [{"function_declarations": function_declarations}]

    async def chat(
        self,
        messages: List[ModelMessage],
        tools: List[ToolDefinition] = None,
        temperature: float = 0.1,
        max_tokens: int = None,
        stream: bool = False
    ) -> ModelResponse:
        if not self._model:
            raise RuntimeError("Provider not initialized")

        formatted_messages = self._format_messages(messages)
        tool_config = self._format_tools(tools) if tools else None

        generation_config = GenerationConfig(
            temperature=temperature,
            max_output_tokens=max_tokens or settings.model_max_tokens,
        )

        try:
            if stream:
                response = await self._model.generate_content_async(
                    formatted_messages,
                    generation_config=generation_config,
                    tools=tool_config,
                    stream=True
                )
                full_text = ""
                async for chunk in response:
                    if chunk.text:
                        full_text += chunk.text
                return ModelResponse(
                    content=full_text,
                    tool_calls=[],
                    finish_reason="stop",
                    usage={},
                    raw_response=None
                )
            else:
                response = await self._model.generate_content_async(
                    formatted_messages,
                    generation_config=generation_config,
                    tools=tool_config
                )

            tool_calls = []
            content = response.text or ""

            if response.candidates:
                candidate = response.candidates[0]
                if candidate.content and candidate.content.parts:
                    for part in candidate.content.parts:
                        if hasattr(part, 'function_call') and part.function_call:
                            fc = part.function_call
                            tool_calls.append({
                                "id": f"call_{len(tool_calls)}",
                                "name": fc.name,
                                "arguments": dict(fc.args) if fc.args else {}
                            })

            usage = {}
            if hasattr(response, 'usage_metadata') and response.usage_metadata:
                usage = {
                    "prompt_tokens": getattr(response.usage_metadata, 'prompt_token_count', 0),
                    "completion_tokens": getattr(response.usage_metadata, 'candidates_token_count', 0),
                    "total_tokens": getattr(response.usage_metadata, 'total_token_count', 0)
                }

            finish_reason = "stop"
            if response.candidates and response.candidates[0].finish_reason:
                finish_reason = response.candidates[0].finish_reason.name.lower()

            return ModelResponse(
                content=content,
                tool_calls=tool_calls,
                finish_reason=finish_reason,
                usage=usage,
                raw_response=response
            )

        except Exception as e:
            logger.error(f"Gemini chat error: {e}")
            raise

    async def chat_stream(
        self,
        messages: List[ModelMessage],
        tools: List[ToolDefinition] = None,
        temperature: float = 0.1,
        max_tokens: int = None
    ) -> AsyncGenerator[str, None]:
        if not self._model:
            raise RuntimeError("Provider not initialized")

        formatted_messages = self._format_messages(messages)
        tool_config = self._format_tools(tools) if tools else None

        generation_config = GenerationConfig(
            temperature=temperature,
            max_output_tokens=max_tokens or settings.model_max_tokens,
        )

        try:
            response = await self._model.generate_content_async(
                formatted_messages,
                generation_config=generation_config,
                tools=tool_config,
                stream=True
            )
            async for chunk in response:
                if chunk.text:
                    yield chunk.text
        except Exception as e:
            logger.error(f"Gemini stream error: {e}")
            raise


async def create_gemini_provider() -> GeminiProvider:
    provider = GeminiProvider()
    await provider.initialize()
    return provider