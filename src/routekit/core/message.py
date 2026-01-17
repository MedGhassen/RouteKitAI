"""Message primitive for RouteKit."""

import json
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class MessageRole(str, Enum):
    """Message role types."""

    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


class Message(BaseModel):
    """Canonical message schema for RouteKit."""

    role: MessageRole = Field(..., description="Message role")
    content: str = Field(..., description="Message content")
    tool_calls: list[dict[str, Any]] | None = Field(
        default=None, description="Tool calls made by the assistant"
    )
    tool_result: dict[str, Any] | None = Field(
        default=None, description="Result from a tool call (for tool role messages)"
    )
    metadata: dict[str, Any] = Field(default_factory=dict, description="Additional metadata")

    @classmethod
    def system(cls, content: str, **metadata: Any) -> "Message":
        """Create a system message.

        Args:
            content: Message content
            **metadata: Additional metadata

        Returns:
            System message
        """
        return cls(role=MessageRole.SYSTEM, content=content, metadata=metadata)

    @classmethod
    def user(cls, content: str, **metadata: Any) -> "Message":
        """Create a user message.

        Args:
            content: Message content
            **metadata: Additional metadata

        Returns:
            User message
        """
        return cls(role=MessageRole.USER, content=content, metadata=metadata)

    @classmethod
    def assistant(
        cls,
        content: str,
        tool_calls: list[dict[str, Any]] | None = None,
        **metadata: Any,
    ) -> "Message":
        """Create an assistant message.

        Args:
            content: Message content
            tool_calls: Optional tool calls
            **metadata: Additional metadata

        Returns:
            Assistant message
        """
        return cls(role=MessageRole.ASSISTANT, content=content, tool_calls=tool_calls, metadata=metadata)

    @classmethod
    def tool(cls, content: str, tool_result: dict[str, Any], **metadata: Any) -> "Message":
        """Create a tool message.

        Args:
            content: Message content
            tool_result: Tool execution result
            **metadata: Additional metadata

        Returns:
            Tool message
        """
        return cls(role=MessageRole.TOOL, content=content, tool_result=tool_result, metadata=metadata)

    def to_dict(self) -> dict[str, Any]:
        """Serialize message to dictionary.

        Returns:
            Dictionary representation
        """
        return self.model_dump()

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Message":
        """Deserialize message from dictionary.

        Args:
            data: Dictionary representation

        Returns:
            Message instance
        """
        return cls(**data)

    def to_json(self) -> str:
        """Serialize message to JSON string.

        Returns:
            JSON string representation
        """
        return self.model_dump_json()

    @classmethod
    def from_json(cls, json_str: str) -> "Message":
        """Deserialize message from JSON string.

        Args:
            json_str: JSON string representation

        Returns:
            Message instance
        """
        return cls.model_validate_json(json_str)
