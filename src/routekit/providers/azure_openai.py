"""Azure OpenAI model provider."""

import json
import os
from typing import Any, AsyncIterator

try:
    import httpx
except ImportError:
    httpx = None  # type: ignore

from routekit.core.errors import ModelError
from routekit.core.message import Message, MessageRole
from routekit.core.model import Model, ModelResponse, StreamEvent, ToolCall, Usage
from routekit.core.tool import Tool


class AzureOpenAIModel(Model):
    """Azure OpenAI model provider.

    Supports Azure OpenAI deployments with custom endpoints and API versions.
    """

    def __init__(
        self,
        name: str = "gpt-4",
        provider: str = "azure-openai",
        api_key: str | None = None,
        endpoint: str | None = None,
        deployment_name: str | None = None,
        api_version: str = "2024-02-15-preview",
        **kwargs: Any,
    ) -> None:
        """Initialize Azure OpenAI model.

        Args:
            name: Model name
            provider: Provider name
            api_key: Azure OpenAI API key (defaults to AZURE_OPENAI_API_KEY env var)
            endpoint: Azure OpenAI endpoint URL (defaults to AZURE_OPENAI_ENDPOINT env var)
            deployment_name: Deployment name (defaults to model name)
            api_version: API version
            **kwargs: Additional configuration
        """
        super().__init__()
        self._name = name
        self._provider = provider
        self.api_key = api_key or os.getenv("AZURE_OPENAI_API_KEY")
        self.endpoint = (endpoint or os.getenv("AZURE_OPENAI_ENDPOINT") or "").rstrip("/")
        self.deployment_name = deployment_name or name
        self.api_version = api_version
        self._client: httpx.AsyncClient | None = None

    @property
    def name(self) -> str:
        """Return the model name."""
        return self._name

    @property
    def provider(self) -> str:
        """Return the provider name."""
        return self._provider

    def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if httpx is None:
            raise ModelError("httpx is required for Azure OpenAI provider. Install with: pip install httpx")
        if not self.endpoint:
            raise ModelError("Azure OpenAI endpoint is required. Set AZURE_OPENAI_ENDPOINT env var or pass endpoint parameter")
        if self._client is None:
            headers = {
                "Content-Type": "application/json",
                "api-key": self.api_key or "",
            }
            self._client = httpx.AsyncClient(
                base_url=self.endpoint,
                headers=headers,
                timeout=60.0,
            )
        return self._client

    def _message_to_openai(self, message: Message) -> dict[str, Any]:
        """Convert RouteKit Message to OpenAI format."""
        role_map = {
            MessageRole.SYSTEM: "system",
            MessageRole.USER: "user",
            MessageRole.ASSISTANT: "assistant",
            MessageRole.TOOL: "tool",
        }
        msg_dict: dict[str, Any] = {
            "role": role_map.get(message.role, "user"),
            "content": message.content,
        }
        if message.tool_calls:
            msg_dict["tool_calls"] = [
                {
                    "id": tc.get("id", ""),
                    "type": "function",
                    "function": {
                        "name": tc.get("name", ""),
                        "arguments": json.dumps(tc.get("arguments", {})),
                    },
                }
                for tc in message.tool_calls
            ]
        if message.tool_result:
            msg_dict["tool_call_id"] = message.tool_result.get("tool_call_id", "")
        return msg_dict

    def _tools_to_openai(self, tools: list[Tool]) -> list[dict[str, Any]]:
        """Convert RouteKit Tools to OpenAI function format."""
        return [
            {
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.parameters,
                },
            }
            for tool in tools
        ]

    def _openai_to_tool_calls(self, tool_calls: list[dict[str, Any]]) -> list[ToolCall]:
        """Convert OpenAI tool calls to RouteKit format."""
        result = []
        for tc in tool_calls:
            if tc.get("type") == "function":
                func = tc.get("function", {})
                try:
                    arguments = json.loads(func.get("arguments", "{}"))
                except (json.JSONDecodeError, TypeError):
                    arguments = func.get("arguments", {})
                result.append(
                    ToolCall(
                        id=tc.get("id", ""),
                        name=func.get("name", ""),
                        arguments=arguments,
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
        """Chat with Azure OpenAI model.

        Args:
            messages: Conversation messages
            tools: Optional tools
            stream: Whether to stream (not yet implemented)
            **kwargs: Additional parameters (temperature, max_tokens, etc.)

        Returns:
            ModelResponse or stream of events

        Raises:
            ModelError: If API call fails
        """
        if stream:
            raise NotImplementedError("Streaming not yet implemented for Azure OpenAI")

        if not self.api_key:
            raise ModelError("Azure OpenAI API key is required. Set AZURE_OPENAI_API_KEY env var or pass api_key parameter")

        client = self._get_client()

        # Convert messages
        openai_messages = [self._message_to_openai(msg) for msg in messages]

        # Prepare request URL with deployment and API version
        url = f"/openai/deployments/{self.deployment_name}/chat/completions?api-version={self.api_version}"

        # Prepare request data
        request_data: dict[str, Any] = {
            "messages": openai_messages,
            **kwargs,  # Allow temperature, max_tokens, etc.
        }

        # Add tools if provided
        if tools:
            request_data["tools"] = self._tools_to_openai(tools)

        try:
            response = await client.post(url, json=request_data)
            response.raise_for_status()
            data = response.json()

            # Parse response
            choice = data.get("choices", [{}])[0]
            message = choice.get("message", {})
            content = message.get("content", "")
            tool_calls_data = message.get("tool_calls", [])

            # Convert tool calls
            tool_calls = None
            if tool_calls_data:
                tool_calls = self._openai_to_tool_calls(tool_calls_data)

            # Parse usage
            usage_data = data.get("usage", {})
            usage = Usage(
                prompt_tokens=usage_data.get("prompt_tokens", 0),
                completion_tokens=usage_data.get("completion_tokens", 0),
                total_tokens=usage_data.get("total_tokens", 0),
            )

            return ModelResponse(
                content=content,
                tool_calls=tool_calls,
                usage=usage,
                metadata={"raw_response": data},
            )

        except httpx.HTTPStatusError as e:
            raise ModelError(f"Azure OpenAI API error: {e.response.status_code} - {e.response.text}") from e
        except Exception as e:
            raise ModelError(f"Failed to call Azure OpenAI API: {e}") from e

    async def __aenter__(self) -> "AzureOpenAIModel":
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type: type[BaseException] | None, exc_val: BaseException | None, exc_tb: Any) -> None:
        """Async context manager exit."""
        if self._client:
            await self._client.aclose()
            self._client = None
