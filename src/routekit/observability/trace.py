"""Trace collection and management."""

import time
from typing import Any

from pydantic import BaseModel, Field


class TraceEvent(BaseModel):
    """Immutable event in a trace."""

    type: str = Field(..., description="Event type")
    timestamp: float = Field(..., description="Event timestamp")
    data: dict[str, Any] = Field(..., description="Event data")


class Trace(BaseModel):
    """Immutable trace of agent execution.

    A trace is an append-only event log that records all execution events.
    """

    trace_id: str = Field(..., description="Trace ID")
    events: list[TraceEvent] = Field(default_factory=list, description="Trace events")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Trace metadata")

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
