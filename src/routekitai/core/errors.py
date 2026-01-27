"""Well-typed exceptions for RouteKit."""

from typing import Any


class RouteKitError(Exception):
    """Base exception for all RouteKit errors."""

    def __init__(self, message: str, context: dict[str, Any] | None = None) -> None:
        """Initialize error with message and optional context.

        Args:
            message: Error message
            context: Optional context dictionary (trace_id, agent_name, step_id, etc.)
        """
        super().__init__(message)
        self.message = message
        self.context = context or {}

    def __str__(self) -> str:
        """Return error message with context if available."""
        if self.context:
            context_str = ", ".join(f"{k}={v}" for k, v in self.context.items())
            return f"{self.message} (context: {context_str})"
        return self.message


class ModelError(RouteKitError):
    """Error raised when model operations fail."""

    pass


class ToolError(RouteKitError):
    """Error raised when tool execution fails."""

    pass


class PolicyError(RouteKitError):
    """Error raised when agent policy fails."""

    pass


class RuntimeError(RouteKitError):
    """Error raised when runtime operations fail."""

    pass
