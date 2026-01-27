"""OpenAI-compatible model provider."""

import json
from collections.abc import AsyncIterator
from typing import Any

import httpx

from routekitai.core.errors import ModelError
from routekitai.core.message import Message, MessageRole
from routekitai.core.model import Model, ModelResponse, StreamEvent, ToolCall, Usage
from routekitai.core.tool import Tool


class OpenAIChatModel(Model):
    """OpenAI-compatible HTTP model provider.

    Supports OpenAI API and compatible endpoints (e.g., local LLM servers).
    """

    def __init__(
        self,
        name: str = "gpt-4",
        provider: str = "openai",
        api_key: str | None = None,
        base_url: str = "https://api.openai.com/v1",
        **kwargs: Any,
    ) -> None:
        """Initialize OpenAI model.

        Args:
            name: Model name
            provider: Provider name
            api_key: API key (defaults to OPENAI_API_KEY env var)
            base_url: API base URL
            **kwargs: Additional configuration
        """
        super().__init__()
        self._name = name
        self._provider = provider
        self.api_key = api_key
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
                "httpx is required for OpenAI provider. Install with: pip install httpx"
            ) from e

        if self._client is None:
            headers = {"Content-Type": "application/json"}
            if self.api_key:
                headers["Authorization"] = f"Bearer {self.api_key}"
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                headers=headers,
                timeout=60.0,
            )
        return self._client

    def _message_to_openai(self, message: Message) -> dict[str, Any]:
        """Convert routkitai Message to OpenAI format."""
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
        """Convert routkitai Tools to OpenAI function format."""
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
        """Convert OpenAI tool calls to routkitai format."""
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
        """Chat with OpenAI-compatible model.

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
        client = self._get_client()

        # Convert messages
        openai_messages = [self._message_to_openai(msg) for msg in messages]

        # Prepare request
        request_data: dict[str, Any] = {
            "model": self.name,
            "messages": openai_messages,
            "stream": stream,
            **kwargs,  # Allow temperature, max_tokens, etc.
        }

        # Add tools if provided
        if tools:
            request_data["tools"] = self._tools_to_openai(tools)

        try:
            if stream:
                # Streaming mode
                async def stream_generator() -> AsyncIterator[StreamEvent]:
                    async with client.stream(
                        "POST", "/chat/completions", json=request_data
                    ) as response:
                        response.raise_for_status()
                        content_buffer = ""
                        tool_calls_buffer: dict[str, dict[str, Any]] = {}

                        async for line in response.aiter_lines():
                            if not line.strip() or line.startswith("data: [DONE]"):
                                continue

                            if line.startswith("data: "):
                                line = line[6:]  # Remove "data: " prefix

                            try:
                                chunk_data = json.loads(line)
                                delta = chunk_data.get("choices", [{}])[0].get("delta", {})

                                # Handle content delta
                                if "content" in delta:
                                    content_chunk = delta["content"]
                                    content_buffer += content_chunk
                                    yield StreamEvent(
                                        type="content",
                                        content=content_chunk,
                                        metadata={"chunk": chunk_data},
                                    )

                                # Handle tool calls delta
                                if "tool_calls" in delta:
                                    for tool_call_delta in delta["tool_calls"]:
                                        index = tool_call_delta.get("index", 0)
                                        if index not in tool_calls_buffer:
                                            tool_calls_buffer[index] = {
                                                "id": "",
                                                "name": "",
                                                "arguments": "",
                                            }

                                        if "id" in tool_call_delta:
                                            tool_calls_buffer[index]["id"] = tool_call_delta["id"]
                                        if "function" in tool_call_delta:
                                            func = tool_call_delta["function"]
                                            if "name" in func:
                                                tool_calls_buffer[index]["name"] = func["name"]
                                            if "arguments" in func:
                                                tool_calls_buffer[index]["arguments"] += func[
                                                    "arguments"
                                                ]

                                # Handle usage (usually in last chunk)
                                if "usage" in chunk_data:
                                    usage_data = chunk_data["usage"]
                                    yield StreamEvent(
                                        type="usage",
                                        usage=Usage(
                                            prompt_tokens=usage_data.get("prompt_tokens", 0),
                                            completion_tokens=usage_data.get(
                                                "completion_tokens", 0
                                            ),
                                            total_tokens=usage_data.get("total_tokens", 0),
                                        ),
                                        metadata={"chunk": chunk_data},
                                    )

                            except json.JSONDecodeError:
                                continue

                        # Final event with complete content and tool calls
                        tool_calls = None
                        if tool_calls_buffer:
                            tool_calls = []
                            for idx in sorted(tool_calls_buffer.keys()):
                                tc_data = tool_calls_buffer[idx]
                                try:
                                    arguments = json.loads(tc_data["arguments"])
                                except json.JSONDecodeError:
                                    arguments = {}
                                tool_calls.append(
                                    ToolCall(
                                        id=tc_data["id"],
                                        name=tc_data["name"],
                                        arguments=arguments,
                                    )
                                )

                        yield StreamEvent(
                            type="done",
                            content=content_buffer if content_buffer else None,
                            tool_calls=tool_calls,
                        )

                return stream_generator()
            else:
                # Non-streaming mode
                response = await client.post("/chat/completions", json=request_data)
                response.raise_for_status()
                data = response.json()

                # Parse response
                choice = data.get("choices", [{}])[0]
                message = choice.get("message", {})
                # Handle None content (can happen when there are tool calls)
                content = message.get("content") or ""
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
            raise ModelError(
                f"OpenAI API error: {e.response.status_code} - {e.response.text}"
            ) from e
        except Exception as e:
            raise ModelError(f"Failed to call OpenAI API: {e}") from e

    async def __aenter__(self) -> "OpenAIChatModel":
        """Async context manager entry."""
        return self

    async def __aexit__(
        self, exc_type: type[BaseException] | None, exc_val: BaseException | None, exc_tb: Any
    ) -> None:
        """Async context manager exit."""
        if self._client:
            await self._client.aclose()
            self._client = None
