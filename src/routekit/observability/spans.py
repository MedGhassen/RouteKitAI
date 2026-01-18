"""Span management for distributed tracing."""

import contextlib
import time
from collections.abc import AsyncGenerator, Generator
from typing import Any

from pydantic import BaseModel, Field


class SpanContext(BaseModel):
    """Context for span propagation."""

    trace_id: str = Field(..., description="Trace ID")
    span_id: str = Field(..., description="Span ID")
    parent_span_id: str | None = Field(default=None, description="Parent span ID")


class Span(BaseModel):
    """Execution span for tracing."""

    span_id: str = Field(..., description="Span ID")
    name: str = Field(..., description="Span name")
    start_time: float = Field(..., description="Start timestamp")
    end_time: float | None = Field(default=None, description="End timestamp")
    attributes: dict[str, Any] = Field(default_factory=dict, description="Span attributes")
    events: list[dict[str, Any]] = Field(default_factory=list, description="Span events")

    def add_event(self, name: str, attributes: dict[str, Any] | None = None) -> None:
        """Add event to span.

        Args:
            name: Event name
            attributes: Optional event attributes
        """
        self.events.append(
            {
                "name": name,
                "timestamp": time.time(),
                "attributes": attributes or {},
            }
        )

    @property
    def duration(self) -> float | None:
        """Get span duration in seconds.

        Returns:
            Duration if span is ended, None otherwise
        """
        if self.end_time is None:
            return None
        return self.end_time - self.start_time


@contextlib.contextmanager
def span(name: str, attributes: dict[str, Any] | None = None) -> Generator[Span, None, None]:
    """Context manager for creating a span.

    Args:
        name: Span name
        attributes: Optional span attributes

    Yields:
        Span instance

    Example:
        >>> with span("operation") as s:
        ...     # do work
        ...     s.add_event("milestone")
    """
    s = Span(
        span_id=f"span_{int(time.time() * 1000000)}",
        name=name,
        start_time=time.time(),
        attributes=attributes or {},
    )
    try:
        yield s
    finally:
        s.end_time = time.time()


@contextlib.asynccontextmanager
async def async_span(
    name: str, attributes: dict[str, Any] | None = None
) -> AsyncGenerator[Span, None]:
    """Async context manager for creating a span.

    Args:
        name: Span name
        attributes: Optional span attributes

    Yields:
        Span instance

    Example:
        >>> async with async_span("async_operation") as s:
        ...     # do async work
        ...     s.add_event("milestone")
    """
    s = Span(
        span_id=f"span_{int(time.time() * 1000000)}",
        name=name,
        start_time=time.time(),
        attributes=attributes or {},
    )
    try:
        yield s
    finally:
        s.end_time = time.time()
