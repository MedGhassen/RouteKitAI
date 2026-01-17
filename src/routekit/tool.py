"""Tool primitive for RouteKit."""

from typing import Any, Awaitable, Callable

from pydantic import BaseModel, Field


class Tool(BaseModel):
    """Represents a callable tool/function."""

    name: str = Field(..., description="Tool name")
    description: str = Field(..., description="Tool description")
    parameters: dict[str, Any] = Field(..., description="JSON Schema for tool parameters")
    func: Callable[..., Any] | Callable[..., Awaitable[Any]] | None = Field(
        default=None, description="Tool implementation function"
    )

    async def call(self, **kwargs: Any) -> Any:
        """Execute the tool with given parameters.

        Args:
            **kwargs: Tool parameters

        Returns:
            Tool execution result
        """
        if self.func is None:
            raise ValueError(f"Tool {self.name} has no implementation")
        result = self.func(**kwargs)
        if hasattr(result, "__await__"):
            return await result
        return result
