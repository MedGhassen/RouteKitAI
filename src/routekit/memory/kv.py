"""Key-value memory for agents."""

from typing import Any

from pydantic import BaseModel, Field


class KVMemory(BaseModel):
    """Key-value memory store for agent state.

    TODO: Implement persistent key-value storage for agent memory.
    """

    store: dict[str, Any] = Field(default_factory=dict, description="In-memory key-value store")

    async def get(self, key: str) -> Any:
        """Get value by key.

        Args:
            key: Key to retrieve

        Returns:
            Stored value

        Raises:
            NotImplementedError: Not yet implemented
        """
        raise NotImplementedError("KV memory not yet implemented")

    async def set(self, key: str, value: Any) -> None:
        """Set value by key.

        Args:
            key: Key to set
            value: Value to store

        Raises:
            NotImplementedError: Not yet implemented
        """
        raise NotImplementedError("KV memory not yet implemented")
