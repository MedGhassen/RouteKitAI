"""Anthropic Claude model provider."""

import os
from collections.abc import AsyncIterator
from typing import TYPE_CHECKING, Any

from routekit.core.errors import ModelError

if TYPE_CHECKING:
    import httpx
from routekit.core.message import Message, MessageRole
from routekit.core.model import Model, ModelResponse, StreamEvent, ToolCall, Usage
from routekit.core.tool import Tool


class AnthropicModel(Model):
    """Anthropic Claude model provider.

    Supports Claude models via Anthropic API with tool use.
    """

    def __init__(
        self,
        name: str = "claude-3-opus-20240229",
        provider: str = "anthropic",
        api_key: str | None = None,
        base_url: str = "https://api.anthropic.com/v1",
        **kwargs: Any,
    ) -> None:
        """Initialize Anthropic model.

        Args:
            name: Model name (e.g., claude-3-opus-20240229, claude-3-sonnet-20240229)
            provider: Provider name
            api_key: Anthropic API key (defaults to ANTHROPIC_API_KEY env var)
            base_url: API base URL
            **kwargs: Additional configuration
        """
        super().__init__()
        self._name = name
        self._provider = provider
        self.api_key = api_key or os.getenv("ANTHROPIC_API_KEY")
        self.base_url = base_url.rstrip("/")
        self._client: httpx.AsyncClient | None = None

    @property
    def name(self) -> str:
        """Return the model name."""
        return self._name

    @property
    def provider(self) -> str:
        """Return the provider name."""
        return self._provider

    def _get_client(self) -> "httpx.AsyncClient":
        """Get or create HTTP client."""
        try:
            import httpx
        except ImportError as e:
            raise ModelError(
                "httpx is required for Anthropic provider. Install with: pip install httpx"
            ) from e

        if self._client is None:
            headers = {
                "Content-Type": "application/json",
                "x-api-key": self.api_key or "",
                "anthropic-version": "2023-06-01",
            }
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                headers=headers,
                timeout=60.0,
            )
        return self._client

    def _message_to_anthropic(self, message: Message) -> dict[str, Any]:
        """Convert RouteKit Message to Anthropic format."""
        role_map = {
            MessageRole.SYSTEM: "system",
            MessageRole.USER: "user",
            MessageRole.ASSISTANT: "assistant",
        }
        # Anthropic doesn't support tool role messages directly
        if message.role == MessageRole.TOOL:
            # Convert tool messages to user messages with tool result
            return {
                "role": "user",
                "content": f"Tool result: {message.content}",
            }
        return {
            "role": role_map.get(message.role, "user"),
            "content": message.content,
        }

    def _tools_to_anthropic(self, tools: list[Tool]) -> list[dict[str, Any]]:
        """Convert RouteKit Tools to Anthropic tool format."""
        return [
            {
                "name": tool.name,
                "description": tool.description,
                "input_schema": tool.parameters,
            }
            for tool in tools
        ]

    def _anthropic_to_tool_calls(self, tool_use_blocks: list[dict[str, Any]]) -> list[ToolCall]:
        """Convert Anthropic tool use blocks to RouteKit format."""
        result = []
        for block in tool_use_blocks:
            if block.get("type") == "tool_use":
                result.append(
                    ToolCall(
                        id=block.get("id", ""),
                        name=block.get("name", ""),
                        arguments=block.get("input", {}),
                    )
                )
        return result

    async def chat(
        self,
        messages: list[Message],
        tools: list[Tool] | None = None,
        stream: bool = False,
        **kwargs: Any,
    ) -> ModelResponse | AsyncIterator[StreamEvent]:
        """Chat with Anthropic Claude model.

        Args:
            messages: Conversation messages
            tools: Optional tools
            stream: Whether to stream (not yet implemented)
            **kwargs: Additional parameters (max_tokens, temperature, etc.)

        Returns:
            ModelResponse or stream of events

        Raises:
            ModelError: If API call fails
        """
        if stream:
            raise NotImplementedError("Streaming not yet implemented for Anthropic")

        if not self.api_key:
            raise ModelError(
                "Anthropic API key is required. Set ANTHROPIC_API_KEY env var or pass api_key parameter"
            )

        client = self._get_client()

        # Separate system messages from conversation
        system_messages = [msg.content for msg in messages if msg.role == MessageRole.SYSTEM]
        conversation_messages = [
            self._message_to_anthropic(msg) for msg in messages if msg.role != MessageRole.SYSTEM
        ]

        # Prepare request
        request_data: dict[str, Any] = {
            "model": self.name,
            "messages": conversation_messages,
            "max_tokens": kwargs.get("max_tokens", 1024),
            **{k: v for k, v in kwargs.items() if k not in ("max_tokens", "stream")},
        }

        if system_messages:
            request_data["system"] = (
                system_messages[0] if len(system_messages) == 1 else "\n".join(system_messages)
            )

        if tools:
            request_data["tools"] = self._tools_to_anthropic(tools)

        try:
            response = await client.post("/messages", json=request_data)
            response.raise_for_status()
            data = response.json()

            # Parse response
            content_blocks = data.get("content", [])
            text_content = ""
            tool_use_blocks = []

            for block in content_blocks:
                if block.get("type") == "text":
                    text_content += block.get("text", "")
                elif block.get("type") == "tool_use":
                    tool_use_blocks.append(block)

            # Convert tool calls
            tool_calls = None
            if tool_use_blocks:
                tool_calls = self._anthropic_to_tool_calls(tool_use_blocks)

            # Parse usage
            usage_data = data.get("usage", {})
            usage = Usage(
                prompt_tokens=usage_data.get("input_tokens", 0),
                completion_tokens=usage_data.get("output_tokens", 0),
                total_tokens=usage_data.get("input_tokens", 0) + usage_data.get("output_tokens", 0),
            )

            return ModelResponse(
                content=text_content,
                tool_calls=tool_calls,
                usage=usage,
                metadata={"raw_response": data},
            )

        except httpx.HTTPStatusError as e:
            raise ModelError(
                f"Anthropic API error: {e.response.status_code} - {e.response.text}"
            ) from e
        except Exception as e:
            raise ModelError(f"Failed to call Anthropic API: {e}") from e

    async def __aenter__(self) -> "AnthropicModel":
        """Async context manager entry."""
        return self

    async def __aexit__(
        self, exc_type: type[BaseException] | None, exc_val: BaseException | None, exc_tb: Any
    ) -> None:
        """Async context manager exit."""
        if self._client:
            await self._client.aclose()
            self._client = None
