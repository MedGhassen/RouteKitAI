"""Model primitive for RouteKit."""

from typing import Any, AsyncIterator, Iterator

from pydantic import BaseModel, Field


class Model(BaseModel):
    """Represents an LLM model interface."""

    name: str = Field(..., description="Model identifier")
    provider: str = Field(..., description="Model provider")
    config: dict[str, Any] = Field(default_factory=dict, description="Model configuration")

    async def generate(
        self,
        messages: list["Message"],
        **kwargs: Any,
    ) -> AsyncIterator["Message"]:
        """Generate a response stream from messages.

        Args:
            messages: List of input messages
            **kwargs: Additional generation parameters

        Yields:
            Message chunks from the model
        """
        raise NotImplementedError("Subclasses must implement generate")

    def generate_sync(
        self,
        messages: list["Message"],
        **kwargs: Any,
    ) -> Iterator["Message"]:
        """Synchronous wrapper for generate.

        Args:
            messages: List of input messages
            **kwargs: Additional generation parameters

        Yields:
            Message chunks from the model
        """
        raise NotImplementedError("Subclasses must implement generate_sync")
