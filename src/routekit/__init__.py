"""RouteKit: An agent development + orchestration framework."""

__version__ = "0.1.0"

# Import hooks first to ensure ToolFilter is defined before Agent
from routekit.core.hooks import ToolFilter

from routekit.core import (
    Agent,
    Message,
    MessageRole,
    Model,
    ModelResponse,
    RouteKitError,
    ModelError,
    ToolError,
    PolicyError,
    RuntimeError as RouteKitRuntimeError,
    RunResult,
    Runtime,
    StreamEvent,
    Tool,
    ToolCall,
    Usage,
)

# Rebuild models to resolve forward references
# Runtime needs Agent, Agent needs ToolFilter, SupervisorPolicy needs Agent
Agent.model_rebuild()
Runtime.model_rebuild()
from routekit.core.policies import SupervisorPolicy

SupervisorPolicy.model_rebuild()

__all__ = [
    "Agent",
    "Message",
    "MessageRole",
    "Model",
    "ModelResponse",
    "RouteKitError",
    "ModelError",
    "ToolError",
    "PolicyError",
    "RouteKitRuntimeError",
    "RunResult",
    "Runtime",
    "StreamEvent",
    "Tool",
    "ToolCall",
    "ToolFilter",
    "Usage",
]
