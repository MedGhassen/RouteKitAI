"""RouteKitAI: An agent development + orchestration framework."""

__version__ = "0.1.0"

# Import hooks first to ensure ToolFilter is defined before Agent
from routekitai.core import (
    Agent,
    Message,
    MessageRole,
    Model,
    ModelError,
    ModelResponse,
    PolicyError,
    RouteKitError,
    RunResult,
    Runtime,
    StreamEvent,
    Tool,
    ToolCall,
    ToolError,
    Usage,
)
from routekitai.core import (
    RuntimeError as RouteKitRuntimeError,
)
from routekitai.core.hooks import ToolFilter
from routekitai.core.policies import SupervisorPolicy

# Rebuild models to resolve forward references
# Runtime needs Agent, Agent needs ToolFilter, SupervisorPolicy needs Agent
Agent.model_rebuild()
Runtime.model_rebuild()
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
