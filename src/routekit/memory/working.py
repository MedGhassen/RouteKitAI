"""Working memory for current run."""

from typing import Any

from pydantic import BaseModel

from routekit.core.memory import Memory


class WorkingMemory(Memory):
    """In-memory dict for current run.

    Ephemeral memory that exists only for the duration of a single agent run.
    """

    def __init__(self) -> None:
        """Initialize working memory."""
        self._store: dict[str, Any] = {}
        self._events: list[dict[str, Any]] = []

    async def get(self, key: str) -> Any:
        """Get value by key.

        Args:
            key: Key to retrieve

        Returns:
            Stored value or None if not found
        """
        return self._store.get(key)

    async def set(self, key: str, value: Any) -> None:
        """Set value by key.

        Args:
            key: Key to set
            value: Value to store
        """
        self._store[key] = value

    async def append(self, event: dict[str, Any]) -> None:
        """Append an event to memory.

        Args:
            event: Event dictionary to append
        """
        self._events.append(event)

    def clear(self) -> None:
        """Clear all memory (useful for testing)."""
        self._store.clear()
        self._events.clear()

    def get_all(self) -> dict[str, Any]:
        """Get all stored key-value pairs.

        Returns:
            Dictionary of all stored values
        """
        return self._store.copy()

    def get_events(self) -> list[dict[str, Any]]:
        """Get all events.

        Returns:
            List of all events
        """
        return self._events.copy()
