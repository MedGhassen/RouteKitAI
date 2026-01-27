"""Policy system for RouteKit agent execution."""

from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel, Field

from routekitai.core.message import Message


class Action(BaseModel):
    """Base class for execution actions."""

    action_type: str = Field(..., description="Action type")


class ModelAction(Action):
    """Action to call the model."""

    action_type: str = Field(default="model", description="Action type")
    messages: list[Message] = Field(..., description="Messages to send to model")
    prompt: str | None = Field(default=None, description="Optional prompt string")


class ToolAction(Action):
    """Action to execute a tool."""

    action_type: str = Field(default="tool", description="Action type")
    tool_name: str = Field(..., description="Tool name to execute")
    tool_input: dict[str, Any] = Field(..., description="Tool input arguments")


class Parallel(Action):
    """Action to execute multiple tool actions in parallel."""

    action_type: str = Field(default="parallel", description="Action type")
    actions: list[Action] = Field(
        ..., description="Actions to execute in parallel (typically ToolActions)"
    )


class Final(Action):
    """Action to finalize execution with output."""

    action_type: str = Field(default="final", description="Action type")
    output: Message = Field(..., description="Final output message")


class Policy(ABC):
    """Policy interface for agent execution.

    A policy determines what actions to take based on the current state.
    """

    @abstractmethod
    async def plan(self, state: dict[str, Any]) -> list[Action]:
        """Plan next actions based on current state.

        Args:
            state: Current execution state containing:
                - agent: Agent instance
                - messages: List of conversation messages
                - tools: Available tools
                - memory: Memory instance (if available)
                - metadata: Additional state metadata

        Returns:
            List of actions to execute
        """
        raise NotImplementedError("Subclasses must implement plan")

    async def reflect(self, state: dict[str, Any], observation: dict[str, Any]) -> dict[str, Any]:
        """Reflect on observation and update state.

        Args:
            state: Current state
            observation: Observation from last action (result, error, etc.)

        Returns:
            Updated state
        """
        # Default implementation: just merge observation into state
        state = state.copy()
        state.setdefault("observations", []).append(observation)
        return state
