"""Trace collection and management."""

import asyncio
import time
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from routekit.observability.streaming import TraceEventBroadcaster


class TraceEvent(BaseModel):
    """Immutable event in a trace."""

    type: str = Field(..., description="Event type")
    timestamp: float = Field(..., description="Event timestamp")
    data: dict[str, Any] = Field(..., description="Event data")


TraceEventCallback = Callable[[TraceEvent], Awaitable[None] | None]


class Trace(BaseModel):
    """Immutable trace of agent execution.

    A trace is an append-only event log that records all execution events.
    """

    trace_id: str = Field(..., description="Trace ID")
    events: list[TraceEvent] = Field(default_factory=list, description="Trace events")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Trace metadata")

    def __init__(self, **data: Any) -> None:
        """Initialize trace with callbacks."""
        super().__init__(**data)
        self._event_callbacks: list[TraceEventCallback] = []

    def add_event_callback(self, callback: TraceEventCallback) -> None:
        """Add a callback to be notified of new events.

        Args:
            callback: Callback function that receives TraceEvent
        """
        self._event_callbacks.append(callback)

    def remove_event_callback(self, callback: TraceEventCallback) -> None:
        """Remove an event callback.

        Args:
            callback: Callback function to remove
        """
        if callback in self._event_callbacks:
            self._event_callbacks.remove(callback)

    def add_event(self, event_type: str, data: dict[str, Any] | None = None) -> None:
        """Add an event to the trace.

        Args:
            event_type: Type of event (run_started, model_called, tool_called, etc.)
            data: Event data
        """
        event = TraceEvent(
            type=event_type,
            timestamp=time.time(),
            data=data or {},
        )
        self.events.append(event)

        # Notify callbacks
        for callback in self._event_callbacks:
            try:
                result = callback(event)
                # If callback is async, schedule it
                if asyncio.iscoroutine(result):
                    # Create task if we're in an event loop, otherwise this will be handled by caller
                    try:
                        loop = asyncio.get_event_loop()
                        if loop.is_running():
                            asyncio.create_task(result)
                    except RuntimeError:
                        # No event loop, skip async callback
                        pass
            except Exception:
                # Don't let callback errors break trace collection
                pass

        # Broadcast to streaming subscribers (lazy import to avoid circular dependency)
        try:
            from routekit.observability.streaming import get_broadcaster

            broadcaster = get_broadcaster()
            # Schedule broadcast in event loop if available
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    asyncio.create_task(broadcaster.broadcast(event))
            except RuntimeError:
                # No event loop, skip broadcasting
                pass
        except Exception:
            # Don't let broadcasting errors break trace collection
            pass

    def get_events_by_type(self, event_type: str) -> list[TraceEvent]:
        """Get all events of a specific type.

        Args:
            event_type: Event type to filter by

        Returns:
            List of matching events
        """
        return [event for event in self.events if event.type == event_type]


class TraceCollector(BaseModel):
    """Collects and manages traces."""

    traces: dict[str, Trace] = Field(default_factory=dict, description="Collected traces")

    def start_trace(self, trace_id: str, metadata: dict[str, Any] | None = None) -> Trace:
        """Start a new trace.

        Args:
            trace_id: Unique trace ID
            metadata: Optional trace metadata

        Returns:
            New trace instance
        """
        trace = Trace(trace_id=trace_id, metadata=metadata or {})
        trace.add_event("run_started", {"trace_id": trace_id, "metadata": metadata or {}})
        self.traces[trace_id] = trace
        return trace

    def get_trace(self, trace_id: str) -> Trace | None:
        """Get trace by ID.

        Args:
            trace_id: Trace ID

        Returns:
            Trace if found, None otherwise
        """
        return self.traces.get(trace_id)
