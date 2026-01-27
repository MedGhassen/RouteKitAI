"""Memory interface for routkitai agents."""

from abc import ABC, abstractmethod
from typing import Any


class Memory(ABC):
    """Base interface for agent memory systems."""

    @abstractmethod
    async def get(self, key: str) -> Any:
        """Get value by key.

        Args:
            key: Key to retrieve

        Returns:
            Stored value or None if not found
        """
        raise NotImplementedError("Subclasses must implement get")

    @abstractmethod
    async def set(self, key: str, value: Any) -> None:
        """Set value by key.

        Args:
            key: Key to set
            value: Value to store
        """
        raise NotImplementedError("Subclasses must implement set")

    @abstractmethod
    async def append(self, event: dict[str, Any]) -> None:
        """Append an event to memory.

        Args:
            event: Event dictionary to append
        """
        raise NotImplementedError("Subclasses must implement append")

    async def search(self, query: str, k: int = 5) -> list[dict[str, Any]]:
        """Search memory (optional for retrieval memory).

        Args:
            query: Search query
            k: Number of results to return

        Returns:
            List of matching results

        Raises:
            NotImplementedError: If search is not supported
        """
        raise NotImplementedError("Search not supported by this memory type")
