"""Base interface for trace exporters."""

from abc import ABC, abstractmethod

from routekitai.observability.trace import Trace


class TraceExporter(ABC):
    """Abstract base class for trace exporters."""

    @abstractmethod
    async def export(self, trace: Trace) -> None:
        """Export a trace.

        Args:
            trace: Trace to export
        """
        raise NotImplementedError

    @abstractmethod
    async def load(self, trace_id: str) -> Trace | None:
        """Load a trace by ID.

        Args:
            trace_id: Trace ID to load

        Returns:
            Trace if found, None otherwise
        """
        raise NotImplementedError
