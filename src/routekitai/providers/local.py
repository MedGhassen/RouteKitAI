"""Local/Fake model provider for testing."""

from collections import deque
from collections.abc import AsyncIterator, Callable
from typing import Any

from pydantic import Field

from routekitai.core.errors import ModelError
from routekitai.core.message import Message
from routekitai.core.model import Model, ModelResponse, StreamEvent, ToolCall, Usage
from routekitai.core.tool import Tool


class FakeModel(Model):
    """Deterministic fake model for testing.

    Uses scripted responses based on message content or a response function.
    Can also use a queue of responses for sequential calls.
    """

    name: str = Field(default="fake", description="Model name")
    provider: str = Field(default="local", description="Provider name")
    responses: dict[str, str | dict[str, Any]] | None = Field(
        default=None, description="Dict mapping message content to response"
    )
    response_fn: Callable[[list[Message], list[Tool] | None], str | dict[str, Any]] | None = Field(
        default=None, description="Function(message, tools) -> response"
    )
    response_queue: deque[str | dict[str, Any] | Callable] = Field(
        default_factory=deque, description="Queue of responses for sequential calls"
    )
    call_count: int = Field(default=0, exclude=True)

    def __init__(
        self,
        name: str = "fake",
        provider: str = "local",
        responses: dict[str, str | dict[str, Any]] | None = None,
        response_fn: Callable[[list[Message], list[Tool] | None], str | dict[str, Any]]
        | None = None,
        response_queue: deque[str | dict[str, Any] | Callable] | None = None,
        **kwargs: Any,
    ) -> None:
        """Initialize fake model.

        Args:
            name: Model name
            provider: Provider name
            responses: Dict mapping message content to response
            response_fn: Function(message, tools) -> response dict
            response_queue: Queue of responses for sequential calls
            **kwargs: Additional configuration
        """
        super().__init__()
        object.__setattr__(self, "name", name)
        object.__setattr__(self, "provider", provider)
        object.__setattr__(self, "responses", responses or {})
        object.__setattr__(self, "response_fn", response_fn)
        object.__setattr__(self, "response_queue", response_queue or deque())
        object.__setattr__(self, "call_count", 0)

    def add_response(
        self,
        response: str
        | dict[str, Any]
        | Callable[[list[Message], list[Tool] | None], str | dict[str, Any]],
    ) -> None:
        """Add a response to the queue.

        Args:
            response: Response string, dict, or callable
        """
        self.response_queue.append(response)

    async def chat(
        self,
        messages: list[Message],
        tools: list[Tool] | None = None,
        stream: bool = False,
        **kwargs: Any,
    ) -> ModelResponse | AsyncIterator[StreamEvent]:
        """Chat with fake model.

        Args:
            messages: Conversation messages
            tools: Optional tools
            stream: Whether to stream (not supported)
            **kwargs: Additional parameters

        Returns:
            ModelResponse

        Raises:
            ModelError: If model call fails
        """
        if stream:
            raise NotImplementedError("Streaming not supported for FakeModel")

        object.__setattr__(self, "call_count", self.call_count + 1)

        # Get last user message
        last_message = None
        for msg in reversed(messages):
            if msg.role.value == "user":
                last_message = msg
                break

        # Use response queue if available (for sequential calls)
        if self.response_queue:
            response_data = self.response_queue.popleft()
            if callable(response_data):
                result = response_data(messages, tools)
            else:
                result = response_data

            if isinstance(result, dict):
                tool_calls = None
                if "tool_calls" in result:
                    tool_calls = [
                        ToolCall(
                            id=tc.get("id", f"call_{i}"),
                            name=tc.get("name", ""),
                            arguments=tc.get("arguments", {}),
                        )
                        for i, tc in enumerate(result.get("tool_calls", []))
                    ]
                return ModelResponse(
                    content=result.get("content", ""),
                    tool_calls=tool_calls,
                    usage=Usage(prompt_tokens=10, completion_tokens=20, total_tokens=30),
                )
            elif isinstance(result, str):
                return ModelResponse(
                    content=result,
                    usage=Usage(prompt_tokens=10, completion_tokens=20, total_tokens=30),
                )

        # Use response function if provided
        if self.response_fn:
            try:
                result = self.response_fn(messages, tools)
                if isinstance(result, dict):
                    return ModelResponse(
                        content=result.get("content", ""),
                        tool_calls=result.get("tool_calls"),
                        usage=result.get(
                            "usage", Usage(prompt_tokens=10, completion_tokens=20, total_tokens=30)
                        ),
                    )
                elif isinstance(result, str):
                    return ModelResponse(
                        content=result,
                        usage=Usage(prompt_tokens=10, completion_tokens=20, total_tokens=30),
                    )
            except Exception as e:
                raise ModelError(f"Response function failed: {e}") from e

        # Use responses dict
        if last_message and self.responses:
            content = last_message.content.lower()
            for key, response in self.responses.items():
                if key.lower() in content:
                    # Check if response includes tool calls
                    if isinstance(response, dict):
                        tool_calls = None
                        if "tool_calls" in response:
                            tool_calls = [
                                ToolCall(
                                    id=tc.get("id", f"call_{i}"),
                                    name=tc.get("name", ""),
                                    arguments=tc.get("arguments", {}),
                                )
                                for i, tc in enumerate(response.get("tool_calls", []))
                            ]
                        return ModelResponse(
                            content=response.get("content", ""),
                            tool_calls=tool_calls,
                            usage=Usage(prompt_tokens=10, completion_tokens=20, total_tokens=30),
                        )
                    return ModelResponse(
                        content=response,
                        usage=Usage(prompt_tokens=10, completion_tokens=20, total_tokens=30),
                    )

        # Default response
        default = "I understand. How can I help you?"
        if tools and last_message:
            # If tools available and user asks something, suggest using a tool
            tool_names = [t.name for t in tools]
            default = f"I can help with that. Available tools: {', '.join(tool_names)}."

        return ModelResponse(
            content=default,
            usage=Usage(prompt_tokens=10, completion_tokens=20, total_tokens=30),
        )
