"""Model primitive for RouteKit."""

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from typing import Any

from pydantic import BaseModel, Field

from routekit.core.message import Message
from routekit.core.tool import Tool


class Usage(BaseModel):
    """Token usage and cost information."""

    prompt_tokens: int = Field(default=0, description="Number of prompt tokens")
    completion_tokens: int = Field(default=0, description="Number of completion tokens")
    total_tokens: int = Field(default=0, description="Total number of tokens")
    cost: float | None = Field(default=None, description="Estimated cost in USD")


class ToolCall(BaseModel):
    """Represents a tool call from the model."""

    id: str = Field(..., description="Tool call ID")
    name: str = Field(..., description="Tool name")
    arguments: dict[str, Any] = Field(..., description="Tool arguments as dictionary")


class ModelResponse(BaseModel):
    """Standard response from a model."""

    content: str = Field(..., description="Response content")
    tool_calls: list[ToolCall] | None = Field(
        default=None, description="Tool calls requested by the model"
    )
    usage: Usage | None = Field(default=None, description="Token usage information")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Additional metadata")


class StreamEvent(BaseModel):
    """Event emitted during streaming."""

    type: str = Field(..., description="Event type")
    content: str | None = Field(default=None, description="Content chunk")
    tool_calls: list[ToolCall] | None = Field(default=None, description="Tool calls")
    usage: Usage | None = Field(default=None, description="Usage information")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Additional metadata")


class Model(ABC):
    """Abstract base class for provider-agnostic model interface."""

    @property
    def name(self) -> str:
        """Return the model name.

        Returns:
            Model name, defaults to class name if not set
        """
        # Check for _name attribute first (set by subclasses like FakeModel)
        if hasattr(self, "_name"):
            name_attr = self._name
            if isinstance(name_attr, str):
                return name_attr
        # Fallback to class name
        return str(self.__class__.__name__)

    @abstractmethod
    async def chat(
        self,
        messages: list[Message],
        tools: list[Tool] | None = None,
        stream: bool = False,
        **kwargs: Any,
    ) -> ModelResponse | AsyncIterator[StreamEvent]:
        """Chat with the model.

        Args:
            messages: List of messages in the conversation
            tools: Optional list of tools available to the model
            stream: Whether to stream the response
            **kwargs: Additional model-specific parameters

        Returns:
            ModelResponse if stream=False, AsyncIterator[StreamEvent] if stream=True

        Raises:
            ModelError: If the model operation fails
        """
        raise NotImplementedError("Subclasses must implement chat")
