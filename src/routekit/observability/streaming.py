"""Streaming support for trace events."""

import asyncio
import json
from collections.abc import AsyncIterator
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from routekit.observability.trace import TraceEvent


class TraceEventBroadcaster:
    """Broadcasts trace events to multiple subscribers via WebSocket/SSE."""

    def __init__(self) -> None:
        """Initialize broadcaster."""
        self._subscribers: set[asyncio.Queue[Any]] = set()
        self._lock = asyncio.Lock()

    async def subscribe(self) -> asyncio.Queue[Any]:
        """Subscribe to trace events.

        Returns:
            Queue that will receive trace events
        """
        queue: asyncio.Queue[Any] = asyncio.Queue()
        async with self._lock:
            self._subscribers.add(queue)
        return queue

    async def unsubscribe(self, queue: asyncio.Queue[Any]) -> None:
        """Unsubscribe from trace events.

        Args:
            queue: Queue to remove from subscribers
        """
        async with self._lock:
            self._subscribers.discard(queue)

    async def broadcast(self, event: Any) -> None:
        """Broadcast an event to all subscribers.

        Args:
            event: Trace event to broadcast
        """
        async with self._lock:
            # Create a copy of subscribers to avoid modification during iteration
            subscribers = list(self._subscribers)

        # Send to all subscribers, removing dead ones
        dead_subscribers = []
        for queue in subscribers:
            try:
                queue.put_nowait(event)
            except Exception:
                dead_subscribers.append(queue)

        # Clean up dead subscribers
        if dead_subscribers:
            async with self._lock:
                for queue in dead_subscribers:
                    self._subscribers.discard(queue)

    async def stream_events(
        self, queue: asyncio.Queue[Any], trace_id: str | None = None
    ) -> AsyncIterator[str]:
        """Stream events as SSE format.

        Args:
            queue: Queue to read events from
            trace_id: Optional trace ID to filter events

        Yields:
            SSE-formatted strings
        """
        try:
            while True:
                try:
                    # Wait for event with timeout to allow periodic checks
                    event = await asyncio.wait_for(queue.get(), timeout=1.0)
                    queue.task_done()

                    # Filter by trace_id if provided
                    if (
                        trace_id
                        and hasattr(event, "data")
                        and event.data.get("trace_id") != trace_id
                    ):
                        continue

                    # Format as SSE
                    event_data = {
                        "type": event.type,
                        "timestamp": event.timestamp,
                        "data": event.data,
                    }
                    yield f"data: {json.dumps(event_data)}\n\n"
                except asyncio.TimeoutError:
                    # Send keepalive
                    yield ": keepalive\n\n"
                except asyncio.CancelledError:
                    break
        finally:
            await self.unsubscribe(queue)


# Global broadcaster instance
_broadcaster: TraceEventBroadcaster | None = None


def get_broadcaster() -> TraceEventBroadcaster:
    """Get the global trace event broadcaster.

    Returns:
        TraceEventBroadcaster instance
    """
    global _broadcaster
    if _broadcaster is None:
        _broadcaster = TraceEventBroadcaster()
    return _broadcaster
