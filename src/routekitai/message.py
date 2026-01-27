"""Message primitive for RouteKit."""

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class MessageRole(str, Enum):
    """Message role types."""

    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"
    TOOL = "tool"


class Message(BaseModel):
    """Represents a message in a conversation."""

    role: MessageRole = Field(..., description="Message role")
    content: str = Field(..., description="Message content")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Additional metadata")
    tool_calls: list[dict[str, Any]] | None = Field(
        default=None, description="Tool calls associated with this message"
    )
    tool_call_id: str | None = Field(
        default=None, description="ID of the tool call this message responds to"
    )
